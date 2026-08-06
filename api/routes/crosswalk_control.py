"""M2 크로스워크 REST API. prefix /api/v1/crosswalk.

core/crosswalk.py 의 시스템·스키마·제안·승인 로직을 노출한다. propose(use_llm=True)만 LLM(Flash,
옵트인) 사용, 나머지는 LLM 0콜. 매핑은 승인(approve)해야만 유효(confirmed=1)하다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}.
"""
import io
import csv
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

# [§6-2] 목록에 등급 가림을 적용하려면 주체가 필요하다(등급은 권한에서 파생한다).
from api.deps import (Principal, assert_governance_readable, assert_identified,
                      current_principal, require_caps, visibility_block_reason)
from core.admin_capability import ADMIN_DATA_ACCESS
from core.crosswalk import crosswalk, CrosswalkError

router = APIRouter(prefix="/api/v1/crosswalk")

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "크로스워크"


def _assert_may_write(p: Principal, action: str) -> None:
    """★★ [2026-08-07 · 트랙 G] 크로스워크를 **바꿔도 되는 주체인가.**

    ## 이 파일은 읽기만 막혀 있었다

    실측: GET 5개는 전부 `assert_governance_readable` 을 지나는데 **쓰기 9개에는 주체 자체가
    없었다.** 그래서 익명이 할 수 있었던 일:

    - 시스템 등록·수정·**삭제**
    - CSV 로 스키마 **일괄 등록**(`schema/import`)
    - 필드 매핑 변경
    - 제안 **승인·기각** — 매핑은 승인해야 유효(`confirmed=1`)해지므로, 이것이 곧
      «어떤 외부 시스템 필드가 우리 표준의 무엇인가» 를 확정하는 행위다

    ⚠️ 「읽기가 막혀 있으니 이 라우터는 통제된다」로 보였다. 읽기·쓰기를 나눠 세지 않으면
      이 모양을 놓친다 — GET 만 훑는 점검은 여기서 초록을 준다.

    ## ★★ 범위 파라미터는 통제가 아니다

    `_gate()` 는 `scope_node_id`·`tenant_id` 가 **둘 다 비면 그냥 반환한다**(아래 주석의
    «범위 미지정 호출 — 종전 동작»). 즉 **파라미터를 주지 않는 것이 가장 넓은 호출**이고,
    `_gate` 를 부르는 쓰기 라우트들도 실제로는 아무나 통과했다. `/planning/facts` 유출의
    두 번째 겹과 같은 구조다(`PROGRESS.md` §G).

    → 그래서 이 검사는 **범위와 무관하게** 먼저 건다. 범위 게이트는 «남의 조직 것을 건드리지
      마라» 이고, 이 검사는 «애초에 바꿀 수 있는 사람인가» 다. 둘은 다른 질문이다.

    ⚠️ 읽기 쪽 `assert_governance_readable` 을 그대로 쓰지 않는다 — 볼 수 있다고 바꿀 수
      있는 것이 아니다(`AdminCapabilities.manageable_dept_ids` 주석과 같은 이유)."""
    assert_identified(p, WHAT)
    require_caps(p, ADMIN_DATA_ACCESS, resource="crosswalk", action=action)


