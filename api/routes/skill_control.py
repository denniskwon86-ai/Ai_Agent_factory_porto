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
from fastapi import APIRouter, HTTPException

from core.skill_evolution import skill_evolution

router = APIRouter(prefix="/skills", tags=["Skill Evolution"])

# proposal_id 는 파일시스템 경로(pending/<id>.json)로 사용되므로 단일 세그먼트만 허용
# ('/','\\','..' 차단 → 디렉토리 이탈 원천 봉쇄). 엔진이 생성하는 id 형식은 prop_<hex8>.
_PROP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_proposal_id(value: str) -> str:
    if not _PROP_ID_RE.match(value or ""):
        raise HTTPException(status_code=400, detail="잘못된 proposal_id 형식입니다.")
    return value


@router.get("/proposals")
async def list_proposals():
    """승인 대기 중(pending)인 스킬 개선 제안 목록(최신순)."""
    try:
        proposals = skill_evolution.list_pending_proposals()
        return {"status": "success", "data": proposals}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제안 목록 조회 오류: {str(e)}")


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    """제안을 승인하고 해당 에이전트의 스킬 마크다운(skills/*.md)에 규칙을 반영한다."""
    _safe_proposal_id(proposal_id)
    ok = skill_evolution.apply_approved_update(proposal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없거나 적용에 실패했습니다.")
    return {"status": "success", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    """제안을 거부하고 rejected 보관소로 이동한다(스킬 파일은 변경하지 않음)."""
    _safe_proposal_id(proposal_id)
    ok = skill_evolution.reject_proposal(proposal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없거나 거부 처리에 실패했습니다.")
    return {"status": "success", "proposal_id": proposal_id}
