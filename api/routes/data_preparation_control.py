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
import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.deps import Principal, current_principal, require_caps, viewing_context
from core.admin_capability import ADMIN_DATA_ACCESS, PROJECT_CREATE, PROJECT_RUN
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
class OwnershipApproveRequest(BaseModel):
    """★ `tenant_id`·`entity_mode` 를 **받지 않는다.** 서버가 문맥에서 파생한다 —
    받으면 남의 tenant 를 적어 보내는 경로가 열린다(이 파일의 다른 모델과 같은 규칙).

    ⚠️ `scope_node_id` 는 받는다. 한 사용자가 여러 범위를 볼 수 있고, **어느 범위의
      소유권인지**는 사용자가 정해야 한다. 다만 볼 수 있는 범위인지 서버가 확인한다."""
    dataset_contract_key: str
    scope_node_id: str
    owner_dept_id: str
    evidence_ref: str
    effective_from: str = ""
    effective_to: str = ""
    purpose: str = ""


class OwnershipRevokeRequest(BaseModel):
    """⚠️ 사유는 **필수**다. 「왜 내렸는가」가 없으면 다음 사람이 되살려야 할지 판단할 수
    없고, 그러면 아무도 손대지 않는다."""
    reason: str


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


def _all_scopes() -> List[str]:
    """무제한 주체 전용 — 지금 저장소에 있는 모든 범위 노드.

    ⚠️ 이것을 일반 경로에서 쓰면 범위 통제가 사라진다. `unrestricted` 분기에서만
      부른다."""
    with store.transaction() as conn:
        rows = conn.execute(
            "SELECT DISTINCT scope_node_id FROM kit_instances").fetchall()
    return [str(r[0]) for r in rows if str(r[0] or "")]


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
    try:
        packages = kit_registry.starter_package_catalog()
    except m.DataPreparationError as e:
        raise HTTPException(status_code=503, detail=f"샘플 패키지 카탈로그를 읽을 수 없습니다: {e}")
    return {"status": "success", "data": {
        # `kits` 는 조직 적용용 운영 템플릿. `starter_packages` 와 섞지 않는다.
        "kits": store.list_kit_versions(),
        "starter_packages": packages,
    }}


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


