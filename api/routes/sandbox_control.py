"""[M2 §4.3] VIRTUAL Sandbox capability token REST API. prefix `/api/v1/sandbox`.

발급 · 조회 · 회수. **읽기 전용 · 가상 문맥 전용 · 짧은 만료.**

⚠️ 토큰 전문은 **발급 응답에서 단 한 번만** 준다. 목록·감사로그에는 앞 12자만 남는다 —
  로그나 목록에 자격증명 전문이 실리면 그 로그를 읽을 수 있는 사람이 곧 권한자가 된다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal
from core.sandbox_token import DEFAULT_TTL_MINUTES, SandboxTokenError, sandbox_tokens

router = APIRouter(prefix="/api/v1/sandbox")


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("임시 권한 발급에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오 — 누구에게 줬는지 모르는 토큰은 추적이 불가능하고, "
                    "추적되지 않는 임시 권한은 뒷문입니다."))
    return uid


class IssueRequest(BaseModel):
    scope_node_id: str                      # 가상 조직 범위
    ttl_minutes: Optional[int] = DEFAULT_TTL_MINUTES
    purpose: Optional[str] = ""
    tenant_id: Optional[str] = "tenant_default"


@router.post("/token")
async def issue_token(req: IssueRequest, p: Principal = Depends(current_principal)):
    """가상 문맥 읽기 토큰을 발급한다.

    ⚠️ 이 토큰은 **REAL 데이터에 대한 권한을 한 조각도 주지 않는다.** 조직 권한을 올리는
      방식이 금지된 이유는, 실험이 끝난 뒤에도 그 권한이 남기 때문이다."""
    try:
        out = await asyncio.to_thread(sandbox_tokens.issue, _actor(p), req.scope_node_id,
                                      req.tenant_id or "tenant_default",
                                      req.ttl_minutes or DEFAULT_TTL_MINUTES,
                                      req.purpose or "")
    except SandboxTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["note"] = ("이 토큰은 가상 문맥(entity_mode=VIRTUAL) **읽기 전용**이며 지정한 가상 조직 "
                   "범위에서만 유효합니다. REAL 데이터는 열리지 않습니다. 토큰 전문은 이 응답에만 "
                   "포함됩니다 — 목록·감사로그에는 앞 12자만 남습니다.")
    return {"status": "success", "data": out}


@router.get("/tokens")
async def active_tokens(mine_only: bool = True, p: Principal = Depends(current_principal)):
    """살아 있는 토큰 목록(전문 미포함).

    ★ "지금 열려 있는 임시 권한이 무엇인가"에 답할 수 없으면 임시 권한을 운영할 수 없다."""
    actor = (p.user_id or "").strip() if mine_only else ""
    return {"status": "success",
            "data": await asyncio.to_thread(sandbox_tokens.active, actor)}


@router.delete("/token/{token}")
async def revoke_token(token: str, p: Principal = Depends(current_principal)):
    """토큰을 즉시 회수한다 — 만료를 기다리지 않고 끊을 수단이 없으면 사고에 대응할 수 없다."""
    ok = await asyncio.to_thread(sandbox_tokens.revoke, token, (p.user_id or "").strip())
    if not ok:
        # 이미 없는 토큰이다. 존재 여부를 알려 주는 것이 문제되지 않는다 — 토큰 문자열을 이미
        #   알고 있는 호출자에게만 답하는 것이고, 없다는 사실이 곧 "회수됨"이다.
        raise HTTPException(status_code=404, detail="유효한 토큰이 아닙니다(이미 만료·회수됨).")
    return {"status": "success", "data": {"revoked": True}}
