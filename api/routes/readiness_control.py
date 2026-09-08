"""[§8.2 / §14 M3] 운영 준비 REST API. prefix `/api/v1/readiness`.

체크리스트(`/checklist`) · 롤백(`/rollback`) · 변경 영향 분석(`/impact`).

⚠️ 체크리스트는 §8.2 판정을 **재조회**한다 — 같은 판정을 두 곳에서 계산하면 어긋난다.
⚠️ 롤백은 **배포된 코드를 되돌리지 못한다.** 응답의 `limitation` 을 그대로 사용자에게
  보여줘야 한다 — "롤백했다"가 실제보다 크게 읽히면 아무도 후속 조치를 하지 않는다.
"""
import asyncio
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (
    Principal,
    assert_can_manage_standard,
    assert_identified,
    current_principal,
)
from core.release_readiness import ReadinessError, release_readiness

router = APIRouter(prefix="/api/v1/readiness")

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "도입 준비"



def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("롤백에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오. 행위자 없는 롤백은 '누가 내렸나'에 답할 수 "
                    "없습니다."))
    return uid


class RollbackRequest(BaseModel):
    release_id: str
    reason: str
    to_release_id: str = ""


@router.get("/checklist")
async def checklist(release_id: str, project_id: str = "",
                    requires_live_integration: bool = False,
        p: Principal = Depends(current_principal)):
    """§8.2 릴리스 게이트 체인 7단계를 재조회한다.

    ⚠️ `unverifiable` 은 통과가 아니며 `operations_ready` 를 막는다.
      `not_required` 는 §8.2 가 해당 종류에 요구하지 않은 단계다(Shadow Mode)."""
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(release_readiness.checklist, release_id,
                                            project_id, requires_live_integration)}


@router.post("/rollback")
async def rollback(req: RollbackRequest, p: Principal = Depends(current_principal)):
    """운영에서 내린다. 전사 승격 철회 + 기록.

    ⚠️ 배포된 코드는 되돌리지 못한다 — 응답의 `limitation` 을 사용자에게 그대로 보여줄 것."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(release_readiness.rollback, req.release_id,
                                      _actor(p), req.reason, req.to_release_id)
    except ReadinessError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail='롤백 기록 저장소에 연결할 수 없습니다. 잠시 후 다시 시도하십시오.')
    if out['outcome'] != 'complete':
        raise HTTPException(status_code=503, detail={'message': out['message'], 'rollback': out})
    return {"status": "success", "data": out}


@router.get("/rollbacks")
async def rollback_history(release_id: str = "",
        p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(release_readiness.rollback_history, release_id)}


@router.get("/impact")
async def change_impact(node_type: str, node_id: str,
        p: Principal = Depends(current_principal)):
    """기준정보·계약·자산이 바뀌면 무엇이 흔들리는가(§14 M3 영향 분석).

    `blast_radius` 가 `enterprise` 면 **전사 승격된 앱이 영향받는다**는 뜻이다 —
    "N개 노드 영향"과는 다른 정보다."""
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(release_readiness.change_impact,
                                            node_type, node_id)}
