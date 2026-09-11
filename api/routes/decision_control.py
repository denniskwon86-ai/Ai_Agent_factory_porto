"""[CL-2] Decision Package API — 작업서 §CL-BE-03.

오류 코드 규약은 CL-1 과 같다(§3-10):
  · 식별 안 됨 → **401** (사용자가 로그인해야 함을 알아야 한다)
  · 형식 오류 → **422**
  · 참여자가 아닌 안건 → **404** (403 은 존재를 알린다)
  · 내 안건의 정책 위반(상태·차단 조건) → **400** (이유를 말해도 정보가 새지 않는다)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.deps import Principal, current_principal
from core.decision_case import (UNRESTRICTED, DecisionCaseError, DecisionNotFound,
                                decision_case)
from core.decision_source_binding import (DecisionSourceBlocked,
                                          DecisionSourceNotFound,
                                          bind_decision_evidence,
                                          decision_sources)

router = APIRouter(tags=["Decision"])


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("사용자 식별이 필요합니다 — 의사결정은 '누가 무엇을 결정했는가'가 기록의 "
                    "전부입니다. 우측 상단에서 사용자를 지정하십시오."))
    return uid


def _scopes(p: Principal):
    """이 요청자가 볼 수 있는 조직 범위. **모든 라우트가 이것을 서비스에 넘긴다.**

    ★★★ [2026-08-08 실측 결함] 이 파일 머리말은 「참여자가 아닌 안건 → 404」를 규정하는데
      **구현이 없었다.** 남남이 안건을 조회하고 뷰를 렌더하고 **참여자를 임의로 추가**하고
      회의를 소집할 수 있었다. `publication_control` 과 같은 유형이며 같은 방식으로 막는다.

    ⚠️ 무제한 주체는 `UNRESTRICTED` 센티넬로 넘긴다 — 빈 집합으로 넘기면 관리자가 자기 것
      말고는 아무것도 못 본다. `None` 을 넘기면 서비스가 판정을 통째로 끈다."""
    sc = getattr(p, "scope", None)
    if sc is None or getattr(sc, "unrestricted", False):
        return UNRESTRICTED
    return frozenset(set(getattr(sc, "readable_dept_ids", None) or ())
                     | set(getattr(sc, "readable_scope_nodes", None) or ()))


def _hidden():
    raise HTTPException(status_code=404, detail="안건을 찾을 수 없습니다.")


def _bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    package: Dict[str, Any]
    evidence: Dict[str, Any] = {}
    due_at: str = ""
    #: ★ [T-4] 기본값을 두지 «않는다». 기본값이 있으면 화면이 생각 없이 보내고,
    #:   그 순간 「산식에 근거하지 않은 결정」과 「적기를 잊은 결정」이 다시 같아진다.
    evidence_basis: str
    record_purpose: str = "BUSINESS"


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participants: List[Dict[str, str]]


class ResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_status: str
    response: str = ""


class MeetingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    schedule: str = ""
    channel: str = ""


class DecideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    rationale: str
    conditions: str = ""


class ActionsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: List[Dict[str, Any]]


class EffectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    measured_effect: str


@router.post("/api/v1/simulations/{run_id}/decision-cases")
async def create_case(run_id: str, req: CaseCreate,
                      p: Principal = Depends(current_principal)):
    """시뮬레이션 결과에서 Decision Package 를 만든다.

    ★ 세 관점 검토서를 따로 저장하지 않는다(§3-5) — 하나의 Package 를 만들고 관점별로 렌더링한다."""
    actor = _actor(p)
    allowed = _scopes(p)
    visible_scopes = None if allowed is UNRESTRICTED else allowed
    try:
        # ★ 목록에서 본 실행을 **생성 시 다시 읽는다.** 화면이 baseline/scenario/scope 를
        # 따로 보내면 서로 다른 실행의 세 값을 조합할 수 있으므로 요청 모델에서 받지 않는다.
        source = await asyncio.to_thread(decision_sources.resolve, run_id, visible_scopes)
    except DecisionSourceNotFound:
        _hidden()
    except DecisionSourceBlocked as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        evidence = bind_decision_evidence(source, req.evidence)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        data = decision_case.create(
            question=req.question, created_by=actor, simulation_run_id=run_id,
            baseline_id=source["baseline_id"], scenario_id=source["scenario_id"],
            scope_id=source["scope_id"],
            package=req.package, evidence=evidence, due_at=req.due_at,
            evidence_basis=req.evidence_basis,
            record_purpose=req.record_purpose)
    except DecisionCaseError as e:
        _bad(e)
    return {"status": "success", "data": data}


@router.get("/api/v1/decisions/sources")
async def list_decision_sources(p: Principal = Depends(current_principal)):
    """내 범위에서 안건으로 결속할 수 있는 실행과 차단 사유를 사람이 읽는 이름으로 돌린다."""
    _actor(p)
    allowed = _scopes(p)
    visible_scopes = None if allowed is UNRESTRICTED else allowed
    data = await asyncio.to_thread(decision_sources.list_options, visible_scopes)
    # binding 은 생성 순간 서버가 다시 파생한다. 목록 응답에 원문 지문·내부 결속을 싣지 않는다.
    public = [{k: v for k, v in row.items()
               if k not in {"binding", "scenario_id", "baseline_id", "scope_id"}}
              for row in data]
    return {"status": "success", "data": public}


@router.get("/api/v1/decisions/queue")
async def queue(p: Principal = Depends(current_principal)):
    """내가 관여한 결정 — **본인이 참여자인 것만.**"""
    return {"status": "success", "data": decision_case.queue(_actor(p))}


@router.get("/api/v1/decisions/{decision_id}")
async def get_case(decision_id: str, p: Principal = Depends(current_principal)):
    try:
        return {"status": "success", "data": decision_case.get(decision_id, _actor(p), viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()


@router.post("/api/v1/decisions/{decision_id}/generate-views")
async def generate_views(decision_id: str, p: Principal = Depends(current_principal)):
    """세 관점 렌더링. **데이터를 복제하지 않는다.**

    ★ 세 관점이 같은 `package_version`·`evidence_hash` 를 들고 나간다 — 화면이 그 값을 표시해
      참석자가 같은 근거를 보고 있음을 확인할 수 있어야 한다."""
    actor = _actor(p)
    from core.decision_case import VIEWS
    try:
        views = {v: decision_case.render_view(decision_id, v, actor,
                                             viewer_scopes=_scopes(p)) for v in VIEWS}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)
    ids = {v["package_version"] for v in views.values()}
    hashes = {v["evidence_hash"] for v in views.values()}
    return {"status": "success",
            "data": {"views": views,
                     # 같은 문서임을 응답 자체가 증명한다(테스트도 이 값을 본다).
                     "same_package": len(ids) == 1 and len(hashes) == 1,
                     "package_version": ids.pop() if len(ids) == 1 else None,
                     "evidence_hash": hashes.pop() if len(hashes) == 1 else None}}


@router.post("/api/v1/decisions/{decision_id}/request-review")
async def request_review(decision_id: str, req: ReviewRequest,
                         p: Principal = Depends(current_principal)):
    try:
        return {"status": "success",
                "data": decision_case.request_review(decision_id, _actor(p), req.participants,
                                             viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)


@router.post("/api/v1/decisions/{decision_id}/request-meeting")
async def request_meeting(decision_id: str, req: MeetingRequest,
                          p: Principal = Depends(current_principal)):
    """회의 **요청**. 외부 캘린더·메시지에 쓰지 않는다(§3-7) — 응답의 `note` 가 그것을 말한다."""
    try:
        return {"status": "success",
                "data": decision_case.request_meeting(decision_id, _actor(p), req.title,
                                                      req.schedule, req.channel,
                                                      viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)


@router.post("/api/v1/decisions/{decision_id}/participant-response")
async def participant_response(decision_id: str, req: ResponseBody,
                               p: Principal = Depends(current_principal)):
    try:
        return {"status": "success",
                "data": decision_case.participant_response(
                    decision_id, _actor(p), req.response_status, req.response,
                    viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)


@router.post("/api/v1/decisions/{decision_id}/decide")
async def decide(decision_id: str, req: DecideBody, p: Principal = Depends(current_principal)):
    """결정 기록. 기준선 불일치·미검증 근거·근거 변경은 **차단**한다(§CL-BE-03)."""
    try:
        return {"status": "success",
                "data": decision_case.decide(decision_id, _actor(p), req.outcome,
                                             req.rationale, req.conditions,
                                             viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)


@router.post("/api/v1/decisions/{decision_id}/create-actions")
async def create_actions(decision_id: str, req: ActionsBody,
                         p: Principal = Depends(current_principal)):
    """실행과제 생성 — **담당·기한 없으면 400.**"""
    try:
        return {"status": "success",
                "data": decision_case.create_actions(decision_id, _actor(p), req.actions,
                                             viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)


@router.post("/api/v1/decisions/{decision_id}/measure-effect")
async def measure_effect(decision_id: str, req: EffectBody,
                         p: Principal = Depends(current_principal)):
    """효과 측정 — 결정 당시 기준선과 비교한다. **미측정을 0 으로 저장하지 않는다.**"""
    try:
        return {"status": "success",
                "data": decision_case.measure_effect(decision_id, _actor(p), req.action_id,
                                                     req.measured_effect,
                                                     viewer_scopes=_scopes(p))}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)
