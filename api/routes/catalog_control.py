"""[§6.3 / §14 M1] 데이터 카탈로그 REST API. prefix `/api/v1/catalog`.

`core/data_catalog.py` 의 자산·필드·연계 동기화·거버넌스 점검·검색을 노출한다. **LLM 0콜**
(§6.4: "LLM 은 후보 검색·설명에만" — 등록·매칭 확정은 결정론).
응답 봉투는 리포 관례 `{"status": "success", "data": ...}`.

⚠️ 라우트 순서: 고정 경로(`/assets/search` 등)는 반드시 `/assets/{asset_id}` **위에** 둔다.
  아래에 두면 경로 변수가 'search' 를 asset_id 로 잡아 404 가 난다(2026-07-29 실제 사고).
  `tests/test_master_api_routes.py` 가 이를 잠근다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.data_catalog import DataCatalogError, data_catalog

router = APIRouter(prefix="/api/v1/catalog")


def _err(e: DataCatalogError):
    msg = str(e)
    raise HTTPException(status_code=409 if "이미 등록된" in msg else 400, detail=msg)


class AssetRequest(BaseModel):
    name: str
    asset_type: str = "table"
    system_id: str = ""
    entity: str = ""
    location: str = ""
    owner_dept_id: str = ""
    owner_user_id: str = ""
    sensitivity: str = "internal"
    refresh_cadence: str = ""
    description: str = ""
    # [ECM E2] 소유 조직. 비우면 전사 공용이 되고 governance/coverage 에 잡힌다.
    tenant_id: str = "tenant_default"
    enterprise_scope_id: str = ""
    entity_mode: str = "REAL"


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_type: Optional[str] = None
    location: Optional[str] = None
    owner_dept_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    sensitivity: Optional[str] = None
    refresh_cadence: Optional[str] = None
    last_refreshed_at: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class FieldRequest(BaseModel):
    name: str
    logical_type: Optional[str] = None
    term_id: Optional[str] = None
    master_code: Optional[str] = None
    pii_classification: Optional[str] = None
    is_key: Optional[bool] = None
    description: Optional[str] = None


class SyncRequest(BaseModel):
    system_id: str
    owner_dept_id: str = ""
    sensitivity: str = "internal"


# ── 고정 경로 (경로 변수보다 위) ──────────────────────────────────────────
@router.get("/assets/search")
async def search_assets(q: str, limit: int = 20, scope_node_id: str = "",
                        tenant_id: str = "", entity_mode: str = "REAL"):
    """업무 용어로 후보 자산을 찾는다(§6.4 3단계). 결정론적 문자열 매칭.

    점수 근거(`why`)와 거버넌스 준비 여부(`governance_ready`)를 함께 준다 — §6.4 는 최종 매칭
    확정을 **데이터 오너 또는 승인된 규칙**의 몫으로 못박았고, 근거 없이 후보만 던지면 확정할
    수 없다."""
    rows = await asyncio.to_thread(data_catalog.search_assets, q, limit, scope_node_id,
                                   tenant_id, entity_mode)
    return {"status": "success", "data": {"query": q, "results": rows, "total": len(rows)}}


@router.get("/governance/coverage")
async def governance_coverage(tenant_id: str = "", entity_mode: str = "REAL"):
    """[ECM E2] 조직 범위가 지정되지 않아 **모든 조직에 보이는** 자산 현황.

    점진 도입 규칙("범위 미지정 = 전사 공용")을 유지하는 대가로 반드시 함께 있어야 하는
    관측이다 — 이게 없어서 기준정보에서 실제 사고가 났다."""
    from core.enterprise_context.scoping import coverage
    rows = await asyncio.to_thread(data_catalog.list_assets, "", "", "", False, "",
                                   tenant_id, entity_mode)
    return {"status": "success", "data": {
        **coverage(rows, "자산"),
        "unscoped_assets": [r["name"] for r in rows if not r.get("enterprise_scope_id")],
    }}


@router.get("/governance/gaps")
async def governance_gaps(scope_node_id: str = "", tenant_id: str = "",
                          entity_mode: str = "REAL",
                          p: Principal = Depends(current_principal)):
    """카탈로그가 '책임·갱신·민감도'를 담지 못한 지점.

    ⚠️ 자동으로 채우지 않는다 — 소유자를 시스템이 추측해 넣으면 아무도 책임지지 않는 자산이
      책임자가 있는 것처럼 보인다."""
    rows = await asyncio.to_thread(data_catalog.governance_gaps, scope_node_id,
                                   tenant_id, entity_mode)
    return {"status": "success", "data": {
        "gaps": rows, "total": len(rows),
        "high": sum(1 for g in rows if g["severity"] == "high"),
    }}


@router.post("/sync/crosswalk")
async def sync_from_crosswalk(req: SyncRequest,
                              p: Principal = Depends(current_principal)):
    """연계 시스템 스키마 → 카탈로그 자산 **단방향** 임포트(멱등)."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(data_catalog.sync_from_crosswalk, req.system_id,
                                      req.owner_dept_id, req.sensitivity)
    except DataCatalogError as e:
        _err(e)
    return {"status": "success", "data": out}