def _err(e: CrosswalkError):
    msg = str(e)
    if "이미 존재" in msg or "이미 처리" in msg or "활성화" in msg:
        raise HTTPException(status_code=409, detail=msg)
    if "존재하지 않는" in msg or "먼저" in msg:
        raise HTTPException(status_code=404, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


# ── [ECM E2] 조직 범위 게이트 ─────────────────────────────────────────
# ⚠️ 자식 자원(스키마·매핑·제안)에는 범위 키를 **복제하지 않았다** — 소유 조직은 시스템 하나에만
#   있다. 그 대가로 자식 경로의 접근 판정은 전부 이 게이트 하나를 지나야 한다. 한 경로라도
#   빠뜨리면 그 경로만 열려 있는 구멍이 된다(그래서 라우트마다 같은 한 줄을 반복한다).
async def _gate(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                entity_mode: str = "REAL"):
    if not (scope_node_id or tenant_id):
        return                      # 범위 미지정 호출 — 종전 동작(ECM 미도입 흐름 보존)
    try:
        await asyncio.to_thread(crosswalk.require_system_visible, system_id,
                                scope_node_id, tenant_id, entity_mode)
    except CrosswalkError as e:
        # 존재하지 않는 것과 **같은 응답**이다 — 다른 조직 시스템의 존재를 알려주지 않는다.
        raise HTTPException(status_code=404, detail=str(e))


# ── 시스템 ────────────────────────────────────────────────────────────
class SystemRequest(BaseModel):
    system_id: str
    name: str = ""
    mcp_endpoint: Optional[str] = ""
    scope: Optional[str] = "read"
    # 이 시스템을 소유·운영하는 조직(비우면 전사 공용 — coverage 로 관측된다)
    tenant_id: Optional[str] = "tenant_default"
    enterprise_scope_id: Optional[str] = ""
    entity_mode: Optional[str] = "REAL"


class SystemUpdateRequest(BaseModel):
    name: Optional[str] = None
    mcp_endpoint: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None


@router.get("/systems")
async def list_systems(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
                       p: Principal = Depends(current_principal)):
    """범위를 주면 그 조직이 볼 수 있는 시스템만. 미지정이면 전량(종전 동작).

    ★ [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 내용은 가려진다."""
    # ⚠️ 이 라우트는 이미 **등급 기반 가림**이 있다(§6-2 사용자 결정) — 낮은 등급에는
    #   제목만 주고 내용을 가린다. 그 설계를 403 으로 덮지 않는다. 다만 익명·미등록·폐지
    #   계정에는 아무것도 주지 않는다(관문 A). 목록형이므로 0건 + 이유로 답한다.
    _reason = visibility_block_reason(p)
    if _reason:
        return {"status": "success", "data": [], "blocked_reason": _reason}
    from core.enterprise_context.classification import clearance_of_scope
    # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체인가 — 이것도 권한에서 파생한다.
    from core.enterprise_context.scoping import may_drill_down
    return {"status": "success",
            "data": await asyncio.to_thread(crosswalk.list_systems, scope_node_id,
                                            tenant_id, entity_mode,
                                            clearance_of_scope(p.scope),
                                            may_drill_down(p.scope))}


@router.get("/systems/coverage")
async def systems_coverage(p: Principal = Depends(current_principal)):
    """범위 미지정(= 모든 조직에 노출) 시스템 관측 (D-014).

    ⚠️ 경로 변수 라우트(`/systems/{system_id}/...`)보다 **위에** 둔다 — FastAPI 는 정의 순서로
      매칭하므로 아래에 두면 'coverage' 가 system_id 로 잡아먹힌다(실측 사고 이력)."""
    assert_governance_readable(p)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.systems_coverage)}


@router.post("/systems")
async def create_system(req: SystemRequest, p: Principal = Depends(current_principal)):
    _assert_may_write(p, "create_system")
    try:
        data = await asyncio.to_thread(crosswalk.create_system, req.system_id, req.name,
                                       req.mcp_endpoint or "", "", req.scope or "read",
                                       req.tenant_id or "tenant_default",
                                       req.enterprise_scope_id or "", req.entity_mode or "REAL")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.put("/systems/{system_id}")
async def update_system(system_id: str, req: SystemUpdateRequest,
                        scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
                        p: Principal = Depends(current_principal)):
    _assert_may_write(p, "update_system")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.update_system, system_id, req.name,
                                       req.mcp_endpoint, req.scope, req.status)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.delete("/systems/{system_id}")
async def delete_system(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                        entity_mode: str = "REAL",
                        p: Principal = Depends(current_principal)):
    _assert_may_write(p, "delete_system")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    await asyncio.to_thread(crosswalk.delete_system, system_id)
    return {"status": "success"}


# ── 스키마 ────────────────────────────────────────────────────────────
class FieldRequest(BaseModel):
    entity: str
    field: str
    field_type: Optional[str] = ""
    is_key: bool = False
    mapped_type: Optional[str] = ""
    mapped_attr: Optional[str] = ""


class FieldMappingRequest(BaseModel):
    entity: str
    field: str
    mapped_type: Optional[str] = ""
    mapped_attr: Optional[str] = ""


@router.get("/systems/{system_id}/schema")
async def get_schema(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                     entity_mode: str = "REAL",
                     p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.get_schema, system_id)}


