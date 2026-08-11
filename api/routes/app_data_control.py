"""[트랙 I-2] 생성 앱 데이터 평면 REST API. prefix `/api/v1/appdata`.

설계: `docs/design_app_data_plane_2026-08-08.md`

## 이 라우터가 지키는 것

생성된 앱은 자기 로그인도, 자기 백엔드도 갖지 않는다(`core/app_manifest.py` CL-0 계약).
그래서 앱의 데이터는 **여기를 통해서만** 드나들고, 그 통로에 이미 있는 통제를 전부 태운다.

| 관심사 | 재사용 |
|---|---|
| 주체 식별 | `api/deps.current_principal` |
| 읽기 범위 | `api/deps.assert_release_readable` |
| **쓰기 범위** | `api/deps.assert_release_writable` (트랙 I 에서 신설) |
| 감사 | `core/decision_ledger` — **구조 변경만**(§6) |

★★ **앱은 `release_id` 를 말하지 않는다.** 앱이 자기 릴리스를 지정할 수 있으면 남의 앱
  데이터를 요청할 수 있다. 브리지(부모 창)가 붙이고, 앱은 데이터셋 «이름» 만 말한다.
  이 라우터는 그 계약의 서버 쪽 절반이다 — `release_id` 를 받되 **매번 권한을 재검사**한다.

⚠️ 식별되지 않은 요청의 쓰기는 401 이다. 트랙 H 가 「식별만으로 열리는 쓰기」 65건을
  봉합했는데 여기서 「식별조차 없는 쓰기」를 새로 만들면 그 작업이 무효가 된다.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.deps import (Principal, assert_release_readable, assert_release_writable,
                      current_principal)
from core.app_data import AppDataError, app_data_service

router = APIRouter(prefix="/api/v1/appdata")


# ── 공통 ──────────────────────────────────────────────────────────────────
def _actor(p: Principal) -> str:
    """쓰기 주체. **비어 있으면 401** — 누가 썼는지 모르는 업무 데이터는 만들지 않는다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("앱 데이터를 쓰려면 사용자 식별이 필요합니다. 누가 입력했는지 남지 않는 "
                    "업무 데이터는 나중에 «이 값이 왜 이런가» 에 답할 수 없습니다."))
    return uid


def _require_dataset(dataset_id: str) -> Dict[str, Any]:
    ds = app_data_service.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="데이터셋을 찾을 수 없습니다.")
    return ds


def _assert_personal_owner(ds: Dict[str, Any], p: Principal, row_creator: str = "") -> None:
    """★ `personal` 앱의 데이터는 만든 사람의 것이다(설계 §5-1).

    부서 범위로 열면 **개인 편의 도구가 부서 공유물이 된다** — 사용자가 그렇게 알고 만든 것이
    아니다. 설계서 §2-4 모순 2 가 같은 갈래를 지적했다."""
    if (ds.get("app_class") or "") != "personal":
        return
    if p.scope.unrestricted:
        return
    owner = row_creator or ds.get("created_by") or ""
    if owner and owner != (p.user_id or ""):
        raise HTTPException(
            status_code=403,
            detail="개인용 앱의 데이터는 만든 사람만 볼 수 있습니다.")


def _ledger(event_type: str, dataset_id: str, actor_id: str, decision: str,
            rationale: str = "", evidence: Optional[List[Any]] = None,
            tenant_id: str = "tenant_default", scope: str = "") -> None:
    """구조 변경만 원장에 남긴다(§6). **실패를 삼키지 않는다** — 감사 기록이 조용히
    누락되면 승인 이력 없는 승인이 생긴다(`core/decision_ledger.append` 의 계약)."""
    from core.decision_ledger import decision_ledger
    decision_ledger.append(
        event_type, "app_dataset", dataset_id,
        actor_type="user", actor_id=actor_id,
        decision=decision, rationale=rationale,
        evidence_refs=evidence or [],
        tenant_id=tenant_id or "tenant_default", enterprise_scope_id=scope or "")