@router.get("/instances")
async def list_instances(p: Principal = Depends(current_principal)):
    """이 조직·문맥에서 **내가 볼 수 있는** 키트 인스턴스들.

    ★★★ 이 목록이 없으면 화면은 사용자에게 `ki_…` 를 «타이핑하라» 고 요구한다.
      기능은 도는데 사람이 시작할 수 없는 화면이 되고, 그것은 도는 것이 아니다.

    ⚠️ 범위 밖은 **개수조차** 세지 않는다 — `store.list_instances` 가 보이는 범위만
      묻고, 범위가 비면 빈 목록을 돌려준다(「비었으니 전부」가 아니다)."""
    require_caps(p, PROJECT_RUN, resource="data_preparation", action="instances:list")
    ctx = _ctx(p)
    scopes = _all_scopes() if p.scope.unrestricted else _visible_scopes(p)
    rows = store.list_instances(tenant_id=str(ctx.get("tenant_id", "")),
                                entity_mode=str(ctx.get("entity_mode", "")),
                                scope_node_ids=scopes)
    return {"status": "success", "data": {"instances": rows}}


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"instances:get:{instance_id}")
    row = _instance_or_404(p, instance_id)
    kit = kit_registry.resolve(store, row["kit_id"], row["version"])
    profile = (kit or {}).get("profile")
    keys = kit_registry.dataset_keys(profile)
    labels = kit_registry.dataset_labels(profile)
    #: ★★★ 계약이 요구하는 **전부**를 돌려준다 — 결속이 없는 것도 이름과 함께.
    #:   결속된 것만 보내면 화면은 「빠진 데이터」를 그릴 재료가 없고, 사용자는
    #:   무엇을 더 연결해야 하는지 이 화면에서 알 수 없다.
    bindings = store.list_bindings(instance_id)
    bound = {str(b.get("dataset_contract_key", "")) for b in bindings}
    required = [{"dataset_contract_key": k, "bound": k in bound, **labels.get(k, {})}
                for k in keys]
    return {"status": "success",
            "data": {**row, "bindings": bindings, "required_datasets": required,
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
    inst = _instance_or_404(p, instance_id)
    rows = store.list_snapshots(instance_id)
    #: ★ 계약이 선언한 이름을 함께 싣는다 — 화면이 `material_arrivals` 를 그대로
    #:   사람에게 보여 주지 않도록(설계 §12). 키트를 못 읽으면 이름칸은 **비운다**;
    #:   계약키를 이름칸에 복사하면 화면은 「이름이 없다」를 알 수 없다.
    kit = kit_registry.resolve(store, inst["kit_id"], inst["version"])
    labels = kit_registry.dataset_labels((kit or {}).get("profile"))
    return {"status": "success",
            "data": {"snapshots": [
                {**r, "display_label": snapshot_service.display_label(r),
                 **labels.get(str(r.get("dataset_contract_key", "")), {})}
                for r in rows]}}


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


def _ownership_scope_or_404(p: Principal, scope_node_id: str) -> Dict[str, Any]:
    """이 사용자가 **이 범위에** 소유권을 세울 수 있는가. 아니면 404 은폐.

    ★★★ 없는 범위와 못 보는 범위를 **같은 404** 로 돌려준다 — 다르게 답하면 그 응답이
      「그 조직이 존재한다」를 알려 주는 신호가 된다.
    ⚠️ 요청의 `scope_node_id` 를 그대로 믿지 않는다. 문맥은 서버가 파생하고, 범위는
      **볼 수 있는 목록 안에서만** 인정한다."""
    want = str(scope_node_id or "").strip()
    ctx = _ctx(p)
    ok = bool(want) and (p.scope.unrestricted or want in _visible_scopes(p))
    if not ok:
        _audit("ACCESS_DENIED_SCOPE_MISMATCH", resource_id=want or "(빈 범위)",
               actor=p.user_id or "", outcome="denied",
               reason="not_found_or_out_of_scope")
        raise HTTPException(status_code=404, detail="조직 범위를 찾을 수 없습니다.")
    return ctx


def _ownership_error_to_http(e: Exception) -> HTTPException:
    """소유권 예외를 경계표에 맞춰 옮긴다.

    ★ 「고칠 것이 없는데 고치라고 말하는」 응답을 만들지 않는다:
      · 권한·입력 문제 → 400(사용자가 고칠 수 있다)
      · 자료가 어긋났다 → 409(사람이 정리해야 한다)
      · 못 읽었다·장애 → 503(점검이 필요하다)
    ⚠️ 셋을 한 코드로 뭉개면 운영자가 무엇을 해야 하는지 알 수 없다."""
    from core.data_preparation import ownership_binding as _ob
    if isinstance(e, _ob.OwnershipUnavailable):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, _ob.OwnershipIntegrityError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


@router.post("/ownership/approve")
async def approve_ownership(req: OwnershipApproveRequest,
                            p: Principal = Depends(current_principal)):
    """★★★ [4.1c-D] **「어느 부서가 이 데이터셋을 소유하는가」를 승인한다.**

    이 경로가 없던 동안 소유권 결속을 만들 수 있는 것은 **시드와 마이그레이션뿐**이었다.
    즉 통제는 다 서 있는데 제품에서 부를 방법이 없었고, 격리된 데이터를 **복구할 길도
    없었다** — 이 저장소에서 이미 지적받은 「통제는 있는데 부르는 경로가 없다」와 같다.

    ## 두 단계를 한 요청으로 묶는다

    승인은 **원장 사건**이고 결속은 **정본 표**다. 다른 저장소이므로 한 트랜잭션으로
    묶을 수 없다. 그래서:

      ⓪ **이미 같은 승인이 서 있으면 그것을 돌려준다**(멱등 — 아래)
      ① `approve()` — 원장에 승인 사건을 남긴다(권한·근거 검증이 여기서 돈다)
      ② `declare()` — 그 사건 id 로 결속을 세운다
      ③ ②가 실패하면 **`abandon()` 으로 ①을 취소한다**

    ## ★★★ [4.1c-E P1-3] ⓪ 멱등이 없으면 재시도가 이력을 오염시킨다

    앞 판은 같은 요청을 두 번 받으면 **승인 사건을 두 개** 만들었다. `declare()` 는 같은
    지문의 결속을 멱등으로 돌려주므로 결속은 하나인데, 두 번째 승인 사건은 어느 결속에도
    연결되지 않아 미물질화 보고에 남는다 — **네트워크 재시도만으로 감사 이력이 오염된다.**

    ★ 그래서 먼저 «같은 문맥·계약·범위에 이미 유효한 결속이 있고, 부서·근거까지 같은가» 를
      본다. 같으면 그 결속을 그대로 돌려준다(원장에 아무것도 더 쓰지 않는다).
    ⚠️ **다르면 돌려주지 않는다** — 부서나 근거가 다르면 그것은 «개정» 이고, 기존 결속을
      먼저 철회해야 한다. 조용히 덮으면 누가 언제 무엇을 바꿨는지 사라진다.

    ## ★★★ [4.1c-E P1-4] ③이 실패하면 상태코드가 그 사실을 말해야 한다

    앞 판은 등록 실패의 예외(409)를 그대로 돌려줬다. 보상 취소까지 실패했다면 실제 상태는
    **원장 보상 실패**이고, 그것은 사람이 정리해야 하는 상태(503)다 — 409 로 답하면
    「입력을 고쳐 다시 하라」로 읽힌다."""
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action=f"ownership:approve:{req.dataset_contract_key}")
    from api.deps import assert_can_manage_standard
    #: ★ 라우트 층에서도 승인 권한을 요구한다. 핵심 층(`approve()`)이 다시 확인하지만,
    #:   여기서 막지 않으면 권한 없는 요청이 **원장 조회까지** 들어온다.
    #:
    #: ⚠️ **정직하게 적는다 — 이 줄은 지금 변이로 관측되지 않는다.** 실측(2026-08-21):
    #:     admin_only  can_manage_standard=True  admin.data_access=True
    #:     data_admin  can_manage_standard=True  admin.data_access=True
    #:     일반        can_manage_standard=False admin.data_access=False
    #:   즉 현재 조직도 규칙에서 두 축이 **완전히 겹친다**(`is_admin` 도 표준 승인권을
    #:   받는다). 그래서 위 `require_caps` 가 이미 같은 사람을 막고, 이 줄을 지워도
    #:   실패하는 시험이 없다. 가짜 시험을 지어 「검사가 있다」고 주장하지 않는다.
    #: ★ 그럼에도 남기는 이유: 두 검사는 **다른 질문**이다 — 표는 「이 탭을 쓸 수 있는가」,
    #:   이것은 「데이터 표준을 승인할 수 있는가」다. 조직도가 그 둘을 한 플래그에서
    #:   파생하는 것은 오늘의 구현 사실일 뿐이고, 갈리는 날 이 줄이 유일한 방어가 된다.
    #: ⚠️ 감사자가 판단할 사실 하나: **시스템 관리자(`is_admin`)도 데이터 소유권을 승인할
    #:   수 있다.** 조직도가 그렇게 정했으므로 여기서 다르게 정하지 않았다.
    assert_can_manage_standard(p)
    ctx = _ownership_scope_or_404(p, req.scope_node_id)
    from core.data_preparation import ownership_binding as _ob
    tenant = str(ctx.get("tenant_id", ""))
    mode = str(ctx.get("entity_mode", ""))

    #: ⓪ 멱등 — 같은 승인이 이미 서 있으면 원장에 아무것도 더 쓰지 않는다.
    try:
        with store.transaction() as conn:
            existing = _ob.resolve(conn, tenant_id=tenant, entity_mode=mode,
                                   dataset_contract_key=req.dataset_contract_key,
                                   scope_node_id=req.scope_node_id)
    except Exception as e:
        raise _ownership_error_to_http(e)
    if existing and str(existing.get("owner_dept_id")) == req.owner_dept_id \
            and str(existing.get("evidence_ref")) == req.evidence_ref:
        _audit("DATASET_OWNERSHIP_APPROVE_IDEMPOTENT",
               resource_id=req.dataset_contract_key, actor=p.user_id or "",
               outcome="success", detail=f"binding={existing['binding_id']}")
        return {"status": "success", "data": existing, "idempotent": True}

    try:
        ap = _ob.approve(
            tenant_id=tenant, entity_mode=mode,
            dataset_contract_key=req.dataset_contract_key,
            scope_node_id=req.scope_node_id, owner_dept_id=req.owner_dept_id,
            actor_id=p.user_id or "", evidence_ref=req.evidence_ref,
            effective_from=req.effective_from, effective_to=req.effective_to,
            purpose=req.purpose)
    except Exception as e:
        _audit("DATASET_OWNERSHIP_APPROVE_DENIED", resource_id=req.dataset_contract_key,
               actor=p.user_id or "", outcome="denied", reason=type(e).__name__,
               detail=str(e)[:300])
        raise _ownership_error_to_http(e)

    try:
        with store.transaction() as conn:
            row = _ob.declare(
                conn, tenant_id=tenant, entity_mode=mode,
                dataset_contract_key=req.dataset_contract_key,
                scope_node_id=req.scope_node_id, owner_dept_id=req.owner_dept_id,
                approved_by=p.user_id or "", evidence_ref=req.evidence_ref,
                approval_event_id=ap["approval_event_id"],
                effective_from=ap["effective_from"], effective_to=req.effective_to)
    except Exception as e:
        #: ★★★ 등록이 실패했으므로 **승인 사건을 취소한다.** 그러지 않으면 원장에
        #:   「승인」만 남는다.
        repair = False
        try:
            _ob.abandon(ap["approval_event_id"], p.user_id or "",
                        f"결속 등록 실패로 취소: {type(e).__name__}")
        except Exception as e2:
            #: ⚠️ 취소도 실패했다. **원래 예외의 상태코드를 그대로 쓰면 안 된다** —
            #:   실제 상태는 「입력이 틀렸다」가 아니라 「원장 보상이 실패해 정리가
            #:   필요하다」다(4.1c-E P1-4).
            repair = True
            _audit("DATASET_OWNERSHIP_REPAIR_REQUIRED",
                   resource_id=req.dataset_contract_key, actor=p.user_id or "",
                   outcome="error", reason=type(e2).__name__,
                   detail=f"approval={ap['approval_event_id']} | {str(e2)[:200]}")
        _audit("DATASET_OWNERSHIP_DECLARE_FAILED", resource_id=req.dataset_contract_key,
               actor=p.user_id or "", outcome="error", reason=type(e).__name__,
               detail=f"{str(e)[:200]} | approval={ap['approval_event_id']} | "
                      f"repair_required={repair}")
        if repair:
            raise HTTPException(
                status_code=503,
                detail={"error": "repair_required",
                        "message": "결속 등록이 실패했고 승인 사건 취소도 실패했습니다 — "
                                   "원장에 살아 있는 승인이 남았습니다. 미물질화 승인 "
                                   "목록에서 확인하고 취소해야 합니다.",
                        "approval_event_id": ap["approval_event_id"],
                        "declare_error": str(e)[:200]})
        raise _ownership_error_to_http(e)

    _audit("DATASET_OWNERSHIP_APPROVED", resource_id=req.dataset_contract_key,
           actor=p.user_id or "", outcome="success",
           detail=f"binding={row['binding_id']} dept={req.owner_dept_id}")
    return {"status": "success", "data": row}


@router.post("/ownership/{binding_id}/revoke")
async def revoke_ownership(binding_id: str, req: OwnershipRevokeRequest,
                           p: Principal = Depends(current_principal)):
    """소유권 결속을 철회한다. **행을 지우지 않는다** — 무엇이 있었는지는 남아야 한다.

    ⚠️ 철회는 승인보다 **조용하다.** 소유권이 내려가면 그 데이터는 아무에게도 안 보이고,
      「안 보인다」는 아무도 신고하지 않는다. 그래서 승인과 같은 권한과 사유를 요구한다.
    ★★★ 보이지 않는 결속은 **404** 로 답한다 — 403 은 「그것이 존재한다」를 알려 준다."""
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action=f"ownership:revoke:{binding_id}")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    from core.data_preparation import ownership_binding as _ob
    ctx = _ctx(p)
    try:
        with store.transaction() as conn:
            row = next((r for r in _ob.list_bindings(conn)
                        if r["binding_id"] == binding_id), None)
            visible = bool(row) and (
                p.scope.unrestricted or (
                    str(row["tenant_id"]) == str(ctx.get("tenant_id", "")) and
                    str(row["entity_mode"]) == str(ctx.get("entity_mode", "")) and
                    str(row["scope_node_id"]) in _visible_scopes(p)))
            if not visible:
                _audit("ACCESS_DENIED_SCOPE_MISMATCH", resource_id=binding_id,
                       actor=p.user_id or "", outcome="denied",
                       reason="not_found_or_out_of_scope", detail=f"exists={bool(row)}")
                raise HTTPException(status_code=404,
                                    detail="소유권 결속을 찾을 수 없습니다.")
            ok = _ob.revoke(conn, binding_id, p.user_id or "", req.reason)
    except HTTPException:
        raise
    except Exception as e:
        _audit("DATASET_OWNERSHIP_REVOKE_DENIED", resource_id=binding_id,
               actor=p.user_id or "", outcome="denied", reason=type(e).__name__,
               detail=str(e)[:300])
        raise _ownership_error_to_http(e)
    if not ok:
        #: 이미 철회됐다 — 「지금 상태에서 할 수 없는 일」이므로 409 다(404 는 존재를 부정한다).
        raise HTTPException(status_code=409, detail="이미 철회된 결속입니다.")
    _audit("DATASET_OWNERSHIP_REVOKED", resource_id=binding_id, actor=p.user_id or "",
           outcome="success", detail=f"reason={req.reason[:120]}")
    return {"status": "success",
            "data": {"binding_id": binding_id, "status": _ob.REVOKED}}


