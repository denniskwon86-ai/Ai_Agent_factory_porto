"""[§12] 외부환경 인텔리전스 REST API. prefix `/api/v1/external`.

## 수집기 (2026-07-30 추가)

종전에는 수집기가 없었고 그 판단은 정당했다 — 승인된 원천이 없는 상태의 수집기는 죽은
코드이거나 값을 지어내는 경로가 된다. 이제 **값을 지어낼 수 없는 구조**로 만들어 붙였다
(`core/external_collector.py`):

  · `/collect/csv`   — 현업이 올린 파일. 승인된 원천에 귀속시켜 vintage·등급과 함께 적재
  · `/collect/{id}`  — 등록된 원천의 `base_url` 만 호출(임의 URL 거부 = §12.4 크롤러 금지)
  · `/collectable`   — **지금 수집할 수 있는 원천이 있는가.** 없으면 없다고 말한다

⚠️ `dry_run` 이 기본이다. 적재 전에 무엇이 빠지는지 먼저 본다.
⚠️ 스케줄러는 없다 — 주기 실행은 운영 스케줄러가 `/collect/{id}` 를 부르면 된다. 프로세스 안에
  타이머를 두면 다중 워커에서 같은 수집이 N배로 돈다.

⚠️ 라우트 순서: 고정 경로는 경로 변수보다 위에 둔다.
"""
import asyncio
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.external_collector import CollectorError, external_collector
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


class CsvCollectRequest(BaseModel):
    source_id: str
    content: str                          # CSV 원문(업로드 파일 텍스트)
    dry_run: bool = True                  # ★ 기본 예행 — 무엇이 빠지는지 먼저 본다
    default_indicator: str = ""


class SourceCollectRequest(BaseModel):
    dry_run: bool = True
    path: str = ""                        # 등록된 base_url 아래 **상대 경로만**
    indicator_map: Optional[Dict[str, str]] = None
    timeout: float = 10.0


@router.get("/readiness")
async def readiness():
    """어떤 외부지표가 **아직 기준 계획에 쓸 수 없는지**와 그 다음 조치."""
    return {"status": "success",
            "data": await asyncio.to_thread(external_intelligence.readiness_report)}


@router.get("/collectable")
async def collectable():
    """**지금 수집할 수 있는 원천이 있는가.** 없으면 없다고 말한다.

    ★ 수집기가 있는데 아무것도 안 들어오는 이유를 사람이 추측하게 두면, 다음 사람은
      "수집기가 고장났다"로 결론짓는다."""
    return {"status": "success",
            "data": await asyncio.to_thread(external_collector.collectable)}


@router.post("/collect/csv")
async def collect_csv(req: CsvCollectRequest, p: Principal = Depends(current_principal)):
    """현업이 올린 CSV 를 **승인된 원천에 귀속시켜** 적재한다.

    ⚠️ `dry_run=true`(기본)면 적재하지 않고 결과만 돌려준다. vintage 없는 행·숫자가 아닌 값은
      건너뛰고 이유를 준다 — 오늘 날짜나 0 으로 채우지 않는다."""
    assert_can_manage_standard(p)
    _actor(p)                             # 누가 적재했는지 없는 데이터는 근거가 없다
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(external_collector.collect_csv, req.content,
                                                req.source_id, req.dry_run,
                                                req.default_indicator)}
    except CollectorError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collect/{source_id}")
async def collect_source(source_id: str, req: SourceCollectRequest,
                         p: Principal = Depends(current_principal)):
    """등록된 원천의 `base_url` 을 호출해 적재한다.

    ⚠️ `path` 는 등록 주소 아래 **상대 경로만** 허용한다 — 임의 URL 수집은 범용 크롤러이고
      §12.4 가 금지한다. RSS·REPORT·WEB 원천은 자동 수집 대상이 아니다(사람이 확인해 CSV)."""
    assert_can_manage_standard(p)
    _actor(p)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(external_collector.collect_source, source_id,
                                                req.dry_run, None, req.path,
                                                req.indicator_map, req.timeout)}
    except CollectorError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
