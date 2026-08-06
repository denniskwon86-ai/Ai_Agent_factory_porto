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
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_identified, assert_project_writable,
                      current_principal, enterprise_context)
from api.routes.factory_control import _safe_id
from core.advisor_blueprint import assemble_blueprint
from core.advisor_playbook import (load_playbook, list_playbooks, score_readiness,
                                   active_requirement_keys)
from core.advisor_store import AdvisorStoreError, advisor_store
from core.enterprise_context import (ENTITY_MODE_KO, EnterpriseContext,
                                     EnterpriseContextError)
from core.paths import workspace_path

router = APIRouter(prefix="/api/v1/advisor", tags=["Advisor"])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "상담 플레이북"



def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def _assert_can_approve(p: Principal, owner_dept_id: str, owner_user_id: str):
    """ECM 설계서 §6 은 `APPROVE` 를 `EDIT` 와 **별개 행동**으로 둔다(주체 × 범위 × 도메인 ×
    행동 × 상태). 초안을 쓸 수 있는 사람과 확정할 수 있는 사람은 다를 수 있다.

    ⚠️ 지금은 행동 권한 축이 없어 판정이 쓰기와 같다. **분리된 호출 지점만 먼저 만든다** —
      E2 에서 도메인·행동 매트릭스가 들어올 때 이 함수 하나만 고치면 되고, 그때 라우트를
      다시 뒤지지 않아도 된다(Phase 4 가 라우트 21곳에 단언을 뒤늦게 주입한 일을 반복하지 않는다)."""
    _assert_can_write(p, owner_dept_id, owner_user_id)


def _validate_ctx(ctx: EnterpriseContext, creating: bool = False) -> EnterpriseContext:
    try:
        return ctx.validate(creating=creating)
    except EnterpriseContextError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _assert_same_context(ctx: EnterpriseContext, row: Dict[str, Any]):
    """저장된 자료의 문맥과 요청 문맥이 같은지 확인한다.

    ⚠️ 설계서 수용 기준 5 — 가상 시나리오의 가정·결과가 실제 데이터와 조회에서 분리되어야 한다.
      목록만 격리하고 단건 조회를 안 막으면 id 를 알면 넘어갈 수 있다. 권한(403)이 아니라
      문맥 불일치(404)로 답한다 — 다른 문맥의 자료는 이 문맥에서 **존재하지 않는 것**이다.

    ⚠️ **키가 없으면 통과가 아니라 차단이다(fail-closed).** 처음엔 `row.get(...)` 이 비면
      넘겨줬는데, `get_blueprint_row` 가 신규 컬럼을 SELECT 하지 않아 다른 테넌트의 Blueprint 가
      조용히 통과했다(테스트가 잡음). 조회부가 문맥 컬럼을 빼먹는 것은 이 프로젝트에서 반복된
      결함 유형이라, 판정 근거가 없으면 막고 시끄럽게 실패하게 둔다."""
    if not row.get("tenant_id"):
        raise HTTPException(status_code=500,
                            detail="자료의 실행 문맥을 확인할 수 없습니다(조회부가 문맥 키를 "
                                   "가져오지 않았습니다).")
    if row["tenant_id"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="현재 테넌트 문맥에 없는 자료입니다.")
    mode = row.get("entity_mode") or ""
    if not mode:
        raise HTTPException(status_code=500,
                            detail="자료의 entity_mode 를 확인할 수 없습니다.")
    if mode != ctx.entity_mode:
        raise HTTPException(
            status_code=404,
            detail=f"현재 문맥({ENTITY_MODE_KO.get(ctx.entity_mode, ctx.entity_mode)})에 없는 "
                   f"자료입니다. 이 자료는 {ENTITY_MODE_KO.get(mode, mode)}에 속합니다.")


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
async def get_playbooks(
        p: Principal = Depends(current_principal)):
    """업무 유형 선택용. 플레이북은 전사 공유 저작 설정이라 부서 필터를 걸지 않는다
    (템플릿·기준정보와 같은 취급 — 설계서 Phase 4 '전사 공유로 두고 문서화')."""
    assert_identified(p, WHAT)
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
                              p: Principal = Depends(current_principal),
                              ctx: EnterpriseContext = Depends(enterprise_context)):
    """상담 시작. 플레이북이 지정되면 첫 질문을 함께 돌려준다."""
    _validate_ctx(ctx, creating=True)
    pb = _playbook_or_400(req.playbook_id) if req.playbook_id else None
    try:
        c = await asyncio.to_thread(
            advisor_store.create_consultation,
            user_id=p.user_id, owner_dept_id=getattr(p.scope, "primary_dept_id", "") or "",
            scope=req.scope, playbook_id=req.playbook_id, initial_prompt=req.initial_prompt,
            ctx=ctx)
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
                       p: Principal = Depends(current_principal),
                       ctx: EnterpriseContext = Depends(enterprise_context)):
    """사용자 답변을 기록하고 다음 질문(또는 완료)을 돌려준다."""
    c = _load_consultation_or_404(consultation_id)
    _assert_same_context(_validate_ctx(ctx), c)
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
async def get_consultations(limit: int = 50, p: Principal = Depends(current_principal),
                            ctx: EnterpriseContext = Depends(enterprise_context)):
    rows = await asyncio.to_thread(advisor_store.list_consultations,
                                   _readable_dept_ids(p), p.user_id, limit,
                                   _validate_ctx(ctx))
    return {"status": "success", "data": rows}