@router.get("/ownership")
async def list_ownership(p: Principal = Depends(current_principal)):
    """지금 보는 문맥의 소유권 결속 · **미물질화 승인** · 격리 · **불일치** 현황.

    ★★★ 권한 밖 자원의 **존재도 개수도** 응답에 넣지 않는다. 보이는 범위로 먼저 거르고,
      거른 뒤의 수만 센다 — 「권한 밖 3건」을 세어 주면 그 3이 곧 「그 조직에 3건이
      있다」가 된다.

    ⚠️⚠️ [4.1c-E P0-1] 앞 판은 결속과 격리만 걸렀고 **미물질화 승인은 원장 전체**를
      돌려줬다. 그래서 A 조직 관리자가 B 조직의 승인 ID·행위자·대상 지문과 건수를 볼 수
      있었다 — **한 응답 안에서 필터가 갈렸다.** 이제 범위를 핵심 층에 넘기고, 그 함수는
      범위 인자를 **필수**로 요구한다(빠뜨리면 조용히 전체를 보는 대신 오류가 난다).

    ⚠️ 원장을 못 읽으면 **503** 이다. 「미물질화 0건」은 아무 문제 없다는 뜻이고, 그 화면을
      보고 아무도 고치러 가지 않는다."""
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action="ownership:list")
    #: ★★ [4.1c-E P1-7] 격리 조회와 **같은 권한 정책**을 쓴다. 두 응답에 같은 종류의
    #:   정보(어느 부서가 소유자로 주장됐는가)가 들어 있는데 정책이 갈리면, 느슨한 쪽이
    #:   우회 경로가 된다.
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    from core.data_preparation import ownership_binding as _ob
    ctx = _ctx(p)
    tenant, mode = str(ctx.get("tenant_id", "")), str(ctx.get("entity_mode", ""))
    visible = set(_visible_scopes(p))
    with store.transaction() as conn:
        rows = _ob.list_bindings(conn, tenant_id=tenant)
        if not p.scope.unrestricted:
            rows = [r for r in rows
                    if str(r["entity_mode"]) == mode
                    and str(r["scope_node_id"]) in visible]
        try:
            dangling = _ob.dangling_approvals(
                conn, tenant_id=tenant, entity_mode=mode,
                unrestricted=bool(p.scope.unrestricted),
                readable_dept_ids=p.scope.readable_dept_ids or (),
                actor_id=p.user_id or "")
            #: ★★★ [4.1c-E P1-5] **표와 원장이 어긋난 결속을 드러낸다.**
            #:   철회가 원장에는 기록됐는데 정본 갱신이 실패하면, 판정은 fail-closed 로
            #:   막히지만 **목록에는 ACTIVE 로 보인다** — 두 화면이 다른 말을 한다.
            mismatched = _ob.ledger_mismatches(conn, rows)
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))
        quarantine = _ob.quarantine_state(conn)
    if not p.scope.unrestricted:
        #: ⚠️ 격리 목록도 같은 규칙으로 거른다. 여기서 새면 위 필터가 무의미하다.
        items = [i for i in quarantine["items"] if str(i["scope_node_id"]) in visible]
        by_key: Dict[str, int] = {}
        for i in items:
            k = str(i["dataset_contract_key"])
            by_key[k] = by_key.get(k, 0) + 1
        quarantine = {"unresolved": len(items), "by_contract_key": by_key, "items": items}
    return {"status": "success",
            "data": {"bindings": rows, "dangling_approvals": dangling,
                     "quarantine": quarantine, "ledger_mismatches": mismatched}}


