"""원본 참고문서 등록부 조회·재스캔 API.

원문을 자동으로 전사 RAG에 넣지 않는다. 이 API는 우선 등록 상태를 투명하게 만들고,
M2 권한 모델이 완성된 뒤 승인된 범위만 실제 지식팩에 색인하도록 하는 안전한 진입점이다.
"""
import asyncio
from fastapi import APIRouter

from core.reference_registry import build_registry, load_registry, registry_summary


router = APIRouter(prefix="/api/v1/reference")


@router.get("/summary")
async def get_summary():
    return {"status": "success", "data": await asyncio.to_thread(registry_summary)}


@router.get("/assets")
async def list_assets(pack_id: str = "", approval_status: str = ""):
    registry = await asyncio.to_thread(load_registry)
    items = registry.get("assets", [])
    if pack_id:
        items = [a for a in items if a.get("pack_id") == pack_id]
    if approval_status:
        items = [a for a in items if a.get("approval_status") == approval_status]
    return {"status": "success", "data": items}


@router.post("/scan")
async def scan_reference_documents():
    """원본 폴더의 신규·변경 문서를 등록부에 반영한다. 색인·LLM 호출은 수행하지 않는다."""
    registry = await asyncio.to_thread(build_registry)
    return {"status": "success", "data": registry.get("summary", {})}
