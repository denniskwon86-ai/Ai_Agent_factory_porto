"""[BDR-203·204] 업무 데이터 준비 API — 키트 적용과 원천 결속.

## 범위는 **복제하지 않는다**

★★★ 조직 범위 판정은 G1-B PDP 위의 `viewing_context` 하나를 쓴다. 프로젝트 전용
  visibility 판정기를 여기에 복제하지 않는다 — 복제하면 두 판정이 반드시 갈라지고,
  갈린 날 어느 쪽이 옳은지 아무도 모른다.

## 경계표

· 타 조직·tenant·entity mode → **404**(은폐). 403 은 「그것이 존재한다」를 알려 준다.
· 문맥을 확정하지 못함 → **503**. 빈 문맥으로 넘어가면 전부 막히고 「고장」으로 보인다.
· 지금 상태에서 할 수 없는 일 → **409**.
⚠️ 은폐는 응답이지 기록이 아니다 — 404 로 돌려주더라도 감사에는 실제 대상을 남긴다.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.deps import Principal, current_principal, require_caps, viewing_context
from core.admin_capability import PROJECT_CREATE, PROJECT_RUN
from core.data_preparation import (kit_registry, models as m, readiness,
                                   snapshot_service, source_binding)
from core.data_preparation.store import data_preparation_store as store
from core.paths import data_path
from core.route_authority import guard as _route_authority_guard

#: ★ 권한은 **표**(`core/route_authority.ROUTE_CAPS`)가 지킨다 — 라우트마다 적으면
#:   새 라우트가 생길 때 아무도 알려 주지 않는다. 의존성은 이 라우터의 모든 요청이
#:   지나므로, 새 라우트는 «표에 넣거나 명시적으로 면제하거나» 둘 중 하나를 해야 한다.
#: ⚠️ 읽기 라우트는 표에 넣지 않는다(표는 쓰기 전용) — 핸들러가 직접 요구한다.
router = APIRouter(prefix="/api/v1/data-preparation", tags=["data-preparation"],
                   dependencies=[Depends(_route_authority_guard)])


# ── 요청 모델 ────────────────────────────────────────────────────────────
class InstanceCreateRequest(BaseModel):
    """★ `tenant_id` 를 **받지 않는다.** 서버가 문맥에서 파생한다 — 받으면 남의
    tenant 를 적어 보내는 경로가 열린다."""
    kit_id: str
    version: str
    scope_node_id: str
    entity_mode: str
    label: str = ""


class BindingCreateRequest(BaseModel):
    dataset_contract_key: str
    provider: str
    config: Dict[str, Any] = {}


class BindingDecisionRequest(BaseModel):
    action: str                      # VALIDATE | APPROVE | ACTIVATE | BLOCK
    reason: str = ""


# ── 공통 ─────────────────────────────────────────────────────────────────
def _audit(event: str, *, resource_id: str, actor: str, outcome: str,
           reason: str = "", detail: str = "") -> None:
    """⚠️ 감사 실패가 요청을 죽이지 않는다 — 다만 **삼키지도 않는다**(모듈이 자체 계수)."""
    try:
        from core.enterprise_context import audit
        audit.record(event=event, resource_type="data_preparation",
                     resource_id=resource_id, actor=actor, outcome=outcome,
                     reason=reason, detail=detail)
    except Exception:
        pass


def _now_iso() -> str:
    """판정 시각. ★ 한 번만 읽어 **판정 전체에 같은 값**을 쓴다 — 데이터셋마다 새로
    읽으면 같은 요청 안에서 어떤 것은 만료, 어떤 것은 아님이 될 수 있다."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _ctx(p: Principal) -> Dict[str, Any]:
    """지금 보는 문맥. 확정 실패는 `viewing_context` 가 503 으로 바꾼다."""
    return viewing_context(p)


def _visible_scopes(p: Principal) -> List[str]:
    """이 사용자가 **볼 수 있는** 조직 노드들. 비면 빈 목록이다.

    ⚠️ 「비었으니 전부」로 읽지 않는다 — 그 순간 타 조직 자원이 목록에 뜬다."""
    return [str(x) for x in (getattr(p.scope, "readable_scope_nodes", ()) or ()) if str(x)]


