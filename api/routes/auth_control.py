"""로그인·로그아웃·현재 사용자. prefix `/api/v1/auth`.

## 이 라우터가 하는 일과 하지 않는 일

**한다**: 비밀번호를 확인하고 세션 토큰을 준다. 그 토큰으로 「지금 누구인가」를 답한다.
**하지 않는다**: 권한 판정. 권한은 매 요청 `org_directory` 가 다시 해석한다 — 토큰에 권한을
담으면 **권한을 회수해도 토큰이 살아 있는 동안 유효**해진다.

⚠️ **신규 가입이 없다**(사용자 지시 2026-08-09). 계정은 관리자 화면에서 만들고, 여기서는
  등록된 계정만 로그인한다. 가입 경로를 열어 두면 조직도에 없는 사용자가 생기고, 그러면
  범위·권한 판정이 전부 «모르는 사람» 으로 떨어진다.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import Principal, current_principal
from core.auth import DEFAULT_PASSWORD, auth_store
from core.org_directory import org_directory

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

#: 세션 토큰을 싣는 헤더. 프론트 인터셉터가 붙인다.
SESSION_HEADER = "X-Session-Token"


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


def _known_user(user_id: str):
    """조직도에 있는 계정인가. **없으면 로그인 자체가 성립하지 않는다.**"""
    try:
        return org_directory.get_user(user_id)
    except Exception:
        return None


def _display_name(u, fallback: str) -> str:
    """사용자 레코드에서 표시 이름을 꺼낸다.

    ⚠️ 이 저장소의 사용자 레코드는 **dict** 다 — `getattr` 로 읽으면 조용히 기본값이 나오고
      화면에는 이름 대신 이메일이 뜬다(실제로 그렇게 나갔다). 두 모양을 모두 받는다."""
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("name") or fallback)
    return str(getattr(u, "display_name", "") or getattr(u, "name", "") or fallback)


@router.post("/login")
async def login(req: LoginRequest):
    """로그인. 성공하면 세션 토큰을 준다.

    ⚠️⚠️ **실패 사유를 «아이디가 없다/비밀번호가 틀렸다» 로 나누지 않는다.** 나누면 아이디
      목록을 그 응답으로 만들어 낼 수 있다(존재 확인 → 대상 계정 특정). 사용자가 할 일은
      어느 쪽이든 같다 — 다시 입력하거나 관리자에게 문의하는 것이다."""
    uid = (req.user_id or "").strip()
    ok = bool(_known_user(uid)) and auth_store.verify(uid, req.password)
    if not ok:
        raise HTTPException(status_code=401,
                            detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    s = auth_store.create_session(uid)
    u = _known_user(uid)
    return {
        "status": "success",
        "data": {
            "token": s["token"],
            "expires_at": s["expires_at"],
            "user_id": uid,
            "display_name": _display_name(u, uid),
            #: ★ 초기 비밀번호를 그대로 쓰는 계정은 화면이 **바꾸라고 말해야 한다.** 알리지
            #  않으면 「전 계정 공통 비밀번호」가 그대로 운영에 들어간다.
            "must_change_password": auth_store.uses_default_password(uid),
        },
    }


@router.post("/logout")
async def logout(request: Request):
    """로그아웃. 토큰이 없거나 이미 죽었어도 **성공으로 답한다** — 사용자가 할 일은 끝났고,
    실패를 알려 봤자 다시 누르는 것 말고 할 수 있는 일이 없다."""
    auth_store.destroy(request.headers.get(SESSION_HEADER, "") or "")
    return {"status": "success", "data": {"ok": True}}


@router.get("/me")
async def me(p: Principal = Depends(current_principal)):
    """지금 누구인가 + 그 권한 요약. **화면이 이것만 보고 진입 여부를 정한다.**

    ⚠️ 권한은 여기서 새로 만들지 않는다 — `Principal.scope` 가 매 요청 해석한 결과 그대로다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    u = _known_user(uid)
    s = p.scope
    return {
        "status": "success",
        "data": {
            "user_id": uid,
            "display_name": _display_name(u, uid),
            "is_admin": bool(getattr(s, "is_admin", False)),
            "is_executive": bool(getattr(s, "is_executive", False)),
            "is_ai_admin": bool(getattr(s, "is_ai_admin", False)),
            "is_data_admin": bool(getattr(s, "is_data_admin", False)),
            "unrestricted": bool(getattr(s, "unrestricted", False)),
            "primary_dept_id": getattr(s, "primary_dept_id", "") or "",
            "must_change_password": auth_store.uses_default_password(uid),
        },
    }


