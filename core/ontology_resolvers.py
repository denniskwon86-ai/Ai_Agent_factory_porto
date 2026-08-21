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

import threading
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
    #: ★ 조직 노드는 인증판에서 오는 것이 아니므로 `snapshot_id` 가 없다.
    #: ⚠️ 그래서 봉인된 판을 요구하는 문맥에서는 **쓸 수 없다** — 런타임이 막는다.
    return ontology_resolve.found(scope, data_kind=mode)


def _resolve_dataset(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """업무 객체(선적·발주라인·재고·생산계획라인·판매라인)의 범위.

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

    try:
        #: ★★★ [2026-08-21 P0] **정체성 두 값을 함께 넘긴다.** 없으면 다른 회사의
        #:   `SHP-000001` 이 우리 것을 가리거나 동점을 만든다.
        if not ctx.tenant_id or not ctx.entity_mode:
            #: ⚠️ 문맥이 반쪽이면 «전부 뒤진다» 로 넓히지 않는다 — 그 순간 회사 경계가
            #:   사라진다. 모르면 **막는다.**
            stats.bump("dataset_identity_missing")
            return ontology_resolve.unavailable(
                "조회 문맥에 tenant·entity_mode 가 없습니다 — 객체를 특정할 수 없습니다.")
        status, row, candidates = scope_index.lookup(
            data_preparation_store, ref.namespace, ref.object_type, ref.object_id,
            ctx.tenant_id, ctx.entity_mode,
            as_of=str(getattr(ctx, "as_of", "") or ""))
    except Exception as exc:
        #: ⚠️ [P0-3] 저장소 장애를 «없음» 으로 접지 않는다. 못 읽은 것과 없는 것은
        #:   다른 사실이고, 앞엣것은 **사람이 손을 써야** 한다.
        stats.bump("dataset_index_unreadable")
        raise OntologyResolverError(
            f"범위 색인을 읽지 못했습니다({ref.key}): {exc}") from exc

    if status == scope_index.AMBIGUOUS:
        #: ⚠️⚠️ 같은 시각의 인증판이 둘이다. **아무거나 고르지 않는다** — 고르면 같은
        #:   질문의 답이 실행마다 달라지고 재실행 지문이 흔들린다.
        stats.bump("dataset_ambiguous_version")
        return ontology_resolve.ambiguous(
            candidates, f"같은 시각의 인증판이 {len(candidates)}개입니다.")
    if status == scope_index.UNBOUND:
        #: ★ 객체는 아는데 **그 시점에는 아직 인증 전**이다.
        stats.bump("dataset_unbound_at_as_of")
        return ontology_resolve.unbound(
            f"그 시점에는 아직 인증되지 않았습니다(as_of={ctx.as_of or '지금'}).")
    if status != scope_index.FOUND or row is None:
        stats.bump("dataset_not_indexed")
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
    scope = _scope(str(row.get("tenant_id", "")), str(row.get("entity_mode", "")),
                   str(row.get("scope_node_id", "")),
                   owner_dept_id=str(row.get("owner_dept_id", "") or ""))
    if scope is None:
        #: ⚠️⚠️ 색인은 범위 없는 행을 애초에 받지 않는다. 그런데도 여기 왔다면 **자료가
        #:   어긋난 것**이지 「안 보이는 것」이 아니다.
        #: ★ 「일어날 리 없다」를 그냥 두면 일어났을 때 `found(None)` 로 터지고, 그
        #:   예외는 «해석 실패» 로 뭉뚱그려져 원인을 잃는다.
        stats.bump("dataset_scope_missing")
        return ontology_resolve.unavailable(
            f"색인 줄에 범위가 없습니다({ref.key}) — 자료가 어긋났습니다.")
    stats.bump("dataset_resolved")
    return ontology_resolve.found(
        scope, snapshot_id=str(row.get("snapshot_id", "")),
        row_evidence=str(row.get("row_evidence", "")),
        data_kind=str(row.get("data_kind", "")))


def _resolve_mdm(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """기준정보. **아직 범위 계약이 없다.**

    ⚠️ [P0-3] `None`(=안 보인다)이 아니라 **장애**로 올린다. `None` 이면 런타임이
      경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 — 사용자는 그것을
      사실로 읽는다. 배선이 없는 것은 사실이 아니라 **우리 쪽 미완성**이다."""
    stats.bump("mdm_not_wired")
    raise OntologyResolverError(
        f"기준정보 namespace 는 아직 범위 계약이 "
        f"없습니다({ref.key}).")


def _resolve_external(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """외부지표. **아직 범위 계약이 없다.**

    ⚠️ [P0-3] `None`(=안 보인다)이 아니라 **장애**로 올린다. `None` 이면 런타임이
      경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 — 사용자는 그것을
      사실로 읽는다. 배선이 없는 것은 사실이 아니라 **우리 쪽 미완성**이다."""
    stats.bump("external_not_wired")
    raise OntologyResolverError(
        f"외부지표 namespace 는 아직 범위 계약이 "
        f"없습니다({ref.key}).")


def _resolve_g4(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """계산 Driver·결과. **아직 범위 계약이 없다.**

    ⚠️ [P0-3] `None`(=안 보인다)이 아니라 **장애**로 올린다. `None` 이면 런타임이
      경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 — 사용자는 그것을
      사실로 읽는다. 배선이 없는 것은 사실이 아니라 **우리 쪽 미완성**이다."""
    stats.bump("g4_not_wired")
    raise OntologyResolverError(
        f"계산 Driver·결과 namespace 는 아직 범위 계약이 "
        f"없습니다({ref.key}).")


def _resolve_decision(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """시나리오·의사결정. **아직 범위 계약이 없다.**

    ⚠️ [P0-3] `None`(=안 보인다)이 아니라 **장애**로 올린다. `None` 이면 런타임이
      경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 — 사용자는 그것을
      사실로 읽는다. 배선이 없는 것은 사실이 아니라 **우리 쪽 미완성**이다."""
    stats.bump("decision_not_wired")
    raise OntologyResolverError(
        f"시나리오·의사결정 namespace 는 아직 범위 계약이 "
        f"없습니다({ref.key}).")


def _resolve_knowledge(ref: "ObjectRef", ctx: ontology_resolve.ResolveContext):
    """승인된 지식. **아직 범위 계약이 없다.**

    ⚠️ [P0-3] `None`(=안 보인다)이 아니라 **장애**로 올린다. `None` 이면 런타임이
      경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 — 사용자는 그것을
      사실로 읽는다. 배선이 없는 것은 사실이 아니라 **우리 쪽 미완성**이다."""
    stats.bump("knowledge_not_wired")
    raise OntologyResolverError(
        f"승인된 지식 namespace 는 아직 범위 계약이 "
        f"없습니다({ref.key}).")


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
