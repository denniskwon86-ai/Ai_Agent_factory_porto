"""[§6.3 / §6.1] 데이터 품질 프로파일 + 계보 REST API. prefix `/api/v1/lineage`.

품질 엔드포인트가 `/api/v1/catalog` 가 아니라 여기 있는 이유: 품질과 계보는 둘 다 "이 데이터를
믿을 수 있나 / 이 값이 바뀌면 무엇이 틀어지나"라는 **같은 질문의 앞뒤**이고, 화면도 함께 쓴다.

LLM 0콜. §6.1 이 품질에 대해 "단순 LLM 평가 금지"라고 못박았고, 계보는 근거 없는 선을 긋지
않는다(추측으로 만든 영향 분석은 "영향 없음"을 잘못 말해 사고를 만든다).
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_can_manage_standard, assert_identified,
                      current_principal)
from core.data_catalog import DataCatalogError, data_catalog
from core.data_lineage import LineageError, data_lineage

router = APIRouter(prefix="/api/v1/lineage")

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "데이터 품질·계보"

# ── [2026-08-07 · 트랙 G] 무방비 라우트 봉합 ─────────────────────────────────
#
# 실측: 쓰기 3개(`POST /quality` · `POST /edges` · `DELETE /edges/{id}` · `POST /derive`)는
# 주체를 받는데 **읽기 4개에는 없었다** — `/quality/{asset}` · `/freshness/{asset}` ·
# `/edges` · `/impact`.
#
# ★ 익명에게 `/impact` 가 열려 있는 것은 목록 유출과 성격이 다르다. 「이 값이 바뀌면 무엇이
#   틀어지나」는 **자산 사이의 연결 지도**이고, 한 번의 조회로 어느 자산이 급소인지 알 수 있다.
#   자산 이름을 몰라도 `/edges` 로 훑어 들어갈 수 있다.
#
# ⬜ 식별된 사용자에 대한 **범위 필터는 아직 없다**(workspace_control 과 같은 상태).
#   봉합은 «익명이 못 본다» 까지이고, 그 이상을 완료로 세지 않는다.


class QualityRequest(BaseModel):
    asset_id: str
    method: str = "declared"
    completeness: Optional[float] = None
    validity: Optional[float] = None
    duplicate_rate: Optional[float] = None
    freshness: Optional[float] = None
    row_count: Optional[int] = None
    evidence_ref: str = ""
    note: str = ""
    measured_at: str = ""


class EdgeRequest(BaseModel):
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    relation_type: str = "feeds"
    confidence: float = 1.0
    evidence_ref: str = ""


# ── 품질 ──────────────────────────────────────────────────────────────────
@router.post("/quality")
async def record_quality(req: QualityRequest, p: Principal = Depends(current_principal)):
    """품질 측정치 기록.

    ⚠️ `method='measured'` 는 `evidence_ref` 없이 기록할 수 없다 — 읽지도 않은 데이터에
      그럴듯한 점수가 붙으면 '품질 확인함'으로 읽히고, 그게 없는 것보다 나쁘다(§6.1)."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            data_catalog.record_quality_profile, req.asset_id, req.method, req.completeness,
            req.validity, req.duplicate_rate, req.freshness, req.row_count, req.evidence_ref,
            p.user_id or "", req.note, req.measured_at)
    except DataCatalogError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}


@router.get("/quality/{asset_id}")
async def quality_history(asset_id: str, limit: int = 20,
                          p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    rows = await asyncio.to_thread(data_catalog.list_quality_profiles, asset_id, limit)
    return {"status": "success", "data": {
        "asset_id": asset_id, "profiles": rows, "latest": rows[0] if rows else None,
        "note": ("측정하지 않은 항목은 0 이 아니라 null 입니다 — 0점과 미측정은 다릅니다."),
    }}


@router.get("/freshness/{asset_id}")
async def freshness(asset_id: str, p: Principal = Depends(current_principal)):
    """최신성 판정(계산, 추정 아님). 판정 근거가 없으면 `unknown` 이고 fresh 로 낙관하지 않는다."""
    assert_identified(p, WHAT)
    try:
        out = await asyncio.to_thread(data_catalog.assess_freshness, asset_id)
    except DataCatalogError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", "data": out}


# ── 계보 ──────────────────────────────────────────────────────────────────
@router.post("/edges")
async def add_edge(req: EdgeRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            data_lineage.add_edge, req.from_type, req.from_id, req.to_type, req.to_id,
            req.relation_type, req.confidence, req.evidence_ref, "user")
    except LineageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}


@router.delete("/edges/{edge_id}")
async def remove_edge(edge_id: str, p: Principal = Depends(current_principal)):
    """소프트 삭제 — 과거 산출물이 왜 그 값을 썼는지 설명하려면 지난 연결이 남아야 한다."""
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(data_lineage.remove_edge, edge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="활성 간선을 찾을 수 없습니다.")
    return {"status": "success", "data": {"edge_id": edge_id, "removed": True}}


@router.post("/derive")
async def derive_edges(p: Principal = Depends(current_principal)):
    """이미 저장된 사실(카탈로그 링크·필드↔기준정보·용어↔기준정보)에서 간선을 도출한다(멱등).

    이름 유사도 같은 추론으로는 잇지 않는다 — 믿을 수 없는 영향 분석은 없는 것보다 위험하다."""
    assert_can_manage_standard(p)
    out = await asyncio.to_thread(data_lineage.derive_edges)
    return {"status": "success", "data": out}


@router.get("/edges")
async def edges_of(node_type: str, node_id: str, direction: str = "both",
                   p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    rows = await asyncio.to_thread(data_lineage.edges_of, node_type, node_id, direction)
    return {"status": "success", "data": rows}


@router.get("/impact")
async def impact(node_type: str, node_id: str, direction: str = "downstream",
                 max_depth: int = 6, p: Principal = Depends(current_principal)):
    """"이 값이 바뀌면 무엇이 틀어지나".

    ⚠️ 응답의 `limitation` 을 무시하지 말 것 — 계보는 **등록된 관계만** 알고, 영향 0건이 곧
      안전을 뜻하지 않는다."""
    assert_identified(p, WHAT)
    try:
        out = await asyncio.to_thread(data_lineage.impact_of, node_type, node_id,
                                      direction, max_depth)
    except LineageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}
