"""조직·사용자·권한 REST API. prefix /api/v1/org (설계서 Phase 1).

응답 봉투는 리포 관례 {"status": "success", "data": ...}.
오류 매핑은 master_control.py 의 _domain_err 와 동일 규약(중복/충돌 409, 검증 실패 400).
동기 SQLite 접근은 asyncio.to_thread 로 감싸 이벤트 루프를 막지 않는다.

⚠️ 조직 미도입 상태에서도 이 라우트는 정상 동작한다 — `/me` 는 unrestricted 스코프를 돌려주고
   목록은 빈 배열이다. 조직을 등록하기 전까지 기존 기능은 전혀 영향받지 않는다.
"""
import asyncio
import functools
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ★ [Phase 2] 식별·권한 판정을 라우트에서 하지 않는다. `api/deps.py` 단일 지점이 담당한다.
#   그래야 SSO 이행 시 라우트를 하나도 안 고치고 전환된다.
from api.deps import (Principal, assert_can_edit_org, current_principal, hidden_envelope,
                      visibility_block_reason)
from core.enterprise_context import audit
from core.master_data import MasterDataError
from core.org_directory import org_directory

router = APIRouter(prefix="/api/v1/org")


def _actor(p: Principal) -> str:
    """감사로그에 남길 행위자.

    ★ **비어 있어도 막지 않는다.** 부트스트랩(사용자 0명)에서는 익명으로 첫 관리자를 만들어야
      하고, 여기서 401 을 내면 시스템이 잠긴다(실측). 대신 감사로그에 `anonymous` 로 남는다 —
      "식별되지 않은 경로로 조직이 바뀌었다"는 사실 자체가 조사 대상이므로 기록은 건너뛰지 않는다.
      실제로 이 기록이 없어서, 2026-07-27 에 최상위 부서 이름이 바뀐 사건의 행위자를 끝내
      확인할 수 없었다."""
    return (p.user_id or "").strip()