def _instance_or_404(p: Principal, instance_id: str) -> Dict[str, Any]:
    """인스턴스를 **보이는 범위 안에서만** 찾는다.

    ★★★ 없는 것과 못 보는 것을 **같은 404** 로 돌려준다 — 다르게 답하면 그 응답이
      「그 조직에 그런 자원이 있다」를 알려 주는 신호가 된다."""
    row = store.get_instance(instance_id)
    ctx = _ctx(p)
    ok = bool(row) and (
        p.scope.unrestricted or (
            str(row["tenant_id"]) == str(ctx.get("tenant_id", "")) and
            str(row["entity_mode"]) == str(ctx.get("entity_mode", "")) and
            str(row["scope_node_id"]) in _visible_scopes(p)))
    if not ok:
        _audit("ACCESS_DENIED_SCOPE_MISMATCH", resource_id=instance_id,
               actor=p.user_id or "", outcome="denied",
               reason="not_found_or_out_of_scope",
               detail=f"exists={bool(row)}")
        raise HTTPException(status_code=404, detail="키트 인스턴스를 찾을 수 없습니다.")
    return row


#: RAW 원본 보관 뿌리. **DB 밖**이다 — 표에 본문을 넣으면 UPDATE 로 고칠 수 있게 되고,
#: 그러면 「우리가 인증한 그 파일」이 무엇이었는지 답할 수 없다.
def _raw_root() -> str:
    return data_path("data_preparation")


#: ⚠️ 상한이 없으면 파일 하나가 프로세스 메모리를 먹는다. 「업로드가 느리다」로 보이고
#:   원인은 한참 뒤에야 드러난다.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def _snapshot_or_404(p: Principal, snapshot_id: str) -> Dict[str, Any]:
    """Snapshot 을 **보이는 범위 안에서만** 찾는다.

    ★★★ 범위 판정을 여기서 새로 쓰지 않고 **인스턴스에게 묻는다** — 판정이 둘이
      되면 반드시 갈라지고, 갈린 날 어느 쪽이 옳은지 아무도 모른다.
    ⚠️ Snapshot 행에도 `tenant_id`·`scope_node_id` 가 있지만 그것으로 판정하지
      않는다. 그 값들은 만들 때 복사된 사본이고, 조직이 옮겨지면 **낡는다**."""
    row = store.get_snapshot(snapshot_id)
    if not row:
        #: 없는 것과 못 보는 것을 같은 문장으로 답한다
        raise HTTPException(status_code=404, detail="데이터 Snapshot 을 찾을 수 없습니다.")
    try:
        _instance_or_404(p, str(row.get("instance_id", "")))
    except HTTPException:
        raise HTTPException(status_code=404, detail="데이터 Snapshot 을 찾을 수 없습니다.")
    return row


def _binding_or_404(p: Principal, binding_id: str) -> Dict[str, Any]:
    row = store.get_binding(binding_id)
    if not row:
        raise HTTPException(status_code=404, detail="원천 결속을 찾을 수 없습니다.")
    _instance_or_404(p, str(row.get("instance_id", "")))   # 범위는 인스턴스가 판정한다
    return row


# ── 키트 ─────────────────────────────────────────────────────────────────
@router.get("/kits")
async def list_kits(p: Principal = Depends(current_principal)):
    """등록된 키트 판본. **템플릿이지 운영 계약이 아니다.**"""
    require_caps(p, PROJECT_RUN, resource="data_preparation", action="kits:list")
    try:
        kit_registry.register_all(store)      # 멱등 — 문서가 바뀌면 지문이 따라 바뀐다
    except m.DataPreparationError as e:
        #: ⚠️ 깨진 키트는 **조용히 건너뛰지 않는다.** 건너뛰면 「키트가 없다」와
        #:   「키트가 깨졌다」가 같은 화면이 된다.
        raise HTTPException(status_code=503, detail=f"키트를 읽을 수 없습니다: {e}")
    return {"status": "success", "data": {"kits": store.list_kit_versions()}}


@router.get("/kits/{kit_id}/versions/{version}")
async def get_kit_version(kit_id: str, version: str,
                          p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"kits:get:{kit_id}")
    row = kit_registry.resolve(store, kit_id, version)
    if not row:
        #: ⚠️ 모르는 버전에 최신을 주지 않는다 — 고른 것과 적용된 것이 달라지고,
        #:   그 차이는 데이터가 들어간 뒤에야 드러난다.
        raise HTTPException(status_code=404, detail="해당 키트 판본을 찾을 수 없습니다.")
    return {"status": "success",
            "data": {**row, "dataset_keys": kit_registry.dataset_keys(row.get("profile"))}}


