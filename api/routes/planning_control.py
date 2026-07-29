"""[M4] 경영계획 REST API. prefix `/api/v1/planning`. **LLM 0콜.**

명세서 §17 첫 파일럿(경영계획–실적–시나리오)의 백엔드 계약이다.

## 권한은 M2 자산을 그대로 쓴다

조직 범위 판정은 `core/scope_guard.resolve_effective_scope` 하나를 탄다 —
**클라이언트가 보낸 범위는 요청이지 권한이 아니다.** 거부는 감사로그에 남고 응답은 404 로
은폐한다(§3.3 경계표). 같은 판정을 여기서 다시 구현하면 반드시 어긋난다.

⚠️ 조직별 손익은 새어 나가면 되돌릴 수 없다. 그래서 이 라우터는 M1~M2 에서 만든 격리를
  **처음부터** 타고, 나중에 붙이는 것이 아니다.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal
from core import planning_engine as engine
from core.planning_model import PLAN, PlanningError, planning_store
from core.scope_guard import resolve_effective_scope

router = APIRouter(prefix="/api/v1/planning", tags=["Planning"])


def _err(e: PlanningError):
    raise HTTPException(status_code=400, detail=str(e))


async def _scope(p: Principal, requested: str, resource_id: str = "") -> str:
    """요청 범위를 인증 주체 안에서 교차 검증한다. 거부는 감사 + 404 은폐."""
    eff = await asyncio.to_thread(resolve_effective_scope, p, requested)
    if eff.denied:
        try:
            from core.enterprise_context import audit
            audit.denied_scope("plan_fact", resource_id or requested, actor=eff.actor,
                               actor_scopes=eff.allowed_scopes, requested_scope=requested,
                               detail=eff.reason)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    return eff.scope_node_id


# ── 계정 ──────────────────────────────────────────────────────────────
class AccountRequest(BaseModel):
    account_code: str
    name: str
    category: str
    sign: int = 1
    parent_code: Optional[str] = ""


@router.get("/accounts")
async def list_accounts():
    return {"status": "success", "data": await asyncio.to_thread(planning_store.list_accounts)}


@router.post("/accounts")
async def upsert_account(req: AccountRequest):
    try:
        data = await asyncio.to_thread(planning_store.upsert_account, req.account_code,
                                       req.name, req.category, req.sign, req.parent_code or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 사실(계획·실적·예측) ──────────────────────────────────────────────
class FactRequest(BaseModel):
    org_id: str
    account_code: str
    period: str
    #: ★ 기본값을 두지 않는다 — 두면 호출자가 생각 없이 넣고 '실적처럼 보이는 계획'이 생긴다.
    value_kind: str
    amount: float
    currency: Optional[str] = "KRW"
    scenario_id: Optional[str] = ""
    source_ref: Optional[str] = ""
    owner_organization_id: Optional[str] = ""
    scope_type: Optional[str] = "ORG_PRIVATE"
    classification: Optional[str] = "INTERNAL"


@router.get("/facts")
async def list_facts(org_id: str = "", period: str = "", value_kind: str = "",
                     scenario_id: str = "", scope_node_id: str = "",
                     tenant_id: str = "", entity_mode: str = "REAL",
                     p: Principal = Depends(current_principal)):
    eff = await _scope(p, scope_node_id, org_id)
    data = await asyncio.to_thread(planning_store.list_facts, org_id, period, value_kind,
                                   scenario_id, eff, tenant_id, entity_mode)
    return {"status": "success", "data": data,
            "permission": {"scope": eff or "(범위 필터 없음)"}}


@router.post("/facts")
async def put_fact(req: FactRequest, p: Principal = Depends(current_principal)):
    await _scope(p, req.owner_organization_id or req.org_id, req.account_code)
    try:
        data = await asyncio.to_thread(
            planning_store.put_fact, req.org_id, req.account_code, req.period,
            req.value_kind, req.amount, req.currency or "KRW", req.scenario_id or "",
            req.source_ref or "", req.owner_organization_id or "",
            req.scope_type or "ORG_PRIVATE", req.classification or "INTERNAL")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 시나리오 ──────────────────────────────────────────────────────────
class ScenarioRequest(BaseModel):
    scenario_id: str
    name: str
    org_id: str = ""
    baseline_kind: str = PLAN
    owner: Optional[str] = ""


class AssumptionRequest(BaseModel):
    target_code: str
    operator: str            # pct | delta | set
    value: float
    target_kind: str = "account"
    unit: Optional[str] = ""
    #: 근거 없는 가정은 재현이 아니라 창작이다(§11.3).
    rationale: str = ""


@router.get("/scenarios")
async def list_scenarios(org_id: str = ""):
    def _q():
        conn = planning_store._connect()
        try:
            sql = "SELECT * FROM scenarios" + (" WHERE org_id=?" if org_id else "")
            return [dict(r) for r in conn.execute(sql, (org_id,) if org_id else ())]
        finally:
            conn.close()
    return {"status": "success", "data": await asyncio.to_thread(_q)}


@router.post("/scenarios")
async def create_scenario(req: ScenarioRequest, p: Principal = Depends(current_principal)):
    await _scope(p, req.org_id, req.scenario_id)

    def _ins():
        from datetime import datetime, timezone
        conn = planning_store._connect()
        try:
            if conn.execute("SELECT 1 FROM scenarios WHERE scenario_id=?",
                            (req.scenario_id,)).fetchone():
                raise PlanningError(f"이미 존재하는 시나리오입니다: {req.scenario_id}")
            conn.execute(
                "INSERT INTO scenarios(scenario_id,name,org_id,baseline_kind,owner,created_at,"
                "owner_organization_id) VALUES(?,?,?,?,?,?,?)",
                (req.scenario_id, req.name, req.org_id, req.baseline_kind, req.owner or "",
                 datetime.now(timezone.utc).isoformat(timespec="seconds"), req.org_id))
            conn.commit()
            return dict(conn.execute("SELECT * FROM scenarios WHERE scenario_id=?",
                                     (req.scenario_id,)).fetchone())
        finally:
            conn.close()
    try:
        return {"status": "success", "data": await asyncio.to_thread(_ins)}
    except PlanningError as e:
        _err(e)


@router.post("/scenarios/{scenario_id}/assumptions")
async def add_assumption(scenario_id: str, req: AssumptionRequest):
    if (req.operator or "").lower() not in ("pct", "delta", "set"):
        raise HTTPException(status_code=400, detail="operator 는 pct | delta | set 이어야 합니다.")
    if not (req.rationale or "").strip():
        # 근거를 강제하는 이유: 나중에 "왜 10% 로 뒀는가"에 답할 수 없으면 그 시나리오는
        # 재현은 되지만 **설명되지 않는다**. 경영 보고에서는 둘 다 필요하다.
        raise HTTPException(status_code=400,
                            detail="rationale(가정의 근거)은 필수입니다 — 근거 없는 가정은 재현이 아니라 창작입니다.")

    def _ins():
        import uuid
        from datetime import datetime, timezone
        conn = planning_store._connect()
        try:
            if not conn.execute("SELECT 1 FROM scenarios WHERE scenario_id=?",
                                (scenario_id,)).fetchone():
                raise PlanningError(f"존재하지 않는 시나리오입니다: {scenario_id}")
            aid = uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                "target_code,operator,value,unit,rationale,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (aid, scenario_id, req.target_kind, req.target_code, req.operator.lower(),
                 req.value, req.unit or "", req.rationale,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
            return {"assumption_id": aid, "scenario_id": scenario_id}
        finally:
            conn.close()
    try:
        return {"status": "success", "data": await asyncio.to_thread(_ins)}
    except PlanningError as e:
        _err(e)


class RunRequest(BaseModel):
    org_id: str
    period: str
    baseline_kind: str = PLAN
    #: 기본 False — 탐색적 실행이 기록을 오염시키면 안 된다.
    persist: bool = False


@router.post("/scenarios/{scenario_id}/run")
async def run_scenario(scenario_id: str, req: RunRequest,
                       p: Principal = Depends(current_principal)):
    await _scope(p, req.org_id, scenario_id)
    try:
        data = await asyncio.to_thread(engine.run_scenario, scenario_id, req.org_id,
                                       req.period, req.baseline_kind, req.persist)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


class CompareRequest(BaseModel):
    scenario_ids: List[str]
    org_id: str
    period: str
    baseline_kind: str = PLAN


@router.post("/scenarios/compare")
async def compare(req: CompareRequest, p: Principal = Depends(current_principal)):
    """여러 시나리오를 **동일 기준선에서** 비교(§17.3 파일럿 성공 기준).

    응답의 `same_baseline` 이 false 면 그 비교는 무효다 — 화면은 그것을 숨기지 말 것."""
    await _scope(p, req.org_id, ",".join(req.scenario_ids))
    if not req.scenario_ids:
        raise HTTPException(status_code=400, detail="비교할 시나리오가 없습니다.")
    try:
        data = await asyncio.to_thread(engine.compare_scenarios, req.scenario_ids,
                                       req.org_id, req.period, req.baseline_kind)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 차이 분석 ─────────────────────────────────────────────────────────
@router.get("/variance")
async def variance(org_id: str, period: str, p: Principal = Depends(current_principal)):
    """계획 대비 실적 차이(§17.2 기능 4).

    ⚠️ 한쪽이 비어 있으면 `comparable=false` 로 돌려주고 **차이를 계산하지 않는다.**
      없는 값을 0 으로 두면 '미달'로 잘못 읽힌다."""
    await _scope(p, org_id, org_id)
    data = await asyncio.to_thread(engine.variance, org_id, period)
    return {"status": "success", "data": data}
