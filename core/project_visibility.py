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

## ★★★ [G1-C3] 두 축을 나누고 **AND 로 묶는다**

    최종 가시성 = authorization_visible(권한)  AND  context_visible(지금 고른 문맥)

권한은 「볼 수 있는가」이고 문맥은 「지금 무엇을 보기로 했는가」다. 둘을 한 함수에 섞으면
어느 쪽 때문에 안 보이는지 말할 수 없고, 그러면 화면은 «0건» 만 보여 준다 —
사용자는 자료가 없는 것인지 권한이 없는 것인지 문맥이 어긋난 것인지 알 수 없다.

목록·상세·수정·SSE 가 **모두 이 함수**를 부른다. 하나라도 다른 규칙을 쓰면
「목록엔 보이는데 이벤트는 안 오는」 또는 그 반대의 어긋남이 생기고, 그것은 조용하다.

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
#: 소유를 유도할 수 없는 시험 산출물의 **임시 관리 책임자**. 실제 작성자를 뜻하지 않는다.
#: ⚠️ 승인된 예시 계정 하나만 쓴다 — 임의 계정을 만들면 실제 인원과 충돌한다.
SANDBOX_CUSTODIAN = "hikwon@lsmnm.com"


def sandbox_scope_id() -> str:
    """검증 샌드박스 조직 노드의 실제 `node_id`. 없으면 빈 문자열.

    ⚠️ 여기서 노드를 **만들지 않는다.** 조회 실패를 「없으니 만들자」로 바꾸면, 어쩌다 한 번
      DB 를 못 읽은 순간에 중복 노드가 생긴다. 노드 생성은 마이그레이션 스크립트의 일이다."""
    try:
        from core.enterprise_context.repository import ecm_repository as repo
        node = repo.find_node_by_code(SANDBOX_SCOPE_CODE, tenant_id="tenant_default")
        return node.node_id if node else ""
    except Exception:
        return ""


#: 선택 범위가 하위 조직을 덮는지 볼 때 거슬러 올라갈 최대 깊이. `config.ORG_MAX_DEPTH` 와
#: 같은 뜻이며, 순환 관계가 있어도 여기서 멈춘다.
_SCOPE_MAX_DEPTH = 8


def scope_covers(selected_node_id: str, resource_node_id: str) -> bool:
    """사용자가 **화면에서 고른 조직 범위**가 이 자원의 범위를 덮는가.

    ★★ [G1-C1.2] 권한(`readable_dept_ids`)과 **다른 축**이다. 권한은 「볼 수 있는가」이고
      이것은 「지금 무엇을 보기로 했는가」다. 여러 계열사 권한을 가진 사람이 A 회사를 골랐다면
      B 회사 이벤트는 **권한이 있어도** 오면 안 된다 — 회사 선택기와 실시간 데이터 범위가
      어긋나면 사용자는 자기가 보는 숫자가 어느 회사 것인지 알 수 없다.

    · 고른 범위가 없으면(`""`) 좁히지 않는다 — 「전체」를 고른 것과 같다.
    · 자원에 범위가 없으면 좁히지 않는다 — 옛 자원을 지금 판정으로 지우지 않는다.
    · 같으면 덮는다. 다르면 **자원에서 위로 거슬러 올라가** 고른 노드가 조상인지 본다.

    ⚠️ 권한 상속과 같은 관계(`OPERATING_PARENT`)만 따른다. 공유서비스·연결집계 관계로
      올라가면 「전사 재무조직이 모든 상세 데이터를 본다」가 되고, 그것은 ECM §6.1 이 명시적으로
      막은 것이다."""
    sel = (selected_node_id or "").strip()
    res = (resource_node_id or "").strip()
    if not sel or not res or sel == res:
        return True
    try:
        from core.enterprise_context.models import REL_OPERATING_PARENT
        from core.enterprise_context.repository import ecm_repository as repo
        seen, frontier = {res}, [res]
        for _ in range(_SCOPE_MAX_DEPTH):
            nxt = []
            for node in frontier:
                for parent in repo.parents(node, REL_OPERATING_PARENT) or []:
                    if parent == sel:
                        return True
                    if parent not in seen:
                        seen.add(parent)
                        nxt.append(parent)
            if not nxt:
                break
            frontier = nxt
        return False
    except Exception:
        # ⚠️ 조상 판정에 실패하면 **좁히지 않는다.** 이 축은 «권한» 이 아니라 «지금 보는 범위»
        #   이고, 판정 실패로 화면을 비우면 사용자는 통제가 아니라 고장으로 읽는다.
        #   권한 경계는 `ownership_visible` 이 따로 지킨다.
        return True


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


#: 실행 모드. `SANDBOX` 는 `VIRTUAL` 안의 특수한 경우로 두지 않고 **별도 값**으로 다룬다 —
#: 「가상 회사 시뮬레이션」과 「우리 시험 산출물」은 목적이 다르고, 섞으면 시뮬레이션 결과에
#: 시험 부산물이 들어간다.
ENTITY_MODES = ("REAL", "VIRTUAL", "SANDBOX")

#: 문맥 판정 결과. 왜 안 보이는지 화면이 **다르게 말할 수 있어야** 한다.
CTX_OK = "OK"
CTX_TENANT_MISMATCH = "TENANT_MISMATCH"
CTX_MODE_MISMATCH = "MODE_MISMATCH"
CTX_SCOPE_OUTSIDE = "SCOPE_OUTSIDE"
CTX_RESOURCE_UNBOUND = "RESOURCE_UNBOUND"
CTX_CONTEXT_MISSING = "CONTEXT_MISSING"
CTX_LOOKUP_FAILED = "LOOKUP_FAILED"