@router.post("/ownership/{binding_id}/reconcile")
async def reconcile_ownership(binding_id: str,
                              p: Principal = Depends(current_principal)):
    """★★★ [4.1c-E P1-5] **원장을 정본으로 삼아 표를 맞춘다.**

    철회는 두 단계다: 원장에 철회 사건을 남기고, 정본 표를 `REVOKED` 로 바꾼다. 두 번째가
    실패하면 **원장에는 철회, 표에는 `ACTIVE`** 가 남는다.

    ⚠️ 권한 판정은 그 상태에서도 안전하다(요청마다 철회 자식을 다시 보므로 fail-closed).
      위험한 것은 **두 화면이 다른 말을 하는 것**이다 — 목록에는 살아 있고 판정은 막는다.
      그러면 운영자는 「왜 안 보이나」를 영원히 못 찾는다.

    ★ 그래서 재조정은 **원장을 정본으로** 표를 맞춘다. 반대 방향(표를 보고 원장을 고치기)은
      절대 하지 않는다 — 원장은 덮어쓸 수 없는 곳이어야 하고, 그것이 원장의 유일한 값이다."""
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action=f"ownership:reconcile:{binding_id}")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    from core.data_preparation import ownership_binding as _ob
    ctx = _ctx(p)
    with store.transaction() as conn:
        row = next((r for r in _ob.list_bindings(conn)
                    if r["binding_id"] == binding_id), None)
        visible = bool(row) and (
            p.scope.unrestricted or (
                str(row["tenant_id"]) == str(ctx.get("tenant_id", "")) and
                str(row["entity_mode"]) == str(ctx.get("entity_mode", "")) and
                str(row["scope_node_id"]) in _visible_scopes(p)))
        if not visible:
            _audit("ACCESS_DENIED_SCOPE_MISMATCH", resource_id=binding_id,
                   actor=p.user_id or "", outcome="denied",
                   reason="not_found_or_out_of_scope", detail=f"exists={bool(row)}")
            raise HTTPException(status_code=404, detail="소유권 결속을 찾을 수 없습니다.")
        try:
            fixed = _ob.reconcile_with_ledger(conn, binding_id)
        except Exception as e:
            raise _ownership_error_to_http(e)
    if not fixed:
        #: 어긋난 것이 없다 — 고칠 것이 없는데 고쳤다고 말하지 않는다.
        raise HTTPException(status_code=409, detail="이 결속은 원장과 어긋나지 않았습니다.")
    _audit("DATASET_OWNERSHIP_RECONCILED", resource_id=binding_id, actor=p.user_id or "",
           outcome="success", detail=f"applied={fixed}")
    return {"status": "success", "data": {"binding_id": binding_id, "applied": fixed}}


@router.get("/ownership/quarantine")
async def list_ownership_quarantine(p: Principal = Depends(current_principal)):
    """★★★ [4.1c-C P1-1] **승인 근거 없이 격리된 구버전 소유권 결속.**

    ⚠️ 앞 판은 격리하면서 기동 로그에 `print` 만 남겼다. 그러면 서비스는 빈 새 표로 계속
      가동되고, **모든 데이터가 UNBOUND 가 된 이유를 운영자가 화면에서 알 수 없다.**
      로그는 다음 재시작에 사라지고, 그때부터는 「원래 소유자가 없었다」와 구분되지 않는다.
    ★ 재승인이 끝날 때까지 해제되지 않는다 — 해제 근거는 **승인된 결속이 실제로 생겼다**는
      사실뿐이고, 「관리자가 확인했다」는 다시 자기진술이 된다.
    ⚠️ 기준정보·데이터 표준 승인 권한자 전용이다. 격리 목록에는 **어느 부서가 소유자라고
      주장돼 있었는지**가 들어 있어, 조직 구조를 읽는 것과 같다."""
    #: ★★ [4.1c-E P1-7] 일반 목록과 **같은 권한 정책**이다. 정책이 갈리면 느슨한 쪽이
    #:   우회 경로가 된다 — 두 응답에 같은 종류의 정보가 들어 있다.
    #: ⚠️ 정직하게: 이 줄은 아래 `assert_can_manage_standard` 와 **등가**여서 지워도
    #:   실패하는 시험이 없다(실측 — 두 권한 축이 현재 조직도에서 겹친다). 남기는 이유는
    #:   ① 두 라우트의 정책 «선언» 이 코드에서 같아 보여야 하고 ② 축이 갈리는 날 감사
    #:   기록(`require_caps` 가 남기는 거부 이력)이 여기서 나온다는 것이다.
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action="ownership:quarantine")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    from core.data_preparation import ownership_binding as _ob
    with store.transaction() as conn:
        state = _ob.quarantine_state(conn)
    return {"status": "success", "data": state}


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
    #: ★★★ [4.1c-C P1-1] **구버전 소유권 격리를 준비도에 싣는다.**
    #:
    #: ⚠️ 앞 판은 격리하면서 기동 로그에 `print` 만 남겼다. 그러면 서비스는 빈 새 표로
    #:   계속 가동되고, **모든 데이터가 UNBOUND 가 된 이유를 운영자가 화면에서 알 수
    #:   없다.** 로그는 다음 재시작에 사라지고, 그때부터는 「원래 소유자가 없었다」와
    #:   구분되지 않는다.
    from core.data_preparation import ownership_binding as _ob
    with store.transaction() as _c:
        _q = _ob.quarantine_state(_c)
    quarantined = {k: v for k, v in (_q.get("by_contract_key") or {}).items() if k in keys}
    try:
        result = readiness.evaluate_instance(
            contract_keys=keys, bindings=bindings, snapshots=snapshots,
            outputs=kit_registry.outputs(profile), now=_now_iso(),
            max_age_days=float(max_age) if max_age is not None else None,
            scope={"tenant_id": inst["tenant_id"], "scope_node_id": inst["scope_node_id"],
                   "entity_mode": inst["entity_mode"]},
            ownership_quarantined=quarantined)
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    #: ★ 이름을 함께 싣는다 — 화면이 `material_arrivals` 를 그대로 사람에게 보여
    #:   주지 않도록. 이름은 계약과 함께 살아야 화면마다 달라지지 않는다.
    labels = kit_registry.dataset_labels(profile)
    from core.data_preparation.business_kits import classify_dataset
    datasets = [
        {**d, **labels.get(str(d.get("dataset_contract_key", "")), {}),
         **classify_dataset(str(d.get("dataset_contract_key", "")))}
        for d in (result.get("datasets") or [])
    ]
    return {"status": "success",
            "data": {**result, "datasets": datasets,
                     "kit_id": inst["kit_id"], "version": inst["version"],
                     "instance_id": instance_id,
                     "data_kind": str(kit.get("mode") or "")}}


