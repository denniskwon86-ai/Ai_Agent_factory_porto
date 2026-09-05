"""★★★ [MVP-P0 ①-B] 온톨로지 런타임의 **제품 Resolver 둘.**

## 왜 이 파일이 생겼나 (2026-08-20 Supervisor 지적)

정식 온톨로지 런타임을 이식했는데 제품 전역 인스턴스는
`object_scope_resolver=None` · `approval_resolver=None` 이었다. 그 상태에서 라우터를
붙이면 관계 제안·영향 질의가 503 이고, 화면은 **고정 `ontology_path` 를 보여 주면서**
「정식 온톨로지가 돈다」는 오해만 만든다.

⚠️ 이식과 함께 들어온 시험 23건은 **가짜 Resolver 를 주입한 시험용 앱**을 본다 —
  「올바른 Resolver 가 주어지면 동작한다」는 증명했지만 「제품에 올라간 것이 회사·조직·
  승인 원장과 연결됐다」는 증명하지 않았다. 이 파일이 그 연결이다.

## 이 파일이 지키는 것 넷

★★★ ① **모르면 막는다(fail-closed).** 모르는 namespace·못 찾는 식별자·판독 실패는
  전부 `None` 이다. 런타임은 `None` 을 「이 문맥에서 볼 수 없다」로 읽고 경로를 통째로
  지운다 — 중간 노드를 몰래 건너뛰지 않는다.
  ⚠️ 「모르니까 통과」가 한 번이라도 열리면 그 경로가 곧 승인 없는 관계가 된다.

★★★ ② **상관 문자열은 승인이 아니다.** `ledger_correlation_id` 가 있다는 것과 누군가
  그 행위를 승인했다는 것은 다른 사실이다. 실제 원장 이벤트를 찾아 **목적·행위자·대상**을
  대조하고, **정정·취소된 승인은 제외**한다.

★★★ ③ **범위는 자원이 말한다.** 여기서 조직 트리를 다시 계산하지 않는다 — 각 저장소가
  이미 들고 있는 `tenant_id`·`entity_mode`·`scope_node_id` 를 그대로 옮긴다. 두 곳에서
  계산하면 언젠가 갈라지고, 갈린 쪽이 느슨한 쪽이 된다.

★★★ ④ **판독 실패와 없음을 구분한다.** 저장소가 흔들려 못 읽은 것을 「없다」로 접으면
  그 순간 관계가 조용히 사라진다. 둘 다 `None` 이지만 **사유를 세어 둔다** — 운영에서
  「왜 경로가 비었나」를 물을 수 있어야 한다.

LLM 0콜. 결정론적이다.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from core import app_policy
from core import ontology_resolve
from core.ontology_errors import OntologyResolverError

#: ⚠️ 모듈 수준에서 `ontology_runtime` 을 읽지 않는다 — 그쪽이 이쪽을 다시 읽어
#:   **순환 참조**가 된다(실측). 타입은 검사기에게만 보이면 충분하다.
if TYPE_CHECKING:                     # pragma: no cover
    from core.ontology_runtime import ObjectRef

#: ★★★ 원장이 증명해야 하는 **행위 목적**. 런타임이 이 이름으로 부른다.
#: ⚠️ 여기 없는 행위는 승인될 수 없다 — 목록을 늘리는 것은 사람의 결정이다.
ACTION_MODEL_INSTALL = "MODEL_INSTALL"
ACTION_RELATION_APPROVE = "RELATION_APPROVE"
ACTION_RELATION_RETIRE = "RELATION_RETIRE"
APPROVABLE_ACTIONS = (ACTION_MODEL_INSTALL, ACTION_RELATION_APPROVE,
                      ACTION_RELATION_RETIRE)

#: 행위 목적 → 원장에서 인정하는 **전용** 이벤트. ★ 목적마다 **하나**다.
#:
#: ⚠️⚠️ [2026-08-20 Supervisor 지적] 종전에는 범용 이벤트를 넓게 받아들였다
#:   (`DECISION_RECORDED` · `BLUEPRINT_APPROVED` · `PUBLICATION_WITHDRAWN` …).
#:   그러면 **같은 행위자의 아무 결정 하나**로 다른 관계 승인을 통과시킬 수 있고,
#:   「발간 철회」가 온톨로지 관계 폐지를 승인하는 도메인 착오까지 생긴다.
#: ★ 승인은 「누가」와 「무엇을」이 같이 있어야 승인이다.
_ACTION_EVENT: Dict[str, str] = {
    ACTION_MODEL_INSTALL: "ONTOLOGY_MODEL_APPROVED",
    ACTION_RELATION_APPROVE: "ONTOLOGY_RELATION_APPROVED",
    ACTION_RELATION_RETIRE: "ONTOLOGY_RELATION_RETIRED",
}

#: 행위 목적 → 원장 `subject_type` 이 무엇이어야 하는가.
#: ⚠️ 대상 종류가 다르면 승인이 아니다 — 관계 승인 이벤트로 계약을 설치할 수 없다.
_ACTION_SUBJECT: Dict[str, str] = {
    ACTION_MODEL_INSTALL: "ontology_model_contract",
    ACTION_RELATION_APPROVE: "ontology_relation",
    ACTION_RELATION_RETIRE: "ontology_relation",
}

#: 호출부가 넘기는 대상 종류 → 원장 `subject_type`.
_TARGET_SUBJECT: Dict[str, str] = {
    "model_contract": "ontology_model_contract",
    "relation": "ontology_relation",
}

#: ⚠️ 이 유형이 승인 이벤트를 **부모로 가리키면** 그 승인은 더 이상 유효하지 않다.
_INVALIDATING = frozenset({"CORRECTION", "ONTOLOGY_APPROVAL_REVOKED"})


class ResolverStats:
    """왜 막혔는지 **세어 둔다.** ⚠️ 로그만 남기면 아무도 세지 않는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: Dict[str, int] = {}

    def bump(self, reason: str) -> None:
        with self._lock:
            self.counts[reason] = self.counts.get(reason, 0) + 1

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self.counts)