def authorization_visible(scope, user_id: str, own: Optional[Dict[str, Any]]) -> bool:
    """축 ①: **이 사람이 이 자원에 접근할 권한이 있는가.** 문맥은 보지 않는다."""
    return ownership_visible(scope, user_id, own)


def context_visible(ctx: Optional[Dict[str, Any]],
                    own: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """축 ②: **지금 고른 회사·조직·실행 문맥과 맞는가.** 권한은 보지 않는다.

    돌려주는 것: `(보이는가, 사유)`. 사유를 함께 주는 이유 — 화면이 「0건」과 「문맥 점검
    필요」를 다르게 말해야 한다. 같은 화면으로 뭉개면 사용자는 통제를 고장으로 읽는다.

    ## 규칙 (D-014 「범위 미지정은 전사 공용이 아니라 비노출」)

    · 문맥의 테넌트·실행모드가 없으면 **판정 불가 → 비노출.**
    · 자원의 테넌트·실행모드·범위가 비어 있어도 **비노출.** 종전에는 빈 값이 모든 비교를
      통과했는데, 그것이 곧 「미지정 = 전사 공용」이었다.
    · 고른 범위가 비면 좁히지 않는다 — 같은 테넌트·같은 모드 안에서 권한이 닿는 전체.
    · 고른 범위가 있으면 자원이 **그 노드이거나 운영 계층상 하위**여야 한다.
    · ECM 계층 조회 실패·순환·끊어진 참조는 **비노출**로 두고 점검 대상으로 보고한다.
    · `visibility="company"` 는 전 세계 공개가 아니라 **같은 테넌트·같은 모드 안에서만** 공개다.

    ⚠️⚠️ 이 함수는 `scope_covers` 와 다르다. `scope_covers` 는 「좁히기」만 하고 실패 시
      통과시켰다(화면 편의). 여기서는 **경계**이므로 실패가 통과가 되면 안 된다."""
    if not isinstance(own, dict) or not own:
        return False, CTX_RESOURCE_UNBOUND
    c = ctx or {}
    c_tenant = str(c.get("tenant_id", "") or "").strip()
    c_mode = str(c.get("entity_mode", "") or "").strip()
    c_scope = str(c.get("scope_node_id", "") or c.get("enterprise_scope_id", "") or "").strip()
    if not c_tenant or not c_mode:
        return False, CTX_CONTEXT_MISSING

    r_tenant = str(own.get("tenant_id", "") or "").strip()
    r_mode = str(own.get("entity_mode", "") or "").strip()
    r_scope = str(own.get("enterprise_scope_id", "") or "").strip()
    if not r_tenant or not r_mode or not r_scope:
        # D-014 — 미지정을 전사 공용으로 읽지 않는다.
        return False, CTX_RESOURCE_UNBOUND
    if r_tenant != c_tenant:
        return False, CTX_TENANT_MISMATCH
    if r_mode != c_mode:
        return False, CTX_MODE_MISMATCH
    if not c_scope:
        return True, CTX_OK              # 「전체」를 고름 — 테넌트·모드 안에서 좁히지 않는다
    if c_scope == r_scope:
        return True, CTX_OK
    ok, failed = _scope_is_ancestor(c_scope, r_scope)
    if failed:
        return False, CTX_LOOKUP_FAILED
    return (True, CTX_OK) if ok else (False, CTX_SCOPE_OUTSIDE)


def _scope_is_ancestor(ancestor: str, node: str) -> Tuple[bool, bool]:
    """`ancestor` 가 `node` 의 운영 계층 상위인가. 돌려주는 것: `(맞는가, 조회실패인가)`.

    ⚠️ 조회 실패를 «맞다» 로도 «아니다» 로도 뭉개지 않는다 — 호출부가 「점검 필요」를 따로
      말할 수 있어야 한다. 순환 관계는 깊이 제한으로 끊고 실패로 세지 않는다."""
    try:
        from core.enterprise_context.models import REL_OPERATING_PARENT
        from core.enterprise_context.repository import ecm_repository as repo
        seen, frontier = {node}, [node]
        for _ in range(_SCOPE_MAX_DEPTH):
            nxt = []
            for n in frontier:
                for parent in repo.parents(n, REL_OPERATING_PARENT) or []:
                    if parent == ancestor:
                        return True, False
                    if parent not in seen:
                        seen.add(parent)
                        nxt.append(parent)
            if not nxt:
                break
            frontier = nxt
        return False, False
    except Exception:
        return False, True


def project_visible(scope, user_id: str, ctx: Optional[Dict[str, Any]],
                    own: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """★★★ [G1-C3] **정본 판정.** 목록·상세·수정·SSE 가 전부 이것을 부른다.

    돌려주는 것: `(보이는가, 사유)`. 권한에서 막히면 `"UNAUTHORIZED"`, 문맥에서 막히면
    위의 `CTX_*` 중 하나다 — 둘을 구분해야 화면이 「없음」·「접근 불가」·「문맥 점검 필요」를
    다르게 말할 수 있다."""
    if not authorization_visible(scope, user_id, own):
        return False, "UNAUTHORIZED"
    return context_visible(ctx, own)


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