@router.post("/sse-ticket")
async def issue_sse_ticket(request: Request):
    """[P0-1B] SSE 1회용 접속표 발급.

    ## ★★★ 왜 `current_principal` 을 쓰지 않는가

    `current_principal` 은 `ORG_TRUST_HEADER` 가 켜져 있는 동안 **`X-Factory-User` 헤더와
    `?as_user=` 쿼리를 그대로 믿는다.** 그 상태에서 이 라우트가 `current_principal` 을 쓰면
    공격자가 `as_user=관리자` 로 **티켓까지 발급받아** 관리자로 구독할 수 있다 — 우회로를
    막으려고 만든 장치가 새 우회로가 된다.

    그래서 여기서는 **세션 토큰만** 본다. 헤더·쿼리 신원은 쳐다보지 않는다.

    ⚠️ 요청자가 `user_id` 나 `scope` 를 **지정하지 않는다.** 서버가 세션에서 정한다 —
      호출자가 정하게 두면 그것이 곧 사칭이다."""
    tok = (request.headers.get(SESSION_HEADER, "") or "").strip()
    if not tok:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    uid = auth_store.resolve(tok)
    if not uid:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인하십시오.")
    if not _known_user(uid):
        raise HTTPException(status_code=401, detail="등록되지 않은 사용자입니다.")

    #: ⚠️⚠️ **요청 헤더의 `X-Tenant-Id` 를 쓰지 않는다.** 종전에는 그것을 받아 티켓에 저장했는데,
    #  그러면 「요청자가 scope 를 지정하지 않는다」는 계약이 그 자리에서 깨진다 — 공격자가
    #  헤더 하나로 다른 테넌트 범위의 표를 받게 된다.
    #
    #  tenant·scope 는 **인증된 사용자·세션·서버 문맥**에서 나와야 한다. 아직 그 연결이 없으므로
    #  **빈 값으로 둔다**(G1-C 미구현). 모르는 것을 헤더로 채우는 것보다 비워 두는 것이 옳다 —
    #  채워 두면 다음 사람이 「테넌트 경계가 있다」고 믿는다.
    t = auth_store.issue_sse_ticket(uid, tok, tenant_id="")
    #: ⚠️ 응답에만 원문을 싣고 로그에는 남기지 않는다(저장소에는 해시만 있다).
    return {"status": "success", "data": t}


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=5)


@router.post("/password")
async def change_password(req: PasswordChange, request: Request,
                          p: Principal = Depends(current_principal)):
    """자기 비밀번호 변경. **바꾸면 다른 세션을 전부 끊는다** — 비밀번호를 바꾸는 이유의
    절반은 「누가 내 계정을 쓰고 있는 것 같다」이고, 그때 기존 세션이 살아 있으면 소용이 없다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if not auth_store.verify(uid, req.current_password):
        raise HTTPException(status_code=403, detail="현재 비밀번호가 올바르지 않습니다.")
    if req.new_password == DEFAULT_PASSWORD:
        raise HTTPException(status_code=400,
                            detail="초기 비밀번호로는 바꿀 수 없습니다 — 다른 값을 쓰십시오.")
    auth_store.set_password(uid, req.new_password)
    keep = request.headers.get(SESSION_HEADER, "") or ""
    auth_store.destroy_all_for(uid)
    fresh = auth_store.create_session(uid) if keep else None
    return {"status": "success",
            "data": {"ok": True, "token": (fresh or {}).get("token", "")}}
