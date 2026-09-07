"""[DAO-8] 데이터 수집 오케스트레이터 API.

## 새 최상위 메뉴를 만들지 않는다(지시 11)

경로 접두어가 `/api/v1/external/acquisition` 이다 — 기존 대외 인텔리전스 아래다. 화면도
`ExternalIntelligenceView` 안에 붙는다. 새 최상위를 만들면 「외부 원천」이 두 군데가 되고,
사용자는 어느 쪽이 정본인지 알 수 없다.

## 권한 — 지시 12 의 세 층

    수집 요청·탐색·Dry-run   데이터 사용자   `assert_identified` + `PROJECT_RUN`
    계약 승인·적용            데이터 관리자   `assert_can_manage_standard`
    자동갱신 활성화·중지       권한 보유 관리자 `ADMIN_DATA_ACCESS`

★★★ 갈라 둔 이유: **Dry-run 까지는 되돌릴 수 있고, 적용부터는 아니다.** 되돌리기 비용이
  달라지는 지점에서 권한이 바뀌어야 한다(`route_authority` 의 배정 기준과 같다).

⚠️ 이 라우터는 `route_authority.guard` 를 **의존성으로** 단다. 라우트마다 적으면 새 라우트가
  생길 때 빠뜨릴 기회가 생기고, 아무도 알려 주지 않는다.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import (Principal, assert_can_manage_standard, assert_identified,
                      current_principal)
from core import route_authority
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import request_interpreter as ri
from core.external_intelligence.acquisition_store import (AcquisitionStoreError,
                                                          acquisition_store)
from core.external_intelligence.orchestrator import (AcquisitionOrchestrator,
                                                     OrchestrationError)
from core.external_intelligence.providers import ProviderError, provider_registry
from core.external_intelligence.raw_store import raw_store
from core.external_intelligence.refresh_runner import BLOCK_REASONS as _BLOCK_REASONS

#: Provider 구현을 등록시킨다. import 만으로 등록부에 들어간다.
#: ⚠️ 새 Provider 를 만들면 **여기에도 추가**한다 — 빠뜨리면 등록부에 없어서
#:   화면의 원천 목록에 나오지 않고, 요청 관문이 「등록되지 않은 원천」으로 거부한다.
from core.external_intelligence.providers import ecos as _ecos  # noqa: F401
from core.external_intelligence.providers import datagokr as _datagokr  # noqa: F401
from core.external_intelligence.providers import kosis as _kosis  # noqa: F401
from core.external_intelligence.providers import opendart as _opendart  # noqa: F401

WHAT = "외부 데이터 수집"

router = APIRouter(prefix="/api/v1/external/acquisition",
                   dependencies=[Depends(route_authority.guard)])


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("수집 요청에는 사용자 식별이 필요합니다. 요청자 없는 수집은 "
                    "'누가 이 자료를 들여왔나'에 답할 수 없습니다."))
    return uid


def _tenant(p: Principal) -> str:
    return str(getattr(p.scope, "tenant_id", "") or "tenant_default")


def _scope(p: Principal) -> str:
    """★★★ 조직 범위는 **서버가 판정한 값**이다. 화면이 보낸 값을 쓰지 않는다."""
    return str(getattr(p.scope, "primary_dept_id", "") or "")


def _orchestrator() -> AcquisitionOrchestrator:
    return AcquisitionOrchestrator(store=acquisition_store, raw_store=raw_store,
                                   registry=provider_registry)


def _err(exc: Exception, status: int = 400):
    raise HTTPException(status_code=status, detail=str(exc))


# ── 요청 본문 ────────────────────────────────────────────────────────────────
class InterpretRequest(BaseModel):
    """자연어 요청 → 구조화 제안 검증. **LLM 제안은 화면이 가져온다.**"""
    proposal: Dict[str, Any] = Field(default_factory=dict)
    purpose_kind: str = "scenario"


class CreateJobRequest(BaseModel):
    proposal: Dict[str, Any] = Field(default_factory=dict)
    purpose_kind: str = "scenario"


class DryRunRequest(BaseModel):
    mapping_proposal: Optional[List[Dict[str, Any]]] = None
    as_of: str = ""


class ApplyRequest(BaseModel):
    as_of: str = ""


class ContractDecisionRequest(BaseModel):
    approve: bool
    reason: str = ""


class ScheduleRequest(BaseModel):
    schedule_rule: str = ""
    next_run_at: str = ""
    #: ★★★ 사람 승인 없이 적용해도 되는가. **기본은 아니다** — 켜는 것 자체가 결정이고
    #:   원장에 남는다. 켜더라도 「처음 승인한 것과 같은 모양일 때만」 적용된다.
    auto_apply: Optional[bool] = None


class DisableRequest(BaseModel):
    reason: str


# ── 카탈로그 (읽기) ──────────────────────────────────────────────────────────
@router.get("/catalog")
async def catalog(p: Principal = Depends(current_principal)):
    """원천 카드와 데이터 계약. **화면은 이것만 보고 원천 비교 카드를 그린다.**"""
    assert_identified(p, WHAT)
    import os
    chosen, excluded = provider_registry.ranked(require_credential_present=True,
                                                env=os.environ)
    return {"status": "success", "data": {
        "providers": [{
            "provider_id": d.provider_id, "name": d.name, "publisher": d.publisher,
            "source_type": d.source_type, "cost": d.cost,
            "requires_credential": d.requires_credential,
            "credential_configured": d.provider_id in {c.provider_id for c in chosen},
            "default_trust_grade": d.default_trust_grade,
            "refresh_frequency": d.refresh_frequency, "coverage_note": d.coverage_note,
            "license_url": d.license_url, "allowed_usage": d.allowed_usage,
            "redistribution_allowed": d.redistribution_allowed,
            "target_contract_keys": list(d.target_contract_keys),
            "data_origin": d.data_origin, "known_limits": list(d.known_limits),
        } for d in provider_registry.descriptors()],
        #: 지시 3 — 「선택하지 않은 원천과 제외 사유」
        "excluded": [{"provider_id": e.provider_id, "reason": e.reason} for e in excluded],
        "routing_table": dict(M.ROUTING_TABLE),
        "data_origins": list(am.DATA_ORIGINS),
        "states": list(am.ACQUISITION_STATES),
    }}


# ── 요청 해석 (데이터 사용자) ────────────────────────────────────────────────
@router.post("/interpret")
async def interpret(req: InterpretRequest, p: Principal = Depends(current_principal)):
    """구조화 제안을 **결정론적으로 판정**한다. 통과 못 하면 아무것도 만들지 않는다."""
    assert_identified(p, WHAT)
    result = _interpret(req.proposal, req.purpose_kind, p)
    return {"status": "success", "data": _interpretation_dict(result)}


def _interpret(proposal: Dict[str, Any], purpose_kind: str, p: Principal):
    from datetime import datetime, timezone
    contracts = _known_contract_keys()
    return ri.validate_proposal(
        proposal, known_provider_ids=list(provider_registry.ids()),
        known_contract_keys=contracts,
        #: ★★★ 화면이 보낸 범위가 아니라 **서버가 판정한 범위**를 넘긴다.
        scope_node_id=_scope(p), purpose_kind=purpose_kind,
        now_year=datetime.now(timezone.utc).year)


def _known_contract_keys() -> List[str]:
    """키트의 인증 계약 + **승인된** 제안. 미승인 제안은 목록에 없다."""
    keys = set()
    try:
        from core.data_preparation import kit_registry
        for kit in kit_registry.discover():
            keys.update(kit_registry.dataset_keys(kit.profile))
    except Exception:
        pass
    for row in acquisition_store.list_contract_proposals("APPROVED"):
        keys.add(str(row["contract_key"]))
    return sorted(keys)


def _interpretation_dict(result) -> Dict[str, Any]:
    request = result.request
    return {
        "ok": result.ok,
        "problems": [{"field": x.field, "reason": x.reason, "got": x.got}
                     for x in result.problems],
        #: 사용자가 「왜 내가 쓴 대로 안 됐나」를 물으면 답이 있어야 한다.
        "overridden": [{"field": x.field, "reason": x.reason, "got": x.got}
                       for x in result.overridden],
        "resolved_scope_node_id": result.resolved_scope_node_id,
        "required_grade": result.required_grade,
        "request": None if request is None else {
            "subject_name": request.subject_name, "purpose": request.purpose,
            "period_from": request.period_from, "period_to": request.period_to,
            "indicators": list(request.indicators),
            "target_contract_keys": list(request.target_contract_keys),
            "frequency": request.frequency, "required_grade": request.required_grade,
            "extras": dict(request.extras)},
    }


@router.post("/jobs")
async def create_job(req: CreateJobRequest, p: Principal = Depends(current_principal)):
    """수집 작업을 만든다. **관문을 통과한 제안만** 작업이 된다."""
    assert_identified(p, WHAT)
    result = _interpret(req.proposal, req.purpose_kind, p)
    if not result.ok:
        raise HTTPException(status_code=400, detail={
            "message": "수집 요청이 관문을 통과하지 못했습니다.",
            **_interpretation_dict(result)})
    r = result.request
    try:
        job = acquisition_store.create(
            tenant_id=_tenant(p), requested_by=_actor(p), scope_node_id=result.resolved_scope_node_id,
            subject_name=r.subject_name, purpose=r.purpose,
            request={"subject_name": r.subject_name, "purpose": r.purpose,
                     "period_from": r.period_from, "period_to": r.period_to,
                     "indicators": list(r.indicators),
                     "target_contract_keys": list(r.target_contract_keys),
                     "frequency": r.frequency, "required_grade": r.required_grade,
                     "extras": dict(r.extras)})
    except AcquisitionStoreError as exc:
        _err(exc)
    return {"status": "success", "data": dict(job, overridden=_interpretation_dict(result)
                                              ["overridden"])}


@router.get("/jobs")
async def list_jobs(status: str = "", limit: int = 50,
                    p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    try:
        rows = acquisition_store.list_jobs(tenant_id=_tenant(p), status=status, limit=limit)
    except AcquisitionStoreError as exc:
        _err(exc)
    return {"status": "success", "data": rows}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    job = acquisition_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 수집 작업입니다.")
    return {"status": "success", "data": dict(
        job, raw_objects=acquisition_store.raw_objects(job_id),
        history=acquisition_store.history(job_id))}


@router.post("/jobs/{job_id}/discover")
async def discover(job_id: str, p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    try:
        job = _orchestrator().discover(job_id, actor_id=_actor(p))
    except (OrchestrationError, ProviderError, AcquisitionStoreError,
            am.AcquisitionStateError) as exc:
        _err(exc)
    return {"status": "success", "data": job}


@router.post("/jobs/{job_id}/dry-run")
async def dry_run(job_id: str, req: DryRunRequest,
                  p: Principal = Depends(current_principal)):
    """★ 되돌릴 수 있는 마지막 단계. 격리 적재본에는 한 줄도 쓰지 않는다."""
    assert_identified(p, WHAT)
    try:
        job, report = _orchestrator().dry_run(job_id, actor_id=_actor(p),
                                              mapping_proposal=req.mapping_proposal,
                                              as_of=req.as_of)
    except (OrchestrationError, ProviderError, AcquisitionStoreError,
            am.AcquisitionStateError) as exc:
        _err(exc)
    return {"status": "success", "data": {"job": job, "report": report.as_dict()}}


# ── 계약 제안·승인 (데이터 관리자) ───────────────────────────────────────────
@router.get("/contract-proposals")
async def list_contract_proposals(status: str = "",
                                  p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": acquisition_store.list_contract_proposals(status)}


@router.post("/contract-proposals/{contract_key}")
async def propose_contract(contract_key: str, p: Principal = Depends(current_principal)):
    """새 계약을 제안한다. **인증된 키트를 건드리지 않는다.**"""
    assert_can_manage_standard(p)
    #: 계약 키 → 제안 문서를 만드는 규칙. **이 표에 없으면 만들지 않는다** —
    #: 화면이 임의의 키로 빈 계약을 만들어 내면 그 계약이 무엇인지 아무도 모른다.
    builders = {"PUB-01": M.pub01_proposal, "EXT-01": M.ext01_public_proposal,
                "EXT-03": M.ext03_public_proposal}
    builder = builders.get(contract_key.upper())
    if builder is None:
        raise HTTPException(
            status_code=400,
            detail=(f"{contract_key} 의 제안 문서를 만드는 규칙이 아직 없습니다. "
                    f"지금 제안할 수 있는 것: {', '.join(sorted(builders))}."))
    try:
        row = acquisition_store.propose_contract(builder(), proposed_by=_actor(p),
                                                 tenant_id=_tenant(p))
    except (AcquisitionStoreError, M.MappingError) as exc:
        _err(exc)
    return {"status": "success", "data": row}


@router.post("/contract-proposals/{proposal_id}/decision")
async def decide_contract(proposal_id: str, req: ContractDecisionRequest,
                          p: Principal = Depends(current_principal)):
    """★★★ 사람의 결정. 승인은 원장에 남고, 승인 전에는 적재 대상이 될 수 없다."""
    assert_can_manage_standard(p)
    try:
        row = acquisition_store.decide_contract(proposal_id, approve=req.approve,
                                                reviewed_by=_actor(p), reason=req.reason,
                                                tenant_id=_tenant(p))
    except AcquisitionStoreError as exc:
        _err(exc)
    return {"status": "success", "data": row}


# ── 적용 (데이터 관리자) ─────────────────────────────────────────────────────
@router.post("/jobs/{job_id}/apply")
async def apply(job_id: str, req: ApplyRequest,
                p: Principal = Depends(current_principal)):
    """★ 되돌릴 수 없는 첫 단계 — 그래서 권한이 한 층 올라간다."""
    assert_can_manage_standard(p)
    try:
        job, report = _orchestrator().apply(job_id, actor_id=_actor(p), as_of=req.as_of)
    except (OrchestrationError, ProviderError, AcquisitionStoreError,
            am.AcquisitionStateError) as exc:
        _err(exc)
    return {"status": "success", "data": {"job": job, "report": report.as_dict()}}


@router.get("/jobs/{job_id}/rows")
async def staged_rows(job_id: str, limit: int = 200,
                      p: Principal = Depends(current_principal)):
    """격리 적재본. **운영 데이터셋이 아니다** — 응답이 그 사실을 함께 말한다."""
    assert_identified(p, WHAT)
    rows = acquisition_store.staged_rows(job_id=job_id, limit=limit)
    return {"status": "success", "data": {
        "rows": rows, "count": len(rows),
        "notice": ("격리 적재본입니다 — 운영 데이터셋이 아니며 인증되지 않았습니다"
                   "(certification_status=UNCERTIFIED). 업무키트 결속은 별도 승인이 필요합니다."),
    }}


# ── 정기 갱신 (권한 보유 관리자) ─────────────────────────────────────────────
@router.post("/jobs/{job_id}/schedule")
async def set_schedule(job_id: str, req: ScheduleRequest,
                       p: Principal = Depends(current_principal)):
    """자동 갱신 일정. ⚠️ **프로세스 안에 타이머를 두지 않는다** — 운영 스케줄러가
    `/due` 를 읽어 하나씩 부른다."""
    assert_can_manage_standard(p)
    if acquisition_store.get(job_id) is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 수집 작업입니다.")
    try:
        job = acquisition_store.set_schedule(job_id, schedule_rule=req.schedule_rule,
                                             next_run_at=req.next_run_at,
                                             auto_apply=req.auto_apply,
                                             actor_id=_actor(p))
    except AcquisitionStoreError as exc:
        _err(exc, status=409)
    return {"status": "success", "data": job}


@router.get("/refresh/preview")
async def refresh_preview(now: str = "", limit: int = 25,
                          p: Principal = Depends(current_principal)):
    """운영 스케줄러가 **무엇을 돌게 될지** 미리 본다. 아무것도 바꾸지 않는다.

    ⚠️ 실제 실행은 이 API 가 아니라 `scripts/run_acquisition_refresh.py` 다 —
      웹 요청으로 돌리면 워커 수만큼 같은 수집이 돈다(지시 9)."""
    assert_can_manage_standard(p)
    due = acquisition_store.due_for_refresh(now=now, limit=limit)
    return {"status": "success", "data": {
        "considered": len(due),
        "jobs": [{"job_id": j["job_id"], "provider_id": j["provider_id"],
                  "contract_key": j["target_contract_key"],
                  "next_run_at": j["next_run_at"], "schedule_rule": j["schedule_rule"],
                  "auto_apply": j["auto_apply"]} for j in due],
        "notice": ("실행은 운영 스케줄러가 `scripts/run_acquisition_refresh.py` 를 부르는 "
                   "것으로 합니다 — 프로세스 안에 타이머를 두지 않습니다."),
        "block_reasons": dict(_BLOCK_REASONS),
    }}


@router.get("/due")
async def due(now: str = "", limit: int = 50, p: Principal = Depends(current_principal)):
    """운영 스케줄러가 읽는 목록. **`ACTIVE` 만** 나온다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": acquisition_store.due_for_refresh(now=now, limit=limit)}


@router.post("/jobs/{job_id}/disable")
async def disable(job_id: str, req: DisableRequest,
                  p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    if not str(req.reason or "").strip():
        raise HTTPException(status_code=400,
                            detail="중지에는 사유가 필요합니다 — 사유가 없으면 되돌릴 근거도 없습니다.")
    try:
        job = acquisition_store.transition(job_id, am.DISABLED, actor_id=_actor(p),
                                           reason=req.reason)
    except (AcquisitionStoreError, am.AcquisitionStateError) as exc:
        _err(exc)
    return {"status": "success", "data": job}
