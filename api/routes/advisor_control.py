"""업무·데이터 설계 상담사 API — 마스터 명세서 §4.6 / M0 백로그 2.

**LLM 0콜이다.** 질문은 플레이북(저작 설정)에서 나오고 Blueprint 는 답변에서 결정론적으로
조립된다(`core/advisor_blueprint.py` 주석 참조 — 바이블 §9.3 "AI 에게 진실을 맡기기" 금지).
나중에 LLM 보강을 얹을 때도 그 항목은 `origin="ai"` 로 표시되어 사람의 확정과 구분된다.

권한은 **처음부터** 부서 스코프로 건다. 이 프로젝트에서 권한을 나중에 얹는 일이 반복적으로
비쌌다 — Phase 4 는 라우트 21곳에 단언을 뒤늦게 주입해야 했고, Phase 5 는 프롬프트 주입 경로가
이미 전역 유출 상태였다. 상담·Blueprint 는 부서 손익·데이터 결손 같은 민감 정보를 담으므로
처음부터 막는다.

미구현(범위 밖, 백로그 4 = M0-d): `bootstrap-project`, `create-data-tasks`.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal
from core.advisor_blueprint import assemble_blueprint
from core.advisor_playbook import (load_playbook, list_playbooks, score_readiness,
                                   active_requirement_keys)
from core.advisor_store import AdvisorStoreError, advisor_store

router = APIRouter(prefix="/api/v1/advisor", tags=["Advisor"])


# ── 권한 헬퍼 ─────────────────────────────────────────────────────────────
def _readable_dept_ids(p: Principal) -> Optional[List[str]]:
    """`None` = 필터하지 말라(무제한). 조직 미도입 기본값(`ORG_ENFORCE=False`)에서 종전 동작."""
    if p.scope.unrestricted:
        return None
    return sorted(p.scope.readable_dept_ids or ())


def _assert_can_read(p: Principal, owner_dept_id: str, owner_user_id: str):
    """부서 자원은 부서 권한으로, 부서 미지정(개인) 자원은 **본인만** 볼 수 있다.

    ⚠️ 여기서 '미지정이면 통과'로 두면 안 된다. 프로젝트 목록은 마이그레이션 전 레거시가
      사라지는 것을 막기 위해 그렇게 했지만(Phase 3), 상담은 **이 기능과 함께 새로 생기는
      데이터**라 레거시가 존재하지 않는다. 하위호환을 지킬 대상이 없으면 fail-closed 가 맞다."""
    if p.scope.unrestricted:
        return
    if owner_dept_id:
        if not p.scope.can_read(owner_dept_id):
            raise HTTPException(status_code=403, detail=f"'{owner_dept_id}' 부서 자료를 볼 권한이 없습니다.")
        return
    if (owner_user_id or "") != p.user_id:
        raise HTTPException(status_code=403, detail="본인의 상담만 조회할 수 있습니다.")


def _assert_can_write(p: Principal, owner_dept_id: str, owner_user_id: str):
    if p.scope.unrestricted:
        return
    if owner_dept_id:
        if not p.scope.can_write(owner_dept_id):
            raise HTTPException(status_code=403, detail=f"'{owner_dept_id}' 부서 자료를 수정할 권한이 없습니다.")
        return
    if (owner_user_id or "") != p.user_id:
        raise HTTPException(status_code=403, detail="본인의 상담만 수정할 수 있습니다.")


def _load_consultation_or_404(consultation_id: str) -> Dict[str, Any]:
    c = advisor_store.get_consultation(consultation_id)
    if not c:
        raise HTTPException(status_code=404, detail="상담을 찾을 수 없습니다.")
    return c


def _playbook_or_400(playbook_id: str):
    try:
        pb = load_playbook(playbook_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not pb:
        raise HTTPException(status_code=404, detail=f"플레이북을 찾을 수 없습니다: {playbook_id}")
    return pb


# ── 플레이북 목록 (상담 진입 화면) ────────────────────────────────────────
@router.get("/playbooks")
async def get_playbooks():
    """업무 유형 선택용. 플레이북은 전사 공유 저작 설정이라 부서 필터를 걸지 않는다
    (템플릿·기준정보와 같은 취급 — 설계서 Phase 4 '전사 공유로 두고 문서화')."""
    return {"status": "success", "data": await asyncio.to_thread(list_playbooks)}


# ── 상담 세션 ─────────────────────────────────────────────────────────────
class ConsultationCreate(BaseModel):
    initial_prompt: str = ""
    playbook_id: str = ""
    scope: str = "department"


def _next_question(pb, answers: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
    """다음에 물을 질문 1개. §4.3 F-DA-02 — **한 번에 하나의 결정만** 요청한다."""
    for q in pb.questions:
        if q.id not in answers:
            d = q.model_dump()
            d["options"] = [{**o, "value": (o.get("value") or o["label"])}
                            for o in d.get("options", [])]
            return d
    return None


def _progress(pb, answers: Dict[str, List[str]]) -> Dict[str, Any]:
    return {"answered": len(answers), "total": len(pb.questions),
            "complete": len(answers) >= len(pb.questions)}


@router.post("/consultations")
async def create_consultation(req: ConsultationCreate,
                              p: Principal = Depends(current_principal)):
    """상담 시작. 플레이북이 지정되면 첫 질문을 함께 돌려준다."""
    pb = _playbook_or_400(req.playbook_id) if req.playbook_id else None
    try:
        c = await asyncio.to_thread(
            advisor_store.create_consultation,
            user_id=p.user_id, owner_dept_id=getattr(p.scope, "primary_dept_id", "") or "",
            scope=req.scope, playbook_id=req.playbook_id, initial_prompt=req.initial_prompt)
    except AdvisorStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))

    question = None
    if pb:
        question = _next_question(pb, {})
        if question:
            await asyncio.to_thread(
                advisor_store.add_turn, c["consultation_id"], "advisor",
                message=question["question"], question_id=question["id"],
                question_type="choice", option_set=question["options"])
    return {"status": "success", "data": {"consultation": c, "next_question": question,
                                          "progress": _progress(pb, {}) if pb else None}}


class MessageIn(BaseModel):
    question_id: str = ""
    selected_values: List[str] = []
    message: str = ""            # '직접 입력'(선택 사항 — §4.3 F-DA-02)


@router.post("/consultations/{consultation_id}/messages")
async def post_message(consultation_id: str, req: MessageIn,
                       p: Principal = Depends(current_principal)):
    """사용자 답변을 기록하고 다음 질문(또는 완료)을 돌려준다."""
    c = _load_consultation_or_404(consultation_id)
    _assert_can_write(p, c["owner_dept_id"], c["user_id"])
    if not (req.selected_values or (req.message or "").strip()):
        raise HTTPException(status_code=400, detail="선택 또는 입력 중 하나는 있어야 합니다.")
    pb = _playbook_or_400(c["playbook_id"]) if c["playbook_id"] else None

    # 알 수 없는 선택지를 조용히 받아두면 조립 단계에서 요구사항이 안 켜져 원인 추적이 어렵다.
    if pb and req.question_id:
        q = next((x for x in pb.questions if x.id == req.question_id), None)
        if not q:
            raise HTTPException(status_code=400, detail=f"플레이북에 없는 질문입니다: {req.question_id}")
        valid = {o.key() for o in q.options}
        unknown = [v for v in req.selected_values if v not in valid]
        if unknown:
            raise HTTPException(status_code=400, detail=f"선택지에 없는 값입니다: {unknown}")
        if not q.multi and len(req.selected_values) > 1:
            raise HTTPException(status_code=400, detail="이 질문은 하나만 선택할 수 있습니다.")

    try:
        await asyncio.to_thread(
            advisor_store.add_turn, consultation_id, "user", message=req.message,
            question_id=req.question_id,
            question_type="choice" if req.selected_values else "free",
            selected_values=req.selected_values)
    except AdvisorStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))

    answers = await asyncio.to_thread(advisor_store.collected_answers, consultation_id)
    question = _next_question(pb, answers) if pb else None
    if pb and question:
        await asyncio.to_thread(
            advisor_store.add_turn, consultation_id, "advisor",
            message=question["question"], question_id=question["id"],
            question_type="choice", option_set=question["options"])
    return {"status": "success", "data": {
        "next_question": question,
        "progress": _progress(pb, answers) if pb else None,
        # 답이 쌓일 때마다 준비도가 어떻게 변하는지 즉시 보여준다(§4.4 상담 결과 보드).
        # 아직 보유 상태를 모르므로 전부 `missing` 기준의 **하한**이다.
        "readiness_preview": (score_readiness(pb, {}, active_requirements=active_requirement_keys(pb, answers))
                              if pb else None),
    }}


@router.get("/consultations")
async def get_consultations(limit: int = 50, p: Principal = Depends(current_principal)):
    rows = await asyncio.to_thread(advisor_store.list_consultations,
                                   _readable_dept_ids(p), p.user_id, limit)
    return {"status": "success", "data": rows}


@router.get("/consultations/{consultation_id}")
async def get_consultation(consultation_id: str, p: Principal = Depends(current_principal)):
    c = _load_consultation_or_404(consultation_id)
    _assert_can_read(p, c["owner_dept_id"], c["user_id"])
    turns = await asyncio.to_thread(advisor_store.list_turns, consultation_id)
    answers = await asyncio.to_thread(advisor_store.collected_answers, consultation_id)
    pb = load_playbook(c["playbook_id"]) if c["playbook_id"] else None
    blueprints = await asyncio.to_thread(advisor_store.list_blueprints, consultation_id)
    return {"status": "success", "data": {
        "consultation": c, "turns": turns, "answers": answers,
        "next_question": _next_question(pb, answers) if pb else None,
        "progress": _progress(pb, answers) if pb else None,
        "blueprints": blueprints,
    }}


# ── Blueprint ─────────────────────────────────────────────────────────────
class BlueprintDraft(BaseModel):
    # 요구사항별 보유 상태. 미지정은 `missing` 으로 본다(모르는 것을 보유로 치지 않는다).
    statuses: Dict[str, str] = {}


@router.post("/consultations/{consultation_id}/blueprint")
async def draft_blueprint(consultation_id: str, req: BlueprintDraft,
                          p: Principal = Depends(current_principal)):
    """상담 답변에서 Blueprint 초안을 **결정론적으로** 조립한다(LLM 0콜)."""
    c = _load_consultation_or_404(consultation_id)
    _assert_can_write(p, c["owner_dept_id"], c["user_id"])
    if not c["playbook_id"]:
        raise HTTPException(status_code=400, detail="플레이북이 지정되지 않은 상담입니다.")
    pb = _playbook_or_400(c["playbook_id"])

    answers = await asyncio.to_thread(advisor_store.collected_answers, consultation_id)
    if not answers:
        raise HTTPException(status_code=400, detail="아직 답변이 없어 Blueprint 를 만들 수 없습니다.")
    free_text = await asyncio.to_thread(advisor_store.collected_free_text, consultation_id)

    bp = assemble_blueprint(pb, answers, statuses=req.statuses,
                            initial_prompt=c["initial_prompt"], free_text=free_text)
    bp.consultation_id = consultation_id
    bp.owner_dept_id = c["owner_dept_id"]
    bp.owner_user_id = c["user_id"]
    saved = await asyncio.to_thread(advisor_store.save_blueprint, bp)
    await asyncio.to_thread(advisor_store.update_consultation, consultation_id,
                            status="blueprint_drafted")
    return {"status": "success", "data": saved.model_dump()}


@router.get("/blueprints")
async def get_blueprints(limit: int = 50, p: Principal = Depends(current_principal)):
    rows = await asyncio.to_thread(advisor_store.list_blueprints, "",
                                    _readable_dept_ids(p), p.user_id, limit)
    return {"status": "success", "data": rows}


@router.get("/blueprints/{blueprint_id}")
async def get_blueprint(blueprint_id: str, p: Principal = Depends(current_principal)):
    row = advisor_store.get_blueprint_row(blueprint_id)
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    _assert_can_read(p, row["owner_dept_id"], row["owner_user_id"])
    bp = await asyncio.to_thread(advisor_store.get_blueprint, blueprint_id)
    if not bp:
        raise HTTPException(status_code=500, detail="Blueprint 페이로드를 읽을 수 없습니다.")
    d = bp.model_dump()
    # 승인 화면이 반드시 봐야 하는 것 둘 — 이걸 안 보여주면 사람이 무엇을 승인하는지 모른다.
    d["unverified_kpis"] = bp.unverified_kpis()
    d["blocking_gap_count"] = len(bp.blocking_gaps())
    return {"status": "success", "data": d}


class DecisionIn(BaseModel):
    decision: str = "approved"        # approved | rejected
    reason: str = ""


@router.post("/blueprints/{blueprint_id}/approve")
async def decide_blueprint(blueprint_id: str, req: DecisionIn,
                           p: Principal = Depends(current_principal)):
    """승인 또는 반려. 승인은 **사람의 확정**이므로 출처 표시의 `confirmed` 를 켠다(§5.2).

    ⚠️ 필수 데이터가 결손인 상태로도 승인할 수 있게 둔다 — 데이터를 갖추기 전에 계획을 확정하는
      것은 흔한 실무 판단이고, 막으면 우회한다. 대신 무엇을 안고 승인하는지 응답에 명시한다
      (`approved_with_blocking_gaps`). 차단이 아니라 가시화가 이 제품의 규약이다."""
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision 은 approved|rejected 여야 합니다.")
    row = advisor_store.get_blueprint_row(blueprint_id)
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    _assert_can_write(p, row["owner_dept_id"], row["owner_user_id"])
    if req.decision == "rejected" and not (req.reason or "").strip():
        raise HTTPException(status_code=400, detail="반려에는 사유가 필요합니다.")
    try:
        bp = await asyncio.to_thread(advisor_store.set_blueprint_decision, blueprint_id,
                                      req.decision, p.user_id, req.reason)
    except AdvisorStoreError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    gaps = bp.blocking_gaps()
    return {"status": "success", "data": {
        "blueprint_id": bp.blueprint_id, "status": bp.status,
        "approved_by": bp.approved_by, "approved_at": bp.approved_at,
        "readiness_score": bp.readiness_score,
        "approved_with_blocking_gaps": [g.canonical_term for g in gaps]
                                       if bp.status == "approved" else [],
        "unverified_kpis": bp.unverified_kpis(),
    }}


# ── 데이터 보드 롤업 (§4.4) ───────────────────────────────────────────────
@router.get("/data-requirements/rollup")
async def requirement_rollup(p: Principal = Depends(current_principal)):
    """"어느 부서가 어떤 데이터를 몇 건 못 갖췄나". M1 카탈로그 매칭의 입력이 된다."""
    rows = await asyncio.to_thread(advisor_store.requirement_rollup, _readable_dept_ids(p))
    return {"status": "success", "data": rows}
