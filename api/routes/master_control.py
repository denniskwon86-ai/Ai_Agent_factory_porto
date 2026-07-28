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
from api.deps import Principal, assert_can_manage_standard, current_principal

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
    scope_node_id: Optional[str] = None
    tenant_id: str = "tenant_default"


@router.post("/grounding/preview")
async def grounding_preview(req: PreviewRequest):
    """실제 주입될 블록을 그대로 보여준다. `scope_node_id` 를 주면 조직 범위 필터까지 적용해
    **그 조직이 실제로 받게 되는 것**을 본다(R-001)."""
    args = (req.text, req.domains or [], req.tenant_id, req.scope_node_id or "")
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
async def document_quality():
    """M1~M4 문서의 **계산으로 드러나는 모순**을 점검한다.

    ⚠️ 값을 고치지 않는다. 수치의 정확도는 구현 단계에서 판정할 수 없으므로(사용자 지시
      2026-07-29), 이 목록은 **실사용 전 보정 작업의 입력**이다."""
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
