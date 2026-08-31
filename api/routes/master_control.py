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
from fastapi import Depends
from api.deps import (Principal, assert_can_manage_standard, current_principal,
                      hidden_envelope, viewer_visible_scopes, visibility_block_reason)

router = APIRouter(prefix="/api/v1/master")


def _domain_err(e: MasterDataError):
    msg = str(e)
    # 중복/삭제 충돌은 409, 그 외 검증 실패는 400
    if "이미 존재" in msg or "삭제할 수 없" in msg:
        raise HTTPException(status_code=409, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


async def _visible_master_codes(p: Principal, tenant_id: str = "tenant_default"):
    """요청자가 열람 가능한 기준정보 코드. ``None`` 은 전면 통과다.

    기준정보 본문에는 조직 컬럼을 복제하지 않고 ``master_scope_bindings`` 가 적용 범위를
    가진다. 따라서 목록도 같은 바인딩을 해석해야 한다. 이 경로를 생략하면 프롬프트 주입은
    막혀도 UI/API 목록에서는 타 조직 기준정보가 그대로 새어 나온다.
    """
    reason = visibility_block_reason(p)
    if reason:
        return reason, frozenset()
    scopes = viewer_visible_scopes(p)
    if scopes is None:
        return "", None
    allowed = set()
    for scope_node_id in scopes:
        bindings = await asyncio.to_thread(
            master_data.bindings_for_scope, tenant_id, scope_node_id, "REAL", "")
        allowed.update(bindings)
    return "", frozenset(allowed)


def _record_allowed(master_code: str, allowed) -> bool:
    return allowed is None or master_code in allowed


def _audit_hidden_record(p: Principal, master_code: str) -> None:
    """Data Stealth 거부는 응답에서만 숨기고 내부 감사에는 실제 코드를 남긴다."""
    from core.enterprise_context import audit
    actor_scopes = viewer_visible_scopes(p)
    # ⚠️ 앞의 두 인자는 **위치 인자**로 넘긴다. 저장소의 다른 호출부 전부
    #   (`crosswalk.py:95` · `mcp_broker.py:191` · `briefing_control.py:32` ·
    #   `connector_control.py:30`) 와 **같은 파일 아래쪽(272행)** 까지 위치 인자를 쓴다.
    #   여기만 전부 키워드로 두면 호출 규약이 두 갈래가 되고, 감사 기록을 검사하는 쪽은 한쪽만
    #   보게 된다 — 실제로 회귀 테스트가 그 차이로 깨졌다(2026-08-04).
    audit.denied_scope(
        "master_record", master_code,
        actor=p.user_id, actor_scopes=actor_scopes or (),
        detail="요청자의 조직 범위에 바인딩되지 않은 기준정보 상세 조회",
    )


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
async def list_types(tenant_id: str = "tenant_default",
                     p: Principal = Depends(current_principal)):
    reason, allowed = await _visible_master_codes(p, tenant_id)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    rows = await asyncio.to_thread(master_data.list_types)
    if allowed is None:
        return {"status": "success", "data": rows}
    records = await asyncio.to_thread(master_data.list_records, None, None, None, True)
    visible_type_ids = {r["type_id"] for r in records if r["master_code"] in allowed}
    shown = [row for row in rows if row["type_id"] in visible_type_ids]
    return {"status": "success", "data": shown, **hidden_envelope(p, len(rows), len(shown))}


@router.post("/types")
async def create_type(req: TypeRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(master_data.create_type, req.type_id, req.name_ko,
                                       req.description or "", req.attr_schema, req.relations)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.put("/types/{type_id}")
async def update_type(type_id: str, req: TypeUpdateRequest,
                      p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(master_data.update_type, type_id, req.name_ko,
                                       req.description, req.attr_schema, req.relations)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.delete("/types/{type_id}")
async def delete_type(type_id: str, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
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


class RecordProposalRequest(BaseModel):
    type_id: str
    name: str
    attributes: Optional[dict] = None
    domains: Optional[list] = None
    aliases: Optional[list] = None
    is_core: bool = False
    rationale: str = ""


class RecordRevisionRequest(BaseModel):
    name: str
    attributes: Optional[dict] = None
    domains: Optional[list] = None
    aliases: Optional[list] = None
    is_core: bool = False
    valid_from: Optional[str] = None


class RecordProposalDecision(BaseModel):
    reason: str = ""


class AliasRequest(BaseModel):
    aliases: List[str]


@router.get("/records")
async def list_records(type_id: Optional[str] = None, q: Optional[str] = None,
                       domain: Optional[str] = None, include_retired: bool = False,
                       tenant_id: str = "tenant_default",
                       p: Principal = Depends(current_principal)):
    reason, allowed = await _visible_master_codes(p, tenant_id)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    data = await asyncio.to_thread(master_data.list_records, type_id, q, domain, include_retired)
    if allowed is None:
        return {"status": "success", "data": data}
    shown = [row for row in data if row["master_code"] in allowed]
    return {"status": "success", "data": shown, **hidden_envelope(p, len(data), len(shown))}


@router.post("/records")
async def create_record(req: RecordRequest, p: Principal = Depends(current_principal)):
    """기존 정본의 개정 전용 하위호환 경로.

    신규 코드를 보내 즉시 현행화하는 옛 동작은 막는다. 신규 정본은 `/records/proposals` 에
    업무 내용만 제안하고 별도 관리자가 승인할 때 서버가 키를 발급한다.
    """
    assert_can_manage_standard(p)
    existing = await asyncio.to_thread(master_data.get_record, req.master_code)
    if not existing:
        raise HTTPException(
            status_code=409,
            detail="신규 기준정보는 코드를 입력해 직접 만들 수 없습니다. 신규 정본 제안을 제출하십시오.")
    try:
        data = await asyncio.to_thread(
            master_data.create_or_revise_record, req.master_code, req.type_id, req.name,
            req.attributes, req.domains, req.aliases, req.is_core, req.valid_from)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.put("/records/{master_code}")
async def revise_record(master_code: str, req: RecordRevisionRequest,
                        p: Principal = Depends(current_principal)):
    """선택된 현행 정본의 내용 개정. 내부 키는 경로 결속이고 사용자가 입력하지 않는다."""
    assert_can_manage_standard(p)
    existing = await asyncio.to_thread(master_data.get_record, master_code)
    if not existing:
        raise HTTPException(status_code=404, detail="존재하지 않는 기준정보입니다.")
    try:
        data = await asyncio.to_thread(
            master_data.create_or_revise_record, master_code, existing["type_id"], req.name,
            req.attributes, req.domains, req.aliases, req.is_core, req.valid_from)
    except MasterDataError as e:
        _domain_err(e)
    from core.enterprise_context import audit
    audit.record(audit.MASTER_DATA_REVISED, "master_record", master_code,
                 actor=p.user_id, outcome="allowed",
                 detail=f"기준정보 개정 · 명칭={req.name} · v{data['version']}"[:500])
    return {"status": "success", "data": data}


@router.get("/records/proposals")
async def list_record_proposals(status: str = "pending",
                                p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        rows = await asyncio.to_thread(master_data.list_record_proposals, status)
        return {"status": "success", "data": rows}
    except MasterDataError as e:
        _domain_err(e)


@router.post("/records/proposals")
async def propose_record(req: RecordProposalRequest,
                         p: Principal = Depends(current_principal)):
    if not (p.user_id or "").strip():
        raise HTTPException(status_code=401, detail="신규 정본 제안을 제출하려면 로그인이 필요합니다.")
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    try:
        data = await asyncio.to_thread(
            master_data.propose_record, req.type_id, req.name,
            attributes=req.attributes, domains=req.domains, aliases=req.aliases,
            is_core=req.is_core, rationale=req.rationale, proposed_by=p.user_id)
    except MasterDataError as e:
        _domain_err(e)
    from core.enterprise_context import audit
    audit.record(audit.MASTER_DATA_PROPOSED, "master_record_proposal", data["proposal_id"],
                 actor=p.user_id, outcome="allowed",
                 detail=f"신규 정본 제안 · 유형={req.type_id} · 명칭={req.name}"[:500])
    return {"status": "success", "data": data}


@router.post("/records/proposals/{proposal_id}/approve")
async def approve_record_proposal(proposal_id: str, req: RecordProposalDecision,
                                  p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(
            master_data.approve_record_proposal, proposal_id,
            reviewed_by=p.user_id, review_reason=req.reason)
    except MasterDataError as e:
        _domain_err(e)
    from core.enterprise_context import audit
    audit.record(audit.MASTER_DATA_APPROVED, "master_record_proposal", proposal_id,
                 actor=p.user_id, outcome="allowed",
                 detail=f"신규 정본 승인 · 명칭={data['record']['name']}"[:500])
    return {"status": "success", "data": data}


@router.post("/records/proposals/{proposal_id}/reject")
async def reject_record_proposal(proposal_id: str, req: RecordProposalDecision,
                                 p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(
            master_data.reject_record_proposal, proposal_id,
            reviewed_by=p.user_id, review_reason=req.reason)
    except MasterDataError as e:
        _domain_err(e)
    from core.enterprise_context import audit
    audit.record(audit.MASTER_DATA_REJECTED, "master_record_proposal", proposal_id,
                 actor=p.user_id, outcome="allowed", reason=req.reason[:500])
    return {"status": "success", "data": data}


@router.get("/records/duplicates")
async def duplicate_candidates(p: Principal = Depends(current_principal)):
    """[§14 M1 「중복 후보」] 같은 대상을 가리키는 것으로 의심되는 기준정보 쌍.

    ⚠️ 자동 병합하지 않는다 — 무엇이 정본인지는 현업 판단이고 시스템이 지우면 되돌릴 수 없다.
      둘 다 활성이면 **두 기준값이 함께 프롬프트에 들어간다**는 점이 문제의 핵심이다.

    ⚠️ **이 라우트는 반드시 `/records/{master_code}` 보다 위에 있어야 한다.** 아래에 두면
      경로 변수가 'duplicates' 를 master_code 로 잡아 404 가 난다(실제로 그렇게 났다).
      함수 단위 테스트로는 안 잡히는 결함이라 `tests/test_master_api_routes.py` 로 잠갔다."""
    assert_can_manage_standard(p)
    rows = await asyncio.to_thread(master_data.find_duplicate_candidates)
    return {"status": "success", "data": {
        "candidates": rows, "total": len(rows),
        "high_confidence": sum(1 for r in rows if r["confidence"] == "high"),
        "note": "정본을 정한 뒤 한쪽을 폐기하거나 별칭으로 흡수하십시오.",
    }}


@router.get("/records/{master_code}")
async def get_record(master_code: str, tenant_id: str = "tenant_default",
                     p: Principal = Depends(current_principal)):
    reason, allowed = await _visible_master_codes(p, tenant_id)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    if not _record_allowed(master_code, allowed):
        _audit_hidden_record(p, master_code)
        raise HTTPException(status_code=404, detail="존재하지 않는 기준정보입니다.")
    data = await asyncio.to_thread(master_data.get_record, master_code)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 기준정보입니다.")
    return {"status": "success", "data": data}


@router.delete("/records/{master_code}")
async def delete_record(master_code: str, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(master_data.retire_record, master_code)
    if not ok:
        raise HTTPException(status_code=404, detail="존재하지 않는(또는 이미 폐기된) 기준정보입니다.")
    return {"status": "success"}


@router.post("/records/{master_code}/aliases")
async def add_aliases(master_code: str, req: AliasRequest,
                      p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(master_data.add_aliases, master_code, req.aliases)
        return {"status": "success", "data": data}
    except MasterDataError as e:
        _domain_err(e)


@router.delete("/records/{master_code}/aliases/{alias}")
async def remove_alias(master_code: str, alias: str,
                       p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    data = await asyncio.to_thread(master_data.remove_alias, master_code, alias)
    return {"status": "success", "data": data}


# ── 일괄 등록 (CSV) ───────────────────────────────────────────────────
@router.post("/import/csv")
async def import_csv(type_id: str = Form(...), file: UploadFile = File(...),
                     p: Principal = Depends(current_principal)):
    if not (p.user_id or "").strip():
        raise HTTPException(status_code=401, detail="일괄 제안을 제출하려면 로그인이 필요합니다.")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # BOM 허용(엑셀 CSV)
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail="빈 CSV 이거나 헤더만 있습니다.")
    report = await asyncio.to_thread(
        master_data.import_proposal_rows, rows, type_id, proposed_by=p.user_id)
    return {"status": "success", "data": report}


# ── 주입 미리보기 ─────────────────────────────────────────────────────
class PreviewRequest(BaseModel):
    text: str
    domains: Optional[list] = None
    scope_node_id: Optional[str] = None
    tenant_id: str = "tenant_default"


@router.post("/grounding/preview")
async def grounding_preview(req: PreviewRequest,
                            p: Principal = Depends(current_principal)):
    """실제 주입될 블록을 그대로 보여준다. `scope_node_id` 를 주면 조직 범위 필터까지 적용해
    **그 조직이 실제로 받게 되는 것**을 본다(R-001)."""
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    from core.scope_guard import resolve_effective_scope
    effective = resolve_effective_scope(p, req.scope_node_id or "")
    if effective.denied:
        from core.enterprise_context import audit
        audit.denied_scope("master_grounding", req.scope_node_id or "unspecified",
                           p.user_id, effective.allowed_scopes, req.scope_node_id,
                           "요청 범위가 사용자 조직 범위를 벗어남")
        raise HTTPException(status_code=404, detail="요청한 조직 범위를 찾을 수 없습니다.")
    if not p.scope.unrestricted and not p.scope.can_manage_standard and not effective.scope_node_id:
        raise HTTPException(status_code=422,
                            detail="조직 범위를 지정해야 주입값을 확인할 수 있습니다.")
    args = (req.text, req.domains or [], req.tenant_id, effective.scope_node_id)
    block = await asyncio.to_thread(master_data.render_grounding, *args)
    selected, stats = await asyncio.to_thread(
        lambda: master_data.select_for_injection(*args, with_stats=True))
    return {"status": "success", "data": {"block": block,
                                          "matched": [r["master_code"] for r in selected],
                                          "stats": stats}}


# ── [R-001 / 감사 Action 1] 문서 시드 · 조직 범위 바인딩 · 품질 점검 ────────
class ScopeBindRequest(BaseModel):
    master_code: str
    scope_node_id: str
    tenant_id: str = "tenant_default"
    inherit_descendants: bool = True
    # 버전 고정 — 지정하면 개정 뒤에도 **그 버전의 값**이 주입된다("그때 그 값으로 재현").
    master_version: Optional[int] = None
    # 적용 기간 — ISO8601. 빈 값은 무제한. 경계는 `from <= 시점 < to`.
    effective_from: str = ""
    effective_to: str = ""


@router.post("/scope-bindings")
async def create_scope_binding(req: ScopeBindRequest,
                               p: Principal = Depends(current_principal)):
    """기준정보를 조직 범위에 적용한다(**원본 1 : 적용범위 N**).

    ⚠️ 이것은 **적용 가능성**이지 열람 권한이 아니다(`DECISIONS.md` D-003·D-009).
      사용자 권한은 ECM 이 따로 판정한다."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            master_data.bind_master_to_scope, req.master_code, req.scope_node_id,
            req.tenant_id, "REAL", req.master_version, req.inherit_descendants,
            req.effective_from, req.effective_to, p.user_id or "")
    except MasterDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}


@router.get("/scope-bindings/coverage")
async def scope_coverage(tenant_id: str = "tenant_default",
                         p: Principal = Depends(current_principal)):
    """[격리 관측] 미바인딩으로 남아 **모든 조직에 노출되는** 기준정보 현황.

    같은 유형의 사고가 반복됐다 — 재시드가 바인딩을 건너뛰거나, 조직 코드가 어긋나거나,
    바인딩을 해제하거나, ECM 시드 전에 적재하면 그 레코드는 전사 공통으로 통과한다.
    규칙은 유지하되 **노출을 조용하지 않게** 만드는 것이 이 엔드포인트의 목적이다."""
    assert_can_manage_standard(p)
    data = await asyncio.to_thread(master_data.scope_coverage, tenant_id)
    return {"status": "success", "data": data}


@router.delete("/scope-bindings/{binding_id}")
async def revoke_scope_binding(binding_id: str,
                               p: Principal = Depends(current_principal)):
    """바인딩 해제(소프트 — `status='revoked'`).

    ⚠️ 해제는 **차단이 아니다.** 그 코드에 다른 바인딩이 없으면 미바인딩 상태가 되고, 점진 도입
      규칙에 따라 전사 공통으로 통과한다. 실제로 막으려면 레코드를 폐기해야 한다."""
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(master_data.unbind_master_from_scope, binding_id, p.user_id or "")
    if not ok:
        raise HTTPException(status_code=404, detail="활성 바인딩을 찾을 수 없습니다.")
    return {"status": "success", "data": {
        "binding_id": binding_id, "revoked": True,
        "warning": ("해제는 차단이 아닙니다. 이 기준정보에 다른 바인딩이 없으면 "
                    "전사 공통으로 통과합니다."),
    }}


@router.get("/scope-bindings")
async def list_scope_bindings(master_code: str = "", scope_node_id: str = "",
                              tenant_id: str = "",
                              p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    rows = await asyncio.to_thread(master_data.list_scope_bindings, master_code, scope_node_id,
                                   tenant_id)
    return {"status": "success", "data": rows}


@router.get("/scope-bindings/allowed")
async def allowed_for_scope(scope_node_id: str, tenant_id: str = "tenant_default",
                            as_of: str = "",
                            p: Principal = Depends(current_principal)):
    """이 조직 범위에 적용 가능한 기준정보 코드.

    `as_of`(ISO8601, 미지정 시 현재)로 **그 시점 기준** 적용 범위를 본다 — 기간 바인딩을
    등록해 놓고 언제부터 무엇이 바뀌는지 미리 확인하려면 이게 필요하다.

    주입 상한은 기본적으로 **없다**(전수 주입). 운영 비상시 환경변수로 걸었다면 그 값을 함께
    주고, 실제로 잘린 건수는 프롬프트 블록에도 명시된다 — 조용히 잘리지 않게."""
    from core.master_data import _INJECT_MAX_CHARS, _INJECT_MAX_ITEMS
    if not (p.scope.unrestricted or p.scope.can_manage_standard):
        from core.scope_guard import resolve_effective_scope
        effective = resolve_effective_scope(p, scope_node_id)
        if effective.denied:
            from core.enterprise_context import audit
            audit.denied_scope("master_scope_binding", scope_node_id, p.user_id,
                               effective.allowed_scopes, scope_node_id,
                               "요청 범위가 사용자 조직 범위를 벗어남")
            raise HTTPException(status_code=404, detail="요청한 조직 범위를 찾을 수 없습니다.")
        scope_node_id = effective.scope_node_id
    binds = await asyncio.to_thread(master_data.bindings_for_scope, tenant_id, scope_node_id,
                                    "REAL", as_of)
    codes = set(binds)
    capped = _INJECT_MAX_ITEMS is not None or _INJECT_MAX_CHARS is not None
    return {"status": "success", "data": {
        "scope_node_id": scope_node_id, "tenant_id": tenant_id,
        "as_of": as_of or "now",
        "allowed_master_codes": sorted(codes), "allowed_count": len(codes),
        # 버전이 고정된 것만 별도로 — 현행판과 다른 값이 주입된다는 사실은 눈에 띄어야 한다.
        "pinned_versions": {c: v for c, v in sorted(binds.items()) if v},
        "injection_limit_items": _INJECT_MAX_ITEMS,
        "injection_limit_chars": _INJECT_MAX_CHARS,
        "injection_capped": capped,
        "note": (("⚠️ 환경변수로 주입 상한이 걸려 있어 일부가 프롬프트에 들어가지 않을 수 있습니다. "
                  if capped else "적용 가능한 기준정보는 전량 주입됩니다(도메인이 어긋난 것만 제외). ")
                 + "표시 순서는 별칭 히트 → 전사 표준·산식 → 도메인 핵심 순입니다."),
    }}


@router.get("/documents/quality")
async def document_quality(p: Principal = Depends(current_principal)):
    """M1~M4 문서의 **계산으로 드러나는 모순**을 점검한다.

    ⚠️ 값을 고치지 않는다. 수치의 정확도는 구현 단계에서 판정할 수 없으므로(사용자 지시
      2026-07-29), 이 목록은 **실사용 전 보정 작업의 입력**이다."""
    assert_can_manage_standard(p)
    from core.master_data_seed import inspect_data_quality
    findings = await asyncio.to_thread(inspect_data_quality)
    return {"status": "success", "data": {
        "findings": findings, "total": len(findings),
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "note": "값은 자동 보정되지 않습니다. 현업 확인 후 문서를 갱신하십시오.",
    }}


@router.post("/documents/seed")
async def seed_documents(force: bool = False, bind_scopes: bool = True,
                         p: Principal = Depends(current_principal)):
    """`docs/master_data/*.json` 을 기준정보로 적재하고 ECM 조직에 바인딩한다(멱등).

    `force=False` 면 이미 있는 코드는 건너뛴다 — 운영 중 사용자가 개정한 값을 시드가 되돌리면
    안 된다(시드는 초기 공급이지 진실원본이 아니다)."""
    assert_can_manage_standard(p)
    from core.master_data_seed import seed_master_documents
    report = await asyncio.to_thread(seed_master_documents, master_data, None,
                                     "docs/master_data", bind_scopes, force)
    return {"status": "success", "data": report}