@router.get("/consultations/{consultation_id}")
async def get_consultation(consultation_id: str, p: Principal = Depends(current_principal),
                           ctx: EnterpriseContext = Depends(enterprise_context)):
    c = _load_consultation_or_404(consultation_id)
    _assert_same_context(_validate_ctx(ctx), c)
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
                          p: Principal = Depends(current_principal),
                          ctx: EnterpriseContext = Depends(enterprise_context)):
    """상담 답변에서 Blueprint 초안을 **결정론적으로** 조립한다(LLM 0콜)."""
    c = _load_consultation_or_404(consultation_id)
    _assert_same_context(_validate_ctx(ctx), c)
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
    # 문맥은 **상담에서 물려받는다**(요청 헤더가 아니라). 상담 중간에 스위처를 바꿨다고
    # Blueprint 가 다른 문맥으로 태어나면 가정과 실제가 섞인다.
    bp.tenant_id = c["tenant_id"]
    bp.enterprise_scope_id = c["enterprise_scope_id"] or c["owner_dept_id"]
    bp.entity_mode = c["entity_mode"]
    saved = await asyncio.to_thread(advisor_store.save_blueprint, bp)
    await asyncio.to_thread(advisor_store.update_consultation, consultation_id,
                            status="blueprint_drafted")
    return {"status": "success", "data": saved.model_dump()}


@router.get("/blueprints")
async def get_blueprints(limit: int = 50, p: Principal = Depends(current_principal),
                         ctx: EnterpriseContext = Depends(enterprise_context)):
    rows = await asyncio.to_thread(advisor_store.list_blueprints, "",
                                    _readable_dept_ids(p), p.user_id, limit,
                                    _validate_ctx(ctx))
    return {"status": "success", "data": rows}


@router.get("/blueprints/{blueprint_id}")
async def get_blueprint(blueprint_id: str, p: Principal = Depends(current_principal),
                        ctx: EnterpriseContext = Depends(enterprise_context)):
    row = advisor_store.get_blueprint_row(blueprint_id)
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    _assert_same_context(_validate_ctx(ctx), row)
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
                           p: Principal = Depends(current_principal),
                           ctx: EnterpriseContext = Depends(enterprise_context)):
    """승인 또는 반려. 승인은 **사람의 확정**이므로 출처 표시의 `confirmed` 를 켠다(§5.2).

    ⚠️ 필수 데이터가 결손인 상태로도 승인할 수 있게 둔다 — 데이터를 갖추기 전에 계획을 확정하는
      것은 흔한 실무 판단이고, 막으면 우회한다. 대신 무엇을 안고 승인하는지 응답에 명시한다
      (`approved_with_blocking_gaps`). 차단이 아니라 가시화가 이 제품의 규약이다."""
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision 은 approved|rejected 여야 합니다.")
    row = advisor_store.get_blueprint_row(blueprint_id)
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    _assert_same_context(_validate_ctx(ctx), row)
    _assert_can_approve(p, row["owner_dept_id"], row["owner_user_id"])
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