class PipelineRequest(BaseModel):
    """판 하나를 인증까지 돌린다.

    ★ `control` 은 **원천이 말한 값**이다(행 수·합계). 이것이 없으면 「잘린 파일」을
      잡을 방법이 없다 — 그래서 선택이 아니라 요청의 일부다.
    ⚠️ 비워서 보내도 받는다. 다만 그때는 대사가 «건너뛴 것» 이고, 그 사실이 판에
      남는다(조용히 통과시키지 않는다)."""
    control: Dict[str, Any] = {}
    code_columns: Dict[str, List[str]] = {}
    unit_columns: Dict[str, str] = {}
    expected_units: Dict[str, str] = {}


@router.post("/snapshots/{snapshot_id}/certify")
async def certify_snapshot(snapshot_id: str, req: PipelineRequest,
                           p: Principal = Depends(current_principal)):
    """[BDR-3] 올라온 판을 **프로파일 → 표준화 → 대사 → 시연 인증**까지 돌린다.

    ★★★ 어느 단계에서 격리되면 **거기서 멈춘다** — 격리된 판을 인증하지 않는다.
    ⚠️ 이 인증은 «시연용 합성 데이터로서 검증되었다» 이지 실적 인증이 아니다.
      `REAL` 데이터에는 붙지 않는다(`snapshot_service.certify_demo` 가 막는다)."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"snapshots:certify:{snapshot_id}")
    row = _snapshot_or_404(p, snapshot_id)

    #: 원문을 다시 읽어 행을 만든다 — 판정은 **보관된 그 파일**로 한다.
    raw_path = str(row.get("raw_path") or "")
    if not raw_path or not snapshot_service.verify_raw(
            raw_path, str(row.get("checksum") or "")):
        #: ⚠️ 「그때 그 파일」이라는 전제가 깨졌다 — 숫자를 내보내지 않는다.
        raise HTTPException(
            status_code=409,
            detail="보관된 원본이 등록 당시와 다릅니다 — 이 판은 인증할 수 없습니다.")
    try:
        with open(raw_path, "rb") as f:
            parsed = snapshot_service.parse_csv(f.read())
    except (OSError, m.DataPreparationError) as e:
        raise HTTPException(status_code=503,
                            detail=f"원본을 읽을 수 없습니다: {str(e)[:120]}")

    try:
        out = snapshot_service.run_pipeline(
            store, snapshot_id, parsed.rows, parsed.columns,
            control=req.control or {}, code_columns=req.code_columns or {},
            unit_columns=req.unit_columns or {},
            expected_units=req.expected_units or {})
    except m.StateConflict as e:
        #: 「지금 상태에서 할 수 없는 일」 — 이미 인증됐거나 격리된 판이다.
        raise HTTPException(status_code=409, detail=str(e))
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _audit("DATA_CONTRACT_PUBLISHED" if out.get("state") == m.DEMO_CERTIFIED
           else "DATA_REQUIREMENT_ACCEPTED",
           resource_id=snapshot_id, actor=p.user_id or "",
           outcome="allowed" if out.get("state") == m.DEMO_CERTIFIED else "denied",
           detail=f"state={out.get('state')}")
    return {"status": "success",
            "data": {**out,
                     "display_label": snapshot_service.display_label(out)}}


# ══════════════════════════════════════════════════════════════════════════
# 키트로 앱 만들기 — 초안 → 승인 → 물질화 (2026-08-23)
#
# ⚠️⚠️ 이 세 경로가 없던 동안 준비도 보드는 `READY` 를 그렸고 **누를 것이 없었다.**
#   통제는 다 서 있었는데 부르는 경로가 없었다 — 소유권 승인(4.1c-D)과 같은 결함이다.
#   「보여 주는 것」과 「되는 것」이 다르면, 보여 주는 쪽이 거짓말을 한다.
# ══════════════════════════════════════════════════════════════════════════

class AppContractDraftRequest(BaseModel):
    """★ `app_class` 를 **받는다.** `app_manifest` 가 「모르면 departmental 로 두지 않고
    비워 둔다 — 추측한 분류는 나중에 권한 판단의 근거로 쓰인다」라고 적어 두었다."""
    app_class: str = ""


class AppContractApproveRequest(BaseModel):
    """⚠️ 근거는 **필수**다. 「왜 이 앱을 열었나」에 답할 수 없는 승인은 나중에 아무도
    뒤집지 못한다(소유권 승인의 `evidence_ref` 와 같은 규칙)."""
    revision: int
    rationale: str


def _blueprint_or_404(profile: Dict[str, Any], app_id: str) -> Dict[str, Any]:
    """키트 등록부의 산출물 → 청사진.

    ★★★ **파일을 다시 읽지 않는다.** 등록부가 이미 정규화해 들고 있다 — 파일을 또
      읽으면 등록 당시의 판본과 지금 디스크의 판본이 갈릴 수 있다.
    ⚠️ 못 찾으면 404 다. 「없는 산출물」을 빈 청사진으로 바꾸면 데이터 0개 앱이 생긴다."""
    for row in kit_registry.outputs(profile):
        if str(row.get("output")) == app_id:
            return {"app_id": app_id, "name": str(row.get("label") or app_id),
                    "datasets": list(row.get("requires") or [])}
    raise HTTPException(status_code=404,
                        detail="이 키트에 그런 산출물이 없습니다.")


def _kit_profile_or_503(inst: Dict[str, Any]) -> Dict[str, Any]:
    kit = kit_registry.resolve(store, inst["kit_id"], inst["version"])
    if not kit:
        #: ⚠️ 키트를 못 읽으면 **아무것도 만들지 않는다.** 빈 요구사항으로 만들면
        #:   데이터가 하나도 없는 앱이 「정상」으로 생긴다.
        raise HTTPException(
            status_code=503,
            detail="이 인스턴스가 적용한 키트 판본을 읽을 수 없어 앱을 만들 수 없습니다.")
    return kit.get("profile") or {}


def _app_readiness(inst: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """준비도 판정. ★ **한 곳에서만** 조립한다 — 두 라우트가 각자 조립하면 언젠가
    한쪽만 고쳐지고, 그때 화면과 생성이 다른 답을 낸다."""
    instance_id = str(inst["instance_id"])
    keys = kit_registry.dataset_keys(profile)
    snapshots: Dict[str, List[Dict[str, Any]]] = {k: [] for k in keys}
    for row in store.list_snapshots(instance_id):
        key = str(row.get("dataset_contract_key") or "")
        if key in snapshots:
            snapshots[key].append(row)
    max_age = profile.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    try:
        return readiness.evaluate_instance(
            contract_keys=keys,
            bindings={k: store.active_binding(instance_id, k) for k in keys},
            snapshots=snapshots, outputs=kit_registry.outputs(profile),
            now=_now_iso(),
            max_age_days=float(max_age) if max_age is not None else None,
            scope={"tenant_id": inst["tenant_id"], "scope_node_id": inst["scope_node_id"],
                   "entity_mode": inst["entity_mode"]})
    except m.DataPreparationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/instances/{instance_id}/apps")
async def list_apps(instance_id: str, p: Principal = Depends(current_principal)):
    """이 인스턴스에서 **지금 무엇을 만들 수 있고 무엇이 이미 있는가.**

    ★ 준비도(만들 수 있는가)와 계약(승인됐는가)을 **한 줄에** 싣는다 — 두 화면으로
      나누면 사용자가 「준비는 됐는데 왜 안 되지」를 스스로 이어 붙여야 한다.
    ⚠️ 계약이 없는 것을 «괜찮음» 으로 그리지 않는다. `contract_status` 가 `null` 이다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"apps:list:{instance_id}")
    inst = _instance_or_404(p, instance_id)
    profile = _kit_profile_or_503(inst)

    from core import kit_app_contract as kac
    contracts: Dict[str, Dict[str, Any]] = {}
    for row in kac.list_for_instance(store, instance_id):
        #: ★ 앱마다 **가장 최근 개정 하나**만 화면에 준다(목록이 revision DESC 다).
        contracts.setdefault(str(row["app_id"]), row)

    #: ★★★ [2026-08-23 실측] **「이미 만들어졌는가」를 함께 싣는다.**
    #:
    #: ⚠️⚠️ 종전 판은 계약 상태만 줬다. 그래서 「앱 만들기」를 눌러 200 이 와도 목록은
    #:   **아무 변화가 없었고**, 사용자는 눌린 건지 알 수 없었다 — 「보여 주는 것과
    #:   되는 것이 다르다」의 반대 방향이다(된 것을 안 보여 준다).
    #: ★ 응답의 「만들었다」를 믿지 않고 **결속을 직접 센다** — 그것이 사실이다.
    from core import app_contract_gate as _gate
    from core import app_preview as _preview
    from core import kit_app_builder as _kb
    _plane = _preview.app_data_for(_preview.AUDIENCE_PREVIEW)

    result = _app_readiness(inst, profile)
    apps = []
    for row in (result.get("outputs") or []):
        app_id = str(row.get("output") or "")
        c = contracts.get(app_id)
        apps.append({
            "app_id": app_id, "label": str(row.get("label") or ""),
            "readiness_state": str(row.get("state") or ""),
            "user_message": str(row.get("user_message") or ""),
            "next_action": str(row.get("next_action") or ""),
            #: ★ 셋을 **따로** 싣는다. 「계약 없음」·「승인 대기」·「승인됨」은 서로 다른
            #:   사실이고, 하나로 뭉개면 화면이 다음 할 일을 말해 줄 수 없다.
            "contract_status": (str(c["status"]) if c else None),
            "contract_revision": (int(c["revision"]) if c else None),
            "drafted_by": (str(c.get("drafted_by") or "") if c else ""),
            "approved_by": (str(c.get("approved_by") or "") if c else ""),
            "release_id": _kb.release_id_for(instance_id, app_id),
            #: ★★★ **후보인가 운영인가.** 만든 앱은 시연 평면의 후보 판이고, 실제 업무
            #:   데이터를 읽으려면 운영으로 올려야 한다. 이 값이 없으면 화면은 「만들었다」
            #:   에서 멈추고 다음 할 일을 말해 줄 수 없다.
            "lifecycle_state": _lifecycle_state(
                _kb.release_id_for(instance_id, app_id)),
            #: ⚠️ 못 읽으면 **0 으로 채우지 않는다.** 0 은 「안 만들어졌다」이고,
            #:   여기서 말해야 하는 것은 「지금 확인하지 못했다」다.
            "built_datasets": _built_count(_gate, _plane, instance_id, app_id),
        })
    return {"status": "success",
            "data": {"instance_id": instance_id, "apps": apps}}


