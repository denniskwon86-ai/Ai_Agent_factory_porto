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

from fastapi import Depends, HTTPException, Request

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


def visibility_block_reason(p: Principal) -> str:
    """★★★ [2026-07-31 실측 결함] **자료 목록을 보여줘도 되는가.** 안 되면 그 이유를 돌려준다.

    권한 강제를 켠 뒤 실서버에서 확인한 것: `/api/v1/org/me` 는 익명 사용자에게
    "목록이 비어 보입니다"라고 안내하는데, `/api/v1/knowledge/packs` 는 **지식팩 4건을 그대로
    돌려주고 있었다.** 조직 범위 필터가 호출자 선택(`scope_node_id` 파라미터)이었기 때문이다.

    ⚠️ 이건 배너가 거짓말을 하는 것보다 나쁘다. 관문 A의 계약은 "미지정 = 비노출"인데,
      **필터를 부르지 않으면 통제가 없다**는 뜻이었다. 통제를 호출자 선택으로 두면 새 라우트가
      생길 때마다 구멍이 하나 생기고, 구멍은 조용하다 — 아무도 오류를 보지 못한다.
      그래서 판정을 여기 한 곳에 두고, 목록 라우트는 이 함수를 **부르지 않으면 안 되는 것**으로
      취급한다(리뷰에서 누락을 눈으로 찾을 수 있는 형태).

    빈 문자열이면 허용이다. 강제가 꺼져 있으면 항상 허용한다(하위호환 계약).

    한계(정직하게 기록): 등록·활성 사용자에게는 허용만 판단하고 **소유 조직별 행 필터는 하지
      않는다** — `users` 에 ECM 노드 컬럼이 없어 사용자→조직범위 매핑이 아직 없다. 그 매핑은
      "부서·사용자 배정"(업무 단계)에서 생기며, 그때 이 함수가 노드를 함께 돌려주게 바꾼다.
      지금 실사용자는 무제한 권한 관리자 1명뿐이라 실효 노출 차이는 없다."""
    try:
        from core.org_directory import _org_enforce_effective, org_directory
        if not _org_enforce_effective():
            return ""
    except Exception:
        return ""                        # 강제 여부를 모르면 기존 흐름을 막지 않는다
    if getattr(p.scope, "unrestricted", False):
        return ""
    uid = (p.user_id or "").strip()
    if not uid:
        return ("익명으로 보고 있어 자료 목록을 표시하지 않습니다 — 우측 상단에서 사용자를 "
                "지정하십시오.")
    try:
        u = org_directory.get_user(uid)
    except Exception:
        u = None
    if not u:
        return f"'{uid}' 는 등록되지 않은 사용자입니다 — 관리자에게 사용자 등록을 요청하십시오."
    if str(u.get("status", "active")) != "active":
        return f"'{uid}' 계정은 폐지되었습니다 — 권한이 회수되어 자료가 보이지 않습니다."
    if not (p.scope.readable_dept_ids or p.scope.can_manage_standard):
        return f"'{uid}' 에게 배정된 부서가 없습니다 — 관리자에게 부서 배정을 요청하십시오."
    return ""


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


# ── Enterprise Context (ECM-lite) ────────────────────────────────────────
# ECM 설계서 §5.1 은 문맥을 "모든 API·SSE·LLM 호출에 전달되는 토큰"으로 정의한다.
# ⚠️ 추출을 **여기 한 곳**으로 모으는 이유는 사용자 식별과 같다: 전역 컨텍스트 스위처(§5.1)나
#   SSO 가 오면 이 함수 하나만 바꾸면 되고, 라우트마다 헤더를 직접 읽으면 어느 하나를
#   빠뜨렸을 때 그 경로만 문맥 없이 실행된다(그게 곧 격리 구멍이다).
async def current_enterprise_context(request: Request,
                                     p: Principal = None) -> "EnterpriseContext":
    from core.enterprise_context import build_context
    h = request.headers
    scope = h.get(getattr(config, "ECM_SCOPE_HEADER", "X-Enterprise-Scope"), "") or ""
    tenant = h.get(getattr(config, "ECM_TENANT_HEADER", "X-Enterprise-Tenant"), "") or ""
    mode = h.get(getattr(config, "ECM_MODE_HEADER", "X-Entity-Mode"), "") or ""
    # SSE/iframe/다운로드 링크는 헤더를 붙일 수 없다(Phase 2 와 같은 이유로 쿼리도 받는다).
    q = request.query_params
    scope = scope or (q.get("enterprise_scope") or "")
    mode = mode or (q.get("entity_mode") or "")
    # 문맥이 명시되지 않으면 요청자의 소속 부서를 범위로 쓴다 — 스위처가 없는 동안 사용자에게
    # 매번 범위 지정을 강제하면 기존 흐름이 전부 막힌다(단계적 도입).
    fallback = ""
    if p is not None:
        fallback = getattr(p.scope, "primary_dept_id", "") or ""
    return build_context(tenant_id=tenant, enterprise_scope_id=scope,
                         entity_mode=mode, fallback_scope_id=fallback)


async def enterprise_context(request: Request,
                             p: Principal = Depends(current_principal)):
    """라우트가 쓰는 의존성. `Principal` 을 함께 해석해 범위 기본값을 채운다."""
    return await current_enterprise_context(request, p)