# ── Blueprint → 프로젝트 연결 (§4.7 / M0 백로그 4) ────────────────────────
class BootstrapIn(BaseModel):
    project_id: str
    template_id: str = ""        # 비우면 Blueprint 의 추천 템플릿


def _blueprint_for_action(blueprint_id: str, ctx: EnterpriseContext, p: Principal):
    row = advisor_store.get_blueprint_row(blueprint_id)
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint 를 찾을 수 없습니다.")
    _assert_same_context(_validate_ctx(ctx), row)
    _assert_can_write(p, row["owner_dept_id"], row["owner_user_id"])
    bp = advisor_store.get_blueprint(blueprint_id)
    if not bp:
        raise HTTPException(status_code=500, detail="Blueprint 페이로드를 읽을 수 없습니다.")
    return bp


def _blueprint_brief(bp) -> str:
    """RFP 이전 단계에 넘길 **요약**. 원문 전체가 아니다.

    ECM §5.2-5 와 명세서 §10.4 가 같은 것을 요구한다 — "LLM 프롬프트에는 원문 전체가 아니라
    필요한 범위의 승인된 프로필·카탈로그 요약만 주입한다" / "대화는 전체 로그 대신 승인된
    Blueprint 요약과 최근 의사결정만 재사용한다". 전문을 넣으면 프롬프트 예산이 터진다."""
    b = bp.business
    lines = [f"[승인된 Solution Blueprint {bp.blueprint_id} · {bp.title}]",
             f"목적: {b.objective}"]
    if b.in_scope:
        lines.append(f"범위: {', '.join(b.in_scope)}")
    if b.out_of_scope:
        # 제외 범위는 사용자가 명시적으로 고르지 않은 것이므로 '하지 말 것'의 근거가 된다.
        lines.append(f"제외 범위(만들지 말 것): {', '.join(b.out_of_scope)}")
    if b.decision_makers:
        lines.append(f"이 산출물로 내릴 결정: {', '.join(b.decision_makers)}")
    lines.append(f"데이터 준비도: {bp.readiness_score}점/100")
    req = [r for r in bp.data_requirements if r.necessity == "required"]
    if req:
        lines.append("필수 데이터: " + ", ".join(
            f"{r.canonical_term}({r.readiness_status})" for r in req[:12]))
    gaps = bp.blocking_gaps()
    if gaps:
        lines.append("⚠️ 미확보 필수 데이터: " + ", ".join(g.canonical_term for g in gaps[:12])
                     + " — 이 데이터가 없으면 해당 기능은 가정값으로만 동작한다.")
    if bp.recommended_sequence:
        lines.append("권장 구축 순서: " + " / ".join(bp.recommended_sequence[:7]))
    return "\n".join(lines)