# ── 요청 모델 ─────────────────────────────────────────────────────────────
# ⚠️ pydantic v2 다. `class Config: fields = {...}` 는 **조용히 무시된다** — v1 문법이라
#   오류도 나지 않고 별칭만 사라진다. 그러면 생성기가 보낸 `schema` 키가 버려지고 «필드 선언이
#   없다» 로 거부돼, 원인이 별칭이라는 것을 아무도 못 찾는다. v2 문법으로 쓴다.
# ⚠️ 필드명이 `schema_def` 인 이유: `schema` 는 BaseModel 의 예약 이름이다.
class DatasetCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    release_id: str
    name: str
    schema_def: Any = Field(default=None, alias="schema")
    label: str = ""
    app_class: str = ""
    owner_dept_id: str = ""
    scope_node_id: str = ""
    tenant_id: str = "tenant_default"


class SchemaUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_def: Any = Field(default=None, alias="schema")


class RecordWrite(BaseModel):
    payload: Dict[str, Any]


# ── 데이터셋 ──────────────────────────────────────────────────────────────
@router.post("/datasets")
async def create_dataset(req: DatasetCreate, p: Principal = Depends(current_principal)):
    actor = _actor(p)
    assert_release_writable(p, req.release_id)
    try:
        ds = app_data_service.create_dataset(
            req.release_id, req.name, req.schema_def, actor_id=actor,
            label=req.label, app_class=req.app_class, owner_dept_id=req.owner_dept_id,
            scope_node_id=req.scope_node_id, tenant_id=req.tenant_id or "tenant_default")
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_CREATED", ds["dataset_id"], actor,
            decision=f"{req.release_id} 앱에 데이터셋 '{req.name}' 생성",
            rationale=f"필드 {len(ds['schema'].get('fields', []))}개",
            evidence=[{"release_id": req.release_id, "name": req.name}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    return ds


@router.get("/datasets")
async def list_datasets(release_id: str = Query(..., description="어느 앱의 데이터셋인가"),
                        include_retired: bool = False,
                        p: Principal = Depends(current_principal)):
    assert_release_readable(p, release_id)
    rows = app_data_service.list_datasets(release_id, include_retired=include_retired)
    out = []
    for ds in rows:
        if (ds.get("app_class") or "") == "personal" and not p.scope.unrestricted \
                and ds.get("created_by") and ds["created_by"] != (p.user_id or ""):
            continue          # 목록에서는 조용히 감춘다(단건은 403 으로 이유를 말한다)
        ds["record_count"] = app_data_service.count_records(ds["dataset_id"])
        out.append(ds)
    return {"datasets": out, "count": len(out), "release_id": release_id}


@router.get("/datasets/by-name")
async def get_dataset_by_name(release_id: str = Query(...), name: str = Query(...),
                              p: Principal = Depends(current_principal)):
    """★ 브리지가 쓰는 경로 — 앱은 이름만 말하고 `release_id` 는 부모가 붙인다."""
    assert_release_readable(p, release_id)
    ds = app_data_service.find_dataset(release_id, name)
    if not ds:
        raise HTTPException(status_code=404, detail=f"데이터셋을 찾을 수 없습니다: {name}")
    _assert_personal_owner(ds, p)
    ds["record_count"] = app_data_service.count_records(ds["dataset_id"])
    return ds


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, p: Principal = Depends(current_principal)):
    ds = _require_dataset(dataset_id)
    assert_release_readable(p, ds["release_id"])
    _assert_personal_owner(ds, p)
    ds["record_count"] = app_data_service.count_records(dataset_id)
    return ds