# ── 자산 ──────────────────────────────────────────────────────────────────
@router.get("/assets")
async def list_assets(owner_dept_id: str = "", sensitivity: str = "", system_id: str = "",
                      include_inactive: bool = False, scope_node_id: str = "",
                      tenant_id: str = "", entity_mode: str = "REAL",
                      p: Principal = Depends(current_principal)):
    """자산 목록. **등급이 낮은 주체에게는 제목만** 주고 내용은 가린다(§6-2 사용자 결정).

    ★ 등급은 주체의 권한에서 파생한다 — 권한과 등급을 두 곳에서 관리하면 어긋난다.
      가려진 행에는 `redacted=True` 와 사유가 실려 나가므로, 화면은 "자료 없음"이 아니라
      "권한 필요"로 표시할 수 있다."""
    from core.enterprise_context.classification import clearance_of_scope
    # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체인가 — 이것도 권한에서 파생한다.
    from core.enterprise_context.scoping import may_drill_down
    rows = await asyncio.to_thread(data_catalog.list_assets, owner_dept_id, sensitivity,
                                   system_id, include_inactive, scope_node_id,
                                   tenant_id, entity_mode, clearance_of_scope(p.scope),
                                   may_drill_down(p.scope))
    return {"status": "success", "data": rows}


@router.post("/assets")
async def create_asset(req: AssetRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            data_catalog.create_asset, req.name, req.asset_type, req.system_id, req.entity,
            req.location, req.owner_dept_id, req.owner_user_id, req.sensitivity,
            req.refresh_cadence, req.description, "user", "",
            req.tenant_id, req.enterprise_scope_id, req.entity_mode)
    except DataCatalogError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    data = await asyncio.to_thread(data_catalog.get_asset, asset_id)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 자산입니다.")
    return {"status": "success", "data": data}


@router.patch("/assets/{asset_id}")
async def update_asset(asset_id: str, req: AssetUpdate,
                       p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(data_catalog.update_asset, asset_id,
                                      **req.model_dump(exclude_none=True))
    except DataCatalogError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.delete("/assets/{asset_id}")
async def retire_asset(asset_id: str, p: Principal = Depends(current_principal)):
    """소프트 삭제 — 어떤 앱·보고서가 이 자산을 썼는지가 계보의 근거라 지우지 않는다."""
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(data_catalog.retire_asset, asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="활성 자산을 찾을 수 없습니다.")
    return {"status": "success", "data": {"asset_id": asset_id, "retired": True}}


@router.put("/assets/{asset_id}/fields")
async def upsert_field(asset_id: str, req: FieldRequest,
                       p: Principal = Depends(current_principal)):
    """필드 등록/수정.

    ⚠️ 연계에서 가져온 필드(`origin='crosswalk'`)의 타입·키 여부는 바꿀 수 없다 — 바꿔도 다음
      동기화에서 되돌아가므로 400 으로 거절하고 이유를 알려준다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            data_catalog.upsert_field, asset_id, req.name, req.logical_type, req.term_id,
            req.master_code, req.pii_classification, req.is_key, req.description)
    except DataCatalogError as e:
        _err(e)
    return {"status": "success", "data": out}