@router.post("/blueprints/{blueprint_id}/bootstrap-project")
async def bootstrap_project(blueprint_id: str, req: BootstrapIn,
                            p: Principal = Depends(current_principal),
                            ctx: EnterpriseContext = Depends(enterprise_context)):
    """승인된 Blueprint 에서 프로젝트를 생성한다(§4.7).

    ⚠️ **Clarification 을 우회하지 않는다**(§18-6). Blueprint 를 `initial_idea` 의 상위
      입력값으로 주입할 뿐, 요구 확인 인터뷰는 그대로 돈다 — 상담은 "무엇을 만들지"를 정했고
      Clarification 은 "어떻게 만들지"의 모호점을 없앤다. 둘은 다른 게이트다.

    ⚠️ **승인 전 Blueprint 로는 만들 수 없다**(§4.2-7 "사용자가 승인하면 ... 프로젝트 초안을
      생성한다"). 초안 상태로 프로젝트가 생기면 승인 게이트가 장식이 된다."""
    bp = _blueprint_for_action(blueprint_id, ctx, p)
    if bp.status != "approved":
        raise HTTPException(status_code=409,
                            detail=f"승인된 Blueprint 만 프로젝트로 만들 수 있습니다"
                                   f"(현재 상태: {bp.status}).")
    from api.routes.factory_control import provision_project

    tid = (req.template_id or bp.system.template_id or "default")
    try:
        tid = await asyncio.to_thread(
            provision_project, req.project_id, tid,
            owner_dept_id=bp.owner_dept_id, owner_user_id=bp.owner_user_id,
            # ECM §10.2 — 프로젝트는 Blueprint 의 문맥을 물려받는다. 여기서 요청 헤더를 쓰면
            #   승인된 Blueprint 와 다른 문맥의 프로젝트가 생겨 추적이 끊긴다.
            tenant_id=bp.tenant_id, enterprise_scope_id=bp.enterprise_scope_id,
            entity_mode=bp.entity_mode, blueprint_id=bp.blueprint_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 id 형식입니다: {e}")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 템플릿입니다: {e.args[0]}")
    except FileExistsError:
        raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트 ID입니다.")

    # 파이프라인 첫 입력. 사용자의 원래 말(`problem`)을 앞에 두고 Blueprint 요약을 근거로 붙인다 —
    #   순서를 바꾸면 LLM 이 요약을 사용자 발화로 오해한다.
    idea = (bp.business.problem or bp.business.objective or "").strip()
    initial_idea = (idea + "\n\n" + _blueprint_brief(bp)).strip()
    ws = workspace_path(req.project_id)
    state_path = os.path.join(ws, "latest_state.json")
    await asyncio.to_thread(_write_json, state_path, {
        "project_name": req.project_id,
        "template_id": tid,
        "initial_idea": initial_idea,
        "blueprint_id": bp.blueprint_id,
        "owner_dept_id": bp.owner_dept_id,
        "owner_user_id": bp.owner_user_id,
        # [R-001] 실행 문맥을 상태에 심는다 — 이것이 없으면 기준정보 주입에 범위 필터가 걸리지
        #   않아 다른 법인 기준정보가 이 프로젝트 프롬프트에 섞인다(감사 Finding 1).
        "tenant_id": bp.tenant_id,
        "enterprise_scope_id": bp.enterprise_scope_id or bp.owner_dept_id,
        "entity_mode": bp.entity_mode,
    })
    # [M0-e] 승인된 설계가 실제 프로젝트로 넘어간 지점을 남긴다 — 이 링크가 없으면 나중에
    #   "이 프로젝트가 어느 승인에서 나왔나"를 프로젝트 파일 말고는 확인할 방법이 없다.
    from core.decision_ledger import decision_ledger
    await asyncio.to_thread(
        decision_ledger.append,
        event_type="PROJECT_BOOTSTRAPPED", subject_type="project", subject_id=req.project_id,
        actor_type="user", actor_id=p.user_id or "",
        decision=f"승인된 Blueprint 로 프로젝트 생성 (템플릿 {tid})",
        rationale=f"준비도 {bp.readiness_score}점/100 · 승인자 {bp.approved_by or '-'}",
        evidence_refs=[{"kind": "blueprint", "blueprint_id": bp.blueprint_id,
                        "version": bp.version, "approved_at": bp.approved_at}],
        output_version_refs=[{"project_id": req.project_id, "template_id": tid}],
        tenant_id=bp.tenant_id or "tenant_default",
        enterprise_scope_id=bp.enterprise_scope_id, entity_mode=bp.entity_mode,
        project_id=req.project_id, blueprint_id=bp.blueprint_id)

    return {"status": "success", "data": {
        "project_id": req.project_id, "template_id": tid,
        "blueprint_id": bp.blueprint_id, "entity_mode": bp.entity_mode,
        "enterprise_scope_id": bp.enterprise_scope_id,
        "next_step": "프로젝트 통제실에서 스프린트를 시작하면 요구 확인 인터뷰부터 진행됩니다.",
    }}


