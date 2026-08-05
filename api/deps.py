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


def capabilities_of(p: "Principal"):
    """[D-017] 요청자의 확정 관리자 권한. **라우트는 이것만 본다.**

    ★ 사용자 레코드를 함께 넘긴다 — `is_ai_admin` 과 부서 역할이 거기 있고, 그 둘이 없으면
      capability 계산이 조용히 좁아진다."""
    from core.admin_capability import resolve
    u = None
    if (p.user_id or "").strip():
        try:
            u = org_directory.get_user(p.user_id)
        except Exception:
            u = None            # 조회 실패는 **넓히지 않는다** — 실패는 닫히는 쪽이어야 한다
    return resolve(p.scope, u)


def require_caps(p: "Principal", *caps: str, resource: str = "", action: str = ""):
    """서버 재검사(D-017 3단계 중 ③). 없으면 **403** 과 감사 기록.

    ⚠️ 여기가 유일한 보안 경계다. 화면 메뉴 숨김과 Route Guard 는 편의이고, 이 함수만이
      «URL 을 아는 사람» 앞에서 실제로 막는다.
    ★ 거부를 **기록한다.** 기록하지 않으면 "누가 무엇을 시도했는가" 를 나중에 물을 수 없고,
      권한 설계가 맞는지 확인할 근거도 남지 않는다."""
    from core.admin_capability import AdminCapabilityError, require
    c = capabilities_of(p)
    try:
        require(c, *caps)
    except AdminCapabilityError as e:
        try:
            from core.enterprise_context import audit
            audit.record(
                audit.ACCESS_DENIED_UNAUTHENTICATED if not (p.user_id or "").strip()
                else audit.ACCESS_DENIED_SCOPE_MISMATCH,
                resource_type=resource or "agent_registry",
                resource_id=action or ",".join(caps),
                actor=p.user_id or "", outcome="denied",
                reason=str(e), detail=f"required={sorted(caps)}")
        except Exception:
            pass            # 감사 실패가 거부를 성공으로 바꾸면 안 된다 — 거부는 그대로 간다
        # ★★ 401 과 403 을 구분한다(저장소 공통 규약). 사용자가 해야 할 일이 다르다:
        #   401 = «누구인지 밝히십시오» / 403 = «당신에게는 그 권한이 없습니다».
        #   뭉개면 이미 로그인한 사용자가 계속 로그인을 시도하거나, 익명 사용자가 관리자에게
        #   권한을 요청한다 — 둘 다 원인에 도달하지 못한다.
        if not (p.user_id or "").strip():
            raise HTTPException(status_code=401, detail="사용자 식별이 필요합니다.")
        raise HTTPException(status_code=403, detail=str(e))
    return c


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


