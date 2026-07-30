"""[§6.3 / §6.1] 데이터 계약 REST API. prefix `/api/v1/contracts`.

§6.1 은 데이터 계약을 "직접 DB 결합의 **대안**"으로 규정한다. 대안이 되려면 약속이 지금
지켜지고 있는지 확인돼야 하므로, 이 API 의 중심은 등록이 아니라 `/evaluate` 다.

⚠️ 라우트 순서: 고정 경로(`/evaluate` 등)는 `/{contract_id}` 위에 둔다.
"""
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.data_contract import DataContractError, data_contracts

router = APIRouter(prefix="/api/v1/contracts")


def _actor(p: Principal) -> str:
    """승인 행위자. 식별이 안 되면 가짜 값을 만들지 않고 방법을 알려준다(용어사전과 동일 판단)."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("계약 활성화에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오. 승인자 없는 활성화는 '누가 이 약속을 승인했나'에 "
                    "답할 수 없습니다."))
    return uid


class ContractRequest(BaseModel):
    name: str
    producer_asset_id: str
    consumer: str
    schema_def: Optional[Dict[str, Any]] = None
    quality_rules: Optional[Dict[str, Any]] = None
    access_policy: Optional[Dict[str, Any]] = None
    contract_key: str = ""
    note: str = ""
    tenant_id: str = "tenant_default"
    enterprise_scope_id: str = ""
    entity_mode: str = "REAL"


class ActivateRequest(BaseModel):
    allow_breached: bool = False


class PreviewRequest(BaseModel):
    contract_key: str
    schema_def: Dict[str, Any]


# ── 고정 경로 (경로 변수보다 위) ──────────────────────────────────────────
@router.get("/evaluate")
async def evaluate_all():
    """활성 계약 전부가 지금 지켜지고 있는지.

    ⚠️ `unverifiable` 은 **통과가 아니다** — 확인하지 못한 항목이다."""
    out = await asyncio.to_thread(data_contracts.evaluate_all)
    return {"status": "success", "data": out}


@router.post("/preview-revision")
async def preview_revision(req: PreviewRequest):
    """개정 전에 **소비자를 깨뜨리는 변경**을 가려낸다(필드 삭제·타입 변경·필수화).

    사람이 기억해서 챙기게 두면 반드시 놓친다."""
    try:
        out = await asyncio.to_thread(data_contracts.preview_revision, req.contract_key,
                                      req.schema_def)
    except DataContractError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", "data": out}


@router.get("")
async def list_contracts(producer_asset_id: str = "", consumer: str = "", status: str = "",
                         include_retired: bool = False, scope_node_id: str = "",
                         tenant_id: str = "", entity_mode: str = "REAL",
                         p: Principal = Depends(current_principal)):
    """★ [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 내용은 가려진다."""
    from core.enterprise_context.classification import clearance_of_scope
    rows = await asyncio.to_thread(data_contracts.list, producer_asset_id, consumer,
                                   status, include_retired, scope_node_id, tenant_id,
                                   entity_mode, clearance_of_scope(p.scope))
    return {"status": "success", "data": rows}


@router.post("")
async def create_contract(req: ContractRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(
            data_contracts.create, req.name, req.producer_asset_id, req.consumer,
            req.schema_def, req.quality_rules, req.access_policy, req.contract_key,
            req.note, None, req.tenant_id, req.enterprise_scope_id, req.entity_mode)
    except DataContractError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}


@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    data = await asyncio.to_thread(data_contracts.get, contract_id)
    if not data:
        raise HTTPException(status_code=404, detail="존재하지 않는 계약입니다.")
    return {"status": "success", "data": data}


@router.get("/{contract_id}/evaluate")
async def evaluate_contract(contract_id: str):
    try:
        out = await asyncio.to_thread(data_contracts.evaluate, contract_id)
    except DataContractError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", "data": out}


@router.post("/{contract_id}/activate")
async def activate_contract(contract_id: str, req: ActivateRequest = ActivateRequest(),
                            p: Principal = Depends(current_principal)):
    """활성화 = "이 약속으로 붙어도 된다"는 선언.

    ⚠️ 이미 위반 중이면 409 로 거절한다 — 선언이 거짓이 되고 소비자는 지켜지지 않는 약속을
      믿고 붙는다. 알면서 활성화하려면 `allow_breached=true`."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(data_contracts.activate, contract_id, _actor(p),
                                      None, req.allow_breached)
    except DataContractError as e:
        raise HTTPException(status_code=409 if "위반 중" in str(e) else 400, detail=str(e))
    return {"status": "success", "data": out}


@router.delete("/{contract_id}")
async def retire_contract(contract_id: str, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(data_contracts.retire, contract_id)
    if not ok:
        raise HTTPException(status_code=404, detail="활성 계약을 찾을 수 없습니다.")
    return {"status": "success", "data": {"contract_id": contract_id, "retired": True}}
