"""★★★ [B2 / M0-3.3] 경로 계산 — **제품이 부르는 경로.**

## 왜 라우트가 따로 필요했는가

계산기(`core.path_calculation`)와 그 서비스 층은 이미 있었지만 **부르는 것은 시험뿐**
이었다. 이 저장소에서 「코어가 있는 것」과 「제품이 호출하는 것」의 차이로 두 번 지적을
받았다 — 코어가 아무리 엄해도 제품이 그 경로로 들어오지 않으면 통제는 걸리지 않는다.

## ⚠️⚠️ 이 라우트가 **받지 않는** 것 — 그것이 설계의 전부다

| 호출자가 못 주는 것 | 왜 | 서버가 어디서 얻는가 |
|---|---|---|
| `relation_ids` | 빈 목록을 보내면 **승인할 것이 없어진다** — 관문이 통째로 빈다 | 질의를 다시 실행해 **경로의 간선**에서 뽑는다 |
| `relation_approvals` | 「승인됐다」는 호출자의 자기진술이 된다 | Decision Ledger |
| `sealed_snapshots` | 어느 판으로 계산했는지가 주장이 된다 | 저장소 인증판 |
| `baseline_id`·배분·인식 규칙 | 「무엇과 비교했는가」가 주장이 된다 | 봉인된 기준선 |
| `path_model_version` | 판을 적어 보내면 옛 판인 척할 수 있다 | 계산기 상수 |
| `tenant_id`·`entity_mode`·`scope_node_id` | 남의 조직 값을 적어 보내면 **봉인 대조가 자기일관**해진다 — 호출자가 준 값끼리 맞춰 보는 셈이다 | **인스턴스 행**에서 읽는다(그 인스턴스가 보이는지는 `_instance_or_404` 가 판정) |

★★★ 호출자가 주는 것은 **질문뿐**이다: 무엇에서 시작해(roots) 무엇까지(target_types),
  언제 기준으로(as_of), 어느 자료로(instance_id), 어떤 가정으로(assumptions).

★ `path_fingerprint` 는 호출자가 고른다 — 다만 **서버가 낸 답 중에서만** 고를 수 있다.
  없는 지문을 보내면 404 다(경로를 지어낼 수 없다).

## 실패를 세 가지로 가른다 — 섞으면 화면이 거짓말한다

· **장애** → 503. 원장을 못 읽었는데 「승인 없음」으로 답하면 승인을 지운 것과 같다.
· **미승인·근거 부족** → 200 + `status="BLOCKED"` + 사유. 오류가 아니라 **답**이다.
· **결과 없음** → 0 으로 표시하지 않는다. 계산기가 `missing_*` 로 답한다.

LLM 호출: 0건.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import (Principal, assert_identified, current_principal,
                      viewing_context, visibility_block_reason)
from core import app_policy
from core import ontology_path_adapter as adapter
from core import path_calculation as pc
from core import calc_dataset_loader as loader
from core import calc_execution_approval as cea
from core import demo_readiness
from core import demo_reset
from core import demo_vertical_slice as dv
from core import enterprise_work_scenario as ews
from core import path_calculation_service as svc
from core.enterprise_context import audit
#: ★★ 인스턴스 가시성 판정을 **한 벌만** 쓴다. 같은 판정을 두 벌로 만들면 한쪽만
#:   고쳐지는 날이 오고, 그날 이 경로만 조용히 헐거워진다.
from api.routes import baseline_control as bc
from api.routes.data_preparation_control import _instance_or_404
from core.data_preparation.store import data_preparation_store as store
from core.ontology_runtime import (ObjectRef, OntologyAccessError, OntologyError,
                                   OntologyIntegrityError, ontology_runtime)
from core.route_authority import guard as _route_authority_guard

router = APIRouter(prefix="/api/v1/calculation", tags=["Path Calculation"],
                   dependencies=[Depends(_route_authority_guard)])


class ObjectRefInput(BaseModel):
    namespace: str
    object_type: str
    object_id: str


class PathCalcInput(BaseModel):
    """★ 호출자는 **질문**만 준다. 승인·판·기준선은 아래 어디에도 없다.

    ⚠️⚠️ `extra="forbid"` 다. 모르는 칸을 **조용히 무시하지 않는다** — 무시하면 통합하는
      사람은 `relation_approvals` 나 `scope_id` 를 자기가 설정했다고 믿는다. 거부해야
      「그건 서버가 정한다」를 배운다(`decision_control` 의 본문 모델과 같은 규약).
    ★ 변이로 확인했다: 이 규약이 없으면 「호출자가 조직을 정하게」 하는 변경이 **등가**로
      보인다 — 모델이 그 칸을 버리기 때문이다. 그러면 무엇이 막는지 알 수 없다."""

    model_config = ConfigDict(extra="forbid")

    #: 무엇을 묻는가
    roots: List[ObjectRefInput]
    target_types: List[str] = Field(default_factory=list)
    relation_types: List[str] = Field(default_factory=list)
    as_of: str
    max_depth: int = 6
    max_paths: int = 20
    #: 서버가 낸 경로 중 어느 것인가(하나뿐이면 생략 가능)
    path_fingerprint: str = ""
    #: 어느 자료로 — ★ 문맥(`tenant_id`·`entity_mode`·`scope_node_id`)은 **받지 않는다.**
    #:   인스턴스 행에서 읽는다. 받으면 남의 조직 값을 적어 보낼 수 있고, 봉인 대조는
    #:   호출자가 준 값끼리 맞추므로 그대로 통과한다(대조는 불일치를 막지 허가를 주지 않는다).
    instance_id: str
    #: 시나리오 손잡이 — ⚠️ 봉인된 키(배분·인식 규칙)를 넣어도 봉인이 이긴다
    assumptions: Dict[str, Any] = Field(default_factory=dict)


class WorkScenarioCreateInput(BaseModel):
    """전사 시나리오의 사람용 이름과 목적만 받는다.

    조직·tenant·실행 모드는 키트 인스턴스에서 얻는다. 클라이언트가 그 값을 보내게
    두면 다른 조직 문맥을 자기일관되게 꾸밀 수 있다.
    """

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)


class DiagnosticInput(PathCalcInput):
    """내부 진단을 펼치거나 복사할 때의 명시적 확인.

    질문·경로·인스턴스는 일반 계산과 같은 선택값을 다시 보내지만, 내부 식별자 자체는
    클라이언트가 보내지 않는다. 서버가 경로와 계산을 다시 실행해 당시 진단을 만든다.
    """

    purpose: str = Field(min_length=10, max_length=300)
    acknowledgement: Literal["SHOW_INTERNAL_DIAGNOSTIC", "COPY_INTERNAL_DIAGNOSTIC"]


class DecisionInput(PathCalcInput):
    """[G5] 안건 입력.

    ★★★ **경영 수치는 계산기가 내지 않는다.** 경로 계산이 내는 것은 부족량·생산가능량·
      매출 이연 같은 **지표**이고, 안건의 3관점 검토서는 `calc_graph` 의 다섯 값
      (생산량·기말재고·구매지급·기말현금·영업이익)으로 짜여 있다. 서로 다른 집합이다.

    ⚠️⚠️ 그 둘을 억지로 맞추면 **숫자를 지어내는 것**이다 — 지표 합계를 「영업이익」
      칸에 넣는 식으로. 그래서 시뮬레이션 입력은 기존 결정 라우트와 **같은 모양**으로
      받고(`baseline_control`), 경로 계산은 **근거로 묶는다**. 그것이 M0-G5-01 이
      요구하는 「B2 계산 결과와 경로·Snapshot 봉인」이다."""

    title: str
    owner: str
    due: str
    #: ★★★ **결정 문장.** 제목이 아니다 — 「무엇을 승인·기각하는가」를 한 문장으로.
    #: ⚠️ 「검토 요청」 같은 제목만 있으면 참석자는 무엇을 결정하는지 모르고, 회의록에는
    #:   「논의함」만 남는다(`core.decision_case.create` 가 같은 이유로 요구한다).
    question: str = ""
    #: 시뮬레이션 기준선 — 재현 가능해야 하므로 판을 **명시**한다(「최신으로 알아서」 금지).
    snapshot_ids: List[str]
    base_values: Dict[str, float]
    scenario_assumptions: Dict[str, float] = Field(default_factory=dict)


def _subject(p: Principal) -> app_policy.Subject:
    return app_policy.Subject(
        user_id=p.user_id or "", scope=p.scope, ctx=viewing_context(p),
        session_id=p.session_id or "", blocked_reason=visibility_block_reason(p))


def _raise_ontology(exc: Exception) -> None:
    if isinstance(exc, OntologyAccessError):
        raise HTTPException(status_code=404, detail="요청한 온톨로지 자원을 찾을 수 없습니다.")
    if isinstance(exc, OntologyIntegrityError):
        #: ⚠️ **장애는 503 이다.** 읽지 못한 것을 「없다」로 답하면 통제를 지운 것이다.
        raise HTTPException(status_code=503, detail=f"온톨로지 상태를 확인할 수 없습니다: {exc}")
    if isinstance(exc, OntologyError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _resolve_path(req: PathCalcInput, p: Principal, actor: str,
                  ctx: Dict[str, str]) -> Dict[str, Any]:
    """질의를 **서버에서 다시 실행해** 경로를 얻는다.

    ★★★ 이것이 이 라우트의 급소다. 호출자가 `relation_ids` 를 적어 보내게 두면 **빈
      목록**을 보낼 수 있고, 그러면 대조할 승인이 없어져 관문이 통째로 빈다. 관계 목록은
      **경로의 간선**에서만 나온다.

    ⚠️ 질의는 저장되지 않는다 — `query_id` 는 질문 payload 의 해시다. 그래서 같은 질문을
      다시 실행하면 같은 `query_id` 가 나오고, 그것으로 정체성이 성립한다."""
    try:
        response = ontology_runtime.find_paths(
            _subject(p),
            [ObjectRef(r.namespace, r.object_type, r.object_id) for r in req.roots],
            req.target_types, req.relation_types, req.as_of,
            req.max_depth, req.max_paths)
    except Exception as exc:  # noqa: BLE001 — 유형별로 아래에서 가른다
        _raise_ontology(exc)
    try:
        #: ★★★ **실제 원장 검증기를 넘긴다.** 없으면 어댑터는 어느 구간도 「실행 가능」으로
        #:   표시하지 않고(그 규약은 B1.1 P1 에서 정했다), 그러면 승인이 다 있어도
        #:   `calculation_blocked` 가 서서 안건이 만들어지지 않는다.
        #: ⚠️ 대역을 넣지 않는다 — 대역을 넣으면 「승인 → 계산」이 아니라 「대역 → 계산」이다.
        evidence = adapter.to_evidence(
            response, path_fingerprint=req.path_fingerprint,
            ledger_verifier=svc.context_verifier(store, **ctx),
            capability_resolver=svc.context_resolver(store, **ctx))
        #: ★ **같은 경로**의 결속을 뽑는다 — 어댑터가 고른 지문을 그대로 넘긴다.
        #: ⚠️ 결속은 근거에 실리지 않는다 — 대외 근거에 구간 목록을 담지 않는 규약이다
        #:   (`blocked_reason` 이 숫자·이름을 감추는 것과 같은 이유).
        bindings = adapter.relation_bindings(
            response, path_fingerprint=evidence["path_fingerprint"])
    except adapter.PathAdapterError as exc:
        #: 지문을 지어냈거나 보이는 경로가 없다 — 존재하지 않는 자원이다.
        raise HTTPException(status_code=404, detail=str(exc))
    return {"evidence": evidence, "bindings": bindings}


def _calculate(req: PathCalcInput, p: Principal, *, include_internal: bool = False) -> Dict[str, Any]:
    #: ★★★ **문맥을 인스턴스에서 읽는다.** 보이지 않는 인스턴스는 404 다(없는 것과 못
    #:   보는 것을 같은 답으로 돌려준다 — 다르면 그 응답이 존재를 알려 준다).
    inst = _instance_or_404(p, req.instance_id)
    tenant_id = str(inst["tenant_id"])
    entity_mode = str(inst["entity_mode"])
    scope_node_id = str(inst["scope_node_id"])

    actor = p.user_id or ""
    found = _resolve_path(req, p, actor,
                          {"instance_id": req.instance_id, "tenant_id": tenant_id,
                           "entity_mode": entity_mode, "scope_node_id": scope_node_id})
    evidence, bindings = found["evidence"], found["bindings"]
    try:
        request = svc.build_request(
            store, query_id=evidence["query_id"],
            path_fingerprint=evidence["path_fingerprint"],
            relation_bindings=bindings,
            instance_id=req.instance_id,
            tenant_id=tenant_id, entity_mode=entity_mode,
            scope_node_id=scope_node_id, as_of=req.as_of, actor=actor,
            assumptions=req.assumptions)
    except svc.PathRequestError as exc:
        #: 봉인·기준선이 없다 — 요청이 성립하지 않는다(장애가 아니다).
        raise HTTPException(status_code=422, detail=str(exc))
    except pc.PathCalculationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        result = svc.run(store, request, actor=actor)
    except loader.SealedDatasetError as exc:
        #: ⚠️⚠️ **읽지 못한 것을 「자료 없음」으로 접지 않는다.** 접으면 화면이 「영향
        #:   없음」을 보여 주고, 그것은 확인되지 않은 상태를 확인된 답으로 바꾼다.
        raise HTTPException(status_code=503, detail=str(exc))
    except pc.PathCalculationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    #: ★ 코어 진단에는 관계 ID·계약키·계산 참조가 들어간다. 일반 제품 API는 닫힌
    #:   사유 코드와 다음 행동만 반환한다. 원본 진단은 권한 분리된 운영 경로의 몫이다.
    if not include_internal:
        result = pc.public_result(result)
    #: ★ 문맥도 함께 돌려준다 — 안건의 조직은 **인스턴스가 정한다**. 호출부가 다시
    #:   유도하면 두 곳이 갈라지고, 갈린 날 안건이 남의 부서로 들어간다.
    return {"evidence": evidence, "result": result,
            "ctx": {"tenant_id": tenant_id, "entity_mode": entity_mode,
                    "scope_node_id": scope_node_id}}


def _diagnostic(got: Dict[str, Any]) -> Dict[str, Any]:
    """계산 내부 결과에서 운영 진단 봉투를 만든다."""
    result = got["result"]
    blocked = result.get("blocked")
    if result.get("status") != pc.BLOCKED or not isinstance(blocked, dict):
        raise HTTPException(status_code=409, detail="차단된 계산 결과에만 내부 진단이 있습니다.")
    internal = blocked.get("internal_reasons")
    if not isinstance(internal, list) or not internal:
        raise HTTPException(status_code=503, detail="내부 진단 근거를 확인할 수 없습니다.")
    payload = {
        "reason_code": str(blocked.get("reason_code") or ""),
        "internal_reasons": [str(v) for v in internal],
        "identifiers": {
            "query_id": str(result.get("query_id") or ""),
            "path_fingerprint": str(result.get("path_fingerprint") or ""),
            "request_fingerprint": str(result.get("request_fingerprint") or ""),
            "required_relation_ids": [str(v) for v in result.get("required_relation_ids") or []],
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["diagnostic_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _record_diagnostic(event: str, diagnostic: Dict[str, Any], got: Dict[str, Any],
                       req: DiagnosticInput, p: Principal) -> None:
    """민감 진단의 열람·복사를 감사하고, 기록 실패 시 공개하지 않는다."""
    ok = audit.record(
        event, "calculation_diagnostic", diagnostic["diagnostic_fingerprint"],
        actor=p.user_id or "", requested_scope=got["ctx"]["scope_node_id"],
        outcome="allowed", reason="explicit_operator_action",
        detail=json.dumps({"purpose": req.purpose.strip(),
                           "reason_code": diagnostic["reason_code"]},
                          ensure_ascii=False, sort_keys=True))
    if not ok:
        raise HTTPException(status_code=503, detail="감사 기록을 남기지 못해 내부 진단을 공개하지 않았습니다.")


class ApprovalInput(BaseModel):
    """승인 요청. ★ **지문을 받지 않는다** — 서버가 다시 산출해 대조한다."""

    instance_id: str
    refs: List[str] = Field(default_factory=list)
    rationale: str
    data_kind: str = ""
    entity_mode: str = ""
    valid_days: int = 0
    #: ★ 화면이 본 제안서의 지문. **대조용**이지 승인 대상이 아니다.
    #: ⚠️ 이것이 없으면 「화면에 뜬 것」과 「실제로 승인되는 것」이 다를 수 있다 —
    #:   사람이 읽고 누르는 사이에 판이 새로 인증될 수 있기 때문이다.
    seen_fingerprints: Dict[str, str] = Field(default_factory=dict)


class RevokeInput(BaseModel):
    reason: str


def _reset_target(p: Principal, instance_id: str) -> Dict[str, Any]:
    """초기화 대상 인스턴스. ★ 가시성 판정은 **한 벌**을 쓴다.

    ⚠️ 권한(`ADMIN_SECURITY`)은 라우터 표가 막는다 — 여기 적지 않는다(앞 관문이 가려
      도달하지 않는 통제를 두지 않는다)."""
    inst = _instance_or_404(p, instance_id)
    return dict(inst)


def _admin_ctx(p: Principal, instance_id: str) -> Dict[str, str]:
    """★★★ **시스템 관리자만.** 데이터 관리자·조직 관리자·프로젝트 관리자는 못 누른다.

    ⚠️ 새 권한 이름을 지어내지 않는다. `ADMIN_SECURITY` 는 이 저장소에서 플랫폼 관리자
      (`is_admin`)에게만 가고, 데이터·AI 관리자와 부서 역할 어디에도 없다 —
      `core/admin_capability.py` 의 `_DATA_ADMIN_CAPS`·`_AI_ADMIN_CAPS`·`_ROLE_CAPS`
      가 그것을 보증한다.
    ★ M1 에서 `DEMO_RESET`·`CALC_APPROVE` 로 갈라 낼 수 있다 — 지금 지어내면 표와
      코드가 갈라진다."""
    #: ⚠️⚠️ 여기에 `require_caps` 를 **적지 않는다.** 라우터 의존성(`route_authority.guard`)
    #:   이 표를 보고 먼저 막는다 — 실제로 여기에 한 줄 더 두었더니 **변이 0건**이었다
    #:   (앞 관문이 가려 도달하지 않는다). 통제처럼 보이는 도달 불가 코드를 두면 나중에
    #:   「여기서 막으니 괜찮다」고 믿고 표에서 빼게 된다.
    #: ★ 이 세 라우트의 권한은 `core/route_authority.py` 의 표에 있다(ADMIN_SECURITY).
    inst = _instance_or_404(p, instance_id)
    return {"instance_id": str(inst["instance_id"]),
            "tenant_id": str(inst["tenant_id"]),
            "entity_mode": str(inst["entity_mode"]),
            "scope_node_id": str(inst["scope_node_id"])}


def _scope_of(ctx: Dict[str, str], want_mode: str, want_kind: str) -> Dict[str, str]:
    """승인 범위를 **인스턴스에서 파생한다.**

    ## ⚠️⚠️ 상수 기본값이 승인을 영원히 안 붙게 했다 (2026-08-24 실측)

    종전에는 `entity_mode or cea.DEFAULT_ENTITY_MODE`(= `VIRTUAL`)였다. 그런데 준비도
    관문과 실행기는 **인스턴스의 `entity_mode`**(시연 자료는 `REAL`)로 승인을 찾는다.
    그래서 화면에서 승인을 눌러 200 과 원장 사건까지 받고도 관문은 계속
    「실행 승인이 없는 계산 3건」이었다 — **오류는 어디에도 나지 않는다.**
    제로베이스 완주를 여기서 막았다.

    ★★★ 문맥은 **인스턴스 행이 정본**이다. 호출자가 정하지 않는다
      (`PathCalcInput` 이 `tenant_id`·`scope_node_id` 를 안 받는 것과 같은 규약).
    ⚠️ 그래도 화면이 다른 값을 적어 보내면 **거부**한다 — 조용히 갈아치우면 사람은
      자기가 고른 범위로 승인됐다고 믿는다.
    ★ `data_kind` 는 조회 키가 아니라 **기록 표시**다. 그래도 상수로 두면 실제 자료를
      「DEMO/SYNTHETIC」으로 적게 되므로 인증판에서 읽는다.
    """
    mode = str(want_mode or "").strip()
    if mode and mode != ctx["entity_mode"]:
        raise HTTPException(
            status_code=422,
            detail=(f"승인 범위의 실체 구분이 인스턴스와 다릅니다 — 인스턴스는 "
                    f"「{ctx['entity_mode']}」인데 「{mode}」로 승인하려 했습니다. "
                    f"다른 구분으로 승인하면 그 승인은 이 인스턴스의 계산에 붙지 "
                    f"않습니다(관문은 계속 「승인 없음」으로 답합니다)."))
    kind = str(want_kind or "").strip() or _kind_of(ctx["instance_id"])
    return {"entity_mode": ctx["entity_mode"], "data_kind": kind}


def _kind_of(instance_id: str) -> str:
    """인스턴스의 **살아 있는 인증판**이 실제로 어떤 자료인지 읽는다.

    ⚠️ 섞여 있으면 하나를 고르지 않는다 — 섞인 채로 승인하면 그 기록은 둘 중 어느
      쪽도 정확히 가리키지 않는다. 그때는 상수 대신 「MIXED」로 적어 눈에 띄게 한다."""
    try:
        with store.transaction() as conn:
            kinds = sorted({str(r[0]) for r in conn.execute(
                "SELECT DISTINCT data_kind FROM dataset_snapshots "
                "WHERE instance_id=? AND status='active'", (instance_id,)) if r[0]})
    except Exception:  # noqa: BLE001 — 못 읽으면 지어내지 않는다
        return cea.DEFAULT_DATA_KIND
    if len(kinds) == 1:
        return kinds[0]
    return "MIXED" if kinds else cea.DEFAULT_DATA_KIND


@router.get("/capabilities")
async def capabilities(instance_id: str = "", data_kind: str = "",
                       entity_mode: str = "", valid_days: int = 0,
                       p: Principal = Depends(current_principal)):
    """[M0-0] 승인 **제안서** — 화면이 보여 줄 정의·단위·부호·범위·유효기간.

    ★★★ **아무것도 승인하지 않는다.** 부작용이 없다. 누르기 전까지 계산은 계속
      `BLOCKED` 로 답한다.
    ★ 서버가 지문을 직접 산출한다 — 호출자가 적어 보낼 수 없다."""
    ctx = _admin_ctx(p, instance_id)
    _sc = _scope_of(ctx, entity_mode, data_kind)
    try:
        data = await asyncio.to_thread(
            cea.proposal, store, instance_id=ctx["instance_id"],
            tenant_id=ctx["tenant_id"],
            entity_mode=_sc["entity_mode"],
            scope_node_id=ctx["scope_node_id"],
            data_kind=_sc["data_kind"],
            valid_days=valid_days or cea.DEFAULT_VALID_DAYS)
    except cea.ExecutionApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except loader.SealedDatasetError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    #: ★ 지금 살아 있는 승인도 함께 — 화면이 「이미 승인됨」을 구분할 수 있어야 한다.
    live = await asyncio.to_thread(cea.list_approvals, store,
                                   tenant_id=ctx["tenant_id"],
                                   scope_node_id=ctx["scope_node_id"])
    data["approvals"] = [{k: r[k] for k in ("approval_id", "ref", "status",
                                            "binding_fingerprint", "valid_until",
                                            "approved_by", "data_kind", "entity_mode")}
                         for r in live]
    return {"status": "success", "data": data}


@router.post("/capabilities/approve")
async def approve_capabilities(req: ApprovalInput,
                               p: Principal = Depends(current_principal)):
    """[M0-0] 사람이 누르는 자리. **능력마다 별도 원장 사건**을 남긴다.

    ⚠️⚠️ 화면에서 셋을 한 번에 고를 수 있어도 원장에는 셋으로 남는다 — 하나를 철회할 때
      나머지가 함께 죽으면 안 되고, 「무엇을 승인했나」가 능력별로 답해져야 한다.

    ★ 멱등: 같은 결속에 살아 있는 승인이 있으면 새 사건을 만들지 않는다.
    ⚠️ 화면이 본 지문과 지금 서버가 산출한 지문이 다르면 **거부**한다 — 사람이 읽고
      누르는 사이에 판이 바뀌었을 수 있고, 그때 승인되는 것은 읽은 것이 아니다."""
    ctx = _admin_ctx(p, req.instance_id)
    _sc = _scope_of(ctx, req.entity_mode, req.data_kind)
    if not str(req.rationale or "").strip():
        raise HTTPException(status_code=422, detail="승인 사유가 필요합니다.")
    try:
        prop = await asyncio.to_thread(
            cea.proposal, store, instance_id=ctx["instance_id"],
            tenant_id=ctx["tenant_id"],
            entity_mode=_sc["entity_mode"],
            scope_node_id=ctx["scope_node_id"],
            data_kind=_sc["data_kind"],
            valid_days=req.valid_days or cea.DEFAULT_VALID_DAYS)
    except cea.ExecutionApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except loader.SealedDatasetError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    wanted = {str(r).strip() for r in req.refs if str(r).strip()}
    items = [i for i in prop["items"] if not wanted or i["ref"] in wanted]
    unknown = sorted(wanted - {i["ref"] for i in prop["items"]})
    if unknown:
        raise HTTPException(status_code=404,
                            detail=f"승인할 수 없는 계산 참조입니다: {unknown}")
    if not items:
        raise HTTPException(status_code=422, detail="승인할 계산이 없습니다.")

    for item in items:
        seen = str(req.seen_fingerprints.get(item["ref"], "") or "").strip()
        if seen and seen != item["binding_fingerprint"]:
            #: ⚠️ 읽은 것과 승인되는 것이 다르다 — 다시 읽게 한다.
            raise HTTPException(
                status_code=409,
                detail=(f"{item['ref']}: 화면에 뜬 조건이 그 사이 바뀌었습니다 — 다시 "
                        f"확인한 뒤 승인하십시오(판이 새로 인증됐거나 코드가 바뀌었습니다)."))
        if not item["approvable"]:
            raise HTTPException(
                status_code=422,
                detail=(f"{item['ref']}: 인증판이 없는 계약키가 있어 승인할 수 없습니다 "
                        f"{item['missing_contract_keys']} — 무엇으로 계산할지 모르는 채 "
                        f"승인하면 그 승인은 아무 판에나 붙습니다."))

    made = []
    for item in items:
        try:
            #: ★★★ 능력마다 **별도 사건**이다.
            made.append(await asyncio.to_thread(
                cea.approve, store, ref=item["ref"], bound=item["binding"],
                actor=p.user_id or "", rationale=req.rationale,
                valid_days=req.valid_days or cea.DEFAULT_VALID_DAYS))
        except cea.ExecutionApprovalError as exc:
            #: ⚠️ 앞엣것은 이미 승인됐다 — **되돌리지 않는다.** 각각이 독립된 승인이고,
            #:   되돌리면 「승인했다가 취소했다」는 사건이 원장에 남는다. 무엇이 됐고
            #:   무엇이 안 됐는지 그대로 알려 준다.
            raise HTTPException(
                status_code=422,
                detail=(f"{item['ref']} 승인에 실패했습니다: {exc} — 앞서 승인된 "
                        f"{[m['ref'] for m in made]} 은(는) 그대로 유효합니다."))
    return {"status": "success",
            "data": {"approved": made, "valid_until": prop["valid_until"]}}


@router.post("/capabilities/{approval_id}/revoke")
async def revoke_capability(approval_id: str, req: RevokeInput,
                            p: Principal = Depends(current_principal)):
    """실행 승인을 철회한다. ⚠️ 철회하면 계산은 **즉시** `BLOCKED` 로 돌아간다."""
    #: ⚠️ 권한은 표가 막는다(위 `_admin_ctx` 머리말 참고).
    if not str(req.reason or "").strip():
        raise HTTPException(status_code=422, detail="철회 사유가 필요합니다.")
    try:
        data = await asyncio.to_thread(cea.revoke, store, approval_id=approval_id,
                                       actor=p.user_id or "", reason=req.reason)
    except cea.ExecutionApprovalError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "data": data}


class ResetInput(BaseModel):
    """초기화 요청. ★ **재확인이 필수**다 — 계획을 보지 않고는 지울 수 없다."""

    instance_id: str
    reason: str
    #: `GET /reset/plan` 이 낸 지문. 없으면 거부한다.
    confirm_fingerprint: str


@router.get("/reset/plan")
async def reset_plan(instance_id: str = "",
                     p: Principal = Depends(current_principal)):
    """[M0-5] **무엇을 지우고 무엇을 남기는가.** 부작용이 없다.

    ★ 화면은 이 목록을 사람에게 보여 주고, 응답의 `plan_fingerprint` 를 그대로
      초기화 요청에 실어 보낸다 — 그것이 **재확인**이다."""
    inst = await asyncio.to_thread(_reset_target, p, instance_id)
    try:
        data = await asyncio.to_thread(demo_reset.plan, store, instance=inst)
    except demo_reset.DemoResetRefused as exc:
        #: ⚠️ **환경이 아니다.** 404 로 감추지 않는다 — 운영 인스턴스를 잘못 고른 것이고,
        #:   그 사실을 알려 주지 않으면 계속 누른다.
        raise HTTPException(status_code=403, detail=str(exc))
    except demo_reset.DemoResetError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"status": "success", "data": data}


@router.post("/reset")
async def reset(req: ResetInput, p: Principal = Depends(current_principal)):
    """[M0-5] 시연을 **처음부터 다시 시작**할 수 있게 되돌린다.

    ⚠️⚠️ 정본과 통제는 유지한다 — 원장·인증판·소유권·온톨로지·계산 승인·조직.
      되돌리는 것은 「이번 시연에서 만든 실행 결과」뿐이다.
    ⚠️ 전체 정본 재생성은 여기 없다. 그것은 별도 운영 명령이다."""
    inst = await asyncio.to_thread(_reset_target, p, req.instance_id)
    if not str(req.reason or "").strip():
        raise HTTPException(status_code=422, detail="초기화 사유가 필요합니다.")
    if not str(req.confirm_fingerprint or "").strip():
        raise HTTPException(
            status_code=422,
            detail="재확인이 필요합니다 — `/reset/plan` 의 `plan_fingerprint` 를 실어 "
                   "보내십시오(무엇을 지우는지 보지 않고는 지울 수 없습니다).")
    try:
        data = await asyncio.to_thread(
            demo_reset.execute, store, instance=inst, actor=p.user_id or "",
            reason=req.reason, confirm_fingerprint=req.confirm_fingerprint)
    except demo_reset.DemoResetRefused as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except demo_reset.DemoResetError as exc:
        #: 계획이 어긋났거나 실행이 실패했다 — 어느 쪽이든 **부분 성공으로 답하지 않는다.**
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "success", "data": data}


@router.get("/readiness")
async def readiness(instance_id: str = "", kit_id: str = dv.KIT_ID,
                    kit_version: str = dv.KIT_VERSION,
                    p: Principal = Depends(current_principal)):
    """[M0-5] **왜 지금 계산이 안 도는가** — 관문별로 답한다.

    ★★★ 셋을 가른다: `READY` · `NOT_YET`(사람이 할 일이 남음) · `FAILED`(확인 못 함).
      그리고 앞 관문이 안 서면 뒤는 **판정하지 않는다**(`UNKNOWN`) — 확인하지 않은
      것을 결론으로 적으면 화면이 없는 일을 시킨다.

    ⚠️ `instance_id` 를 주면 그 인스턴스로 본다. 없으면 인스턴스 관문에서 멈춘다 —
      **아무 인스턴스나 골라 주지 않는다**(고르면 그 답이 어느 인스턴스의 것인지 모른다).
    """
    assert_identified(p, "경로 계산")
    inst = None
    if str(instance_id or "").strip():
        #: 못 보는 인스턴스는 여기서 404 다 — 준비도 응답으로 존재를 알려 주지 않는다.
        inst = await asyncio.to_thread(_instance_or_404, p, instance_id)
    data = await asyncio.to_thread(demo_readiness.evaluate, store,
                                   instance=inst, kit_id=kit_id, kit_version=kit_version)
    return {"status": "success", "data": data}


@router.post("/path")
async def calculate_path(req: PathCalcInput, p: Principal = Depends(current_principal)):
    """경로 하나를 **실제로 계산한다.**

    ★ 막힌 계산도 200 으로 답한다 — 「승인이 없다」는 오류가 아니라 **답**이고, 그
      사유가 화면에 그대로 보여야 다음에 무엇을 해야 하는지 알 수 있다."""
    assert_identified(p, "경로 계산")
    got = await asyncio.to_thread(_calculate, req, p)
    return {"status": "success", "data": got["result"]}


def _work_scenario_or_404(p: Principal, scenario_id: str) -> Dict[str, Any]:
    """보이는 인스턴스에 속한 시나리오만 돌려준다."""
    try:
        scenario = ews.enterprise_work_scenarios.get(str(scenario_id or "").strip())
    except ews.WorkScenarioStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not scenario:
        raise HTTPException(status_code=404, detail="전사 업무 시나리오를 찾을 수 없습니다.")
    inst = _instance_or_404(p, str(scenario["instance_id"]))
    actual = (str(inst["tenant_id"]), str(inst["scope_node_id"]), str(inst["entity_mode"]))
    expected = (str(scenario["tenant_id"]), str(scenario["scope_node_id"]),
                str(scenario["entity_mode"]))
    if actual != expected:
        raise HTTPException(
            status_code=503,
            detail="전사 업무 시나리오의 조직 문맥이 현재 키트 적용 정보와 다릅니다.")
    return scenario


def _assert_active_work_kit_app(instance_id: str, app_id: str) -> None:
    """운영으로 승격된 부서 앱만 전사 시나리오에 결과를 보탠다."""
    if app_id not in ews.APP_SEGMENTS:
        raise HTTPException(
            status_code=422,
            detail="부서 계산 결과를 등록할 수 없는 앱입니다. 전사 앱은 결과를 집계합니다.")
    from core import kit_app_builder as kb
    from core import kit_app_contract as kac
    from core import library_paths
    from core.program_lifecycle import ACTIVE, program_lifecycle

    try:
        contract = kac.approved(store, instance_id, app_id)
    except Exception as exc:  # noqa: BLE001 — 못 읽은 것을 미승인으로 접지 않는다
        raise HTTPException(
            status_code=503, detail="업무 앱의 승인 계약을 확인할 수 없습니다.") from exc
    if not contract:
        raise HTTPException(
            status_code=409, detail="승인된 업무 앱 계약이 있어야 전사 시나리오에 저장할 수 있습니다.")
    release_id = kb.release_id_for(instance_id, app_id)
    if not os.path.exists(library_paths.release_json(release_id)):
        raise HTTPException(status_code=409, detail="이 업무 앱은 아직 생성되지 않았습니다.")
    try:
        state = str(program_lifecycle.get_status(release_id).get("status") or "")
    except Exception as exc:  # noqa: BLE001 — 못 읽은 상태를 비활성으로 접지 않는다
        raise HTTPException(
            status_code=503, detail="업무 앱의 운영 상태를 확인할 수 없습니다.") from exc
    if state != ACTIVE:
        raise HTTPException(
            status_code=409, detail="운영 중인 업무 앱에서만 전사 시나리오 결과를 저장할 수 있습니다.")


@router.post("/work-scenarios")
async def create_work_scenario(req: WorkScenarioCreateInput,
                               p: Principal = Depends(current_principal)):
    """같은 키트 적용본 위에 부서 결과가 모일 전사 시나리오를 만든다."""
    assert_identified(p, "전사 업무 시나리오")
    inst = await asyncio.to_thread(_instance_or_404, p, req.instance_id)
    try:
        scenario = await asyncio.to_thread(
            ews.enterprise_work_scenarios.create,
            tenant_id=str(inst["tenant_id"]), instance_id=str(inst["instance_id"]),
            scope_node_id=str(inst["scope_node_id"]), entity_mode=str(inst["entity_mode"]),
            name=req.name, purpose=req.purpose, actor=p.user_id or "")
    except ews.WorkScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ews.WorkScenarioStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "data": scenario}


@router.get("/work-scenarios")
async def list_work_scenarios(instance_id: str,
                              p: Principal = Depends(current_principal)):
    """현재 사용자가 볼 수 있는 한 키트 적용본의 전사 시나리오 목록."""
    assert_identified(p, "전사 업무 시나리오")
    inst = await asyncio.to_thread(_instance_or_404, p, instance_id)
    try:
        rows = await asyncio.to_thread(
            ews.enterprise_work_scenarios.list_for,
            tenant_id=str(inst["tenant_id"]), instance_id=str(inst["instance_id"]))
    except ews.WorkScenarioStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "data": {"scenarios": rows}}


@router.get("/work-scenarios/{scenario_id}")
async def get_work_scenario(scenario_id: str,
                            p: Principal = Depends(current_principal)):
    assert_identified(p, "전사 업무 시나리오")
    scenario = await asyncio.to_thread(_work_scenario_or_404, p, scenario_id)
    return {"status": "success", "data": scenario}


@router.post("/work-scenarios/{scenario_id}/contributions/{app_id}")
async def record_work_scenario_contribution(
        scenario_id: str, app_id: str, req: PathCalcInput,
        p: Principal = Depends(current_principal)):
    """제품 계산을 다시 실행해 해당 부서 구간만 전사 시나리오에 봉인한다."""
    assert_identified(p, "전사 업무 시나리오 기여")
    scenario = await asyncio.to_thread(_work_scenario_or_404, p, scenario_id)
    if str(req.instance_id) != str(scenario["instance_id"]):
        raise HTTPException(status_code=404, detail="전사 업무 시나리오를 찾을 수 없습니다.")
    await asyncio.to_thread(_assert_active_work_kit_app, req.instance_id, app_id)
    got = await asyncio.to_thread(_calculate, req, p)
    result = got["result"]
    if str(result.get("status") or "") != pc.COMPLETE:
        return {"status": "success", "data": {
            "calculation": result, "contribution": None, "scenario": scenario}}
    try:
        contribution = await asyncio.to_thread(
            ews.enterprise_work_scenarios.record_contribution,
            scenario_id=scenario_id, app_id=app_id, result=result, as_of=req.as_of,
            tenant_id=got["ctx"]["tenant_id"], instance_id=req.instance_id,
            scope_node_id=got["ctx"]["scope_node_id"],
            entity_mode=got["ctx"]["entity_mode"], actor=p.user_id or "")
        updated = await asyncio.to_thread(
            ews.enterprise_work_scenarios.require, scenario_id)
    except ews.WorkScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ews.WorkScenarioStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "data": {
        "calculation": result, "contribution": contribution, "scenario": updated}}


@router.post("/path/diagnostics/reveal")
async def reveal_path_diagnostic(req: DiagnosticInput,
                                 p: Principal = Depends(current_principal)):
    """시스템 관리자가 차단 진단을 명시적으로 펼친다. 열람 자체를 감사한다."""
    assert_identified(p, "경로 계산 내부 진단")
    if req.acknowledgement != "SHOW_INTERNAL_DIAGNOSTIC":
        raise HTTPException(status_code=422, detail="내부 진단 펼침 확인값이 올바르지 않습니다.")
    got = await asyncio.to_thread(_calculate, req, p, include_internal=True)
    diagnostic = _diagnostic(got)
    _record_diagnostic(audit.CALCULATION_DIAGNOSTIC_REVEALED, diagnostic, got, req, p)
    return {"status": "success", "data": diagnostic}


@router.post("/path/diagnostics/copy")
async def copy_path_diagnostic(req: DiagnosticInput,
                               p: Principal = Depends(current_principal)):
    """시스템 관리자가 진단을 복사한다. 서버가 만든 본문만 감사 후 반환한다."""
    assert_identified(p, "경로 계산 내부 진단 복사")
    if req.acknowledgement != "COPY_INTERNAL_DIAGNOSTIC":
        raise HTTPException(status_code=422, detail="내부 진단 복사 확인값이 올바르지 않습니다.")
    got = await asyncio.to_thread(_calculate, req, p, include_internal=True)
    diagnostic = _diagnostic(got)
    _record_diagnostic(audit.CALCULATION_DIAGNOSTIC_COPY_ISSUED, diagnostic, got, req, p)
    return {"status": "success", "data": {
        "diagnostic_fingerprint": diagnostic["diagnostic_fingerprint"],
        "copy_text": json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True),
    }}


def _decision_sections(pkg, base, scenario, baseline, snapshots) -> Dict[str, Any]:
    """계산 패키지를 **안건 섹션 모음**으로 옮긴다.

    ## ⚠️⚠️ 「Decision Package」가 두 개다

    `core.decision_package` 는 **계산 비교 패키지**(title·question·views·evidence)를
    만들고, `core.decision_case` 는 **보고서 섹션 모음**(executive_brief·baseline·
    options·financial_impact…)을 저장한다. 이름이 같고 모양이 다르다.

    ★★★ **계산이 실제로 주는 것만 채운다.** 민감도·되돌릴 수 있는가·규정 리스크는
      계산이 답하지 않는다 — 비워 두면 `_sections` 가 `missing` 으로 표시하고, 검토자는
      「아직 안 채웠다」를 본다. 채워 넣으면 그 순간 **검토된 척**이 된다.

    ⚠️ 대안을 지어내지 않는다. 「기준」과 「시나리오」 둘은 계산이 실제로 비교한 것이다.
    """
    from core import calc_graph as cg

    rows = cg.compare(base, scenario)
    money = [r for r in rows if r.get("unit") == "원"]
    return {
        #: 사람이 먼저 읽는 한 페이지 — 브리핑 문장 그대로.
        "executive_brief": list(pkg.get("briefing") or []),
        "baseline": {
            "baseline_id": str(getattr(baseline, "build_id", "") or ""),
            "baseline_fingerprint": base.baseline_fingerprint,
            "as_of": str(getattr(baseline, "as_of", "") or ""),
            "data_kind": base.data_kind,
            #: ★ 어느 판 위에 섰는지 — 계산이 읽은 그 판이다.
            "snapshot_ids": list(snapshots),
        },
        #: ★ 「기준 유지」와 「시나리오 적용」 — 계산이 **실제로 비교한** 둘이다.
        "options": {
            "compared": rows,
            "assumptions": dict(scenario.assumptions),
        },
        #: ★ 같은 표에서 **금액 행만** 고른 것이다. 새 숫자를 만들지 않는다.
        #: ⚠️ 비워 두면 「손익을 안 봤다」로 읽히는데, 실은 위 표 안에 있다.
        "financial_impact": {"compared": money} if money else None,
        #: ⚠️ 아래는 **계산이 답하지 않는다.** 비워 둔다 — 채우면 검토된 척이 된다.
        #:   민감도 · 되돌릴 수 있는가 · 규정·안전·품질 리스크 · 반대 의견 · 승인 조건
    }


@router.post("/path/decision")
async def calculate_and_decide(req: DecisionInput,
                               p: Principal = Depends(current_principal)):
    """[G5] 계산 결과를 **안건으로** 만든다 — 계산 결속이 근거에 봉인된다.

    ⚠️⚠️ `BLOCKED` 로는 안건을 만들지 않는다. 계산되지 않은 경로 옆에 숫자를 놓으면
      그 숫자가 답으로 읽힌다."""
    assert_identified(p, "경로 계산")
    got = await asyncio.to_thread(_calculate, req, p)
    result = got["result"]
    if result.get("status") != pc.COMPLETE:
        #: ★ 오류가 아니라 **답**이다 — 사유를 그대로 돌려 준다.
        return {"status": "success",
                "data": {"decision": None, "calculation": result}}
    from core import calc_graph as cg
    from core import decision_package as dp

    #: ★ 시뮬레이션 기준선·비교는 **기존 결정 경로와 같은 코드**로 만든다. 여기서 또
    #:   만들면 두 벌이 되고, 두 벌은 반드시 갈라진다.
    baseline = await asyncio.to_thread(bc._baseline, p, req.instance_id, req.snapshot_ids)
    try:
        base = cg.simulate(baseline, req.base_values, {})
        scenario = cg.simulate(baseline, req.base_values, req.scenario_assumptions)
        pkg = dp.build(title=req.title, owner=req.owner, due=req.due,
                       base=base, scenario=scenario, baseline=baseline,
                       path=got["evidence"], calculation=result)
    except cg.CalcError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except dp.DecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    #: ★★★ [M0-4] **저장한다.** 저장하지 않으면 발간할 것이 없고, 「HTML 보고서까지
    #:   완주」가 성립하지 않는다 — 화면에 잠깐 떴다 사라지는 것은 안건이 아니다.
    #: ⚠️ 결정 문장이 없으면 만들지 않는다. 제목으로 대신하지 않는다(같은 이유로
    #:   `decision_case.create` 도 요구한다).
    from core.decision_case import DecisionCaseError, decision_case

    #: ⚠️ **여기서 결정 문장을 검사하지 않는다.** `decision_case.create` 가 이미 막고,
    #:   같은 판정을 두 겹으로 두면 어느 것이 실제로 막는지 알 수 없다 — 변이로 확인했다
    #:   (이 자리를 지워도 실패 0건이었다). 코어의 예외를 아래에서 422 로 옮긴다.
    question = str(req.question or "").strip()
    #: ⚠️ 안건의 조직은 **인스턴스의 조직**이다. 호출자가 적어 보내면 남의 부서 이름으로
    #:   안건을 만들어 넣을 수 있다(`decision_control` 이 같은 자리를 막는다).
    try:
        saved = await asyncio.to_thread(
            decision_case.create, question=question, created_by=p.user_id or "",
            baseline_id=str(getattr(baseline, "build_id", "") or ""),
            scope_id=got["ctx"]["scope_node_id"],
            package=_decision_sections(
                {**pkg.public(), "briefing": dp.briefing_lines(pkg)},
                base, scenario, baseline, req.snapshot_ids),
            evidence=pkg.evidence, due_at=req.due, tenant_id=got["ctx"]["tenant_id"])
    except DecisionCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"status": "success",
            "data": {"decision": {**pkg.public(), "briefing": dp.briefing_lines(pkg),
                                  #: ★ 이 id 로 발간·검토·회의로 이어 간다.
                                  "decision_id": saved["decision_id"]},
                     "calculation": result}}
