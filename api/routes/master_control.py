"""M1 기준정보 저장소 REST API. prefix /api/v1/master.

core/master_data.py 의 동기 CRUD 를 asyncio.to_thread 로 감싸 이벤트 루프 블로킹을 막는다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}. 검증 실패(MasterDataError)는 400,
중복/삭제 충돌은 409 로 매핑한다.
"""
import io
import csv
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List

from core.master_data import master_data, MasterDataError

router = APIRouter(prefix="/api/v1/master")


def _domain_err(e: MasterDataError):
    msg = str(e)
    # 중복/삭제 충돌은 409, 그 외 검증 실패는 400
    if "이미 존재" in msg or "삭제할 수 없" in msg:
        raise HTTPException(status_code=409, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


# ── 타입(온톨로지) ────────────────────────────────────────────────────
class TypeRequest(BaseModel):
    type_id: str
    name_ko: str
    description: Optional[str] = ""
    attr_schema: Optional[dict] = None
    relations: Optional[list] = None


class TypeUpdateRequest(BaseModel):
    name_ko: Optional[str] = None
    description: Optional[str] = None
    attr_schema: Optional[dict] = None
    relations: Optional[list] = None


@router.get("/types")
async def list_types():
    return {"status": "success", "data": await asyncio.to_thread(master_data.list_types)}


@router.post("/types")
async def create_type(req: TypeRequest):
    try:
        data = await asyncio.to_thread(master_data.create_type, req.type_id, req.name_ko,
                                       req.description or "", req.attr_schema, req.relations)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.put("/types/{type_id}")
async def update_type(type_id: str, req: TypeUpdateRequest):
    try:
        data = await asyncio.to_thread(master_data.update_type, type_id, req.name_ko,
                                       req.description, req.attr_schema, req.relations)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.delete("/types/{type_id}")
async def delete_type(type_id: str):
    try:
        await asyncio.to_thread(master_data.delete_type, type_id)
        return {"status": "success"}
    except MasterDataError as e:
        _domain_err(e)


# ── 레코드 ────────────────────────────────────────────────────────────
class RecordRequest(BaseModel):
    master_code: str
    type_id: str
    name: str
    attributes: Optional[dict] = None
    domains: Optional[list] = None
    aliases: Optional[list] = None
    is_core: bool = False
    valid_from: Optional[str] = None


class AliasRequest(BaseModel):
    aliases: List[str]


@router.get("/records")
async def list_records(type_id: Optional[str] = None, q: Optional[str] = None,
                       domain: Optional[str] = None, include_retired: bool = False):
    data = await asyncio.to_thread(master_data.list_records, type_id, q, domain, include_retired)
    return {"status": "success", "data": data}


@router.post("/records")
async def create_record(req: RecordRequest):
    try:
        data = await asyncio.to_thread(
            master_data.create_or_revise_record, req.master_code, req.type_id, req.name,
            req.attributes, req.domains, req.aliases, req.is_core, req.valid_from)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.get("/records/{master_code}")
async def get_record(master_code: str):
    data = await asyncio.to_thread(master_data.get_record, master_code)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 기준정보입니다.")
    return {"status": "success", "data": data}


@router.delete("/records/{master_code}")
async def delete_record(master_code: str):
    ok = await asyncio.to_thread(master_data.retire_record, master_code)
    if not ok:
        raise HTTPException(status_code=404, detail="존재하지 않는(또는 이미 폐기된) 기준정보입니다.")
    return {"status": "success"}


@router.post("/records/{master_code}/aliases")
async def add_aliases(master_code: str, req: AliasRequest):
    try:
        data = await asyncio.to_thread(master_data.add_aliases, master_code, req.aliases)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.delete("/records/{master_code}/aliases/{alias}")
async def remove_alias(master_code: str, alias: str):
    data = await asyncio.to_thread(master_data.remove_alias, master_code, alias)
    return {"status": "success", "data": data}


# ── 일괄 등록 (CSV) ───────────────────────────────────────────────────
@router.post("/import/csv")
async def import_csv(type_id: str = Form(...), file: UploadFile = File(...)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # BOM 허용(엑셀 CSV)
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail="빈 CSV 이거나 헤더만 있습니다.")
    report = await asyncio.to_thread(master_data.import_csv_rows, rows, type_id)
    return {"status": "success", "data": report}


# ── 주입 미리보기 ─────────────────────────────────────────────────────
class PreviewRequest(BaseModel):
    text: str
    domains: Optional[list] = None


@router.post("/grounding/preview")
async def grounding_preview(req: PreviewRequest):
    block = await asyncio.to_thread(master_data.render_grounding, req.text, req.domains or [])
    selected = await asyncio.to_thread(master_data.select_for_injection, req.text, req.domains or [])
    return {"status": "success", "data": {"block": block,
                                          "matched": [r["master_code"] for r in selected]}}