stats = ResolverStats()


def _scope(tenant_id: str, entity_mode: str, scope_node_id: str,
           owner_dept_id: str = "", owner_user_id: str = "",
           status: str = "active") -> Optional[app_policy.ResourceScope]:
    """저장소가 들고 있는 값을 **그대로** 범위로 옮긴다.

    ⚠️ 범위 필드가 비어 있으면 `None` 이다 — D-014(「미지정은 전사 공용이 아니라
      비노출」)와 같은 규칙이다. 빈 범위를 «전부 허용» 으로 읽으면 그 순간 통제가 사라진다."""
    if not str(tenant_id or "").strip() or not str(scope_node_id or "").strip():
        stats.bump("unbound_scope")
        return None
    return app_policy.ResourceScope(
        tenant_id=str(tenant_id), entity_mode=str(entity_mode or "REAL"),
        scope_node_id=str(scope_node_id), owner_dept_id=str(owner_dept_id or ""),
        owner_user_id=str(owner_user_id or ""), status=str(status or "active"))


# ── namespace 별 해석 ────────────────────────────────────────────────────
def _resolve_ecm(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """조직 노드. 노드 자신이 자기 범위다.

    ⚠️⚠️ [2026-08-20 Supervisor 지적] `entity_mode` 를 `"REAL"` 로 **고정하면 안 된다.**
      노드가 속한 Enterprise Entity 는 `VIRTUAL`(시나리오·복제) 일 수 있고, 가상 조직
      노드를 실제로 판정하면 **시나리오 관계와 실제 관계가 섞인다.**
    ★ 그래서 Entity 를 읽어 실제 `entity_mode` 를 쓴다. 못 읽으면 **막는다** —
      모르는 문맥을 REAL 로 떨어뜨리는 것이 바로 그 사고다."""
    from core.enterprise_context.repository import ecm_repository

    try:
        node = ecm_repository.get_node(ref.object_id)
    except Exception as exc:
        #: ⚠️ [P0-3] 저장소 장애를 «없음» 으로 접지 않는다.
        stats.bump("ecm_unreadable")
        raise OntologyResolverError("ECM 조직 노드를 "
                                    "읽지 못했습니다.") from exc
    if not node:
        #: ★ 없는 것은 **없는 것**이다. 무엇을 할지는 **런타임이 문맥으로 정한다** —
        #:   임의 조회면 빈 결과, 승인된 관계의 끝점이면 무결성 장애(503).
        #: ⚠️ 여기서 존재 여부를 메시지로 누설하지 않는다.
        stats.bump("ecm_not_found")
        return ontology_resolve.not_found("조직 노드가 없습니다.")
    try:
        entity = ecm_repository.get_entity(getattr(node, "entity_id", "") or "")
    except Exception as exc:
        stats.bump("ecm_unreadable")
        raise OntologyResolverError("ECM 법인을 "
                                    "읽지 못했습니다.") from exc
    if not entity:
        #: ⚠️ 노드는 있는데 법인이 없다 = **자료 불일치**다. 통과시키면 실행 모드를
        #:   모르는 채로 관계가 선다.
        stats.bump("ecm_entity_not_found")
        raise OntologyResolverError(
            "조직 노드의 법인을 찾지 "
            "못했습니다 — 실행 문맥을 "
            "정할 수 없습니다.")
    mode = str(getattr(entity, "entity_mode", "") or "").strip()
    if not mode:
        #: ⚠️⚠️ [2026-08-20 Supervisor 지적] `None` 은 「안 보인다」다. 실행 모드가 비어
        #:   있는 것은 **자료 불일치**이지 「이 문맥에서 안 보인다」가 아니다.
        #:   `None` 으로 두면 화면이 「영향 경로 없음」을 그리고, 사람은 그것을 사실로
        #:   읽는다 — 실제로는 REAL/VIRTUAL 을 모르는 상태다.
        stats.bump("ecm_entity_mode_missing")
        raise OntologyResolverError(
            "조직의 실행 문맥(entity_mode)이 "
            "비어 있습니다 — 실적과 "
            "시나리오를 구분할 수 없습니다.")
    scope = _scope(getattr(node, "tenant_id", ""), mode, getattr(node, "node_id", ""),
                   owner_dept_id=getattr(node, "dept_id", ""),
                   status="active" if getattr(node, "status", "") == "ACTIVE" else "retired")
    try:
        from core import ontology_object_display
        descriptor = ontology_object_display.describe_ecm_object(
            object_id=str(getattr(node, "node_id", "") or ""),
            node_name=str(getattr(node, "name_ko", "") or ""),
            entity_id=str(getattr(entity, "entity_id", "") or ""),
            entity_name=str(getattr(entity, "name_ko", "") or ""),
            entity_mode=mode,
        )
    except Exception as exc:
        stats.bump("ecm_display_unavailable")
        return ontology_resolve.unavailable(
            f"조직 객체의 사람용 표시 설명을 만들지 못했습니다: {exc}")
    #: ★ 조직 노드는 인증판에서 오는 것이 아니므로 `snapshot_id` 가 없다.
    #: ⚠️ 그래서 봉인된 판을 요구하는 문맥에서는 **쓸 수 없다** — 런타임이 막는다.
    return ontology_resolve.found(
        scope, data_kind=mode,
        display_name=descriptor.display_name,
        display_fingerprint=descriptor.display_fingerprint)


def _resolve_dataset(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """인증판 범위 색인에 결속된 dataset·mdm·external 객체의 범위.

    ★★★ [2026-08-20 §7 4단계] **범위 색인을 통해 해석한다.**

    ## 무엇이 어긋나 있었나

    계약의 `dataset` 객체 id 는 **업무 레코드 ID**(`SHP-000001`·`STK-…`)이지 인증판
    ID(`ds_…`)가 아니다. 종전 구현은 그 값을 그대로 `get_snapshot()` 에 넣었으므로
    **영영 찾지 못했고**, 결과가 `None` 이라 「범위 밖」과 구분되지 않았다.

    ⚠️ `INV-01` 은 자기 열 이름이 하필 `snapshot_id` 라서 특히 헷갈린다.

    ## 이 함수가 하는 일과 하지 않는 일

        한다      업무 ID → 그 시점의 인증판 → 그 판의 **범위·근거·성격** 을 번역
        안 한다   사용자·조직 **권한 판정**(PDP 의 일) · 「없음」을 어떻게 다룰지(문맥의 일)

    ⚠️⚠️ 권한을 여기서도 판정하면 규칙이 두 곳으로 갈라지고, 갈라진 규칙은 언젠가
      한쪽만 고쳐진다.

    ## 판은 `as_of` 로 고른다

    ★ 「그냥 최신」을 쓰지 않는다 — 과거 시점 질의에 **오늘의 답**을 주게 된다.
    ⚠️ 문맥에 `as_of` 가 없으면 「지금」이고, 그때도 규칙은 하나다."""
    from core.data_preparation import scope_index
    from core.data_preparation.store import data_preparation_store
    stats_namespace = str(ref.namespace or "dataset")

    try:
        #: ★★★ [2026-08-21 P0] **정체성 두 값을 함께 넘긴다.** 없으면 다른 회사의
        #:   `SHP-000001` 이 우리 것을 가리거나 동점을 만든다.
        if not ctx.tenant_id or not ctx.entity_mode:
            #: ⚠️ 문맥이 반쪽이면 «전부 뒤진다» 로 넓히지 않는다 — 그 순간 회사 경계가
            #:   사라진다. 모르면 **막는다.**
            stats.bump(f"{stats_namespace}_identity_missing")
            return ontology_resolve.unavailable(
                "조회 문맥에 tenant·entity_mode 가 없습니다 — 객체를 특정할 수 없습니다.")
        status, row, candidates = scope_index.lookup(
            data_preparation_store, ref.namespace, ref.object_type, ref.object_id,
            ctx.tenant_id, ctx.entity_mode,
            as_of=str(getattr(ctx, "as_of", "") or ""))
    except Exception as exc:
        #: ⚠️ [P0-3] 저장소 장애를 «없음» 으로 접지 않는다. 못 읽은 것과 없는 것은
        #:   다른 사실이고, 앞엣것은 **사람이 손을 써야** 한다.
        stats.bump(f"{stats_namespace}_index_unreadable")
        raise OntologyResolverError(
            f"범위 색인을 읽지 못했습니다({ref.key}): {exc}") from exc

    if status == scope_index.AMBIGUOUS:
        #: ⚠️⚠️ 같은 시각의 인증판이 둘이다. **아무거나 고르지 않는다** — 고르면 같은
        #:   질문의 답이 실행마다 달라지고 재실행 지문이 흔들린다.
        stats.bump(f"{stats_namespace}_ambiguous_version")
        return ontology_resolve.ambiguous(
            candidates, f"같은 시각의 인증판이 {len(candidates)}개입니다.")
    if status == scope_index.UNBOUND:
        #: ★ 객체는 아는데 **그 시점에는 아직 인증 전**이다.
        stats.bump(f"{stats_namespace}_unbound_at_as_of")
        return ontology_resolve.unbound(
            f"그 시점에는 아직 인증되지 않았습니다(as_of={ctx.as_of or '지금'}).")
    if status != scope_index.FOUND or row is None:
        try:
            needs_index = scope_index.has_unmaterialized_snapshot(
                data_preparation_store, ref.namespace, ref.object_type,
                ctx.tenant_id, ctx.entity_mode)
        except Exception as exc:
            stats.bump(f"{stats_namespace}_index_readiness_unreadable")
            raise OntologyResolverError(
                f"인증판 색인 준비 상태를 읽지 못했습니다({ref.key}): {exc}") from exc
        if needs_index:
            stats.bump(f"{stats_namespace}_needs_materialization")
            return ontology_resolve.unavailable(
                "인증된 원본은 있으나 객체 범위 색인이 아직 물질화되지 않았습니다 — "
                "색인 백필이 필요합니다.")
        stats.bump(f"{stats_namespace}_not_indexed")
        #: ⚠️ 존재를 누설하지 않는다 — 무엇을 할지는 **문맥**이 정한다(임의 조회면 빈
        #:   결과, 승인된 관계의 끝점이면 무결성 장애).
        return ontology_resolve.not_found("색인에 없는 업무 객체입니다.")

    #: ★★★ [2026-08-21 4.1b-0] **조직 노드를 부서 칸에 넣지 않는다.**
    #:
    #: ⚠️⚠️ 종전에는 `owner_dept_id=scope_node_id` 로 채웠다. PDP 는
    #:   `owner_dept_id in readable_dept_ids` 를 보는데 그 집합은 `org_directory` 의
    #:   **부서 ID** 로 만들어진다. 노드 ID 를 넣으면 시험에서만 통과하고(시험이 노드
    #:   ID 로 가짜 Scope 를 만드니까) **실제 제품 권한과 다른 세계**가 된다.
    #: ⚠️ 지금 시연 데이터에는 부서 칸이 없다 — 비워 둔다. 그러면 PDP 가
    #:   `RESOURCE_UNBOUND` 로 막는다(D-014: 미지정은 전사 공용이 아니라 **비노출**).
    #:   막히는 것이 맞다. 「누가 소유하는가」를 정하지 않았기 때문이다.
    #: ★★★ [G2 Ownership Binding] **색인 값을 그대로 믿지 않는다 — 요청 시 다시 해석한다.**
    #:
    #: ⚠️⚠️ 색인의 `owner_dept_id` 는 **물질화된 사본**이고 정본은
    #:   `dataset_ownership_bindings` 다. 승인 철회 · 결속 폐지 · 부서 폐지는 모두 색인이
    #:   만들어진 **뒤에** 일어난다. 물질화 시점의 판단을 영구히 믿으면 그것이 곧
    #:   「회수해도 계속 유효한 권한」이다 — SSE 티켓에서 이미 같은 실수를 고쳤다.
    #: ⚠️ 봉인된 결속 지문과 지금 해석이 **다르면 막는다**(503). 색인이 낡았다는 뜻이고,
    #:   그 상태에서 어느 쪽을 쓸지 임의로 고르면 같은 질문에 다른 답이 나온다.
    from core.data_preparation import ownership_binding as _ob
    owner_dept = ""
    try:
        #: ⚠️ 정본은 색인과 **같은 저장소**에 있다. 별도 연결을 열지 않고 그 트랜잭션을 쓴다 —
        #:   두 저장소로 나누면 「색인은 새 판, 소유는 옛 판」인 순간이 생긴다.
        with data_preparation_store.transaction() as _conn:
            _b = _ob.resolve(_conn, tenant_id=str(row.get("tenant_id", "")),
                             entity_mode=str(row.get("entity_mode", "")),
                             dataset_contract_key=str(row.get("dataset_contract_key", "")),
                             scope_node_id=str(row.get("scope_node_id", "")),
                             as_of=str(ctx.as_of or ""))
    except _ob.OwnershipIntegrityError as e:
        stats.bump("ownership_integrity")
        return ontology_resolve.unavailable(f"데이터셋 소유권 결속이 어긋났습니다: {e}")
    except _ob.OwnershipUnavailable as e:
        stats.bump("ownership_unavailable")
        return ontology_resolve.unavailable(f"데이터셋 소유권 정본을 읽지 못했습니다: {e}")
    #: ★★★ [재감사 보정] **봉인 대조를 네 상태로 가른다.**
    #:
    #: ⚠️⚠️ 첫 판은 `if sealed and sealed != now` 였다. 그래서 색인 생성 당시 결속이 없어
    #:   `sealed=""` 였는데 나중에 결속이 추가되면, **재물질화 없이 새 소유 부서가 즉시
    #:   권한이 됐다.** 봉인 계약이라면 「봉인 없음 + 현재 있음」은 통과가 아니라 점검이다 —
    #:   색인이 그 결속을 근거로 만들어진 적이 없기 때문이다.
    sealed = str(row.get("owner_binding_fingerprint", "") or "")
    if _b is None:
        if sealed:
            #: 봉인 있음 + 현재 없음 → 철회·폐지됐다. 비노출(정상).
            stats.bump("ownership_revoked")
        else:
            #: 봉인 없음 + 현재 없음 → 소유를 아직 정하지 않았다. 비노출(정상).
            stats.bump("ownership_unbound")
        owner_dept = ""
    elif not sealed:
        #: 봉인 없음 + 현재 있음 → **재물질화가 필요하다.** 색인은 이 결속을 모른다.
        stats.bump("ownership_needs_rematerialize")
        return ontology_resolve.unavailable(
            "이 색인은 소유권 결속이 없던 때에 만들어졌는데 지금은 결속이 있습니다 — "
            "재물질화가 필요합니다(색인이 모르는 승인을 권한으로 쓰지 않습니다).")
    elif sealed != _b["fingerprint"]:
        stats.bump("ownership_stale_index")
        return ontology_resolve.unavailable(
            "색인에 봉인된 소유권 결속과 지금 승인된 결속이 다릅니다 — 재물질화가 "
            "필요합니다(어느 쪽을 쓸지 임의로 고르지 않습니다).")
    else:
        #: 봉인 있음 + 현재 있음 + 지문 일치 → 유일하게 허용되는 상태.
        owner_dept = str(_b["owner_dept_id"])

    scope = _scope(str(row.get("tenant_id", "")), str(row.get("entity_mode", "")),
                   str(row.get("scope_node_id", "")),
                   owner_dept_id=owner_dept)
    if scope is None:
        #: ⚠️⚠️ 색인은 범위 없는 행을 애초에 받지 않는다. 그런데도 여기 왔다면 **자료가
        #:   어긋난 것**이지 「안 보이는 것」이 아니다.
        #: ★ 「일어날 리 없다」를 그냥 두면 일어났을 때 `found(None)` 로 터지고, 그
        #:   예외는 «해석 실패» 로 뭉뚱그려져 원인을 잃는다.
        stats.bump(f"{stats_namespace}_scope_missing")
        return ontology_resolve.unavailable(
            f"색인 줄에 범위가 없습니다({ref.key}) — 자료가 어긋났습니다.")
    try:
        from core import ontology_object_display
        descriptor = ontology_object_display.describe_dataset_object(
            namespace=ref.namespace,
            object_type=ref.object_type,
            object_id=ref.object_id,
            snapshot_id=str(row.get("snapshot_id", "")),
            dataset_contract_key=str(row.get("dataset_contract_key", "")),
            raw_path=str(row.get("snapshot_raw_path", "")),
            checksum=str(row.get("snapshot_checksum", "")),
        )
    except Exception as exc:
        stats.bump(f"{stats_namespace}_display_unavailable")
        return ontology_resolve.unavailable(
            f"봉인된 객체 표시 설명을 만들지 못했습니다({ref.key}): {exc}")
    stats.bump(f"{stats_namespace}_resolved")
    return ontology_resolve.found(
        scope, snapshot_id=str(row.get("snapshot_id", "")),
        row_evidence=str(row.get("row_evidence", "")),
        data_kind=str(row.get("data_kind", "")),
        display_name=descriptor.display_name,
        display_fingerprint=descriptor.display_fingerprint)


def _resolve_mdm(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """인증된 기준정보 중 열쇠·집합·표시 계약이 확정된 유형만 해석한다."""
    from core.data_preparation import scope_index
    supported = {target[1] for key in (set(scope_index.REFERENCE_OBJECTS)
                                      | set(scope_index.COMPOSITE_REFERENCE_OBJECTS)
                                      | set(scope_index.GROUPED_REFERENCE_OBJECTS))
                 for target in scope_index.object_specs(key) if target[0] == "mdm"}
    if ref.object_type not in supported:
        stats.bump("mdm_type_not_wired")
        return ontology_resolve.unavailable(
            f"이 기준정보 유형은 복합키 또는 사람용 표시 계약이 아직 없습니다({ref.object_type}).")
    return _resolve_dataset(ref, ctx)


def _resolve_external(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """승인된 외부 관측값을 인증판·조직 범위·공표 근거에 결속해 해석한다."""
    if ref.object_type != "external-observation":
        stats.bump("external_type_not_wired")
        return ontology_resolve.unavailable(
            f"이 대외정보 유형은 범위·표시 계약이 아직 없습니다({ref.object_type}).")
    return _resolve_dataset(ref, ctx)


def _resolve_g4(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """Approved immutable planning-driver release bound to scope and ledger."""
    if ref.object_type != "driver":
        stats.bump("g4_type_not_wired")
        return ontology_resolve.unavailable("이 경영 동인 유형은 승인 판본 계약이 없습니다.")
    try:
        from core import planning_driver_release as release
        row = release.effective_release(ref.object_id, as_of=str(ctx.as_of or ""))
    except Exception as exc:
        stats.bump("g4_release_unavailable")
        raise OntologyResolverError("승인된 경영 동인 판본을 읽지 못했습니다.") from exc
    if not row:
        stats.bump("g4_driver_unbound")
        return ontology_resolve.unbound("그 시점에 유효한 승인 동인 판본이 없습니다.")
    scope = _scope(row["tenant_id"], row["entity_mode"], row["scope_node_id"])
    if scope is None:
        return ontology_resolve.unavailable("승인 동인 판본의 조직 범위가 비어 있습니다.")
    try:
        from core import ontology_object_display
        descriptor = ontology_object_display.describe_driver_object(
            object_id=ref.object_id, name=row["name"], version=int(row["version"]),
            fingerprint=row["fingerprint"], category=row["category"], unit=row["unit"],
            external_code=row["external_code"], approved_at=row["approved_at"])
    except Exception as exc:
        stats.bump("g4_display_unavailable")
        return ontology_resolve.unavailable(f"경영 동인 표시 설명을 만들지 못했습니다: {exc}")
    stats.bump("g4_driver_resolved")
    return ontology_resolve.found(
        scope, row_evidence=f"approval={row['approval_event_id']};version={row['version']}",
        data_kind="APPROVED_DRIVER", display_name=descriptor.display_name,
        display_fingerprint=descriptor.display_fingerprint)


def current_g4_object_types() -> tuple[str, ...]:
    """Return current binding at type level; never expose driver count or IDs."""
    from core import planning_driver_release as release
    from core.planning_model import planning_store
    conn = planning_store._connect()
    try:
        codes = [str(row[0]) for row in conn.execute(
            "SELECT DISTINCT driver_code FROM driver_releases ORDER BY driver_code").fetchall()]
    except sqlite3.Error as exc:
        raise OntologyResolverError("경영 동인 판본 저장소를 읽지 못했습니다.") from exc
    finally:
        conn.close()
    for code in codes:
        try:
            if release.effective_release(code):
                return ("driver",)
        except Exception as exc:
            raise OntologyResolverError("경영 동인 승인 결속을 확인하지 못했습니다.") from exc
    return ()


def _instant(value: object) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OntologyResolverError(f"업무 객체 시각을 읽지 못했습니다: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decision_row(decision_id: str) -> Optional[dict]:
    """Read the authoritative case without creating or migrating its database."""
    from core.collaboration_store import collaboration_store

    path = Path(collaboration_store.db_path)
    if not path.is_file():
        raise OntologyResolverError("의사결정 정본 저장소가 준비되지 않았습니다.")
    try:
        conn = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT decision_id,tenant_id,scope_id,question,evidence_hash,"
                "package_version,status,outcome,created_by,created_at,updated_at "
                "FROM decision_cases WHERE decision_id=?", (decision_id,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise OntologyResolverError("의사결정 정본 저장소를 읽지 못했습니다.") from exc
    return dict(row) if row else None


def current_decision_object_types() -> tuple[str, ...]:
    """Return type-level current binding only; never expose case counts or IDs."""
    from core.collaboration_store import collaboration_store
    from core.enterprise_context.repository import ecm_repository

    path = Path(collaboration_store.db_path)
    if not path.is_file():
        raise OntologyResolverError("의사결정 정본 저장소가 준비되지 않았습니다.")
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT tenant_id,scope_id,question,evidence_hash,created_at,updated_at,status "
                "FROM decision_cases WHERE status<>'CANCELLED' ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise OntologyResolverError("의사결정 정본 저장소를 읽지 못했습니다.") from exc
    for raw in rows:
        row = dict(raw)
        tenant = str(row.get("tenant_id") or "").strip()
        scope_id = str(row.get("scope_id") or "").strip()
        if not all((tenant, scope_id, str(row.get("question") or "").strip(),
                    str(row.get("evidence_hash") or "").strip(),
                    str(row.get("created_at") or "").strip(),
                    str(row.get("updated_at") or "").strip())):
            continue
        try:
            node = ecm_repository.get_node(scope_id)
            entity = ecm_repository.get_entity(getattr(node, "entity_id", "") or "") \
                if node else None
        except Exception as exc:
            raise OntologyResolverError("의사결정의 조직 정본을 읽지 못했습니다.") from exc
        if (node and entity and str(getattr(node, "tenant_id", "") or "") == tenant
                and str(getattr(entity, "entity_mode", "") or "").strip()):
            return ("decision",)
    return ()


def current_scenario_object_types() -> tuple[str, ...]:
    """Return scenario type readiness without exposing release counts or IDs."""
    from core.decision_ledger import decision_ledger
    from core.planning_model import planning_store
    from core import planning_scenario_release

    conn = planning_store._connect()
    try:
        scenario_ids = [str(row[0]) for row in conn.execute(
            "SELECT DISTINCT scenario_id FROM scenario_releases").fetchall()]
    except sqlite3.Error as exc:
        raise OntologyResolverError("승인 시나리오 판본 저장소를 읽지 못했습니다.") from exc
    finally:
        conn.close()
    for scenario_id in scenario_ids:
        try:
            if planning_scenario_release.effective_release(
                    scenario_id, store=planning_store, ledger=decision_ledger):
                return ("scenario",)
        except Exception as exc:
            raise OntologyResolverError("시나리오 승인 판본을 검증하지 못했습니다.") from exc
    return ()


def _decision_scope(row: dict, ctx: ontology_resolve.ResolveContext):
    """Bind a decision's stored scope node to its canonical ECM execution mode."""
    from core.enterprise_context.repository import ecm_repository

    tenant_id = str(row.get("tenant_id") or "").strip()
    scope_node_id = str(row.get("scope_id") or "").strip()
    if not tenant_id or not scope_node_id:
        return None
    try:
        node = ecm_repository.get_node(scope_node_id)
        entity = ecm_repository.get_entity(getattr(node, "entity_id", "") or "") if node else None
    except Exception as exc:
        raise OntologyResolverError("의사결정의 조직 범위를 읽지 못했습니다.") from exc
    if not node or not entity:
        raise OntologyResolverError("의사결정이 가리키는 조직 정본이 없습니다.")
    node_tenant = str(getattr(node, "tenant_id", "") or "").strip()
    if node_tenant != tenant_id:
        raise OntologyResolverError("의사결정과 조직 정본의 tenant가 일치하지 않습니다.")
    mode = str(getattr(entity, "entity_mode", "") or "").strip()
    if not mode:
        raise OntologyResolverError("의사결정 조직의 실행 문맥이 비어 있습니다.")
    if ctx.tenant_id and ctx.tenant_id != tenant_id:
        return ontology_resolve.not_found("현재 tenant의 의사결정이 아닙니다.")
    if ctx.entity_mode and ctx.entity_mode != mode:
        return ontology_resolve.not_found("현재 실행 문맥의 의사결정이 아닙니다.")
    return _scope(
        tenant_id, mode, scope_node_id,
        owner_dept_id=str(getattr(node, "dept_id", "") or ""),
        owner_user_id=str(row.get("created_by") or ""),
        status="active")


def _resolve_decision(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """Resolve decision cases and immutable approved scenario releases."""
    if ref.object_type == "scenario":
        from core import planning_scenario_release
        from core.decision_ledger import decision_ledger
        from core.planning_model import planning_store

        try:
            row = planning_scenario_release.effective_release(
                ref.object_id, ctx.as_of, store=planning_store, ledger=decision_ledger)
        except Exception as exc:
            stats.bump("scenario_release_unreadable")
            raise OntologyResolverError("승인 시나리오 판본을 확인하지 못했습니다.") from exc
        if not row:
            stats.bump("scenario_not_approved")
            return ontology_resolve.unbound("기준 시각에 유효한 승인 시나리오 판본이 없습니다.")
        scenario_scope = _decision_scope({
            "tenant_id": row["tenant_id"], "scope_id": row["scope_node_id"],
            "created_by": row["approved_by"],
        }, ctx)
        if isinstance(scenario_scope, ontology_resolve.ObjectResolution):
            return scenario_scope
        if scenario_scope is None:
            return ontology_resolve.unbound("승인 시나리오의 조직 범위가 결속되지 않았습니다.")
        try:
            from core import ontology_object_display
            descriptor = ontology_object_display.describe_scenario_object(
                object_id=ref.object_id, name=row["name"], version=int(row["version"]),
                fingerprint=row["fingerprint"], baseline_kind=row["baseline_kind"],
                baseline_period=row["baseline_period"], approved_at=row["approved_at"])
        except Exception as exc:
            stats.bump("scenario_display_unavailable")
            return ontology_resolve.unavailable(
                f"승인 시나리오 표시 설명을 만들지 못했습니다: {exc}")
        stats.bump("scenario_resolved")
        return ontology_resolve.found(
            scenario_scope,
            row_evidence=(f"scenario_release:fingerprint={row['fingerprint']}:"
                          f"version={row['version']}:approval={row['approval_event_id']}"),
            data_kind=scenario_scope.entity_mode,
            display_name=descriptor.display_name,
            display_fingerprint=descriptor.display_fingerprint)

    if ref.object_type != "decision":
        stats.bump("decision_type_not_wired")
        raise OntologyResolverError(
            f"이 시나리오·의사결정 유형은 승인·유효시점 계약이 아직 없습니다({ref.key}).")
    row = _decision_row(ref.object_id)
    if not row:
        stats.bump("decision_not_found")
        return ontology_resolve.not_found("의사결정 안건이 없습니다.")
    if str(row.get("status") or "").upper() == "CANCELLED":
        stats.bump("decision_cancelled")
        return ontology_resolve.unbound("취소된 의사결정 안건입니다.")

    created = _instant(row.get("created_at"))
    updated = _instant(row.get("updated_at"))
    if created is None or updated is None:
        stats.bump("decision_time_unreadable")
        raise OntologyResolverError("의사결정 안건의 생성·갱신 시각이 비어 있습니다.")
    cutoff = _instant(ctx.as_of) if str(ctx.as_of or "").strip() else None
    if cutoff and cutoff < created:
        stats.bump("decision_not_created_as_of")
        return ontology_resolve.unbound("기준 시각에는 아직 생성되지 않은 안건입니다.")
    if cutoff and cutoff < updated:
        # decision_cases is the current projection, not an append-only version
        # store.  Returning it for an earlier time would leak future edits.
        stats.bump("decision_historical_version_unavailable")
        return ontology_resolve.unavailable(
            "기준 시각의 의사결정 안건 판본을 재구성할 수 없습니다.")

    scope_or_resolution = _decision_scope(row, ctx)
    if isinstance(scope_or_resolution, ontology_resolve.ObjectResolution):
        return scope_or_resolution
    if scope_or_resolution is None:
        stats.bump("decision_scope_unbound")
        return ontology_resolve.unbound("의사결정 안건의 조직 범위가 결속되지 않았습니다.")
    try:
        from core import ontology_object_display
        descriptor = ontology_object_display.describe_decision_object(
            object_id=str(row.get("decision_id") or ""),
            question=str(row.get("question") or ""),
            evidence_hash=str(row.get("evidence_hash") or ""),
            package_version=int(row.get("package_version") or 0),
            status=str(row.get("status") or ""),
            outcome=str(row.get("outcome") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )
    except Exception as exc:
        stats.bump("decision_display_unavailable")
        return ontology_resolve.unavailable(
            f"의사결정 표시 설명을 만들지 못했습니다: {exc}")
    stats.bump("decision_resolved")
    return ontology_resolve.found(
        scope_or_resolution,
        row_evidence=(f"decision_cases:evidence={row.get('evidence_hash')}:"
                      f"version={row.get('package_version')}"),
        data_kind=scope_or_resolution.entity_mode,
        display_name=descriptor.display_name,
        display_fingerprint=descriptor.display_fingerprint,
    )


def _resolve_knowledge(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """Resolve a source-byte and ledger-bound reference asset."""
    if ref.object_type != "reference-asset":
        stats.bump("knowledge_type_not_wired")
        return ontology_resolve.unavailable("이 승인 지식 유형은 범위 계약이 없습니다.")
    try:
        from core import knowledge_asset_release as release
        from core.reference_registry import REFERENCE_ROOT, REGISTRY_PATH
        asset = release.effective_asset(
            ref.object_id, str(ctx.as_of or ""), registry_path=REGISTRY_PATH,
            reference_root=REFERENCE_ROOT)
    except release.KnowledgeAssetError as exc:
        stats.bump("knowledge_release_unavailable")
        raise OntologyResolverError("승인 지식 판본을 검증하지 못했습니다.") from exc
    if not asset:
        stats.bump("knowledge_asset_unbound")
        return ontology_resolve.unbound("기준 시각에 유효한 원장 결속 지식 판본이 없습니다.")
    tenant_id = str(asset.get("approval_tenant_id") or "")
    entity_mode = str(asset.get("approval_entity_mode") or "")
    scope_node_id = str(asset.get("approval_scope_node_id") or "")
    scope = _scope(tenant_id, entity_mode, scope_node_id,
                   owner_user_id=str(asset.get("approved_by") or ""))
    if scope is None:
        return ontology_resolve.unavailable("승인 지식 판본의 조직 범위가 비어 있습니다.")
    try:
        from core import ontology_object_display
        descriptor = ontology_object_display.describe_knowledge_asset(
            object_id=ref.object_id, filename=str(asset.get("filename") or ""),
            pack_id=str(asset.get("pack_id") or ""),
            classification=str(asset.get("classification") or ""),
            approved_sha256=str(asset.get("approved_sha256") or ""),
            approval_fingerprint=str(asset.get("approval_fingerprint") or ""),
            approved_at=str(asset.get("approved_at") or ""))
    except Exception as exc:
        stats.bump("knowledge_display_unavailable")
        return ontology_resolve.unavailable("승인 지식의 사람용 표시 설명을 만들지 못했습니다.")
    stats.bump("knowledge_asset_resolved")
    return ontology_resolve.found(
        scope, snapshot_id=str(asset.get("approval_fingerprint") or ""),
        row_evidence=(f"reference_registry:approval={asset.get('approval_event_id')}:"
                      f"sha256={asset.get('approved_sha256')}"),
        data_kind="APPROVED_KNOWLEDGE", display_name=descriptor.display_name,
        display_fingerprint=descriptor.display_fingerprint)


def current_knowledge_object_types() -> tuple[str, ...]:
    """Return current effective type only; never expose asset counts or names."""
    try:
        from core import knowledge_asset_release as release
        from core.reference_registry import REFERENCE_ROOT, REGISTRY_PATH
        return release.current_object_types(
            registry_path=REGISTRY_PATH, reference_root=REFERENCE_ROOT)
    except release.KnowledgeAssetError as exc:
        raise OntologyResolverError("승인 지식 판본 저장소를 읽지 못했습니다.") from exc


#: namespace → 해석기. ★ **닫힌 표다.** 여기 없는 namespace 는 `None` 이다.
#: ⚠️⚠️ 아직 배선하지 않은 namespace 를 «통과» 로 두지 않는다. 그것이 열리면 승인 없는
#:   관계가 그 자리로 들어오고, 화면은 그것을 정상으로 그린다. 배선은 계약이 정해질 때
#:   하나씩 연다 — 그때 이 표와 시험을 **함께** 고친다.
_RESOLVERS = {
    "ecm": _resolve_ecm,
    "dataset": _resolve_dataset,
    "mdm": _resolve_mdm,
    "external": _resolve_external,
    "g4": _resolve_g4,
    "decision": _resolve_decision,
    "knowledge": _resolve_knowledge,
}


def product_object_scope_resolver(
        ref: "ObjectRef",
        ctx: ontology_resolve.ResolveContext) -> ontology_resolve.ObjectResolution:
    """제품 ObjectScopeResolver.

    ★★★ [2026-08-20 §7-0] **범위·판·근거만 번역한다.** 사용자·조직 권한은 여기서
      판정하지 않는다 — PDP(`app_policy.decide`)의 일이다. 두 곳에서 권한을 판정하면
      규칙이 갈라지고, 갈라진 규칙은 언젠가 한쪽만 고쳐진다.

    ⚠️ 「없음」을 어떻게 다룰지도 **여기서 정하지 않는다.** 같은 「없음」이 임의 조회
      에서는 빈 결과이고 승인된 관계의 끝점에서는 503 이다. 그 판단은 문맥을 아는
      런타임이 한다."""
    fn = _RESOLVERS.get(str(getattr(ref, "namespace", "")))
    if fn is None:
        #: ★ 모르는 namespace 는 **없는 것**으로 본다 — 계약이 닫힌 목록이므로,
        #:   여기 없는 이름은 애초에 우리 세계에 없는 것이다.
        stats.bump("unknown_namespace")
        return ontology_resolve.not_found("계약에 없는 namespace 입니다.")
    try:
        res = fn(ref, ctx)
    except OntologyResolverError as exc:
        #: ⚠️ [P0-3] 장애를 «없음» 으로 접지 않는다. 이제는 상태로 말한다 —
        #:   런타임이 목적과 무관하게 503 으로 바꾼다.
        stats.bump("resolver_unavailable")
        return ontology_resolve.unavailable(str(exc))
    except Exception as exc:
        stats.bump("resolver_error")
        return ontology_resolve.unavailable(
            f"범위를 해석하지 못했습니다({getattr(ref, 'key', '?')}): {exc}")
    if not isinstance(res, ontology_resolve.ObjectResolution):
        #: ⚠️⚠️ 옛 서명으로 남은 해석기를 **조용히 받지 않는다.** 받으면 `None` 이 다시
        #:   «안 보임» 이 되어 목적별 판정이 통째로 무력해진다.
        stats.bump("resolver_contract_violation")
        return ontology_resolve.unavailable(
            f"해석기가 ObjectResolution 을 돌려주지 않았습니다({ref.key}).")
    return res


# ── 승인 판정 ────────────────────────────────────────────────────────────
def product_approval_resolver(ledger_id: str, action: str, actor: str,
                             target_type: str = "", target_id: str = "") -> bool:
    """제품 ApprovalResolver — **원장이 실제로 «이 행위를 이 대상에» 승인했는가.**

    ★★★ 상관 문자열이 있다는 것은 승인이 아니다. 다음을 **전부** 본다:

        ① 그 이벤트가 실제로 있는가
        ② 목적 전용 이벤트 유형인가(`ONTOLOGY_*` — 범용 결정 이벤트를 재사용하지 않는다)
        ③ **대상이 같은가** — 계약 지문 / relation_id
        ④ 승인자가 요청 행위자와 같은가
        ⑤ 정정·철회된 승인이 아닌가

    ⚠️⚠️ [2026-08-20 실측] ④ 에서 `event["actor"]` 를 읽고 있었다. 원장의 실제 필드는
      **`actor_id`** 다 — 그래서 실제 승인 이벤트가 있어도 **항상 거짓**이었다.
      「대조한다」고 적혀 있었지만 대조되는 것이 없었다.

    ⚠️ 하나라도 확인할 수 없으면 **거짓**이다. 「모르니까 승인」은 승인이 아니다."""
    lid = str(ledger_id or "").strip()
    act = str(action or "").strip()
    who = str(actor or "").strip()
    t_type = str(target_type or "").strip()
    t_id = str(target_id or "").strip()

    if not lid or not who:
        stats.bump("approval_missing_args")
        return False
    if act not in APPROVABLE_ACTIONS:
        stats.bump("approval_unknown_action")
        return False
    #: ★★★ 대상 없이 승인하지 않는다 — 그것이 P0-2 의 요점이다.
    if not t_id:
        stats.bump("approval_missing_target")
        return False
    if _TARGET_SUBJECT.get(t_type) != _ACTION_SUBJECT[act]:
        #: 호출부가 넘긴 대상 종류가 이 행위의 것이 아니다.
        stats.bump("approval_target_kind_mismatch")
        return False

    from core.decision_ledger import decision_ledger

    try:
        #: ★★★ **strict 조회를 쓴다.** `get_event()` 는 DB 장애를 `None` 으로 접고,
        #:   그러면 장애가 「승인 이벤트가 없다」와 구별되지 않는다.
        event = decision_ledger.get_event_strict(lid)
    except Exception:
        #: ★★★ [2026-08-20 Supervisor 지적] **예외를 다시 던진다.**
        #:
        #: ⚠️⚠️ 여기서 `False` 로 접으면 원장 장애가 「승인이 무효다」(400)로 보인다.
        #:   사용자는 «승인을 안 받았구나» 로 읽고 승인을 다시 요청하지만, 실제 문제는
        #:   저장소이므로 몇 번을 해도 같다. 장애는 **503** 으로 드러나야 한다.
        #: ★ 통계는 올리고 예외는 그대로 — `_assert_approval` 이 503 으로 바꾼다.
        stats.bump("approval_ledger_unreadable")
        raise
    if not event:
        #: ★ **없는 것만** 거짓이다. 이것이 유일한 「승인 없음」이다.
        stats.bump("approval_event_missing")
        return False

    #: ② 목적 전용 이벤트인가.
    if str(event.get("event_type") or "") != _ACTION_EVENT[act]:
        stats.bump("approval_wrong_purpose")
        return False

    #: ③ **대상 대조** — 종류와 식별자가 둘 다 같아야 한다.
    if str(event.get("subject_type") or "") != _ACTION_SUBJECT[act]:
        stats.bump("approval_subject_type_mismatch")
        return False
    if str(event.get("subject_id") or "").strip() != t_id:
        stats.bump("approval_subject_id_mismatch")
        return False

    #: ④ 승인자와 요청 행위자. ⚠️ 원장 필드는 `actor_id` 다.
    if str(event.get("actor_id") or "").strip() != who:
        stats.bump("approval_actor_mismatch")
        return False

    #: ⑤ 이 승인을 무효로 만드는 후속 이벤트가 있는가.
    #:
    #: ⚠️⚠️ [2026-08-20 Supervisor 지적 P0-2] `list_events()` 로 세면 안 된다 —
    #:   `LIMIT` 이 있어서 **철회 뒤에 무관한 이벤트가 100건 넘게 쌓이면** 철회가
    #:   조회 밖으로 밀려나고 **원 승인이 되살아난다.** 게다가 그 함수는 판독 실패를
    #:   빈 배열로 접으므로 원장 장애도 「철회 없음」이 된다.
    #: ★ 전용 API 는 제한 없이 인덱스로 묻고, 못 읽으면 **던진다.**
    try:
        revoked = decision_ledger.has_invalidating_child(lid, sorted(_INVALIDATING))
    except Exception:
        #: ⚠️ 같은 이유로 **다시 던진다** — 「철회가 있는지 못 읽었다」를 「없다」로도
        #:   「무효다」로도 접지 않는다.
        stats.bump("approval_ledger_unreadable")
        raise
    if revoked:
        stats.bump("approval_invalidated")
        return False
    return True
    try:
        return [e for e in (rows or [])
                if str(e.get("parent_event_id") or "").strip() == ledger_id]
    except Exception:
        return None