@router.post("/systems/{system_id}/schema/field")
async def add_field(system_id: str, req: FieldRequest, scope_node_id: str = "",
                    tenant_id: str = "", entity_mode: str = "REAL",
                    p: Principal = Depends(current_principal)):
    _assert_may_write(p, "add_field")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.add_schema_field, system_id, req.entity, req.field,
                                       req.field_type or "", req.is_key, req.mapped_type or "",
                                       req.mapped_attr or "")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/systems/{system_id}/schema/import")
async def import_schema(system_id: str, file: UploadFile = File(...), scope_node_id: str = "",
                        tenant_id: str = "", entity_mode: str = "REAL",
                        p: Principal = Depends(current_principal)):
    # ⚠️ 파일을 읽기 **전에** 막는다 — 거부할 요청의 업로드 본문을 굳이 메모리에 올리지 않는다.
    _assert_may_write(p, "import_schema")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail="빈 CSV 이거나 헤더만 있습니다.")
    try:
        report = await asyncio.to_thread(crosswalk.import_schema_rows, system_id, rows)
        return {"status": "success", "data": report}
    except CrosswalkError as e:
        _err(e)


@router.put("/systems/{system_id}/schema/mapping")
async def set_mapping(system_id: str, req: FieldMappingRequest, scope_node_id: str = "",
                      tenant_id: str = "", entity_mode: str = "REAL",
                      p: Principal = Depends(current_principal)):
    _assert_may_write(p, "set_mapping")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.set_field_mapping, system_id, req.entity, req.field,
                                       req.mapped_type or "", req.mapped_attr or "")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


# ── 제안 / 승인 ───────────────────────────────────────────────────────
class ApproveRequest(BaseModel):
    external_key: Optional[str] = None


@router.post("/systems/{system_id}/propose")
async def propose(system_id: str, use_llm: bool = False, scope_node_id: str = "",
                  tenant_id: str = "", entity_mode: str = "REAL",
                  p: Principal = Depends(current_principal)):
    """매핑 초안 생성. use_llm=True 는 Flash(옵트인, 쿼터 소비)."""
    # ⚠️ 쿼터를 태우는 경로다 — 익명이 반복 호출하면 비용이 나간다.
    _assert_may_write(p, "propose")
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await crosswalk.propose(system_id, use_llm=use_llm)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/proposals")
async def list_proposals(system_id: str, status: Optional[str] = None, scope_node_id: str = "",
                         tenant_id: str = "", entity_mode: str = "REAL",
                         p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    data = await asyncio.to_thread(crosswalk.list_proposals, system_id, status)
    return {"status": "success", "data": data}


async def _gate_proposal(proposal_id: int, scope_node_id: str, tenant_id: str, entity_mode: str):
    """제안은 시스템에 종속된다 — 부모 시스템이 안 보이면 승인·기각도 안 된다."""
    if not (scope_node_id or tenant_id):
        return
    sid = await asyncio.to_thread(crosswalk.system_of_proposal, proposal_id)
    if not sid:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 제안입니다: {proposal_id}")
    await _gate(sid, scope_node_id, tenant_id, entity_mode)


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: int, req: ApproveRequest = None, scope_node_id: str = "",
                  tenant_id: str = "", entity_mode: str = "REAL",
                  p: Principal = Depends(current_principal)):
    # ★ 승인해야 매핑이 유효(`confirmed=1`)해진다 — 이 한 줄이 «외부 필드 = 우리 표준의 무엇» 을
    #   확정한다. 이 라우터에서 가장 되돌리기 어려운 쓰기다.
    _assert_may_write(p, "approve_proposal")
    await _gate_proposal(proposal_id, scope_node_id, tenant_id, entity_mode)
    try:
        ext = req.external_key if req else None
        data = await asyncio.to_thread(crosswalk.approve_proposal, proposal_id, ext)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: int, scope_node_id: str = "", tenant_id: str = "",
                 entity_mode: str = "REAL",
                 p: Principal = Depends(current_principal)):
    _assert_may_write(p, "reject_proposal")
    await _gate_proposal(proposal_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.reject_proposal, proposal_id)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/mappings")
async def list_mappings(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                       entity_mode: str = "REAL",
                        p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.list_mappings, system_id)}