# ── 인스턴스 ─────────────────────────────────────────────────────────────
@router.post("/instances")
async def create_instance(req: InstanceCreateRequest,
                          p: Principal = Depends(current_principal)):
    """키트를 조직에 적용한다. **명시 범위·모드 없이는 만들지 않는다.**"""
    require_caps(p, PROJECT_CREATE, resource="data_preparation", action="instances:create")
    ctx = _ctx(p)
    tenant_id = str(ctx.get("tenant_id", "") or "")

    scope = str(req.scope_node_id or "").strip()
    if not p.scope.unrestricted and scope not in _visible_scopes(p):
        _audit("ACCESS_DENIED_SCOPE_MISMATCH", resource_id=scope, actor=p.user_id or "",
               outcome="denied", reason="scope_not_visible")
        raise HTTPException(status_code=404, detail="요청한 조직 범위를 찾을 수 없습니다.")

    kit = kit_registry.resolve(store, req.kit_id, req.version)
    if not kit:
        raise HTTPException(status_code=404, detail="해당 키트 판본을 찾을 수 없습니다.")

    try:
        row = store.create_instance(
            kit_id=req.kit_id, version=req.version,
            kit_fingerprint=str(kit.get("fingerprint", "")),
            tenant_id=tenant_id, scope_node_id=scope,
            entity_mode=str(req.entity_mode or "").strip(),
            label=req.label, created_by=p.user_id or "")
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _audit("ENTERPRISE_CONTEXT_CHANGED", resource_id=row["instance_id"],
           actor=p.user_id or "", outcome="allowed",
           detail=f"kit={req.kit_id}@{req.version}")
    return {"status": "success", "data": row}


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"instances:get:{instance_id}")
    row = _instance_or_404(p, instance_id)
    kit = kit_registry.resolve(store, row["kit_id"], row["version"])
    keys = kit_registry.dataset_keys((kit or {}).get("profile"))
    return {"status": "success",
            "data": {**row,
                     "bindings": store.list_bindings(instance_id),
                     "coverage": source_binding.coverage(store, instance_id, keys)}}


# ── 원천 결속 ────────────────────────────────────────────────────────────
@router.post("/instances/{instance_id}/bindings")
async def create_binding(instance_id: str, req: BindingCreateRequest,
                         p: Principal = Depends(current_principal)):
    """결속 **후보**를 만든다 — 후보는 여럿일 수 있다(비교해 고르기 위해서)."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"bindings:create:{instance_id}")
    inst = _instance_or_404(p, instance_id)
    try:
        row = store.create_binding(
            instance_id=instance_id, dataset_contract_key=req.dataset_contract_key,
            provider=req.provider, config=req.config or {},
            tenant_id=inst["tenant_id"], scope_node_id=inst["scope_node_id"],
            entity_mode=inst["entity_mode"], created_by=p.user_id or "")
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit("DATA_REQUIREMENT_ACCEPTED", resource_id=row["binding_id"],
           actor=p.user_id or "", outcome="allowed",
           detail=f"{req.dataset_contract_key}@{req.provider}")
    return {"status": "success", "data": row}


@router.post("/bindings/{binding_id}/decision")
async def decide_binding(binding_id: str, req: BindingDecisionRequest,
                         p: Principal = Depends(current_principal)):
    """검증·승인·활성·차단. **상태 전이 규칙은 `models` 하나가 답한다.**"""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"bindings:decide:{binding_id}")
    _binding_or_404(p, binding_id)
    action = str(req.action or "").strip().upper()
    try:
        if action == "VALIDATE":
            row = source_binding.validate(store, binding_id)
        elif action == "APPROVE":
            row = source_binding.approve(store, binding_id)
        elif action == "ACTIVATE":
            row = source_binding.activate(store, binding_id)
        elif action == "BLOCK":
            row = source_binding.block(store, binding_id, req.reason)
        else:
            raise HTTPException(
                status_code=422,
                detail="action 은 VALIDATE · APPROVE · ACTIVATE · BLOCK 중 하나여야 합니다.")
    except m.StateConflict as e:
        _audit("PERMISSION_GRANTED", resource_id=binding_id, actor=p.user_id or "",
               outcome="denied", reason=str(e)[:200])
        raise HTTPException(status_code=409, detail=str(e))
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _audit("DATA_CONTRACT_PUBLISHED" if row.get("state") == m.ACTIVE
           else "DATA_REQUIREMENT_ACCEPTED",
           resource_id=binding_id, actor=p.user_id or "", outcome="allowed",
           detail=f"state={row.get('state')}")
    return {"status": "success", "data": row}


# ── 데이터 Snapshot ──────────────────────────────────────────────────────
@router.post("/bindings/{binding_id}/snapshots")
async def upload_snapshot(binding_id: str, file: UploadFile = File(...),
                          p: Principal = Depends(current_principal)):
    """파일 하나를 올려 `RAW` Snapshot 을 만든다.

    ★★★ **파싱에 실패하면 아무것도 남기지 않는다.** 「0행 Snapshot」이 남으면 그것은
      「데이터가 없다」로 읽히고, 그 위에서 돌아간 계산은 합계 0 을 낸다 — 그리고
      아무도 그것을 고장으로 보지 않는다. 그래서 실패는 **422** 이지 200 이 아니다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"snapshots:upload:{binding_id}")
    binding = _binding_or_404(p, binding_id)

    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다({len(payload)} 바이트) — "
                   f"{MAX_UPLOAD_BYTES} 바이트까지 받습니다.")
    try:
        row = snapshot_service.ingest(
            store, binding=binding, payload=payload,
            file_name=str(file.filename or ""), workspace_root=_raw_root(),
            created_by=p.user_id or "")
    except m.DataPreparationError as e:
        #: ⚠️ 사유를 뭉개지 않는다 — 「올라가지 않는다」만 남으면 사용자는 파일이
        #:   아니라 시스템을 의심한다.
        _audit("DATA_REQUIREMENT_ACCEPTED", resource_id=binding_id,
               actor=p.user_id or "", outcome="denied", reason=str(e)[:200])
        raise HTTPException(status_code=422, detail=str(e))

    _audit("DATA_REQUIREMENT_ACCEPTED", resource_id=row["snapshot_id"],
           actor=p.user_id or "", outcome="allowed",
           detail=f"rows={row.get('row_count')} checksum={row.get('checksum', '')[:12]}")
    return {"status": "success",
            "data": {**row, "display_label": snapshot_service.display_label(row)}}


