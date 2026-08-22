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
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
from core import path_calculation_service as svc
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
    """★ 호출자는 **질문**만 준다. 승인·판·기준선은 아래 어디에도 없다."""

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


def _calculate(req: PathCalcInput, p: Principal) -> Dict[str, Any]:
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
    return {"evidence": evidence, "result": result}


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


@router.get("/capabilities")
async def capabilities(instance_id: str = "", data_kind: str = "",
                       entity_mode: str = "", valid_days: int = 0,
                       p: Principal = Depends(current_principal)):
    """[M0-0] 승인 **제안서** — 화면이 보여 줄 정의·단위·부호·범위·유효기간.

    ★★★ **아무것도 승인하지 않는다.** 부작용이 없다. 누르기 전까지 계산은 계속
      `BLOCKED` 로 답한다.
    ★ 서버가 지문을 직접 산출한다 — 호출자가 적어 보낼 수 없다."""
    ctx = _admin_ctx(p, instance_id)
    try:
        data = await asyncio.to_thread(
            cea.proposal, store, instance_id=ctx["instance_id"],
            tenant_id=ctx["tenant_id"],
            entity_mode=entity_mode or cea.DEFAULT_ENTITY_MODE,
            scope_node_id=ctx["scope_node_id"],
            data_kind=data_kind or cea.DEFAULT_DATA_KIND,
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
    if not str(req.rationale or "").strip():
        raise HTTPException(status_code=422, detail="승인 사유가 필요합니다.")
    try:
        prop = await asyncio.to_thread(
            cea.proposal, store, instance_id=ctx["instance_id"],
            tenant_id=ctx["tenant_id"],
            entity_mode=req.entity_mode or cea.DEFAULT_ENTITY_MODE,
            scope_node_id=ctx["scope_node_id"],
            data_kind=req.data_kind or cea.DEFAULT_DATA_KIND,
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
    return {"status": "success",
            "data": {"decision": {**pkg.public(), "briefing": dp.briefing_lines(pkg)},
                     "calculation": result}}
