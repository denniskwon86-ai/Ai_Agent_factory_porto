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
from core.org_activation import preflight
from core.scope_policy import (ScopePolicyError, policy, set_app_pdp_enforce,
                               set_legacy_deadline, set_org_enforce)

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


class AppPdpRequest(BaseModel):
    """앱 데이터 판정 전환/롤백.

    ⚠️ `enabled` 라는 이름을 `org-enforcement` 와 **같게** 쓴다. 비슷한 두 API 가 서로 다른
      필드명을 쓰면 화면이 반드시 하나를 틀리고, 그 틀림은 422 로만 드러난다(실제로 조직
      권한 전환에서 그렇게 났다 — 프런트는 `enforce`, 서버는 `enabled` 였다)."""
    enabled: bool
    reason: Optional[str] = ""


class EnforceRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = ""
    #: 사전 점검의 `blockers` 를 무시하고 켠다. **기본은 거부**다 — 잠금 사고를 막는 문이다.
    force: bool = False


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


@router.get("/org-enforcement/preflight")
async def enforcement_preflight(p: Principal = Depends(current_principal)):
    """권한 강제를 켜면 **무엇이 어떻게 바뀌는지** 먼저 센다(켜지는 않는다).

    ★ `ORG_ENFORCE` 가 꺼진 동안에는 조직 범위·등급·드릴다운 통제가 **하나도 작동하지 않는다.**
      이 점검이 그 전환의 문이다 — 관리자 계정이 없으면 켜지 말라고 막는다(잠금 사고 방지)."""
    _admin(p)
    return {"status": "success", "data": await asyncio.to_thread(preflight)}


@router.put("/org-enforcement")
async def put_org_enforcement(req: EnforceRequest,
                              p: Principal = Depends(current_principal)):
    """조직 권한 강제를 켜거나 끈다 — **코드 배포 없이**, 감사와 함께.

    ⚠️ 켜기 전에 사전 점검을 통과해야 한다. `blockers` 가 있으면 409 로 거부한다(잠금 방지).
      끄는 것은 언제나 허용한다 — 사고 상황에서 되돌릴 수 없는 스위치는 되돌림 장치가 아니다."""
    actor = _admin(p)
    if req.enabled and not req.force:
        pre = await asyncio.to_thread(preflight)
        if pre["blockers"]:
            raise HTTPException(status_code=409, detail={
                "message": "사전 점검을 통과하지 못해 강제를 켜지 않았습니다.",
                "blockers": pre["blockers"], "warnings": pre["warnings"],
                "how_to_override": ("정말 켜야 한다면 `force=true` 로 요청하십시오 — 다만 "
                                    "관리자 계정이 없는 상태로 켜면 시스템이 잠깁니다."),
            })
    try:
        out = await asyncio.to_thread(set_org_enforce, req.enabled, actor, req.reason or "")
    except ScopePolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["preflight"] = await asyncio.to_thread(preflight)
    return {"status": "success", "data": out}


@router.put("/app-pdp-enforcement")
async def put_app_pdp_enforcement(req: AppPdpRequest,
                                  p: Principal = Depends(current_principal)):
    """★★★ [G1-B 6] 앱 데이터를 **어느 판정기가 지키는가** 를 바꾼다 — 배포 없이, 감사와 함께.

    ## 왜 API 가 필요한가 (교차검토 89 ③)

    스위치가 정책 파일에만 있으면 **파일을 직접 고쳐** 행위자·사유·이력·감사를 전부 우회할 수
    있다. 그러면 「정책 파일 한 줄로 롤백」과 「롤백 사유 필수」가 **동시에 성립하지 않는다** —
    후자는 이 경로로 들어올 때만 강제되기 때문이다.

    ⚠️ 되돌리면 통제가 **넓어진다**(기존 판정은 앱 증명·매니페스트·실행 문맥을 보지 않는다).
      그래서 끌 때는 사유를 요구한다. 켜는 것은 사유 없이도 되지만 이력은 남는다.
    ★ 켜는 데 사전 점검을 두지 않는 이유: 이 전환은 **닫는 방향**이라 잠금 사고를 만들지
      않는다. 되돌리는 쪽이 위험한 방향이고, 그쪽에 사유를 건다."""
    actor = _admin(p)
    try:
        out = await asyncio.to_thread(set_app_pdp_enforce, req.enabled, actor, req.reason or "")
    except ScopePolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": out}


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