@router.get("/instances/{instance_id}/snapshots")
async def list_snapshots(instance_id: str, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"snapshots:list:{instance_id}")
    _instance_or_404(p, instance_id)
    rows = store.list_snapshots(instance_id)
    return {"status": "success",
            "data": {"snapshots": [
                {**r, "display_label": snapshot_service.display_label(r)} for r in rows]}}


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str, p: Principal = Depends(current_principal)):
    """Snapshot 한 건. **화면 표시 문구를 서버가 준다.**

    ⚠️ 「시연용 합성 데이터」 표시를 화면마다 각자 붙이게 두면 한 화면에서 빠지고,
      그 화면의 숫자는 실적으로 읽힌다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"snapshots:get:{snapshot_id}")
    row = _snapshot_or_404(p, snapshot_id)
    return {"status": "success",
            "data": {**row, "display_label": snapshot_service.display_label(row)}}


# ── 준비도 ───────────────────────────────────────────────────────────────
#: ★ 인증판이 이보다 오래되면 `STALE`. **정책값이지 상수가 아니다** — 키트가
#:   `max_age_days` 를 선언하면 그쪽을 쓴다.
DEFAULT_MAX_AGE_DAYS = 30.0


@router.get("/instances/{instance_id}/readiness")
async def get_readiness(instance_id: str, p: Principal = Depends(current_principal)):
    """「지금 무엇까지 믿고 만들 수 있는가」. **결정론적이다** — 같은 입력이면 같은 답.

    ★★★ 권한 밖 결속·판의 **존재도 개수도** 응답에 넣지 않는다. 인스턴스가 보이지
      않으면 그 앞에서 404 로 끝나고, 보이면 그 안의 것은 전부 같은 범위다.
    ⚠️ 준비되지 않은 데이터를 0건으로 채우지 않는다 — 0건은 「없다」이고 여기서
      말해야 하는 것은 「아직 아니다」다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"readiness:get:{instance_id}")
    inst = _instance_or_404(p, instance_id)

    kit = kit_registry.resolve(store, inst["kit_id"], inst["version"])
    if not kit:
        #: ⚠️ 키트를 못 읽으면 **판정하지 않는다.** 빈 요구사항으로 판정하면 아무
        #:   데이터도 없는 인스턴스가 「전부 준비됨」으로 나온다.
        raise HTTPException(
            status_code=503,
            detail="이 인스턴스가 적용한 키트 판본을 읽을 수 없어 준비도를 판정할 수 "
                   "없습니다.")

    keys = kit_registry.dataset_keys(kit.get("profile"))
    bindings = {k: store.active_binding(instance_id, k) for k in keys}
    snapshots: Dict[str, List[Dict[str, Any]]] = {k: [] for k in keys}
    for row in store.list_snapshots(instance_id):
        key = str(row.get("dataset_contract_key") or "")
        if key in snapshots:
            snapshots[key].append(row)

    profile = kit.get("profile") or {}
    max_age = profile.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    try:
        result = readiness.evaluate_instance(
            contract_keys=keys, bindings=bindings, snapshots=snapshots,
            outputs=kit_registry.outputs(profile), now=_now_iso(),
            max_age_days=float(max_age) if max_age is not None else None,
            scope={"tenant_id": inst["tenant_id"], "scope_node_id": inst["scope_node_id"],
                   "entity_mode": inst["entity_mode"]})
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"status": "success",
            "data": {**result, "kit_id": inst["kit_id"], "version": inst["version"],
                     "instance_id": instance_id,
                     "data_kind": str(kit.get("mode") or "")}}
