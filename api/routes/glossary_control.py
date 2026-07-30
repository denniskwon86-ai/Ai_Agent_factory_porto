"""[§6.3 / §6.4] 업무 용어사전 + 데이터 요구사항 매칭 REST API. prefix `/api/v1/glossary`.

LLM 0콜. §6.4 가 "LLM 은 후보 검색·설명에만, 최종 매칭 확정은 데이터 오너 또는 승인된 규칙"
이라고 못박았으므로 `/match` 는 후보·근거·확정 차단 사유만 주고, 상태 갱신은 `/confirm` 이라는
**별도의 사람 행위**로 분리했다.

⚠️ 라우트 순서: 고정 경로(`/terms/expand` 등)는 `/terms/{term_id}` 위에 둔다.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.business_glossary import GlossaryError, business_glossary

router = APIRouter(prefix="/api/v1/glossary")


def _err(e: GlossaryError):
    raise HTTPException(status_code=409 if "이미 등록된" in str(e) else 400, detail=str(e))


def _actor(p: Principal) -> str:
    """승인·확정에 쓸 행위자. 식별이 안 되면 **가짜 값을 만들지 않고** 방법을 알려준다.

    ⚠️ 조직 강제 모드가 꺼져 있으면(기본값·점진 도입) `user_id` 가 비어 있다. 여기서
      'unknown' 같은 값을 넣으면 **아무도 승인하지 않은 것이 승인된 것처럼** 기록된다 —
      승인 기록의 존재 이유가 사라진다. 그렇다고 이유 없는 400 을 던지면 사용자는 무엇을
      해야 할지 모르므로, 401 로 해결 방법과 함께 거절한다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("승인·확정에는 사용자 식별이 필요합니다. 요청에 사용자 헤더(X-User-Id)를 "
                    "포함하거나 조직 강제 모드(ORG_ENFORCE)를 켜십시오. 승인자 없는 승인은 "
                    "'누가 이 정의에 합의했나'에 답할 수 없어 기록의 근거가 되지 못합니다."))
    return uid


class TermRequest(BaseModel):
    canonical_name: str
    definition: str = ""
    calculation: str = ""
    domain: str = ""
    owner_dept_id: str = ""
    master_code: str = ""
    synonyms: Optional[List[str]] = None
    tenant_id: str = "tenant_default"
    enterprise_scope_id: str = ""
    entity_mode: str = "REAL"


class SynonymRequest(BaseModel):
    synonym: str
    language: str = "ko"
    confidence: float = 1.0
    approved_by: str = ""


class ConfirmRequest(BaseModel):
    blueprint_id: str
    req_key: str
    asset_id: str
    readiness_status: str = "held"


# ── 고정 경로 (경로 변수보다 위) ──────────────────────────────────────────
@router.get("/terms/expand")
async def expand_term(q: str, approved_only: bool = False, scope_node_id: str = "",
                      tenant_id: str = "", entity_mode: str = "REAL"):
    """용어 → 정본명 + 동의어 확장(§6.4 1~2단계).

    `unapproved` 는 확장에는 썼지만 **확정 근거로는 약한** 동의어다 — 섞어서 주면 나중에
    "이 매칭의 근거가 승인된 것이었나"를 되짚을 수 없다."""
    data = await asyncio.to_thread(business_glossary.expand, q, approved_only,
                                   scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": data}


@router.get("/match")
async def match_requirement(term: str, scope_node_id: str = "", tenant_id: str = "",
                            entity_mode: str = "REAL"):
    """업무 용어 → 카탈로그 후보(§6.4 전체 흐름).

    ⚠️ 확정하지 않는다. 각 후보에 `blockers`(무엇이 확정을 막고 있나)와 `confirmable` 을 준다."""
    data = await asyncio.to_thread(business_glossary.match_requirement, term, None,
                                   scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": data}


@router.post("/match/confirm")
async def confirm_match(req: ConfirmRequest, p: Principal = Depends(current_principal)):
    """사람이 매칭을 확정하고 데이터 요구사항 상태를 갱신한다(§6.4 6단계).

    ⚠️ 확정자를 기록한다 — 준비도는 착수 판단에 쓰이므로 근거 없는 상향이 가장 위험하다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            business_glossary.confirm_match, req.blueprint_id, req.req_key, req.asset_id,
            _actor(p), req.readiness_status)
    except GlossaryError as e:
        _err(e)
    return {"status": "success", "data": out}


# ── 용어 ──────────────────────────────────────────────────────────────────
@router.get("/terms")
async def list_terms(domain: str = "", status: str = "", include_retired: bool = False,
                     scope_node_id: str = "", tenant_id: str = "",
                     entity_mode: str = "REAL",
                     p: Principal = Depends(current_principal)):
    """용어 목록. **등급이 낮은 주체에게는 제목만** 주고 정의는 가린다(§6-2 사용자 결정)."""
    from core.enterprise_context.classification import clearance_of_scope
    rows = await asyncio.to_thread(business_glossary.list_terms, domain, status,
                                   include_retired, scope_node_id, tenant_id, entity_mode,
                                   clearance_of_scope(p.scope))
    return {"status": "success", "data": rows}


@router.post("/terms")
async def create_term(req: TermRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            business_glossary.create_term, req.canonical_name, req.definition, req.calculation,
            req.domain, req.owner_dept_id, req.master_code, req.synonyms, "",
            req.tenant_id, req.enterprise_scope_id, req.entity_mode)
    except GlossaryError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.get("/terms/{term_id}")
async def get_term(term_id: str):
    data = await asyncio.to_thread(business_glossary.get_term, term_id)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 용어입니다.")
    return {"status": "success", "data": data}


@router.post("/terms/{term_id}/approve")
async def approve_term(term_id: str, p: Principal = Depends(current_principal)):
    """승인 = "이 정의로 전사가 같은 말을 쓴다"는 선언. 승인자를 반드시 남긴다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(business_glossary.approve_term, term_id, _actor(p))
    except GlossaryError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.delete("/terms/{term_id}")
async def retire_term(term_id: str, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(business_glossary.retire_term, term_id)
    if not ok:
        raise HTTPException(status_code=404, detail="활성 용어를 찾을 수 없습니다.")
    return {"status": "success", "data": {"term_id": term_id, "retired": True}}


@router.post("/terms/{term_id}/synonyms")
async def add_synonym(term_id: str, req: SynonymRequest,
                      p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(business_glossary.add_synonym, term_id, req.synonym,
                                      req.language, req.confidence, req.approved_by)
    except GlossaryError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/terms/{term_id}/synonyms/{synonym}/approve")
async def approve_synonym(term_id: str, synonym: str,
                          p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(business_glossary.approve_synonym, term_id, synonym,
                                      _actor(p))
    except GlossaryError as e:
        _err(e)
    return {"status": "success", "data": out}