@router.post("/blueprints/{blueprint_id}/create-data-tasks")
async def create_data_tasks(blueprint_id: str, project_id: str,
                            p: Principal = Depends(current_principal),
                            ctx: EnterpriseContext = Depends(enterprise_context)):
    """미확보 데이터를 WBS 준비 태스크로 추가한다(§4.7 "WBS에 데이터 준비·연계·검증 태스크").

    ⚠️ **기획 완료 후에 호출해야 한다.** `WBSManager.initialize_wbs` 는 파일을 통째로 다시
      쓰므로 기획 전에 넣은 태스크는 PMO 가 WBS 를 만드는 순간 사라진다. WBS 가 없으면 409 로
      돌려보낸다 — 조용히 만들어 두면 지워진 줄도 모른다.
      (근본적으로는 Blueprint 요약이 기획 프롬프트에 들어가 PMO 가 처음부터 포함하게 하는 것이
       맞고, `bootstrap-project` 가 `initial_idea` 에 필수/미확보 데이터를 실어 보낸다.
       이 엔드포인트는 기획이 놓친 것을 사람이 보강하는 경로다.)"""
    bp = _blueprint_for_action(blueprint_id, ctx, p)
    _safe_id(project_id, "project_id")
    ws = workspace_path(project_id)
    if not os.path.isdir(ws):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    assert_project_writable(p, project_id)

    gaps = [r for r in bp.data_requirements
            if r.necessity in ("required", "recommended") and r.readiness_status != "held"]
    if not gaps:
        return {"status": "success", "data": {"created": [], "message": "미확보 데이터가 없습니다."}}

    from nodes.utils.wbs_manager import WBSManager
    mgr = WBSManager(workspace_root=ws)
    created = []
    try:
        for g in gaps:
            owner = f"[{g.owner_department}] " if g.owner_department else ""
            tid_ = await asyncio.to_thread(
                mgr.add_data_task,
                f"{owner}데이터 준비: {g.canonical_term}",
                # 목표에 영향과 조치를 함께 넣는다 — 태스크만 있고 왜/무엇을 모르면 방치된다.
                f"{g.purpose}\n\n[없으면] {g.gap_impact}\n[조치] {g.next_action}\n"
                f"[필요 단위] {g.expected_grain or '미정'} / [최신성] {g.freshness_requirement or '미정'}\n"
                f"[데이터 구분] {g.data_kind} / [현재 상태] {g.readiness_status}")
            created.append({"task_id": tid_, "canonical_term": g.canonical_term,
                            "owner_department": g.owner_department,
                            "necessity": g.necessity, "status": g.readiness_status})
        # [M0-e] 어떤 데이터 요구를 준비 작업으로 확정했는지 남긴다(§5.2 DATA_REQUIREMENT_ACCEPTED).
        from core.decision_ledger import decision_ledger
        await asyncio.to_thread(
            decision_ledger.append,
            event_type="DATA_REQUIREMENT_ACCEPTED", subject_type="project",
            subject_id=project_id, actor_type="user", actor_id=p.user_id or "",
            decision=f"미확보 데이터 {len(created)}건을 WBS 준비 태스크로 확정",
            rationale="Blueprint 의 필수·권장 데이터 중 보유(held)가 아닌 항목",
            evidence_refs=[{"kind": "blueprint", "blueprint_id": bp.blueprint_id},
                           {"kind": "requirements", "items": created}],
            output_version_refs=[{"wbs_task_ids": [t["task_id"] for t in created]}],
            tenant_id=bp.tenant_id or "tenant_default",
            enterprise_scope_id=bp.enterprise_scope_id, entity_mode=bp.entity_mode,
            project_id=project_id, blueprint_id=bp.blueprint_id)
    except FileNotFoundError:
        raise HTTPException(status_code=409,
                            detail="WBS가 아직 없습니다. 기획(WBS 생성)을 마친 뒤 호출하십시오 — "
                                   "기획이 WBS를 새로 쓰면서 먼저 넣은 태스크를 지웁니다.")
    return {"status": "success", "data": {"created": created, "project_id": project_id}}


# ── 데이터 보드 롤업 (§4.4) ───────────────────────────────────────────────
@router.get("/data-requirements/rollup")
async def requirement_rollup(p: Principal = Depends(current_principal),
                             ctx: EnterpriseContext = Depends(enterprise_context)):
    """"어느 부서가 어떤 데이터를 몇 건 못 갖췄나". M1 카탈로그 매칭의 입력이 된다."""
    rows = await asyncio.to_thread(advisor_store.requirement_rollup, _readable_dept_ids(p), _validate_ctx(ctx))
    return {"status": "success", "data": rows}