def _enforced() -> bool:
    """조직 권한 강제가 켜져 있는가. 판정 함수들이 **모두 여기서** 같은 답을 얻는다.

    ⚠️ 이걸 함수마다 따로 확인하면 어긋난다 — 실제로 어긋났다: `visibility_block_reason` 은
      강제를 확인했지만 `viewer_scope_nodes` 는 확인하지 않아, 강제가 꺼진 환경에서
      "목록은 열어 주는데 행 필터가 전부 걸러내는" 상태가 됐다(전체 테스트에서 잡혔다)."""
    try:
        from core.org_directory import _org_enforce_effective
        return bool(_org_enforce_effective())
    except Exception:
        return False                     # 강제 여부를 모르면 기존 흐름을 막지 않는다


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

    행 단위 필터는 `viewer_scope_nodes()` 가 담당한다 — 이 함수는 "목록을 열어도 되는가"만
    판단한다. 둘을 나눈 이유: 열어도 되는 사람에게 **무엇까지** 보이는지는 자료의 소유 조직에
    달렸고, 그 판정은 조직도(ECM)를 봐야 하기 때문이다."""
    from core.org_directory import org_directory
    if not _enforced():
        return ""
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


def viewer_may_drill_down(p: Principal) -> bool:
    """하위 조직 자료까지 볼 수 있는 주체인가 — **경영진만**(사용자 결정 2026-07-30 ③).

    ★ 이 한 줄을 라우트마다 쓰지 않고 여기서만 정한다. 어떤 라우트가 실수로
      `include_descendants=True` 를 기본으로 쓰면 일반 직원이 전 사업부 자료를 보게 되고,
      그 라우트만 조용히 넓어진다 — 오늘 아침에 잡은 구멍과 같은 유형이다."""
    return bool(getattr(p.scope, "can_run_enterprise", False)
                or getattr(p.scope, "is_executive", False))


async def assert_scope_allowed(p: Principal, requested: str, *, resource_type: str,
                               resource_id: str = "", tenant_id: str = "",
                               entity_mode: str = ""):
    """[D-018 ③④] **API 경계의 단일 범위 정규화 지점.**

    요청으로 들어온 `node_id`·업무 코드·부서 id 를 정본 `node_id` 로 정규화하고, 주체 범위 안인지
    교차 검증한다. 거부는 **감사에 남기고 404 로 은폐**한다(§3.3 경계표).

    ★★ 왜 여기 두는가: 종전에는 같은 헬퍼(`_scope`)가 `planning_control`·`briefing_control`·
      `connector_control` 에 **각각 복제**돼 있었다. 세 벌이면 문맥 인자를 하나에만 붙이거나
      감사 이름을 한 곳만 고치는 일이 생기고, 그 경로만 조용히 달라진다 — 이 저장소가 목록
      API·자산 목록에서 이미 겪은 유형이다.
    ★ 반환값은 `EffectiveScope` 다. 호출부가 `scope_node_id`(판정·저장용)와 함께
      `scope_code`·`scope_name`(표시용)·`ref_kind`(백필 대상 여부)를 쓸 수 있어야 한다.
      문자열 하나만 필요하면 `.scope_node_id` 를 꺼낸다.
    ⚠️ 판정·저장에는 **`scope_node_id` 만** 쓴다. 코드와 이름은 바뀔 수 있는 의미값이다(D-018).
    """
    import asyncio as _asyncio

    from core.scope_guard import resolve_effective_scope
    eff = await _asyncio.to_thread(resolve_effective_scope, p, requested, tenant_id, entity_mode)
    if eff.denied:
        try:
            from core.enterprise_context import audit
            audit.denied_scope(resource_type, resource_id or requested or "(전사)",
                               actor=eff.actor, actor_scopes=eff.allowed_scopes,
                               requested_scope=requested, detail=eff.reason)
        except Exception:
            pass            # 감사 실패가 거부를 통과로 바꾸지 않는다 — 거부는 그대로 간다
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    return eff


def scope_meta(eff) -> dict:
    """[D-018 ③] 응답에 실을 범위 표시 정보. **화면은 정본 해시를 사람에게 보여줄 수 없다.**

    `scope_node_id` 는 판정·저장의 정본이고, `scope_code`·`scope_name` 은 표시용이다.
    `needs_normalization` 은 그 요청이 별칭(코드·부서 id)으로 들어왔다는 뜻 — 저장분이 아직
    정규화되지 않았음을 화면·운영자가 알 수 있게 한다(백필 진척의 관측 지점, D-018 ⑤)."""
    kind = getattr(eff, "ref_kind", "") or ""
    return {
        "scope_node_id": getattr(eff, "scope_node_id", "") or "",
        "scope_code": getattr(eff, "scope_code", "") or "",
        "scope_name": getattr(eff, "scope_name", "") or "",
        "scope_ref_kind": kind,
        #: 빈 요청(전사)은 정규화할 대상이 없으므로 False 다.
        "needs_normalization": bool(kind) and kind != "ecm_node",
    }


#: 자료 종류별로 **정확한 숨김 건수**를 볼 자격. 종류마다 «관리할 사람» 이 다르다.
#  ⚠️ 여기 없는 종류를 넘기면 `hidden_envelope` 가 예외를 던진다 — 오타를 조용히
#    «건수 안 줌» 으로 처리하면 관리자가 못 보는 이유를 아무도 찾지 못한다.
_EXACT_COUNT_RULES = {
    "standard": lambda s: bool(s.unrestricted or s.can_manage_standard),
    "org": lambda s: bool(s.unrestricted or getattr(s, "can_edit_org", False)),
    # 경영계획은 재무 정보다 — «전사에 계획이 몇 건 있는가» 자체가 정보이므로 경영진과
    # 데이터 관리자에게만 정확한 수를 준다(2026-08-05 Planning 통제).
    "plan": lambda s: bool(s.unrestricted or getattr(s, "can_run_enterprise", False)
                           or s.can_manage_standard),
}


def hidden_envelope(p: Principal, total: int, shown: int,
                    exact_for: str = "standard") -> dict:
    """★★ 목록이 무언가를 **가렸다**는 사실을 응답에 담는다. 건수를 줄지는 여기서만 정한다.

    두 가지를 동시에 만족해야 한다.
      ① 사용자는 "이게 전부가 아니다"를 반드시 알아야 한다. 모르면 자기가 본 목록을 전량으로
         믿고 결정한다 — 그래서 `hidden_present` 는 **누구에게나** 준다.
      ② 그러나 **정확한 건수는 남의 조직 자료 규모를 알려준다.** 404 Data Stealth 로 존재를
         숨기면서 "옆 조직에 47건 있다"를 말하면 통제가 앞뒤로 어긋난다. 건수를 세어 보면
         조직 규모·프로젝트 수를 추정할 수 있고, 그건 목록을 여는 것과 크게 다르지 않다.
         → 정확한 건수는 **자료를 관리할 사람(DA·관리자)** 에게만 준다.

    ⚠️ 이 판정을 라우트에 흩어 두지 않는다. 프론트에서 가리는 것도 답이 아니다 —
      응답에 숫자가 들어 있으면 다른 클라이언트·스크립트에는 그대로 새어 나간다.
      숨김은 **보내지 않는 것**이지 보여주지 않는 것이 아니다.
    """
    hidden = max(0, int(total) - int(shown))
    out: dict = {"hidden_present": hidden > 0}
    rule = _EXACT_COUNT_RULES.get(exact_for)
    if rule is None:
        raise ValueError(f"hidden_envelope: 모르는 자료 종류 '{exact_for}' "
                         f"— {sorted(_EXACT_COUNT_RULES)} 중 하나여야 한다")
    if hidden and rule(p.scope):
        out["hidden_count"] = hidden
    return out


def viewer_scope_nodes(p: Principal) -> Optional[frozenset]:
    """요청자의 **소속 조직 노드**(상속을 펼치지 않은 원본). `None` 은 "필터하지 않는다".

    상속을 스스로 펼치는 호출자(`visible_assets` 처럼 `include_descendants` 를 받는 쪽)는
    이것을 쓰고, 이미 펼쳐진 집합이 필요한 쪽은 `viewer_visible_scopes()` 를 쓴다.
    ⚠️ 두 번 펼치면 안 된다 — 펼친 집합을 다시 펼치면 조상의 자손, 즉 **형제 사업부**가 들어온다."""
    if not _enforced():
        return None
    if getattr(p.scope, "unrestricted", False) or p.scope.can_manage_standard:
        return None
    return frozenset(getattr(p.scope, "readable_scope_nodes", frozenset()) or frozenset())


def viewer_visible_scopes(p: Principal) -> Optional[frozenset]:
    """이 요청자에게 보이는 **ECM 조직 범위 전체**(상속을 이미 펼친 집합).
    `None` 은 "필터하지 않는다"는 뜻이다.

    `None`(전면 통과)이 되는 경우는 셋이다:
      · 강제 OFF — 단계적 도입을 위한 하위호환 계약
      · `unrestricted` — 조직 미도입·부트스트랩·시스템 관리자
      · 표준 관리 권한(DA) — 카탈로그·용어 정리는 전사 메타를 봐야 성립한다

    그 밖에는 **부서에 적힌 조직 노드**에서 시작한다(사용자가 아니라 부서가 들고 있다 —
    `AccessScope.readable_scope_nodes` 주석 참조). 노드를 하나도 모르면 빈 집합을 준다:
    호출자는 그것을 "전부 허용"이 아니라 **"아무것도 허용하지 않음"** 으로 다뤄야 한다.

    ★★ **하향 열람(하위 조직 자료)은 경영진에게만 준다**(사용자 결정 2026-07-30 ③).
      이 판정을 라우트마다 두면 어긋난다 — 한 라우트에서 `include_descendants=True` 를
      기본으로 쓰면 일반 직원이 전 사업부 자료를 보게 되고, 그 라우트만 조용히 넓어진다.
      그래서 "어디까지 펼치는가"를 여기 한 곳에서 정하고, 라우트는 결과 집합만 쓴다.
      상향(사업부 → 전사 표준)은 `visible_scopes` 가 항상 포함한다 — 그건 상속이지 승급이 아니다."""
    nodes = viewer_scope_nodes(p)
    if nodes is None:
        return None
    if not nodes:
        return frozenset()
    drill = viewer_may_drill_down(p)
    try:
        from core.enterprise_context.scoping import visible_scopes
        out = set()
        for n in nodes:
            out |= set(visible_scopes(n, include_descendants=drill))
        return frozenset(out)
    except Exception as e:                                           # pragma: no cover
        print(f"⚠️ [deps] 조직 범위 해석 실패(비노출로 처리): {e}")
        return frozenset()


def scope_allows_owner(scopes: Optional[frozenset], owner_org_id: str) -> bool:
    """소유 조직이 `owner_org_id` 인 자료를 이 범위 집합으로 볼 수 있는가(단순 소속 판정).

    ⚠️ 소유 조직이 **비어 있는 자료**는 보이지 않는다. 미기재를 "공개"로 읽으면 이행 기간에
      들어온 모든 자료가 전사 공개가 된다(관문 A 가 막으려던 바로 그 결과다)."""
    if scopes is None:
        return True
    owner = (owner_org_id or "").strip()
    return bool(owner) and owner in scopes


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
