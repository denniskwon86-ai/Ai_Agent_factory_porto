"""[§7.3 / §7.4] Shadow Mode REST API. prefix `/api/v1/shadow`.

§7.3 5단계를 그대로 엔드포인트로 옮겼다: 기준선 설정(`POST /runs`) → 병렬 실행 기록
(`POST /runs/{id}/sides`) → 비교(`GET /runs/{id}/compare`) → 검토(`POST /runs/{id}/review`)
→ 승격(`POST /runs/{id}/promote`).

⚠️ **승격 전 결과는 운영값이 아니다.** 모든 응답의 `note` 가 그 사실을 말한다.
⚠️ 라우트 순서: 고정 경로(`/summary`)는 `/runs/{run_id}` 위에 둔다.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.shadow_mode import ShadowModeError, shadow_mode

router = APIRouter(prefix="/api/v1/shadow")


def _actor(p: Principal) -> str:
    """검토·승격 행위자. 식별이 안 되면 가짜 값을 만들지 않고 방법을 알려준다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("검토·승격에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오. 승인자 없는 승격은 '누가 이 차이를 받아들였나'에 "
                    "답할 수 없습니다."))
    return uid


def _err(e: ShadowModeError):
    raise HTTPException(status_code=400, detail=str(e))


class RunRequest(BaseModel):
    name: str
    candidate_kind: str = "rule"
    enterprise_scope_id: str          # 필수(D-014 개정) — 기본값을 두지 않는다
    evaluation_period: str            # 필수 — 언제의 데이터로 비교했는가
    candidate_ref: str = ""
    baseline_ref: str = ""
    blueprint_id: str = ""
    scenario_ref: str = ""
    input_snapshot_ref: str = ""
    tenant_id: str = "tenant_default"
    entity_mode: str = "REAL"


class SideRequest(BaseModel):
    side: str                          # baseline | candidate
    metrics: Dict[str, Any]            # 값이 null 이면 **미측정**으로 남는다(0 아님)
    input_snapshot: Optional[Any] = None
    input_hash: str = ""
    note: str = ""


class PlanningShadowRequest(BaseModel):
    baseline_scenario_id: str
    candidate_scenario_id: str
    org_id: str
    period: str


class ReviewRequest(BaseModel):
    decision: str                      # approved | rejected
    note: str = ""
    acknowledged_regressions: Optional[List[str]] = None


class PromoteRequest(BaseModel):
    promotion_scope: str               # 필수 — 비우면 제한적 적용이 아니다


# ── 고정 경로 (경로 변수보다 위) ──────────────────────────────────────────
@router.get("/summary")
async def summary(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL"):
    """현황. `incomparable` 은 실패가 아니라 **판정 불가**다(같은 입력이 아니었다)."""
    return {"status": "success",
            "data": await asyncio.to_thread(shadow_mode.summary, scope_node_id,
                                            tenant_id, entity_mode)}


@router.get("/runs")
async def list_runs(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
                    review_status: str = "",
                    p: Principal = Depends(current_principal)):
    """★ [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 내용은 가려진다."""
    from core.enterprise_context.classification import clearance_of_scope
    return {"status": "success",
            "data": await asyncio.to_thread(shadow_mode.list_runs, scope_node_id,
                                            tenant_id, entity_mode, review_status,
                                            clearance_of_scope(p.scope))}


@router.post("/runs")
async def create_run(req: RunRequest, p: Principal = Depends(current_principal)):
    """1단계 — 기준선 설정. 아직 아무것도 실행하지 않은 상태로 만들어진다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            shadow_mode.create_run, req.name, req.candidate_kind, req.enterprise_scope_id,
            req.candidate_ref, req.baseline_ref, req.blueprint_id, req.scenario_ref,
            req.input_snapshot_ref, req.evaluation_period, req.tenant_id, req.entity_mode)
    except ShadowModeError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    data = await asyncio.to_thread(shadow_mode.get, run_id)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 Shadow run 입니다.")
    return {"status": "success", "data": data}


@router.post("/runs/{run_id}/sides")
async def record_side(run_id: str, req: SideRequest,
                      p: Principal = Depends(current_principal)):
    """2단계 — 한쪽 실행 결과 기록.

    ⚠️ `input_snapshot` 또는 `input_hash` 중 하나는 필수다. 같은 입력이었음을 증명할 수 없으면
      비교 결과가 후보의 효과인지 입력 차이인지 구분되지 않는다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(shadow_mode.record_side, run_id, req.side, req.metrics,
                                      req.input_snapshot, req.input_hash, req.note)
    except ShadowModeError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/runs/{run_id}/run-planning-scenario")
async def run_planning_scenario(run_id: str, req: PlanningShadowRequest,
                                p: Principal = Depends(current_principal)):
    """[실행 어댑터] 경영계획 시나리오 두 개를 같은 조직·기간으로 돌려 양쪽을 기록한다.

    지금 실제로 실행 가능한 유일한 후보 종류다 — 범용 후보 실행기는 만들지 않았다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            shadow_mode.run_planning_scenario, run_id, req.baseline_scenario_id,
            req.candidate_scenario_id, req.org_id, req.period)
    except ShadowModeError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.get("/runs/{run_id}/compare")
async def compare(run_id: str):
    """3단계 — 비교. **같은 입력이 아니면 `comparable=false`** 다."""
    try:
        out = await asyncio.to_thread(shadow_mode.compare, run_id)
    except ShadowModeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", "data": out}


@router.post("/runs/{run_id}/review")
async def review(run_id: str, req: ReviewRequest,
                 p: Principal = Depends(current_principal)):
    """4단계 — 검토.

    ⚠️ 악화 항목을 `acknowledged_regressions` 에 명시하지 않으면 승인되지 않는다.
      모르고 승격하는 것과 알고 승격하는 것은 달라야 한다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(shadow_mode.review, run_id, req.decision, _actor(p),
                                      req.note, req.acknowledged_regressions)
    except ShadowModeError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/runs/{run_id}/promote")
async def promote(run_id: str, req: PromoteRequest,
                  p: Principal = Depends(current_principal)):
    """5단계 — 승격. **승인된 범위에서만 제한적 운영 적용**(§7.3).

    ⚠️ `promotion_scope` 를 비우면 제한적 적용이 아니라 전면 적용이 되므로 거절한다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(shadow_mode.promote, run_id, req.promotion_scope,
                                      _actor(p))
    except ShadowModeError as e:
        _err(e)
    return {"status": "success", "data": out}