class AppPromoteRequest(BaseModel):
    """⚠️ 사유는 **필수**다 — 「왜 운영으로 올렸나」에 답할 수 없는 승격은 나중에
    아무도 뒤집지 못한다(계약 승인과 같은 규칙)."""
    reason: str


@router.post("/instances/{instance_id}/apps/{app_id}/promote")
async def promote_app(instance_id: str, app_id: str, req: AppPromoteRequest,
                      p: Principal = Depends(current_principal)):
    """[2026-08-24] 만든 앱을 **운영으로 올린다** — 그래야 실제 업무 데이터를 읽는다.

    ## 왜 이 라우트가 따로 있는가

    `factory_control` 의 승격은 `/{project_id}/releases/{release_id}/promote` 이고
    `assert_project_writable(p, project_id)` 로 **공장 프로젝트 작업공간**을 요구한다.
    업무 키트 앱에는 그런 작업공간이 없다 — 청사진과 승인된 계약뿐이다.

    ★★★ 그렇다고 검사를 건너뛰지 않는다. **같은 `release_promotion.promote()`** 를
      부른다: 상태·계약↔물질화·정적 검사·계약 승인·데이터 준비도 다섯 가지를 그대로
      본다. 면제를 만들면 그 면제가 곧 승격 게이트의 구멍이 된다.

    ## 왜 승격이 필요한가 (2026-08-24 실측)

    앱을 만들면 데이터셋은 **시연 평면**에 물질화된다. 그런데 후보 판의 앱 증명은
    `SYNTHETIC_TEST` 문맥에서만 발급되고(`app_preview.assert_preview_context`),
    업무 키트 인스턴스는 `REAL` 이다. 그래서 만든 앱을 열면 표는 보이는데 **레코드가
    0** 이었다 — 실제 인증판을 읽는 통로가 운영 청중에만 있기 때문이다.
    """
    #: ★ 운영으로 올리는 일이다 — 계약 승인과 **같은 권한**을 요구한다.
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action=f"apps:promote:{instance_id}/{app_id}")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    inst = _instance_or_404(p, instance_id)
    profile = _kit_profile_or_503(inst)
    _blueprint_or_404(profile, app_id)
    #: ⚠️⚠️ 사유를 **여기서 막는다.** 모델 주석에 「필수」라고 적어 두고 검사가 없었다 —
    #:   `release_promotion.promote()` 는 빈 사유를 기본 문구로 채우므로 그대로 통과했다
    #:   (2026-08-24 실측). 주석이 코드를 대신 주장하면 안 된다.
    if not str(req.reason or "").strip():
        raise HTTPException(
            status_code=422,
            detail="운영 전환 근거가 필요합니다 — 「왜 지금 이 앱을 운영에 올리는가」에 "
                   "답할 수 없는 승격은 나중에 아무도 뒤집지 못합니다.")

    import json as _json

    from core import app_preview, library_paths, release_promotion
    from core import kit_app_builder as kb
    from core.program_lifecycle import program_lifecycle

    release_id = kb.release_id_for(instance_id, app_id)
    path = library_paths.release_json(release_id)
    if not os.path.exists(path):
        #: ⚠️ 「아직 안 만들었다」는 409 다 — 404 로 답하면 앱 자체가 없는 것으로 읽힌다.
        raise HTTPException(
            status_code=409,
            detail="아직 만들어지지 않은 앱입니다 — 계약을 승인하고 «앱 만들기» 를 "
                   "누른 뒤에 운영으로 올릴 수 있습니다.")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            release = _json.load(fh)
    except Exception as exc:
        #: ⚠️ 판독 실패는 «없다» 가 아니다 — 서버 상태 이상이고 사용자가 고칠 수 없다.
        raise HTTPException(status_code=503,
                            detail=f"릴리스를 읽을 수 없습니다: {str(exc)[:120]}")

    #: ★★★ 준비도는 **판정하지 않고 넘긴다.** `release_promotion` 이 「확인하지 못한
    #:   것을 «준비됨» 으로 세지 않는다」로 막는다.
    #:
    #: ⚠️⚠️ [2026-08-24 실측] 처음엔 `_app_readiness(inst, profile)` 를 그대로 넘겼다.
    #:   그것은 **키트 전체**의 준비도라서, APP-01 이 읽는 자료가 다 준비돼 있어도
    #:   APP-03 이 쓰는 `INV-02` 가 없으면 APP-01 승격이 막혔다 — 그 앱과 무관한
    #:   이유로 막는 게이트는 사람이 고칠 수 없다(무엇을 고쳐야 할지 안 맞는다).
    #: ★ `factory_control._release_readiness_state` 도 그 릴리스가 **실제로 읽는 것**만
    #:   본다. 같은 규칙을 쓴다.
    readiness_state = _app_data_readiness(inst, profile, app_id)

    def _materialize_operational() -> None:
        """★★★ 운영 평면에 **같은 계약으로** 물질화한다.

        ⚠️ 실패하면 `promote()` 가 상태를 바꾸지 않는다 — 「운영이라고 적혀 있는데
          읽을 데이터가 없는 판」을 만들지 않기 위해서다."""
        from core import app_contract_gate, contract_materializer as cm

        contract = app_contract_gate.release_contract(release)
        if not contract:
            raise HTTPException(status_code=409,
                                detail="릴리스에 봉인된 계약이 없습니다.")
        cm.materialize(contract, release_id=release_id, actor_id=p.user_id or "",
                       store=store,
                       app_data=app_preview.app_data_for(
                           app_preview.AUDIENCE_OPERATIONAL),
                       tenant_id=str(inst["tenant_id"]),
                       scope_node_id=str(inst["scope_node_id"]),
                       entity_mode=str(inst["entity_mode"]))

    try:
        out = await asyncio.to_thread(
            release_promotion.promote,
            release=release, release_id=release_id, lifecycle=program_lifecycle,
            actor=(p.user_id or ""), code_paths=[library_paths.release_dir(release_id)],
            readiness_state=readiness_state, reason=req.reason,
            #: ★★★ 검사는 **후보가 사는 평면**으로, 물질화는 **운영 평면**에.
            #: ⚠️ 운영 평면으로 대조하면 「계약에 있는 데이터셋이 물질화되지
            #:   않았습니다」로 모든 승격이 막힌다(`_check_contract` 의 실측 주석).
            plane=app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW),
            on_promote=_materialize_operational)
    except release_promotion.PromotionError as exc:
        #: ⚠️ 「지금 상태에서 할 수 없는 일」은 409 다 — 422 로 주면 사용자가 요청을
        #:   고쳐 보려 하는데, 고칠 것은 요청이 아니라 판의 상태다.
        _audit("APP_RELEASE_PROMOTED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="denied", reason=str(exc)[:200])
        raise HTTPException(status_code=409, detail=str(exc))

    #: 승격 사실을 릴리스에도 남긴다 — 「언제 운영이 됐나」는 파일이 답해야 한다.
    release["lifecycle_state"] = out["status"]
    release["promoted_by"] = p.user_id or ""
    release["promoted_at"] = _now_iso()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(release, fh, ensure_ascii=False, indent=2)
    except Exception:                       # pragma: no cover - 파일 기록 실패
        #: ⚠️ 상태는 이미 바뀌었다. 파일 기록 실패로 승격을 되돌리지 않는다 —
        #:   되돌리면 「운영인데 파일은 후보」보다 더 나쁜 상태가 된다.
        _audit("APP_RELEASE_PROMOTED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="allowed",
               detail=f"release={release_id} 상태는 바뀌었으나 파일 기록 실패")
        return {"status": "success", "data": out}
    _audit("APP_RELEASE_PROMOTED", resource_id=f"{instance_id}/{app_id}",
           actor=p.user_id or "", outcome="allowed",
           detail=f"release={release_id} status={out.get('status')}")
    return {"status": "success", "data": out}


def _app_data_readiness(inst: Dict[str, Any], profile: Dict[str, Any],
                        app_id: str) -> Any:
    """**이 앱이 읽는 자료만** 본 준비도.

    ⚠️ 산출물 선언에 요구 목록이 없으면 `None` 을 돌려준다 — 「확인하지 못했다」이고,
      `release_promotion._check_readiness` 가 그것을 «준비됨» 으로 세지 않는다.
      여기서 `NOT_APPLICABLE` 로 접으면 요구 선언이 빠진 키트가 조용히 승격된다."""
    needs = [str(k).strip()
             for spec in kit_registry.outputs(profile)
             if str(spec.get("output") or "") == app_id
             for k in (spec.get("requires") or []) if str(k).strip()]
    if not needs:
        return None
    instance_id = str(inst["instance_id"])
    snapshots: Dict[str, List[Dict[str, Any]]] = {k: [] for k in needs}
    for row in store.list_snapshots(instance_id):
        key = str(row.get("dataset_contract_key") or "")
        if key in snapshots:
            snapshots[key].append(row)
    max_age = profile.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    try:
        return readiness.evaluate_instance(
            contract_keys=needs,
            bindings={k: store.active_binding(instance_id, k) for k in needs},
            snapshots=snapshots, outputs=[], now=_now_iso(),
            max_age_days=float(max_age) if max_age is not None else None,
            scope={"tenant_id": inst["tenant_id"], "scope_node_id": inst["scope_node_id"],
                   "entity_mode": inst["entity_mode"]})
    except m.DataPreparationError:
        #: ⚠️ 확인하지 못한 것을 «해당 없음» 으로 바꾸지 않는다.
        return None


def _lifecycle_state(release_id: str) -> str:
    """이 릴리스가 **후보인가 운영인가.** 아직 안 만들었으면 빈 문자열.

    ⚠️ 미기록을 `active` 로 그리지 않는다 — `program_lifecycle` 은 하위호환을 위해
      미기록을 `active` 로 답하지만, 여기서는 「아직 만들지 않았다」와 「운영이다」가
      **다른 사실**이다. 뭉개면 화면이 승격 버튼을 숨긴다."""
    from core import library_paths
    from core.program_lifecycle import program_lifecycle

    if not os.path.exists(library_paths.release_json(release_id)):
        return ""
    try:
        return str(program_lifecycle.get_status(release_id).get("status") or "")
    except Exception:                          # pragma: no cover - 상태 조회 실패
        return ""


def _built_count(gate: Any, plane: Any, instance_id: str, app_id: str) -> Optional[int]:
    """이 앱의 릴리스에 **실제로 결속된 데이터셋 수**. 못 읽으면 `None`."""
    from core import kit_app_builder as kb

    try:
        return len(gate._materialized(kb.release_id_for(instance_id, app_id), plane))
    except Exception:
        return None


@router.post("/instances/{instance_id}/apps/{app_id}/contract")
async def draft_app_contract(instance_id: str, app_id: str,
                             req: AppContractDraftRequest,
                             p: Principal = Depends(current_principal)):
    """앱 계약 **초안**을 만든다. ⚠️ 승인하지 않는다 — 누르는 것은 다른 사람이다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"apps:contract:draft:{instance_id}/{app_id}")
    inst = _instance_or_404(p, instance_id)
    profile = _kit_profile_or_503(inst)
    blueprint = _blueprint_or_404(profile, app_id)

    from core import kit_app_builder as kb
    from core import kit_app_contract as kac
    try:
        out = kac.draft(
            store, blueprint=blueprint, instance_id=instance_id,
            actor_id=p.user_id or "", tenant_id=str(inst["tenant_id"]),
            scope_node_id=str(inst["scope_node_id"]),
            entity_mode=str(inst["entity_mode"]), app_class=req.app_class,
            labels=kit_registry.dataset_labels(profile))
    except (kac.ContractFlowError, kb.KitAppError) as e:
        #: ⚠️ 여기 오는 것은 대부분 「인증판이 아직 없다」·「app_class 를 안 정했다」다 —
        #:   사람이 고칠 수 있는 입력이므로 422 다.
        raise HTTPException(status_code=422, detail=str(e))
    _audit("APP_CONTRACT_DRAFTED", resource_id=f"{instance_id}/{app_id}",
           actor=p.user_id or "", outcome="success",
           detail=f"revision={out.get('revision')}")
    return {"status": "success", "data": out}


@router.post("/instances/{instance_id}/apps/{app_id}/contract/approve")
async def approve_app_contract(instance_id: str, app_id: str,
                               req: AppContractApproveRequest,
                               p: Principal = Depends(current_principal)):
    """**다른 사람이** 초안을 승인한다.

    ⚠️⚠️ 만든 사람은 승인할 수 없다 — 핵심 층이 막고 DB 트리거도 막는다. 여기서
      세 번째 판정을 만들지 않는다(만들면 규칙이 갈라지고 한쪽만 고쳐지는 날이 온다)."""
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation",
                 action=f"apps:contract:approve:{instance_id}/{app_id}")
    from api.deps import assert_can_manage_standard
    #: ★ 라우트 층에서도 승인 권한을 요구한다 — 소유권 승인과 같은 규칙이다.
    assert_can_manage_standard(p)
    _instance_or_404(p, instance_id)

    from core import kit_app_contract as kac
    try:
        out = kac.approve(store, instance_id=instance_id, app_id=app_id,
                          revision=int(req.revision), actor_id=p.user_id or "",
                          rationale=req.rationale)
    except kac.LedgerUnavailable as e:
        #: ★ 「사람이 정리해야 하는 상태」다 — 409 로 답하면 「입력을 고쳐 다시 하라」로 읽힌다.
        _audit("APP_CONTRACT_REJECTED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="denied", reason=str(e)[:200])
        raise HTTPException(status_code=503, detail=str(e))
    except kac.ContractFlowError as e:
        _audit("APP_CONTRACT_REJECTED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="denied", reason=str(e)[:200])
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        #: ⚠️ 승인 권한 검사(`ownership_binding`)가 던지는 것도 여기로 온다 — 삼키지 않는다.
        _audit("APP_CONTRACT_REJECTED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="denied", reason=str(e)[:200])
        raise HTTPException(status_code=403, detail=str(e))
    _audit("APP_CONTRACT_APPROVED", resource_id=f"{instance_id}/{app_id}",
           actor=p.user_id or "", outcome="allowed",
           detail=f"revision={out.get('revision')} ledger={out.get('ledger_event_id')}")
    return {"status": "success", "data": out}


@router.post("/instances/{instance_id}/apps/{app_id}/build")
async def build_app(instance_id: str, app_id: str,
                    p: Principal = Depends(current_principal)):
    """승인된 계약으로 **실제 앱을 만든다.**

    ★★★ 준비도를 여기서 다시 판정하지 않는다 — `readiness` 의 결과를 그대로 넘긴다.
    ⚠️ 승인이 없으면 만들지 않는다. 「일부라도 열어 주자」가 위험하다 — 열린 앱은 빈
      화면을 보여 주고, 사용자는 그것을 「우리 회사에 자료가 없다」로 읽는다."""
    require_caps(p, PROJECT_RUN, resource="data_preparation",
                 action=f"apps:build:{instance_id}/{app_id}")
    inst = _instance_or_404(p, instance_id)
    profile = _kit_profile_or_503(inst)
    blueprint = _blueprint_or_404(profile, app_id)

    from core import app_preview
    from core import kit_app_builder as kb
    from core import kit_app_contract as kac
    approved = kac.approved(store, instance_id, app_id)
    if not approved or not isinstance(approved.get("contract"), dict):
        raise HTTPException(
            status_code=409,
            detail="승인된 앱 계약이 없습니다 — 계약을 만들어 승인을 받은 뒤에 "
                   "만들 수 있습니다.")

    result = _app_readiness(inst, profile)
    try:
        out = kb.build(
            blueprint=blueprint, approved_contract=approved["contract"],
            instance_id=instance_id, outputs=result.get("outputs") or [],
            actor_id=p.user_id or "", store=store,
            #: ★ 시연 평면에 만든다. ⚠️ 운영 평면 물질화는 **승격의 일**이다
            #:   (`factory_control._promotion_materializer`) — 여기서 하면 승격을 건너뛴다.
            app_data=app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW),
            tenant_id=str(inst["tenant_id"]),
            scope_node_id=str(inst["scope_node_id"]),
            entity_mode=str(inst["entity_mode"]))
    except kb.KitAppError as e:
        _audit("APP_DATASET_CREATED", resource_id=f"{instance_id}/{app_id}",
               actor=p.user_id or "", outcome="denied", reason=str(e)[:200])
        #: ⚠️ 「아직 만들 수 없다」는 409 다 — 422 로 답하면 「입력을 고쳐라」로 읽힌다.
        raise HTTPException(status_code=409, detail=str(e))
    _audit("APP_DATASET_CREATED", resource_id=f"{instance_id}/{app_id}",
           actor=p.user_id or "", outcome="allowed",
           detail=f"release={out.get('release_id')} "
                  f"datasets={len(out.get('datasets') or [])}")
    return {"status": "success", "data": out}
