"""★★★ [G1-C / G1-C1.1] 프로젝트 가시성 판정 — **한 곳에서만 답한다.**

## 왜 `api/routes/factory_control.py` 에서 옮겼는가 (G1-C)

이 규칙은 원래 라우트 파일 안의 사설 함수였다. 목록 API 만 쓰던 동안은 그래도 됐다.
G1-C 로 **SSE 이벤트도 같은 질문을 하게 되면서** 사정이 달라졌다 —
「이 프로젝트가 이 사람에게 보이는가」에 두 곳이 각자 답하기 시작하면,
목록에서는 안 보이는 프로젝트의 진행 이벤트가 실시간으로 흘러드는 상태가 만들어진다.
그리고 그 어긋남은 **조용하다.**

## 무엇이 틀렸었나 (G1-C1.1 교차검증에서 드러남)

1차 구현은 **판독 실패와 미바인딩을 구별하지 않았다.** 메타 파일 누락 · JSON 손상 · 읽기
오류를 전부 `{}` 로 바꾸고, 그것을 「소유권 미기록」으로 읽어 **열어 주었다.**
실측 결과 61개 프로젝트 중 바인딩 7 · 미바인딩 53 · 메타 없음 1 이었다. 즉
「목록 61 대 54」라고 보고한 격리는 **7개에서만 일어나고 있었고**, 나머지는 사실상 전원 공개였다.

그래서 상태를 넷으로 가른다.

    BOUND           명시된 범위로 판정한다
    COMPANY_PUBLIC  명시적으로 전사 공개를 선언한 것만
    LEGACY_UNBOUND  마이그레이션 대상 — 제한 노출
    INVALID         메타 없음 · 손상 · 판독 불가 → **Fail-closed**

⚠️⚠️ **판정 실패를 «공개» 로 답하지 않는다.** 1차 구현은 `except: return True` 였다.
  「하위호환이 우선」이라는 원본의 판단을 그대로 옮긴 것인데, **보안 판정에서는 그 보수성이
  방향을 거꾸로 잡은 것**이다. 열람 실패는 화면이 비는 것으로 끝나지만, 판정 실패를 공개로
  답하면 그 순간 통제가 없다.

## `private` 는 정식 상태다

`visibility="private"` 는 **소유자 본인과 플랫폼 관리자만** 본다. 검증 샌드박스로 옮긴 과거
시험 산출물이 이 상태를 쓴다 — 실제 부서에 추정 배정하면 시험 산출물이 조직 자산·경영
데이터처럼 검색되고 집계된다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

#: 소유권 바인딩 상태. 문자열로 두는 이유 — 프로젝트 메타·API 응답·로그에 그대로 실린다.
BOUND = "BOUND"
COMPANY_PUBLIC = "COMPANY_PUBLIC"
LEGACY_UNBOUND = "LEGACY_UNBOUND"
INVALID = "INVALID"

#: 검증 샌드박스 조직 코드. 과거 시험 산출물이 실제 부서로 새어 들어가지 않게 하는 격벽.
#: ⚠️ 이 범위의 자료는 경영 브리핑·실적·지식 승격·CERTIFIED 계산 기준선에서 제외한다.
SANDBOX_SCOPE_CODE = "AFS_TEST_SANDBOX"
SANDBOX_ENTITY_MODE = "VIRTUAL"
SANDBOX_NODE_TYPE = "validation_sandbox"


def project_meta_path(workspace_root: str) -> str:
    return os.path.join(workspace_root, "project_meta.json")


def read_project_ownership(workspace_root: str) -> Dict[str, Any]:
    """소유권 필드만 별도로 읽는다 (설계서 Phase 3).

    ★★ [G1-C1.1] 결과에 **`binding_state` 를 함께 담는다.** 종전에는 실패도 미기록도 똑같이
      `{}` 였고, 호출부는 둘을 구별할 방법이 없었다 — 그래서 손상된 메타가 «공개» 로 읽혔다.

    ⚠️ `_read_project_meta` 의 3-튜플 반환은 **바꾸지 않는다** — 호출부가 많아 시그니처를
      건드리면 전 경로가 깨진다."""
    path = project_meta_path(workspace_root)
    if not os.path.exists(path):
        return {"binding_state": INVALID, "binding_reason": "project_meta.json 이 없습니다."}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {"binding_state": INVALID,
                    "binding_reason": "project_meta.json 의 최상위가 객체가 아닙니다."}
    except Exception as e:
        # ⚠️ 여기서 `{}` 를 돌려주면 **손상된 메타가 「미기록 = 공개」로 읽힌다.**
        return {"binding_state": INVALID, "binding_reason": f"project_meta.json 판독 실패: {e}"}

    own = {
        "owner_dept_id": str(d.get("owner_dept_id", "") or ""),
        "owner_user_id": str(d.get("owner_user_id", "") or ""),
        "visibility": str(d.get("visibility", "dept") or "dept"),
        "nature": str(d.get("nature", "") or ""),
        "forked_from": d.get("forked_from") or {},
        # [ECM-lite] 설계서 §10.2 "프로젝트는 반드시 enterprise_scope_id 와 entity_mode 를
        #   소유한다". 구 프로젝트는 기본값(기본 테넌트 · 실제 문맥)으로 읽는다.
        "tenant_id": str(d.get("tenant_id", "") or "tenant_default"),
        "enterprise_scope_id": str(d.get("enterprise_scope_id", "") or ""),
        "entity_mode": str(d.get("entity_mode", "") or "REAL"),
        "blueprint_id": str(d.get("blueprint_id", "") or ""),
        #: [G1-C1.1] 소유가 어떻게 정해졌는가. 추정 배정과 사용자 선언을 구별한다.
        "ownership_basis": str(d.get("ownership_basis", "") or ""),
        "data_origin": str(d.get("data_origin", "") or ""),
    }
    own["binding_state"] = _classify(own)
    return own


def _classify(own: Dict[str, Any]) -> str:
    """무엇으로 판정할 수 있는 상태인가."""
    vis = own.get("visibility", "dept")
    if vis == "company":
        return COMPANY_PUBLIC
    if own.get("owner_dept_id") or own.get("owner_user_id") or own.get("enterprise_scope_id"):
        return BOUND
    return LEGACY_UNBOUND


def ownership_visible(scope, user_id: str, own: Optional[Dict[str, Any]]) -> bool:
    """이 소유권 정보를 가진 자원이 이 사람에게 보이는가 (예외를 던지지 않는 목록 필터용).

    ★ `Principal` 이 아니라 `(scope, user_id)` 를 받는다. `core/` 가 `api/` 의 타입을 알면
      의존 방향이 뒤집히고, SSE 브로드캐스터처럼 **요청 밖에서** 판정해야 하는 호출자가
      Principal 을 만들 수 없다.

    ⚠️⚠️ **판정에 필요한 것이 없으면 «보이지 않는다» 로 답한다.** 종전에는 여기서 `True` 였다."""
    uid = (user_id or "").strip()
    if own is None:
        return False                                  # 재료가 없다 = 판정 불가 = 차단
    state = own.get("binding_state") or _classify(own)
    if state == INVALID:
        # ⚠️ 무제한 권한자에게도 열지 않는다. 손상된 메타는 **고쳐야 할 것**이고, 관리자 화면에
        #   조용히 섞여 보이면 아무도 고치지 않는다. 목록 API 는 이것을 «점검 필요» 로 드러낸다.
        return False

    try:
        unrestricted = bool(scope is not None and scope.unrestricted)
        is_platform_admin = bool(getattr(scope, "is_admin", False))
    except Exception:
        return False                                  # 권한 객체가 이상하면 차단

    vis = own.get("visibility", "dept")

    # ── private: 소유자 본인과 플랫폼 관리자만 ────────────────────────────
    #   ⚠️ `unrestricted`(조직 미도입·강제 해제) 는 **여기서도 통과시킨다** — 조직을 세우기
    #     전에는 모든 필터가 no-op 이어야 한다는 저장소 공통 계약(AccessScope 주석)이다.
    if vis == "private":
        if unrestricted or is_platform_admin:
            return True
        return bool(uid) and own.get("owner_user_id") == uid

    if unrestricted:
        return True
    if state == COMPANY_PUBLIC:
        return True
    if state == LEGACY_UNBOUND:
        # 마이그레이션 대상 — 제한 노출. 플랫폼 관리자만 본다.
        # ⚠️ 이 상태가 남아 있다는 것 자체가 부채다. 신규 생성은 Fail-closed 로 막는다.
        return is_platform_admin
    if own.get("owner_user_id") and own["owner_user_id"] == uid:
        return True
    dept = own.get("owner_dept_id", "")
    try:
        return bool(dept) and dept in scope.readable_dept_ids
    except Exception:
        return False


def user_can_see_project(user_id: str, project_id: str) -> bool:
    """[G1-C] **요청 밖에서** 쓰는 편의 판정 — SSE 이벤트 배달용.

    ⚠️ 권한(scope)을 **부를 때마다 다시 해석한다.** 구독 시점에 굳혀 두면 안 된다 —
      SSE 연결은 12시간까지 살아 있고, 그 사이 권한을 회수해도 이미 열린 스트림으로는
      계속 흘러간다. `api/deps` 가 세션 토큰에 권한을 담지 않는 이유와 같다.

    ⚠️ 판정에 필요한 것을 못 읽으면 **보이지 않는 쪽**으로 답한다."""
    pid = (project_id or "").strip()
    if not pid:
        return False
    try:
        from core.org_directory import org_directory
        from core.paths import workspace_path
        scope = org_directory.resolve_scope((user_id or "").strip())
        return ownership_visible(scope, (user_id or "").strip(),
                                 read_project_ownership(workspace_path(pid)))
    except Exception:
        return False


def is_sandbox(own: Optional[Dict[str, Any]]) -> bool:
    """검증 샌드박스 자료인가.

    ★ 경영 브리핑·실적·지식 승격·CERTIFIED 계산 기준선은 이것을 **제외**해야 한다.
      시험 산출물이 실제 조직 자산처럼 검색되고 집계되면, 그 수치를 보고 경영 판단을 한다."""
    if not own:
        return False
    return (str(own.get("entity_mode", "")) == SANDBOX_ENTITY_MODE
            and str(own.get("nature", "")) == "test_fixture")
