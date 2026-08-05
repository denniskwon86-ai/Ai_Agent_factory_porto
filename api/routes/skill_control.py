"""
스킬 진화(Skill Evolution) 제어 API.

에이전트가 실패/반려 경험을 통해 스스로 제안한 스킬 개선안(pending)을 사용자가
검토·승인·거부하는 엔드포인트를 제공한다. 실제 제안 생성/적용 로직은
core.skill_evolution.SkillEvolutionEngine 이 담당하며, 본 라우터는 그 얇은 래퍼다.

프리픽스(/skills)는 프론트(SkillEvolutionPanel.tsx)가 호출하는 경로와 일치시킨다:
  - GET  /skills/proposals
  - POST /skills/proposals/{proposal_id}/approve
  - POST /skills/proposals/{proposal_id}/reject
"""
import re
from fastapi import APIRouter, Depends, HTTPException

from api.deps import (Principal, assert_can_manage_standard, current_principal,
                      visibility_block_reason)
from core.enterprise_context import audit
from core.skill_evolution import skill_evolution

router = APIRouter(prefix="/skills", tags=["Skill Evolution"])


# ★★★ [2026-08-04 이관 6/10 실측 결함] **이 파일의 모든 라우트에 권한 검사가 없었다.**
#   즉 익명 요청으로 `POST /skills/proposals/{id}/approve` 가 통했다 — 승인은 에이전트의
#   스킬 문서(`skills/*.md`)를 **실제로 고친다.** 그 문서는 다음 실행부터 에이전트가 따르는
#   행동 규칙이므로, 승인 한 번이 이후 모든 산출물의 만들어지는 방식을 바꾼다.
#   ⚠️ 「제안을 검토·승인한다」는 것 자체가 사람의 판단을 요구하는 관문인데, 그 관문에 자격이
#     없으면 관문이 아니다. 승인은 데이터 표준 관리자·관리자만 할 수 있어야 한다.
def _assert_readable(p: Principal):
    """목록 조회 자격. 제안 본문에는 실패 사례와 내부 규칙이 담긴다."""
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)

# proposal_id 는 파일시스템 경로(pending/<id>.json)로 사용되므로 단일 세그먼트만 허용
# ('/','\\','..' 차단 → 디렉토리 이탈 원천 봉쇄). 엔진이 생성하는 id 형식은 prop_<hex8>.
_PROP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_proposal_id(value: str) -> str:
    if not _PROP_ID_RE.match(value or ""):
        raise HTTPException(status_code=400, detail="잘못된 proposal_id 형식입니다.")
    return value


@router.get("/proposals")
async def list_proposals(p: Principal = Depends(current_principal)):
    """승인 대기 중(pending)인 스킬 개선 제안 목록(최신순)."""
    _assert_readable(p)
    try:
        proposals = skill_evolution.list_pending_proposals()
        return {"status": "success", "data": proposals}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제안 목록 조회 오류: {str(e)}")


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, p: Principal = Depends(current_principal)):
    """제안을 승인하고 해당 에이전트의 스킬 마크다운(skills/*.md)에 규칙을 반영한다."""
    assert_can_manage_standard(p)
    _safe_proposal_id(proposal_id)
    ok = skill_evolution.apply_approved_update(proposal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없거나 적용에 실패했습니다.")
    # 승인은 에이전트의 행동 규칙을 바꾼다 — 누가 언제 승인했는지가 남아야 이후 산출물의
    # 변화를 설명할 수 있다.
    audit.record(audit.WORK_STANDARD_CHANGED, "skill_proposal", proposal_id,
                 actor=p.user_id, outcome="allowed",
                 detail="스킬 개선안 승인 — 에이전트 스킬 문서에 규칙 반영")
    return {"status": "success", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, p: Principal = Depends(current_principal)):
    """제안을 거부하고 rejected 보관소로 이동한다(스킬 파일은 변경하지 않음)."""
    assert_can_manage_standard(p)
    _safe_proposal_id(proposal_id)
    ok = skill_evolution.reject_proposal(proposal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없거나 거부 처리에 실패했습니다.")
    # 거부도 남긴다 — «왜 그 개선이 반영되지 않았나»는 나중에 반드시 묻는 질문이다.
    audit.record(audit.WORK_STANDARD_CHANGED, "skill_proposal", proposal_id,
                 actor=p.user_id, outcome="allowed", detail="스킬 개선안 거부")
    return {"status": "success", "proposal_id": proposal_id}
