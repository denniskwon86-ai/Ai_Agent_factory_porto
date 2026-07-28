"""조직·사용자·권한 REST API. prefix /api/v1/org (설계서 Phase 1).

응답 봉투는 리포 관례 {"status": "success", "data": ...}.
오류 매핑은 master_control.py 의 _domain_err 와 동일 규약(중복/충돌 409, 검증 실패 400).
동기 SQLite 접근은 asyncio.to_thread 로 감싸 이벤트 루프를 막지 않는다.

⚠️ 조직 미도입 상태에서도 이 라우트는 정상 동작한다 — `/me` 는 unrestricted 스코프를 돌려주고
   목록은 빈 배열이다. 조직을 등록하기 전까지 기존 기능은 전혀 영향받지 않는다.
"""
import asyncio
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ★ [Phase 2] 식별·권한 판정을 라우트에서 하지 않는다. `api/deps.py` 단일 지점이 담당한다.
#   그래야 SSO 이행 시 라우트를 하나도 안 고치고 전환된다.
from api.deps import Principal, assert_can_edit_org, current_principal
from core.master_data import MasterDataError
from core.org_directory import org_directory

router = APIRouter(prefix="/api/v1/org")


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


class DeptUpdate(BaseModel):
    name_ko: Optional[str] = None
    parent_id: Optional[str] = None
    master_domains: Optional[List[str]] = None
    default_template_id: Optional[str] = None
    domain_agents: Optional[List[str]] = None
    legacy_domain: Optional[str] = None


class UserUpsert(BaseModel):
    user_id: str
    display_name: str
    primary_dept_id: str = ""
    is_executive: bool = False
    is_admin: bool = False
    is_data_admin: bool = False


class RolesUpdate(BaseModel):
    roles: Dict[str, str] = {}      # {dept_id: viewer|member|manager}


# ── 조회 ─────────────────────────────────────────────────────────────────
@router.get("/me")
async def whoami(p: Principal = Depends(current_principal)):
    """현재 요청자와 확정 권한 스코프. 프론트의 화면 게이팅이 이 값을 기준으로 한다."""
    return {"status": "success", "data": p.scope.to_dict()}


@router.get("/tree")
async def get_tree():
    return {"status": "success", "data": await asyncio.to_thread(org_directory.get_tree)}


@router.get("/departments")
async def list_departments(include_retired: bool = False):
    data = await asyncio.to_thread(org_directory.list_departments, include_retired)
    return {"status": "success", "data": data}


@router.get("/departments/{dept_id}")
async def get_department(dept_id: str):
    d = await asyncio.to_thread(org_directory.get_department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"부서 '{dept_id}' 가 없습니다.")
    return {"status": "success", "data": d}


@router.get("/departments/{dept_id}/history")
async def dept_history(dept_id: str):
    """개편 이력 — 과거 산출물의 소유 부서를 해석하려면 구판이 필요하다."""
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
            req.legacy_domain, req.aliases)
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
            req.master_domains, req.default_template_id, req.domain_agents, req.legacy_domain)
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": d}


@router.delete("/departments/{dept_id}")
async def retire_department(dept_id: str, p: Principal = Depends(current_principal)):
    """소프트 폐지. 물리 삭제하지 않는다 — ownership 이 참조하므로 과거 해석이 깨지면 안 된다."""
    assert_can_edit_org(p)
    try:
        ok = await asyncio.to_thread(org_directory.retire_department, dept_id)
    except MasterDataError as e:
        _err(e)
    if not ok:
        raise HTTPException(status_code=404, detail=f"부서 '{dept_id}' 가 없습니다.")
    return {"status": "success", "data": {"dept_id": dept_id, "status": "retired"}}


# ── 사용자 ───────────────────────────────────────────────────────────────
@router.get("/users")
async def list_users():
    return {"status": "success", "data": await asyncio.to_thread(org_directory.list_users)}


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    u = await asyncio.to_thread(org_directory.get_user, user_id)
    if not u:
        raise HTTPException(status_code=404, detail=f"사용자 '{user_id}' 가 없습니다.")
    return {"status": "success", "data": u}


@router.post("/users")
async def upsert_user(req: UserUpsert, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    try:
        u = await asyncio.to_thread(
            org_directory.upsert_user, req.user_id, req.display_name, req.primary_dept_id,
            req.is_executive, req.is_admin, req.is_data_admin)
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": u}


@router.put("/users/{user_id}/roles")
async def set_roles(user_id: str, req: RolesUpdate,
                    p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    try:
        u = await asyncio.to_thread(org_directory.set_user_roles, user_id, req.roles)
    except MasterDataError as e:
        _err(e)
    return {"status": "success", "data": u}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    ok = await asyncio.to_thread(org_directory.delete_user, user_id)
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
