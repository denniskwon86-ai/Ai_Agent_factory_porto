import asyncio
import re
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from core.knowledge_base import knowledge_base, extract_text

router = APIRouter(prefix="/api/v1/knowledge")

# pack_id 는 디스크 경로/Chroma 컬렉션명으로 쓰이므로 단일 세그먼트만 허용(경로 이탈 차단)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# 파일명은 확장자 포함 안전 문자만(경로 구분자·상위 이동 차단)
_FNAME_RE = re.compile(r"^[\w가-힣 .()\[\]-]{1,128}$")

INDEXABLE_EXTS = (".pdf", ".txt", ".md", ".csv", ".json")


def _safe_pack_id(v: str) -> str:
    if not _ID_RE.match(v or ""):
        raise HTTPException(status_code=400, detail="잘못된 pack_id 형식입니다 (영문/숫자/_/- 만 허용).")
    return v


class PackCreateRequest(BaseModel):
    pack_id: str
    name: str = ""
    description: str = ""


class PackSearchRequest(BaseModel):
    query: str
    n_results: int = 5


@router.get("/packs")
async def list_packs():
    return {"status": "success", "data": knowledge_base.list_packs()}


@router.post("/packs")
async def create_pack(req: PackCreateRequest):
    _safe_pack_id(req.pack_id)
    try:
        # 임베딩 모델 워밍업이 포함될 수 있어(첫 호출 수 초) 스레드로
        manifest = await asyncio.to_thread(knowledge_base.create_pack, req.pack_id, req.name, req.description)
        return {"status": "success", "data": manifest}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/packs/{pack_id}")
async def get_pack(pack_id: str):
    _safe_pack_id(pack_id)
    manifest = knowledge_base.get_pack(pack_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    return {"status": "success", "data": manifest}


@router.delete("/packs/{pack_id}")
async def delete_pack(pack_id: str):
    _safe_pack_id(pack_id)
    ok = await asyncio.to_thread(knowledge_base.delete_pack, pack_id)
    if not ok:
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    return {"status": "success"}


@router.post("/packs/{pack_id}/documents")
async def upload_document(pack_id: str, file: UploadFile = File(...)):
    """참고자료 업로드 → 텍스트 추출 → 청킹·인덱싱. 동일 파일명은 교체된다."""
    _safe_pack_id(pack_id)
    if not knowledge_base.get_pack(pack_id):
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    fname = (file.filename or "").strip()
    if not _FNAME_RE.match(fname):
        raise HTTPException(status_code=400, detail="파일명에 허용되지 않는 문자가 있습니다.")
    if not fname.lower().endswith(INDEXABLE_EXTS):
        raise HTTPException(status_code=400, detail=f"지원 형식: {', '.join(INDEXABLE_EXTS)}")

    raw = await file.read()
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다(30MB 제한).")

    def _ingest():
        text = extract_text(fname, raw)
        return knowledge_base.add_document(pack_id, fname, text, source="upload", raw=raw)

    try:
        # 추출+임베딩은 CPU 집약 - 이벤트 루프 동결 방지 위해 스레드로
        chunks = await asyncio.to_thread(_ingest)
    except ValueError as e:
        # add_document/extract_text 의 도메인 오류(이미 한국어 메시지)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # 예기치 못한 라이브러리 오류도 한국어로 안내(원인은 디버깅용으로 덧붙임)
        print(f"⚠️ [Knowledge] 문서 등록 실패({fname}): {e}")
        raise HTTPException(status_code=500, detail=f"문서 등록 중 오류가 발생했습니다. 원인: {e}")
    return {"status": "success", "filename": fname, "chunks": chunks}


@router.delete("/packs/{pack_id}/documents/{filename}")
async def delete_document(pack_id: str, filename: str):
    _safe_pack_id(pack_id)
    if not _FNAME_RE.match(filename or ""):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    ok = await asyncio.to_thread(knowledge_base.remove_document, pack_id, filename)
    if not ok:
        raise HTTPException(status_code=404, detail="지식팩 또는 문서를 찾을 수 없습니다.")
    return {"status": "success"}


@router.post("/packs/{pack_id}/search")
async def search_pack(pack_id: str, req: PackSearchRequest):
    """검색 품질 확인용(등록 자료가 질의에 어떻게 검색되는지 UI에서 테스트)."""
    _safe_pack_id(pack_id)
    if not knowledge_base.get_pack(pack_id):
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    hits = await asyncio.to_thread(knowledge_base.search_packs, [pack_id], req.query, req.n_results)
    return {"status": "success", "data": hits}