@router.put("/datasets/{dataset_id}/schema")
async def update_schema(dataset_id: str, req: SchemaUpdate,
                        p: Principal = Depends(current_principal)):
    ds = _require_dataset(dataset_id)
    actor = _actor(p)
    assert_release_writable(p, ds["release_id"])
    _assert_personal_owner(ds, p)
    try:
        out = app_data_service.update_schema(dataset_id, req.schema_def, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_SCHEMA_CHANGED", dataset_id, actor,
            decision=f"'{ds['name']}' 스키마 변경",
            rationale=(f"추가 {out.get('added_fields') or '없음'} · "
                       f"제거 {out.get('removed_fields') or '없음'}"),
            evidence=[{"added": out.get("added_fields"), "removed": out.get("removed_fields")}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    # ⚠️ 제거된 필드가 있으면 **응답에서 드러낸다.** 기존 레코드의 그 값은 조회에서 사라진다.
    if out.get("removed_fields"):
        out["warning"] = (f"필드 {len(out['removed_fields'])}개가 선언에서 빠졌습니다 — "
                          f"기존 레코드의 해당 값은 화면에서 보이지 않게 됩니다(데이터는 남아 "
                          f"있습니다): {', '.join(out['removed_fields'])}")
    return out


@router.delete("/datasets/{dataset_id}")
async def retire_dataset(dataset_id: str, p: Principal = Depends(current_principal)):
    """폐지. **레코드는 지우지 않는다**(설계 §4-2)."""
    ds = _require_dataset(dataset_id)
    actor = _actor(p)
    assert_release_writable(p, ds["release_id"])
    _assert_personal_owner(ds, p)
    try:
        out = app_data_service.retire_dataset(dataset_id, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_RETIRED", dataset_id, actor,
            decision=f"'{ds['name']}' 폐지",
            rationale="레코드는 보존한다 — 원장이 가리키는 대상이 사라지면 감사 증적이 아니다",
            evidence=[{"record_count": app_data_service.count_records(dataset_id)}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    return out


# ── 레코드 ────────────────────────────────────────────────────────────────
@router.get("/datasets/{dataset_id}/records")
async def list_records(dataset_id: str, limit: int = 200, offset: int = 0,
                       include_deleted: bool = False,
                       p: Principal = Depends(current_principal)):
    ds = _require_dataset(dataset_id)
    assert_release_readable(p, ds["release_id"])
    _assert_personal_owner(ds, p)
    # `personal` 앱은 자기 것만 — 데이터셋 소유자와 레코드 작성자가 다를 수 있다.
    creator = ""
    if (ds.get("app_class") or "") == "personal" and not p.scope.unrestricted:
        creator = (p.user_id or "")
    rows, total = app_data_service.list_records(
        dataset_id, limit=limit, offset=offset,
        include_deleted=include_deleted, created_by=creator)
    # ★ 목록 길이와 총계를 함께 준다 — 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린
    #   순간 사용자는 「우리 데이터는 200건」으로 믿는다.
    return {"records": rows, "count": len(rows), "total": total,
            "limit": limit, "offset": offset,
            "truncated": (offset + len(rows)) < total,
            "schema": ds.get("schema", {})}


@router.post("/datasets/{dataset_id}/records")
async def create_record(dataset_id: str, req: RecordWrite,
                        p: Principal = Depends(current_principal)):
    ds = _require_dataset(dataset_id)
    actor = _actor(p)
    assert_release_writable(p, ds["release_id"])
    _assert_personal_owner(ds, p)
    try:
        return app_data_service.create_record(dataset_id, req.payload, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/records/{record_id}")
async def update_record(record_id: str, req: RecordWrite,
                        p: Principal = Depends(current_principal)):
    rec = app_data_service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    ds = _require_dataset(rec["dataset_id"])
    actor = _actor(p)
    assert_release_writable(p, ds["release_id"])
    _assert_personal_owner(ds, p, row_creator=rec.get("created_by", ""))
    try:
        return app_data_service.update_record(record_id, req.payload, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/records/{record_id}")
async def delete_record(record_id: str, p: Principal = Depends(current_principal)):
    """논리 삭제. 물리 삭제는 제공하지 않는다(설계 §4-2)."""
    rec = app_data_service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    ds = _require_dataset(rec["dataset_id"])
    actor = _actor(p)
    assert_release_writable(p, ds["release_id"])
    _assert_personal_owner(ds, p, row_creator=rec.get("created_by", ""))
    try:
        return app_data_service.delete_record(record_id, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
