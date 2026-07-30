"""[관리자] 감사로그 열람·보존, 범위 정책. prefix `/api/v1/admin`.

## 사용자 결정 (2026-07-30)

> 감사로그는 **5년간 보존**, 열람권한은 **admin 만**.
> 한시 예외 만료일은 우선 설정한 대로 두고 **관리자 페이지에서 admin 이 변경 가능**하도록.

## 왜 감사로그 열람을 admin 으로 좁히는가

**감사로그 자체가 민감정보다.** "누가 무엇을 시도했는가"가 그대로 담겨 있어, 열람을 열어 두면
그것이 새로운 유출 경로가 된다 — 거부된 접근 시도 목록은 곧 "무엇이 어디에 있는지"의 지도다.
그래서 이 라우터의 **모든** 경로는 `assert_can_edit_org`(관리자 전용)를 지난다.

⚠️ 이 파일에 경로를 추가할 때 권한 검사를 빠뜨리면 그 경로만 열린 구멍이 된다. 예외는 없다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_edit_org, current_principal
from core.enterprise_context import audit
from core.scope_policy import ScopePolicyError, policy, set_legacy_deadline

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


def _admin(p: Principal) -> str:
    """관리자 확인 + 행위자 식별. 둘 다 필요하다 —
    권한만 보고 행위자를 안 남기면 "누가 정책을 바꿨나"에 답할 수 없다."""
    assert_can_edit_org(p)
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("관리자 작업에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오 — 정책 변경·감사 열람은 누가 했는지 남아야 합니다."))
    return uid


class DeadlineRequest(BaseModel):
    legacy_grandfather_until: str          # YYYY-MM-DD
    reason: Optional[str] = ""


class PruneRequest(BaseModel):
    apply: bool = False                   # ★ 기본 예행 — 감사로그를 지우는 쪽으로 기울지 않는다


# ── 감사로그 (admin 전용) ─────────────────────────────────────────────────
@router.get("/audit/events")
async def audit_events(limit: int = 50, event: str = "",
                       p: Principal = Depends(current_principal)):
    """최근 감사 이벤트. **관리자 전용** — 감사로그 자체가 민감정보다."""
    _admin(p)
    return {"status": "success",
            "data": await asyncio.to_thread(audit.recent, limit, event)}


@router.get("/audit/stats")
async def audit_stats(p: Principal = Depends(current_principal)):
    """집계 + **기록 실패 횟수.** 실패가 0 이 아니면 이 로그는 불완전하다 —
    그 사실을 감추면 "거부가 없었다"는 거짓 안심을 준다."""
    _admin(p)
    return {"status": "success", "data": await asyncio.to_thread(audit.stats)}


@router.get("/audit/retention")
async def audit_retention(p: Principal = Depends(current_principal)):
    """보존 기간(5년)을 넘긴 기록이 몇 건인가 — **지우기 전에 무엇을 지우는지 본다.**"""
    _admin(p)
    return {"status": "success", "data": await asyncio.to_thread(audit.retention_report)}


@router.post("/audit/prune")
async def audit_prune(req: PruneRequest, p: Principal = Depends(current_principal)):
    """보존 기간을 넘긴 기록을 정리한다.

    ⚠️ `apply=false`(기본)면 예행이다. 실행하면 원본을 `.pruned-<시각>` 으로 남기고, 정리
      자체도 감사로그에 기록한다 — 감사로그를 지우는 작업이 감사되지 않으면 그게 가장 큰 구멍이다."""
    actor = _admin(p)
    out = await asyncio.to_thread(audit.prune, req.apply)
    out["actor"] = actor
    return {"status": "success", "data": out}


# ── 범위 정책 (admin 전용) ────────────────────────────────────────────────
@router.get("/scope-policy")
async def get_scope_policy(p: Principal = Depends(current_principal)):
    """한시 예외 만료일 + 변경 이력(관리자 화면용)."""
    _admin(p)
    return {"status": "success", "data": await asyncio.to_thread(policy)}


@router.put("/scope-policy/legacy-deadline")
async def put_legacy_deadline(req: DeadlineRequest,
                              p: Principal = Depends(current_principal)):
    """한시 예외 만료일을 변경한다(**코드 배포 없이**).

    ⚠️ 미루는 것은 통제를 느슨하게 하는 결정이다 — 그동안 범위 미지정 데이터가 계속 전 조직에
      보인다. 응답의 `note` 를 그대로 화면에 보여줘야 그 사실이 결정자에게 전달된다."""
    actor = _admin(p)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(set_legacy_deadline,
                                                req.legacy_grandfather_until, actor,
                                                req.reason or "")}
    except ScopePolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
