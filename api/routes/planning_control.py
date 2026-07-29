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
from core.planning_model import PLAN, VALUE_KINDS, PlanningError, planning_store
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
    #: 분석 차원. 빈 값 = 그 차원으로 나누지 않은 **합계** 행이다(상세 행과 섞이면 이중 계상).
    product_code: Optional[str] = ""
    cost_center: Optional[str] = ""


@router.get("/facts")
async def list_facts(org_id: str = "", period: str = "", value_kind: str = "",
                     scenario_id: str = "", scope_node_id: str = "",
                     tenant_id: str = "", entity_mode: str = "REAL",
                     product_code: str = "", cost_center: str = "",
                     p: Principal = Depends(current_principal)):
    eff = await _scope(p, scope_node_id, org_id)
    data = await asyncio.to_thread(planning_store.list_facts, org_id, period, value_kind,
                                   scenario_id, eff, tenant_id, entity_mode,
                                   product_code, cost_center)
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
            req.scope_type or "ORG_PRIVATE", req.classification or "INTERNAL",
            "tenant_default", "REAL", req.product_code or "", req.cost_center or "")
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


# ── 제출·승인 흐름 (§17.2 기능 3) ─────────────────────────────────────
# ⚠️ 승인은 상태 플래그가 아니다 — 승인 시점의 값 지문을 함께 박고, 조회 때 무결성을
#   다시 확인한다. "승인됐다"와 "승인받은 그 값 그대로다"는 다른 질문이다.
from core import planning_approval as approval


class SubmitRequest(BaseModel):
    org_id: str
    period: str
    value_kind: str = PLAN
    note: Optional[str] = ""


class ApproveRequest(BaseModel):
    #: 자기 승인은 통제가 아니라 형식이라 기본 차단. 1인 부서면 명시적으로 연다(감사에 남는다).
    allow_self_approval: bool = False


class RejectRequest(BaseModel):
    #: 사유 없는 반려는 제출자가 무엇을 고쳐야 할지 모른다.
    reason: str


@router.get("/submissions")
async def list_submissions(org_id: str = "", period: str = "", status: str = ""):
    return {"status": "success",
            "data": await asyncio.to_thread(approval.list_submissions, org_id, period, status)}


@router.get("/submissions/current")
async def current_approved(org_id: str, period: str, value_kind: str = PLAN):
    """현재 유효한 승인본 + **무결성 판정**. 없으면 data=null(빈 객체로 위장하지 않는다)."""
    data = await asyncio.to_thread(approval.current_approved, org_id, period, value_kind)
    return {"status": "success", "data": data}


@router.post("/submissions")
async def submit_plan(req: SubmitRequest, p: Principal = Depends(current_principal)):
    await _scope(p, req.org_id, req.org_id)
    if not p.user_id:
        raise HTTPException(status_code=401, detail="제출자 식별 정보가 없습니다.")
    try:
        data = await asyncio.to_thread(approval.submit, req.org_id, req.period,
                                       p.user_id, req.value_kind, req.note or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/submissions/{submission_id}/approve")
async def approve_plan(submission_id: str, req: ApproveRequest = None,
                       p: Principal = Depends(current_principal)):
    if not p.user_id:
        raise HTTPException(status_code=401, detail="승인자 식별 정보가 없습니다 — "
                                                   "익명 승인은 받지 않습니다.")
    try:
        data = await asyncio.to_thread(approval.approve, submission_id, p.user_id,
                                       bool(req.allow_self_approval) if req else False)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/submissions/{submission_id}/reject")
async def reject_plan(submission_id: str, req: RejectRequest,
                      p: Principal = Depends(current_principal)):
    if not p.user_id:
        raise HTTPException(status_code=401, detail="반려자 식별 정보가 없습니다.")
    try:
        data = await asyncio.to_thread(approval.reject, submission_id, p.user_id, req.reason)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/submissions/{submission_id}/integrity")
async def check_integrity(submission_id: str):
    """★ 승인 후 값이 바뀌었는지 — 상태만 보면 알 수 없다."""
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(approval.verify_integrity, submission_id)}
    except PlanningError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 계획 동인 (§17.2 기능 5) ──────────────────────────────────────────
# ⚠️ 파급 계수는 **사람이 등록하고 근거를 남긴다.** LLM·자동 회귀로 만들면 그럴듯한 가짜
#   인과가 생기고, 그것이 경영 보고서에 "환율 때문에 원가가 이만큼 오릅니다"로 인쇄된다.
from core import planning_drivers as drivers


