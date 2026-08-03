"""[CL-2] Decision Package API — 작업서 §CL-BE-03.

오류 코드 규약은 CL-1 과 같다(§3-10):
  · 식별 안 됨 → **401** (사용자가 로그인해야 함을 알아야 한다)
  · 형식 오류 → **422**
  · 참여자가 아닌 안건 → **404** (403 은 존재를 알린다)
  · 내 안건의 정책 위반(상태·차단 조건) → **400** (이유를 말해도 정보가 새지 않는다)
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.deps import Principal, current_principal
from core.decision_case import DecisionCaseError, DecisionNotFound, decision_case

router = APIRouter(tags=["Decision"])


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("사용자 식별이 필요합니다 — 의사결정은 '누가 무엇을 결정했는가'가 기록의 "
                    "전부입니다. 우측 상단에서 사용자를 지정하십시오."))
    return uid


def _hidden():
    raise HTTPException(status_code=404, detail="안건을 찾을 수 없습니다.")


def _bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    package: Dict[str, Any]
    evidence: Dict[str, Any] = {}
    baseline_id: str = ""
    scenario_id: str = ""
    scope_id: str = ""
    due_at: str = ""


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
    try:
        data = decision_case.create(
            question=req.question, created_by=actor, simulation_run_id=run_id,
            baseline_id=req.baseline_id, scenario_id=req.scenario_id,
            scope_id=req.scope_id or (p.scope.primary_dept_id or ""),
            package=req.package, evidence=req.evidence, due_at=req.due_at)
    except DecisionCaseError as e:
        _bad(e)
    return {"status": "success", "data": data}


@router.get("/api/v1/decisions/queue")
async def queue(p: Principal = Depends(current_principal)):
    """내가 관여한 결정 — **본인이 참여자인 것만.**"""
    return {"status": "success", "data": decision_case.queue(_actor(p))}


@router.get("/api/v1/decisions/{decision_id}")
async def get_case(decision_id: str, p: Principal = Depends(current_principal)):
    try:
        return {"status": "success", "data": decision_case.get(decision_id, _actor(p))}
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
        views = {v: decision_case.render_view(decision_id, v, actor) for v in VIEWS}
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
                "data": decision_case.request_review(decision_id, _actor(p), req.participants)}
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
                                                      req.schedule, req.channel)}
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
                    decision_id, _actor(p), req.response_status, req.response)}
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
                                             req.rationale, req.conditions)}
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
                "data": decision_case.create_actions(decision_id, _actor(p), req.actions)}
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
                                                     req.measured_effect)}
    except DecisionNotFound:
        _hidden()
    except DecisionCaseError as e:
        _bad(e)
