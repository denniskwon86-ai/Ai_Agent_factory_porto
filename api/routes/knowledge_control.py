import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from api.deps import (Principal, assert_can_manage_standard, current_principal,
                      scope_allows_owner, viewer_visible_scopes, visibility_block_reason)
from core.knowledge_base import knowledge_base, extract_text

router = APIRouter(prefix="/api/v1/knowledge")

# pack_id 는 디스크 경로/Chroma 컬렉션명으로 쓰이므로 단일 세그먼트만 허용(경로 이탈 차단)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# 파일명은 확장자 포함 안전 문자만(경로 구분자·상위 이동 차단)
_FNAME_RE = re.compile(r"^[\w가-힣 .()\[\]-]{1,128}$")

# DOCX/PPTX는 core.knowledge_base의 Office Open XML 추출기로 본문·표·슬라이드를 읽는다.
# 구형 PPT는 원본 보존 뒤 안전한 변환을 요구한다(바이너리 문자열을 근거로 색인하지 않음).
INDEXABLE_EXTS = (".pdf", ".docx", ".pptx", ".ppt", ".txt", ".md", ".csv", ".json")


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


class PackScopeRequest(BaseModel):
    owner_org_id: str
    dry_run: bool = True          # 소급 부여는 되돌리기 번거롭다 — 예행이 기본
    only_missing: bool = True     # 이미 범위가 있는 청크는 건드리지 않는다
    classification: str = ""


@router.get("/packs")
async def list_packs(p: Principal = Depends(current_principal)):
    """지식팩 목록. **권한 강제가 켜져 있으면 볼 자격이 없는 요청자에게는 빈 목록을 준다.**

    ★ 왜 이유를 함께 주는가 — 빈 목록만 주면 화면은 "등록된 지식팩이 없습니다"라고 말하고,
      사용자는 자료가 없다고 믿는다(실측: 익명 상태에서 실제로 그 문구가 떴다).
      없는 것과 안 보이는 것은 **정반대의 사실**이므로 화면이 구분해 말할 수 있어야 한다."""
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    packs = knowledge_base.list_packs()
    nodes = viewer_visible_scopes(p)
    if nodes is not None:
        shown = [k for k in packs if scope_allows_owner(nodes, k.get("owner_org_id", ""))]
        if len(shown) < len(packs):
            # 몇 건이 가려졌는지 말한다 — 숫자가 없으면 "이게 전부인가"를 판단할 수 없다.
            return {"status": "success", "data": shown,
                    "hidden_count": len(packs) - len(shown),
                    "blocked_reason": (f"소속 조직 범위 밖의 지식팩 "
                                       f"{len(packs) - len(shown)}건은 표시되지 않습니다."
                                       if not shown else "")}
        return {"status": "success", "data": shown}
    return {"status": "success", "data": packs}


@router.get("/scope-report")
async def scope_report(p: Principal = Depends(current_principal)):
    """팩별로 **조직 범위가 심긴 청크가 몇 개인지.**

    ★ 이 숫자를 모르면 `KB_SCOPE_ENFORCE` 를 켤 수 없다 — 켜는 순간 범위 미기재 청크가 전부
      검색에서 제외되므로(fail-closed), "켜면 무엇이 사라지는가"를 먼저 알아야 한다."""
    assert_can_manage_standard(p)      # 팩별 노출 현황은 통제 정보다 — 관리자에게만
    return {"status": "success",
            "data": await asyncio.to_thread(knowledge_base.pack_scope_report)}


@router.post("/packs/{pack_id}/scope")
async def set_pack_scope(pack_id: str, req: PackScopeRequest,
                         p: Principal = Depends(current_principal)):
    """기존 청크에 소유 조직을 소급 부여한다(재색인 없이 메타데이터만).

    ⚠️ 소유 조직을 추측하지 않는다 — 잘못 찍으면 팩의 모든 청크가 엉뚱한 조직에 열린다."""
    assert_can_manage_standard(p)
    _safe_pack_id(pack_id)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(knowledge_base.set_pack_scope, pack_id,
                                                req.owner_org_id, req.dry_run,
                                                req.only_missing, req.classification)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/packs")
async def create_pack(req: PackCreateRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    _safe_pack_id(req.pack_id)
    try:
        # 임베딩 모델 워밍업이 포함될 수 있어(첫 호출 수 초) 스레드로
        manifest = await asyncio.to_thread(knowledge_base.create_pack, req.pack_id, req.name, req.description)
        return {"status": "success", "data": manifest}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/packs/{pack_id}")
async def get_pack(pack_id: str, p: Principal = Depends(current_principal)):
    _safe_pack_id(pack_id)
    reason = visibility_block_reason(p)
    if reason:
        # 403 으로 "있지만 못 본다"를 알린다 — 404 로 감추면 관리자도 원인을 찾을 수 없다.
        raise HTTPException(status_code=403, detail=reason)
    manifest = knowledge_base.get_pack(pack_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    return {"status": "success", "data": manifest}


@router.delete("/packs/{pack_id}")
async def delete_pack(pack_id: str, p: Principal = Depends(current_principal)):
    # ⚠️ [2026-07-31] 여기에 권한이 없었다 — **익명 요청으로 전사 지식팩을 지울 수 있었다.**
    #   읽기 구멍은 자료가 새는 것이고 쓰기 구멍은 자료가 사라지는 것이다. 후자가 더 무겁다.
    assert_can_manage_standard(p)
    _safe_pack_id(pack_id)
    ok = await asyncio.to_thread(knowledge_base.delete_pack, pack_id)
    if not ok:
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    return {"status": "success"}


@router.post("/packs/{pack_id}/documents")
async def upload_document(pack_id: str, file: UploadFile = File(...),
                          p: Principal = Depends(current_principal)):
    """참고자료 업로드 → 텍스트 추출 → 청킹·인덱싱. 동일 파일명은 교체된다."""
    assert_can_manage_standard(p)
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
async def delete_document(pack_id: str, filename: str,
                          p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    _safe_pack_id(pack_id)
    if not _FNAME_RE.match(filename or ""):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    ok = await asyncio.to_thread(knowledge_base.remove_document, pack_id, filename)
    if not ok:
        raise HTTPException(status_code=404, detail="지식팩 또는 문서를 찾을 수 없습니다.")
    return {"status": "success"}


@router.post("/packs/{pack_id}/search")
async def search_pack(pack_id: str, req: PackSearchRequest,
                      p: Principal = Depends(current_principal)):
    """검색 품질 확인용(등록 자료가 질의에 어떻게 검색되는지 UI에서 테스트).

    ⚠️ 목록보다 이쪽이 더 위험하다 — 목록은 제목을, 검색은 **본문 조각**을 돌려준다."""
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    _safe_pack_id(pack_id)
    if not knowledge_base.get_pack(pack_id):
        raise HTTPException(status_code=404, detail="지식팩을 찾을 수 없습니다.")
    hits = await asyncio.to_thread(knowledge_base.search_packs, [pack_id], req.query, req.n_results)
    return {"status": "success", "data": hits}
