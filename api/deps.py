"""요청자 식별과 권한 검사의 **단일 지점** (설계서 Phase 2).

⚠️ 왜 한 곳으로 모으는가:
  지금은 라우트마다 `Header(X-User-Id)` 를 직접 받고 있다. 그대로 두면 SSO 로 갈 때
  라우트를 전부 고쳐야 하고, 어느 하나를 빠뜨리면 그 경로만 인증이 새어나간다.
  추출을 이 파일 한 곳으로 모으면 **SSO 이행 시 함수 1개 + 미들웨어 1개**만 바뀐다.

식별 우선순위:
  ① `request.state.principal_user_id` — 미래 SSO 미들웨어가 채우는 슬롯(최우선)
  ② `ORG_USER_HEADER` 헤더 — 경량 전환용
  ③ `?as_user=` 쿼리 — EventSource/iframe/ZIP 링크는 헤더를 못 붙인다
  ④ `ORG_DEFAULT_USER_ID`

⚠️ ②③ 은 인증이 아니다. 브라우저가 임의 값을 보낼 수 있다. `ORG_TRUST_HEADER=False` 로
   끄고 ① 만 신뢰하는 것이 최종 형태다.
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

import config
from core.org_directory import AccessScope, org_directory


def _extract_user_id(request: Request) -> str:
    uid = getattr(request.state, "principal_user_id", "") or ""     # ① SSO 슬롯
    if uid:
        return uid
    if getattr(config, "ORG_TRUST_HEADER", True):
        uid = request.headers.get(getattr(config, "ORG_USER_HEADER", "X-Factory-User"), "") or ""
        # 하위호환: Phase 1 의 org_control 이 쓰던 헤더도 받아준다.
        uid = uid or (request.headers.get("X-User-Id", "") or "")
        # ③ SSE/iframe/다운로드 링크는 헤더를 붙일 수 없다.
        uid = uid or (request.query_params.get("as_user") or "")
    return (uid or getattr(config, "ORG_DEFAULT_USER_ID", "")).strip()


@dataclass(frozen=True)
class Principal:
    """현재 요청자와 그 확정 권한. 라우트는 이 객체만 보면 된다."""
    user_id: str
    scope: AccessScope

    @property
    def unrestricted(self) -> bool:
        return self.scope.unrestricted


async def current_principal(request: Request) -> Principal:
    uid = _extract_user_id(request)
    scope = await asyncio.to_thread(org_directory.resolve_scope, uid)
    # 강제 모드인데 식별이 안 되면 401. 무제한(조직 미도입/부트스트랩)이면 통과시킨다 —
    # 그러지 않으면 조직을 세우기도 전에 전 API 가 막힌다.
    if getattr(config, "ORG_ENFORCE", False) and not scope.unrestricted and not uid:
        raise HTTPException(status_code=401, detail="사용자 식별 정보가 없습니다.")
    return Principal(user_id=uid, scope=scope)


# ── 권한 단언 헬퍼 ────────────────────────────────────────────────────────
# 라우트는 이 함수들만 호출한다. 판정 규칙이 바뀌어도 여기만 고치면 된다.

def _deny(msg: str):
    raise HTTPException(status_code=403, detail=msg)


def assert_can_read_dept(p: Principal, dept_id: str):
    if not p.scope.can_read(dept_id):
        _deny(f"'{dept_id}' 부서 자료를 볼 권한이 없습니다.")


def assert_can_write_dept(p: Principal, dept_id: str):
    if not p.scope.can_write(dept_id):
        _deny(f"'{dept_id}' 부서 자료를 수정할 권한이 없습니다.")


def assert_enterprise(p: Principal):
    """전사 롤업·전사 시뮬레이션·전사 승인 — 경영진/관리자만."""
    if not (p.scope.unrestricted or p.scope.can_run_enterprise):
        _deny("전사 단위 실행 권한이 없습니다(경영진/관리자 전용).")


def assert_can_edit_org(p: Principal):
    if not (p.scope.unrestricted or p.scope.can_edit_org):
        _deny("조직·사용자 편집 권한이 없습니다(관리자 전용).")


def assert_can_manage_standard(p: Principal):
    """표준 사전·카탈로그·매핑 승인 — DA/관리자만."""
    if not (p.scope.unrestricted or p.scope.can_manage_standard):
        _deny("데이터 표준 관리 권한이 없습니다(DA/관리자 전용).")


def dept_visible(p: Principal, dept_id: str) -> bool:
    """목록 필터용 — 예외를 던지지 않는 판정."""
    return p.scope.can_read(dept_id)


def _resource_readable(p: Principal, kind: str, rid: str) -> bool:
    if p.scope.unrestricted:
        return True
    own = org_directory.get_ownership(kind, rid)
    if not own:
        return True   # 소유권 미기록 자원은 막지 않는다(미러 재구축 전 하위호환)
    if own.get("visibility") == "company":
        return True
    if own.get("owner_user_id") and own["owner_user_id"] == p.user_id:
        return True
    return bool(own.get("dept_id")) and own["dept_id"] in p.scope.readable_dept_ids


def assert_project_readable(p: Principal, project_id: str):
    if not _resource_readable(p, "project", project_id):
        _deny(f"'{project_id}' 프로젝트를 볼 권한이 없습니다.")


def assert_project_writable(p: Principal, project_id: str):
    if p.scope.unrestricted:
        return
    own = org_directory.get_ownership("project", project_id)
    if not own:
        return
    if own.get("owner_user_id") and own["owner_user_id"] == p.user_id:
        return
    assert_can_write_dept(p, own.get("dept_id", ""))


def assert_release_readable(p: Principal, release_id: str):
    if not _resource_readable(p, "release", release_id):
        _deny(f"'{release_id}' 릴리스를 볼 권한이 없습니다.")


def visible_filter(p: Principal, kind: str) -> Optional[set]:
    """목록 API 가 쓸 가시 자원 집합. `None` = 필터하지 말라(무제한)."""
    ids = org_directory.visible_resources(p.scope, kind)
    return None if ids is None else set(ids)
