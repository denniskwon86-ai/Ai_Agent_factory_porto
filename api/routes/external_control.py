"""[§12] 외부환경 인텔리전스 REST API. prefix `/api/v1/external`.

⚠️ **수집기·스케줄러는 없다.** 승인된 원천이 없는 상태의 수집기는 죽은 코드이거나 값을
  지어내는 경로가 된다(§12.4 "범용 웹 크롤러를 만들지 않는다"). 지금 이 API 의 실질 산출물은
  `/readiness` — **무엇이 아직 없는지 정확히 아는 것**이다.

⚠️ 라우트 순서: 고정 경로는 경로 변수보다 위에 둔다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.external_intelligence import (ExternalIntelligenceError,
                                        external_intelligence)

router = APIRouter(prefix="/api/v1/external")


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("원천 승인에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오. 승인자 없는 승인은 '누가 이 출처를 신뢰하기로 "
                    "했나'에 답할 수 없습니다."))
    return uid


def _err(e: ExternalIntelligenceError):
    raise HTTPException(status_code=400, detail=str(e))


class SourceRequest(BaseModel):
    name: str
    source_type: str
    base_url: str = ""
    license_type: str = ""
    allowed_usage: str = ""
    refresh_frequency: str = ""
    owner_department: str = ""
    trust_grade: str = "silver"
    note: str = ""


class ObservationRequest(BaseModel):
    indicator_code: str
    observed_at: str
    value: float
    vintage: str
    grade: str = "silver"
    source_id: str = ""
    published_at: str = ""
    unit: str = ""
    source_record_ref: str = ""
    quality_status: str = "RAW"
    note: str = ""


@router.get("/readiness")
async def readiness():
    """어떤 외부지표가 **아직 기준 계획에 쓸 수 없는지**와 그 다음 조치.

    수집기가 없는 지금 이것이 이 모듈의 실질 산출물이다."""
    return {"status": "success",
            "data": await asyncio.to_thread(external_intelligence.readiness_report)}


@router.post("/indicators/seed-from-playbooks")
async def seed_from_playbooks(p: Principal = Depends(current_principal)):
    """플레이북이 선언한 외부지표를 등록부로 옮긴다(멱등).

    지표를 창작하지 않는다 — 두 곳이 어긋나면 어느 쪽이 요구사항인지 알 수 없다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await asyncio.to_thread(external_intelligence.seed_from_playbooks)}


@router.get("/indicators")
async def list_indicators():
    return {"status": "success",
            "data": await asyncio.to_thread(external_intelligence.list_indicators)}


@router.get("/sources")
async def list_sources(enabled_only: bool = False):
    return {"status": "success",
            "data": await asyncio.to_thread(external_intelligence.list_sources, enabled_only)}


@router.post("/sources")
async def register_source(req: SourceRequest, p: Principal = Depends(current_principal)):
    """원천 등록. **등록만으로는 쓰이지 않는다** — 승인해야 활성이다(§12.4)."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            external_intelligence.register_source, req.name, req.source_type, req.base_url,
            req.license_type, req.allowed_usage, req.refresh_frequency, req.owner_department,
            req.trust_grade, req.note)
    except ExternalIntelligenceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/sources/{source_id}/approve")
async def approve_source(source_id: str, p: Principal = Depends(current_principal)):
    """원천 승인 = "이 출처의 값을 회사 계획에 쓴다"는 결정."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(external_intelligence.approve_source, source_id, _actor(p))
    except ExternalIntelligenceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/observations")
async def record_observation(req: ObservationRequest,
                             p: Principal = Depends(current_principal)):
    """관측값 기록. `vintage` 필수(§12.5), 승인된 원천만, 출처보다 높은 등급 불가."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            external_intelligence.record_observation, req.indicator_code, req.observed_at,
            req.value, req.vintage, req.grade, req.source_id, req.published_at, req.unit,
            req.source_record_ref, req.quality_status, req.note)
    except ExternalIntelligenceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.get("/observations/{indicator_code}")
async def list_observations(indicator_code: str, limit: int = 50):
    rows = await asyncio.to_thread(external_intelligence.list_observations,
                                   indicator_code, limit)
    return {"status": "success", "data": rows}


@router.get("/value/{indicator_code}")
async def resolve_value(indicator_code: str, purpose: str = "baseline_plan",
                        as_of: str = "", vintage: str = ""):
    """용도에 맞는 값. **등급이 안 되면 값을 주지 않는다**(§12.2).

    `vintage` 를 주면 그 시점 발표값 — 과거 계획의 재현 경로다."""
    try:
        out = await asyncio.to_thread(external_intelligence.resolve_value, indicator_code,
                                      purpose, as_of, vintage)
    except ExternalIntelligenceError as e:
        _err(e)
    return {"status": "success", "data": out}