class DriverRequest(BaseModel):
    driver_code: str
    name: str
    unit: Optional[str] = ""
    category: Optional[str] = ""
    #: §12 외부 지표 연결. **표시일 뿐 자동 주입이 아니다**(등급 정책은 외부 인텔리전스가 강제).
    external_code: Optional[str] = ""
    note: Optional[str] = ""


class ImpactRequest(BaseModel):
    account_code: str
    #: 동인이 1% 변할 때 계정이 몇 % 변하는가.
    elasticity: float
    rationale: str        # 필수 — 근거 없는 계수는 창작이다
    source: str           # 필수 — 실적회귀·업계자료·전문가판단 중 무엇인가


@router.get("/drivers")
async def list_drivers():
    return {"status": "success", "data": await asyncio.to_thread(drivers.list_drivers)}


@router.post("/drivers")
async def register_driver(req: DriverRequest):
    try:
        data = await asyncio.to_thread(drivers.register_driver, req.driver_code, req.name,
                                       req.unit or "", req.category or "",
                                       req.external_code or "", req.note or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/drivers/{driver_code}/impacts")
async def list_impacts(driver_code: str):
    return {"status": "success",
            "data": await asyncio.to_thread(drivers.impacts_of, driver_code)}


@router.post("/drivers/{driver_code}/impacts")
async def add_impact(driver_code: str, req: ImpactRequest,
                     p: Principal = Depends(current_principal)):
    """파급 계수 등록. 승인자는 인증 주체로 기록된다(익명이면 미승인 상태로 남는다)."""
    try:
        data = await asyncio.to_thread(drivers.add_impact, driver_code, req.account_code,
                                       req.elasticity, req.rationale, req.source, p.user_id)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/drivers/{driver_code}/preview")
async def preview_driver(driver_code: str, pct_change: float):
    """동인 가정을 계정 단위로 **펼쳐서 미리 본다** — 시나리오에 넣기 전에 파급을 확인한다.

    `warnings` 가 비어 있지 않으면 매핑이 없거나 미승인 계수가 섞여 있다는 뜻이다."""
    rows, warns = await asyncio.to_thread(drivers.expand_driver_assumption,
                                          driver_code, pct_change)
    return {"status": "success", "data": {"expanded": rows, "warnings": warns}}


@router.get("/cash-flow")
async def cash_flow(org_id: str, period: str, value_kind: str = PLAN,
                    p: Principal = Depends(current_principal)):
    """현금흐름(간접법, §17.2 기능 6).

    ⚠️ `computable=false` 면 **계산하지 않은 것**이다(0 이 아니다). `missing` 에 무엇이
      없는지 이름이 있다. 감가상각·운전자본·CAPEX 를 0 으로 채우면 '영업현금흐름 = 순이익'이
      되어 현금이 충분한 것처럼 보인다 — 화면은 이 구분을 반드시 표시할 것."""
    await _scope(p, org_id, org_id)
    data = await asyncio.to_thread(engine.cash_flow_for, org_id, period, value_kind)
    return {"status": "success", "data": data}


# ── 실적·계획 파일 등록 (§17.2 기능 2) ────────────────────────────────
# ⚠️ 파일 등록은 **조용히 틀리기 가장 쉬운 경로**다. 엑셀 오타 하나가 그대로 경영 보고서에
#   들어가고 아무 오류도 나지 않는다. 그래서 먼저 검증하고 나중에 저장하며,
#   한 행이라도 문제가 있으면 **전부 거부**한다(부분 저장 금지).
from fastapi import File, UploadFile

from core import planning_import as importer


class ImportRowsRequest(BaseModel):
    rows: List[dict]
    #: 기본 False — 무엇이 들어갈지 먼저 보여준다.
    commit: bool = False
    source_ref: Optional[str] = ""


@router.post("/import/rows")
async def import_rows(req: ImportRowsRequest, p: Principal = Depends(current_principal)):
    """행 목록 등록. `commit=false`(기본)면 **검증만** 하고 저장하지 않는다."""
    try:
        data = await asyncio.to_thread(importer.import_rows, req.rows, req.commit,
                                       req.source_ref or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...), commit: bool = False,
                     p: Principal = Depends(current_principal)):
    """CSV 등록. 인코딩은 UTF-8(BOM 허용) → CP949 순으로 시도한다(국내 엑셀 관례)."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    try:
        rows = await asyncio.to_thread(importer.parse_csv, text)
        data = await asyncio.to_thread(importer.import_rows, rows, commit, file.filename or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/import/template")
async def import_template():
    """등록 양식 안내 — 열 이름을 추측하게 두면 조용히 틀린 열을 읽는다."""
    return {"status": "success", "data": {
        "required_columns": list(importer.REQUIRED_COLUMNS),
        "optional_columns": list(importer.OPTIONAL_COLUMNS),
        "value_kinds": list(VALUE_KINDS),
        "example_csv": ("org_id,account_code,period,value_kind,amount,source_ref\n"
                        "MNM_BATTERY,4000,2026,ACTUAL,\"1,100\",2026결산.xlsx\n"),
        "notes": [
            "한 행이라도 문제가 있으면 아무것도 저장하지 않습니다(부분 저장 없음).",
            "계정은 먼저 등록해야 합니다 — 자동 생성하면 오타가 새 계정이 됩니다.",
            "value_kind 는 비울 수 없습니다(실제·계획·예측·시나리오를 섞지 않습니다).",
            "천단위 구분(1,000)과 회계 음수 표기((600))를 지원합니다.",
        ],
    }}


# ── Backtest (§17.3 파일럿 성공 기준 "과거 기간 재현") ────────────────
# ⚠️ Backtest 의 고전적 실패는 **결과를 알고 나서 만든 가정으로 과거를 맞히는 것**이다.
#   오차가 0 에 가깝게 나오고 사람들은 모델을 신뢰하게 된다 — 실제 미래엔 빗나간다.
#   그래서 응답의 `lookahead_risk` 와 `warnings` 를 화면이 반드시 함께 보여줘야 한다.
from core import planning_backtest as backtest


class BacktestSeriesRequest(BaseModel):
    org_id: str
    periods: List[str]


@router.get("/backtest/plan")
async def backtest_plan(org_id: str, period: str, p: Principal = Depends(current_principal)):
    """계획 vs 실적 오차. `measurable=false` 면 **재지 않은 것**이다(오차 0 이 아니다)."""
    await _scope(p, org_id, org_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_plan, org_id, period)}


@router.get("/backtest/scenario")
async def backtest_scenario(scenario_id: str, org_id: str, period: str,
                            baseline_kind: str = PLAN,
                            p: Principal = Depends(current_principal)):
    """시나리오를 과거 기간에 돌려 실적과 비교한다.

    `lookahead_risk=true` 면 가정이 대상 기간 이후에 작성된 것이다 —
    그 오차는 **실제 예측력이 아니다.**"""
    await _scope(p, org_id, scenario_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_scenario, scenario_id,
                                            org_id, period, baseline_kind)}


@router.post("/backtest/series")
async def backtest_series(req: BacktestSeriesRequest,
                          p: Principal = Depends(current_principal)):
    """여러 기간 연속 검증 — **한 해만 맞힌 것은 우연일 수 있다.**

    `systematic_bias=true` 면 편향이 여러 기간에 걸쳐 같은 방향이라는 뜻이고,
    그것은 우연이 아니라 모델의 습관이다(MAPE 가 작아도 그대로 쓰면 안 된다)."""
    await _scope(p, req.org_id, req.org_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_series, req.org_id, req.periods)}


@router.get("/rollup-check")
async def rollup_check(org_id: str, period: str, value_kind: str = PLAN,
                       p: Principal = Depends(current_principal)):
    """★ 합계 행과 상세 행이 섞였는지 점검한다(제품·원가센터 차원의 필연적 함정).

    둘이 함께 있으면 단순 합산 시 **이중 계상**이다. 어느 쪽이 정본인지는 데이터를 넣은
    사람만 알기 때문에 자동으로 고르지 않고 **표시만** 한다."""
    await _scope(p, org_id, org_id)
    facts = await asyncio.to_thread(planning_store.list_facts, org_id, period, value_kind)
    return {"status": "success", "data": await asyncio.to_thread(engine.rollup_conflicts, facts)}


@router.get("/drivers/{driver_code}/external")
async def driver_external_value(driver_code: str, purpose: str = "scenario",
                                baseline_value: Optional[float] = None,
                                as_of: str = "", vintage: str = ""):
    """연결된 외부 지표의 **실제 관측값**으로 동인 변화율을 산출한다(§12.7·§12.8).

    ⚠️ 등급 정책(§12.2)은 외부 인텔리전스가 강제한다 — 여기서 다시 판정하지 않고 **물고 온다.**
      `usable=false` 면 값을 쓸 수 없다는 뜻이고, **0% 로 대체하지 않는다**
      (0% 는 '변화 없음'이라는 주장이고 '모른다'와 다르다).
    `vintage` 를 주면 그 시점 발표값으로 계산한다 — 과거 계획의 재현 경로다."""
    data = await asyncio.to_thread(drivers.resolve_external_change, driver_code,
                                   purpose, baseline_value, as_of, vintage)
    return {"status": "success", "data": data}