def _err(e: MasterDataError):
    msg = str(e)
    if "이미 존재" in msg or "폐지할 수 없" in msg:
        raise HTTPException(status_code=409, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


# ── 요청 모델 ─────────────────────────────────────────────────────────────
class DeptCreate(BaseModel):
    dept_id: str
    name_ko: str
    parent_id: str = ""
    master_domains: List[str] = []
    default_template_id: str = ""
    domain_agents: List[str] = []
    legacy_domain: str = ""
    aliases: List[str] = []
    #: 이 부서가 대응하는 ECM 조직 노드(예: MNM_BATTERY). 비우면 미지정 — 그 부서 사람들에게는
    #: 조직 소유 자료가 보이지 않는다(관문 A: 미지정 = 비노출).
    scope_node_id: str = ""


class DeptUpdate(BaseModel):
    name_ko: Optional[str] = None
    parent_id: Optional[str] = None
    master_domains: Optional[List[str]] = None
    default_template_id: Optional[str] = None
    domain_agents: Optional[List[str]] = None
    legacy_domain: Optional[str] = None
    scope_node_id: Optional[str] = None


class UserUpsert(BaseModel):
    user_id: str
    display_name: str
    primary_dept_id: str = ""
    is_executive: bool = False
    is_admin: bool = False
    is_data_admin: bool = False
    #: ★ 저장소가 받는 칸을 **빠짐없이** 싣는다. 빠뜨리면 화면에서 켤 수 없는 권한이
    #:   생기고, 그때는 DB 를 직접 고치게 된다.
    is_ai_admin: bool = False


class RolesUpdate(BaseModel):
    roles: Dict[str, str] = {}      # {dept_id: viewer|member|manager}


# ── 조회 ─────────────────────────────────────────────────────────────────
@router.get("/me")
async def whoami(p: Principal = Depends(current_principal)):
    """현재 요청자와 확정 권한 스코프. 프론트의 화면 게이팅이 이 값을 기준으로 한다.

    ★ [2026-07-30] **강제 여부와 식별 상태를 함께 준다.** 권한 강제를 켠 뒤 식별되지 않은
      사용자는 목록이 전부 비는데, 그 이유를 화면이 설명하지 못하면 사용자는 "시스템이
      고장났다"고 판단한다 — 오늘 내내 막아 온 조용한 실패와 같은 유형이다.
      이 값으로 화면이 "익명으로 보고 있습니다"를 말할 수 있어야 강제를 켤 수 있다."""
    data = p.scope.to_dict()
    identified = bool((p.user_id or "").strip())
    # ⚠️ try 안에서만 만들면 조회가 실패했을 때 아래 capability 계산이 NameError 로 죽는다.
    _u = None
    try:
        from core.org_directory import _org_enforce_effective, org_directory
        enforced = _org_enforce_effective()
        _u = org_directory.get_user(p.user_id) if identified else None
        # ★ [2026-07-31 실측] **폐지 여부를 등록 여부와 분리한다.**
        #   `resolve_scope` 는 status != active 를 미등록과 같게 처리해 권한을 0으로 만든다.
        #   그런데 여기서 `get_user` 결과만 보고 "등록됨"이라고 답하면, 화면은 빈 목록의 이유를
        #   **부서 미배정**이라고 설명한다(실측: 폐지한 `admin` 이 그 안내를 받았다).
        #   ⚠️ 판정은 같은데 설명이 다르면 사용자는 관리자에게 "부서를 배정해 달라"고 요청하고,
        #     관리자는 이미 배정된 것을 보고 시스템 오류로 판단한다 — 실제 이유(계정 폐지)는
        #     아무도 보지 못한다. 권한의 단일 판정 지점과 **같은 규칙**을 화면도 써야 한다.
        retired = bool(_u) and str(_u.get("status", "active")) != "active"
        registered = bool(_u) and not retired
        bootstrap = org_directory.is_bootstrap()
    except Exception as e:                                       # pragma: no cover
        enforced, registered, bootstrap, retired = False, False, False, False
        data["resolve_error"] = str(e)
    data.update({
        "user_id": p.user_id or "", "identified": identified,
        "registered": registered, "org_enforced": bool(enforced),
        "bootstrap": bool(bootstrap), "retired": bool(retired),
    })
    # ★★ [D-017] 관리자 capability 를 **여기서 함께 준다.** 3단계 강제(① 메뉴 가시성
    #   ② Route Guard ③ 서버 재검사)가 전부 같은 표를 봐야 한다 — 화면이 자기 규칙으로
    #   메뉴를 그리면 서버가 막는 것과 화면이 숨기는 것이 서서히 갈라지고, 갈라진 그 틈이
    #   «보이는데 안 되는» 또는 «안 보이는데 되는» 상태가 된다.
    # ⚠️ 이 값은 **편의용**이다. 최종 권한 진실원본은 서버 API 재검사이며, 화면이 이 값을
    #   조작해도 서버 판정은 바뀌지 않는다(D-017 «페이지 분리는 보안 자체가 아니다»).
    try:
        from core.admin_capability import resolve as _resolve_caps
        _caps = _resolve_caps(p.scope, _u if identified else None)
        data["admin"] = _caps.to_dict()
    except Exception as e:                                       # pragma: no cover
        # 권한 계산 실패를 «권한 있음» 으로 두지 않는다 — 실패는 닫히는 쪽이어야 한다.
        data["admin"] = {"capabilities": [], "any_admin": False, "visible_tabs": [],
                         "bootstrap": False, "resolve_error": str(e)}
    if enforced and not identified:
        # ⚠️ [P0-1C] 종전 안내는 «우측 상단에서 사용자를 지정하십시오» 였다. 그 전환기는
        #   로그인 도입으로 사라졌고, 헤더 신뢰도 껐다 — 지금 할 수 있는 일은 로그인뿐이다.
        #   없는 조작을 가리키는 안내는 사용자를 그 자리에 묶어 둔다.
        data["access_note"] = ("**익명으로 보고 있습니다.** 조직 권한 강제가 켜져 있어 목록이 "
                               "비어 보입니다 — 자료가 없는 것이 아닙니다. 로그인하십시오.")
    elif enforced and retired:
        data["access_note"] = (f"**'{p.user_id}' 계정은 폐지되었습니다.** 권한이 회수되어 어떤 "
                               f"자료도 보이지 않습니다 — 부서 배정 문제가 아닙니다. 계정이 다시 "
                               f"필요하면 관리자에게 재등록을 요청하십시오.")
    elif enforced and not registered:
        data["access_note"] = (f"**'{p.user_id}' 는 등록되지 않은 사용자입니다.** 조직 권한 "
                               f"강제가 켜져 있어 어떤 부서 자료도 보이지 않습니다 — 관리자에게 "
                               f"사용자 등록·부서 배정을 요청하십시오.")
    elif enforced and not (data.get("unrestricted") or data.get("readable_dept_ids")):
        data["access_note"] = ("**부서가 배정되지 않았습니다.** 읽을 수 있는 부서가 없어 목록이 "
                               "비어 보입니다 — 관리자에게 부서 배정을 요청하십시오.")
    elif not enforced:
        data["access_note"] = ("조직 권한 강제가 **꺼져 있습니다** — 지금은 모든 사용자가 전체를 "
                               "봅니다(조직 범위·등급 통제가 작동하지 않습니다).")
    else:
        data["access_note"] = ""
    return {"status": "success", "data": data}


def _assert_directory_readable(p: Principal, what: str):
    """★★★ [2026-08-04 이관 4/10 실측 결함] 조직 읽기 라우트에 **자격 검사가 없었다.**
    익명 요청 하나로 전 직원 21명의 **이름·이메일·소속 부서·관리자 여부**가 그대로 나왔다.
    이건 목록이 새는 것이 아니라 **개인정보가 새는 것**이다 — 명부는 그 자체로 조직 규모·
    인사 구조·권한 보유자를 알려주고, 그 조합은 표적 공격의 출발점이 된다.

    ⚠️ 404 로 숨기지 않는다. 부서·사람의 «존재»는 비밀이 아니고(같이 일하는 사람들이다),
      404 로 두면 «없는 부서»와 «권한 없음»이 섞여 관리자가 원인을 못 찾는다.
    """
    reason = visibility_block_reason(p)
    if reason:
        audit.record(audit.ACCESS_DENIED_UNAUTHENTICATED, "org_directory", what,
                     actor=p.user_id, reason=reason,
                     detail="조직·사용자 명부 조회 자격 없음")
        raise HTTPException(status_code=403, detail=reason)


@router.get("/tree")
async def get_tree(p: Principal = Depends(current_principal)):
    """부서 트리.

    ★ 결정: 트리는 자격이 있는 사용자에게 **전체**를 준다. 조직도는 사내 공개 정보이고,
      범위로 잘라 내면 상위 조직이 사라져 트리 자체가 해석되지 않는다(부모 없는 노드가 뜬다).
      가릴 것은 **사람**이지 회사의 구조가 아니다 — 사용자 명부는 아래에서 범위로 필터한다."""
    _assert_directory_readable(p, "(부서 트리)")
    return {"status": "success", "data": await asyncio.to_thread(org_directory.get_tree)}


@router.get("/departments")
async def list_departments(include_retired: bool = False,
                           p: Principal = Depends(current_principal)):
    _assert_directory_readable(p, "(부서 목록)")
    data = await asyncio.to_thread(org_directory.list_departments, include_retired)
    return {"status": "success", "data": data}


@router.get("/departments/{dept_id}")
async def get_department(dept_id: str, p: Principal = Depends(current_principal)):
    _assert_directory_readable(p, dept_id)
    d = await asyncio.to_thread(org_directory.get_department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"부서 '{dept_id}' 가 없습니다.")
    return {"status": "success", "data": d}


@router.get("/departments/{dept_id}/history")
async def dept_history(dept_id: str, p: Principal = Depends(current_principal)):
    """개편 이력 — 과거 산출물의 소유 부서를 해석하려면 구판이 필요하다."""
    _assert_directory_readable(p, dept_id)
    data = await asyncio.to_thread(org_directory.get_department_history, dept_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"부서 '{dept_id}' 이력이 없습니다.")
    return {"status": "success", "data": data}


# ── 부서 편집 ────────────────────────────────────────────────────────────
@router.post("/departments")
async def create_department(req: DeptCreate, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    try:
        d = await asyncio.to_thread(
            org_directory.create_department, req.dept_id, req.name_ko, req.parent_id,
            req.master_domains, req.default_template_id, req.domain_agents,
            req.legacy_domain, req.aliases, req.scope_node_id, _actor(p))
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": d}


@router.put("/departments/{dept_id}")
async def update_department(dept_id: str, req: DeptUpdate,
                            p: Principal = Depends(current_principal)):
    """개정. 새 버전이 되고 구판은 이력으로 보존된다. parent_id 변경 시 하위 트리가 함께 이동한다."""
    assert_can_edit_org(p)
    try:
        d = await asyncio.to_thread(
            org_directory.update_department, dept_id, req.name_ko, req.parent_id,
            req.master_domains, req.default_template_id, req.domain_agents, req.legacy_domain,
            req.scope_node_id, _actor(p))
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": d}


@router.delete("/departments/{dept_id}")
async def retire_department(dept_id: str, p: Principal = Depends(current_principal)):
    """소프트 폐지. 물리 삭제하지 않는다 — ownership 이 참조하므로 과거 해석이 깨지면 안 된다."""
    assert_can_edit_org(p)
    try:
        ok = await asyncio.to_thread(org_directory.retire_department, dept_id, _actor(p))
    except MasterDataError as e:
        _err(e)
    if not ok:
        raise HTTPException(status_code=404, detail=f"부서 '{dept_id}' 가 없습니다.")
    return {"status": "success", "data": {"dept_id": dept_id, "status": "retired"}}


# ── 사용자 ───────────────────────────────────────────────────────────────
def _user_in_scope(p: Principal, u: dict) -> bool:
    """이 사용자를 명부에서 보여줄 것인가.

    ⚠️ «자기 자신»은 항상 보인다 — 자기 소속·권한을 못 보면 무엇을 요청해야 할지 알 수 없다.
      그 밖에는 **읽기 가능한 부서에 속한 사람만**. 부서가 없는 사람은 보이지 않는다:
      미배정을 «전사 공개»로 읽으면 이행 기간에 들어온 모든 계정이 전원에게 노출된다
      (관문 A 가 막으려던 결과와 같다)."""
    if p.scope.unrestricted or getattr(p.scope, "can_edit_org", False):
        return True
    uid = (p.user_id or "").strip()
    if uid and str(u.get("user_id", "")).strip() == uid:
        return True
    dept = str(u.get("primary_dept_id") or "").strip()
    return bool(dept) and p.scope.can_read(dept)


@router.get("/users")
async def list_users(p: Principal = Depends(current_principal)):
    """사용자 명부. **범위 밖 인원은 주지 않는다.**

    ★ 조직 편집 권한자에게는 전량과 정확한 숨김 건수를, 일반 사용자에게는 자기 부서 인원과
      «가려진 것이 있다»는 사실만 준다(`api.deps.hidden_envelope` — 자료 종류는 `org`).
      전 직원 수는 그 자체로 조직 규모를 알려주므로 건수도 권한을 따른다."""
    _assert_directory_readable(p, "(사용자 명부)")
    rows = await asyncio.to_thread(org_directory.list_users)
    shown = [u for u in rows if _user_in_scope(p, u)]
    return {"status": "success", "data": shown,
            **hidden_envelope(p, len(rows), len(shown), exact_for="org")}


@router.get("/users/{user_id}")
async def get_user(user_id: str, p: Principal = Depends(current_principal)):
    _assert_directory_readable(p, user_id)
    u = await asyncio.to_thread(org_directory.get_user, user_id)
    if not u:
        raise HTTPException(status_code=404, detail=f"사용자 '{user_id}' 가 없습니다.")
    if not _user_in_scope(p, u):
        # 개인의 권한 플래그·역할은 명부 한 줄보다 민감하다. 범위 밖이면 상세를 주지 않는다.
        audit.denied_scope("org_user", user_id, actor=p.user_id,
                           actor_scopes=sorted(p.scope.readable_dept_ids or ()),
                           detail="읽기 가능한 부서 밖 사용자의 상세 조회")
        raise HTTPException(status_code=403,
                            detail="읽을 수 있는 부서 밖의 사용자입니다 — 상세를 표시하지 않습니다.")
    return {"status": "success", "data": u}


@router.post("/users")
async def upsert_user(req: UserUpsert, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    try:
        #: ★★★ **이름으로 넘긴다.** ⚠️ 위치로 넘기고 있었고 `is_ai_admin` 을 빠뜨려
        #:   `actor` 가 그 자리에 들어갔다 — 저장소가 `int('hikwon@lsmnm.com')` 을
        #:   시도하며 **500** 이었다. 즉 관리자 화면에서 **사용자를 추가·수정할 수
        #:   없었다.** 위치 인자는 서명이 늘어나는 순간 조용히 어긋난다.
        u = await asyncio.to_thread(
            functools.partial(
                org_directory.upsert_user,
                req.user_id, req.display_name,
                primary_dept_id=req.primary_dept_id,
                is_executive=req.is_executive, is_admin=req.is_admin,
                is_data_admin=req.is_data_admin, is_ai_admin=req.is_ai_admin,
                actor=_actor(p)))
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": u}


@router.put("/users/{user_id}/roles")
async def set_roles(user_id: str, req: RolesUpdate,
                    p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    try:
        u = await asyncio.to_thread(org_directory.set_user_roles, user_id, req.roles,
                                    _actor(p))
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": u}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    ok = await asyncio.to_thread(org_directory.delete_user, user_id, _actor(p))
    if not ok:
        raise HTTPException(status_code=404, detail=f"사용자 '{user_id}' 가 없습니다.")
    return {"status": "success", "data": {"user_id": user_id, "status": "retired"}}


# ── 시드 · 재구축 ────────────────────────────────────────────────────────
@router.post("/seed")
async def seed(p: Principal = Depends(current_principal)):
    """하드코딩되어 있던 부서 맵을 `departments` 로 최초 적재(멱등).

    이 시드가 돌고 나면 코드에서 부서를 지워도 되고, 이후 부서 추가·개명·이동·폐지에
    코드 수정이 필요 없어진다."""
    assert_can_edit_org(p)
    from core.org_seed import seed_departments
    return {"status": "success", "data": await asyncio.to_thread(seed_departments)}


@router.post("/reconcile")
async def reconcile(p: Principal = Depends(current_principal)):
    """파일(project_meta.json / release.json)에서 `ownership` 미러를 재구축한다.

    미러가 필요한 이유: 프로젝트·릴리스 목록이 전량 디렉터리 스캔 + 파일 오픈이라
    거기에 부서 필터·정렬·페이지네이션을 얹으면 감당이 안 된다. 미러가 어긋나면 이 API 로 재구축한다."""
    assert_can_edit_org(p)
    from core.org_seed import reconcile_ownership
    return {"status": "success", "data": await asyncio.to_thread(reconcile_ownership)}
