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
    # ①-b 세션 토큰(2026-08-09 로그인 도입). **헤더보다 먼저 본다** — 헤더는 브라우저가 임의
    #     값을 보낼 수 있는 값이고(아래 ②③ 주석), 세션은 서버가 발급하고 서버가 들고 있다.
    #     즉 로그인한 사용자는 헤더로 다른 사람인 척할 수 없다.
    #     ⚠️ 여기서 권한을 읽지 않는다 — user_id 만 얻고 권한은 `resolve_scope` 가 매 요청
    #       다시 해석한다. 토큰에 권한을 담으면 회수해도 토큰이 사는 동안 유효해진다.
    try:
        tok = request.headers.get("X-Session-Token", "") or ""
        if tok:
            from core.auth import auth_store
            uid = auth_store.resolve(tok)
            if uid:
                return uid
    except Exception:
        pass                    # 인증 저장소 장애가 요청을 죽이지 않는다(아래에서 익명 처리)
    # ★★★ [P0-1C · 2026-08-09] 이 블록은 **기본적으로 실행되지 않는다.**
    #   `config.ORG_TRUST_HEADER` 기본값이 False 로 내려갔다(그 이유는 config.py 주석 참조).
    #   즉 ②③ 은 «개발 모드에서만 열리는 문» 이고, 운영에서는 위의 ①·①-b 만이 신원의 출처다.
    #   ⚠️ 기본값을 `True` 로 되돌리지 말 것 — `getattr` 의 세 번째 인자도 False 로 맞춘다.
    #     여기만 True 로 남으면 `config` 에서 이름이 사라지는 날 통제가 조용히 되살아난다.
    if getattr(config, "ORG_TRUST_HEADER", False):
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
    #
    # ★★★ [2026-08-08 실측] **`config.ORG_ENFORCE` 를 직접 읽지 않는다.** 강제 여부의 정본은
    #   `data/scope_policy.json` 이고 그것이 **코드 기본값을 이긴다**(2026-07-30 사용자 지시로
    #   `org_enforce=true` 로 켜져 있다). 이 한 줄만 코드 기본값(False)을 보고 있어서, 정책이
    #   켜졌는데도 **여기서는 익명이 통과**했다.
    #
    #   실제 증상: `/agent-governance/capabilities` 가 익명에게 200 을 줬다. 뒤에 `require_caps`
    #   가 있는 라우트는 거기서 막혔지만, **이 401 에만 기대던 라우트는 열려 있었다** — 그리고
    #   그런 라우트는 조용하다. 아무도 오류를 보지 못한다.
    #
    #   ⚠️⚠️ 단위 테스트가 이것을 **구조적으로 못 봤다.** 테스트는 `monkeypatch` 로
    #   `config.ORG_ENFORCE=True` 를 직접 켜므로 이 줄이 정상 동작하는 것처럼 보이고
    #   (`test_capabilities_needs_identification` 은 401 을 단언하며 초록이었다), 실서버는
    #   정책 파일로 켜므로 다른 세계가 된다. **같은 뜻의 스위치를 두 곳에서 읽으면** 테스트는
    #   그 불일치를 볼 수 없다.
    #
    #   ★ `_enforced()` 는 이 파일에 **이미 있었고**, 그 주석이 「판정 함수들이 모두 여기서 같은
    #     답을 얻는다」고 못박고 있다. 새 규칙을 만든 것이 아니라 그 계약을 지키는 것이다.
    if _enforced() and not scope.unrestricted and not uid:
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


def eul(word: str) -> str:
    """받침에 맞는 목적격 조사(을/를). 사용자에게 보이는 문구이므로 맞춘다.

    ⚠️ 자료 이름을 문구에 끼워 넣는 함수가 여럿 있으면 «경영계획를» 같은 문장이 화면에 남는다.
      틀린 조사는 기능을 막지 않지만, 통제 메시지가 어설퍼 보이면 사용자는 그 통제도 어설프다고
      읽는다. 판정은 한 곳에 둔다."""
    if not word:
        return "를"
    last = word.strip()[-1]
    if not ("가" <= last <= "힣"):
        return "를"                          # 한글이 아니면 판정할 근거가 없다
    return "을" if (ord(last) - 0xAC00) % 28 else "를"


def assert_identified(p: Principal, what: str) -> None:
    """★★ 익명·미등록·폐지 사용자 차단. **이 자료를 열어도 되는 주체인가**만 본다.

    ## 왜 여기 있는가 (트랙 G 의 첫 단계)

    이 함수는 원래 `planning_control.py` 안의 `_assert_identified` 였다. 트랙 G 는 무방비
    라우트가 남은 **16개 파일**을 봉합하는 일인데, 그 방식이 「각 파일에 같은 헬퍼를 복사」라면
    판정이 열일곱 벌이 된다. ⚠️ **이 저장소에서 가장 비쌌던 결함 유형이 바로 그것이다** —
    2026-08-06 인계서가 「판정이 두 곳에 있으면 두 곳이 갈라진다」를 여덟 번 기록했다.

    복사본이 갈라지는 방식은 조용하다: 한 파일에서 401/403 구분을 고쳐도 나머지 열여섯은
    그대로 남고, 아무도 오류를 보지 못한다. 그래서 **봉합을 시작하기 전에 판정을 여기로 올린다.**

    ## 무엇을 보고 무엇을 보지 않는가

    ★ 행 단위 필터(`viewer_scope_nodes`)와 나눈 이유는 `visibility_block_reason` 주석과 같다 —
      «열어도 되는가» 와 «무엇까지 보이는가» 는 다른 질문이고, 후자는 조직도(ECM)를 봐야 한다.

    ⚠️ **401 과 403 을 구분한다**: 401 = «누구인지 밝히십시오», 403 = «당신에게는 권한이 없습니다».
      뭉개면 이미 로그인한 사용자가 계속 로그인을 시도한다.

    ⚠️⚠️ **이것만으로는 부족하다.** `/api/v1/planning/facts` 유출의 두 번째 겹은 «빈 범위 요청이
      통제를 우회한다» 였다 — `org_id` 를 비우면 정규화할 대상이 없어 통과하고, 저장소로 넘어가는
      범위도 비어 행 필터가 걸리지 않는다. **파라미터를 주지 않는 것이 가장 넓은 조회다.**
      그러므로 이 함수를 부른 뒤에도 행 필터를 반드시 함께 건다.

    :param what: 사용자에게 보일 자료 이름(예: "경영계획"). 조사는 `eul()` 이 맞춘다.
    """
    reason = visibility_block_reason(p)
    if not reason:
        return
    if not (p.user_id or "").strip():
        raise HTTPException(status_code=401,
                            detail=f"{what}{eul(what)} 보려면 사용자 식별이 필요합니다.")
    raise HTTPException(status_code=403, detail=reason)


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
#  기준정보·업무표준은 데이터 표준 관리자(DA)가 고칠 사람이고, 조직·사용자 명부는 조직 편집
#  권한자가 고칠 사람이다. 둘을 한 권한으로 묶으면 DA 에게 전 직원 명부 규모가 새거나,
#  조직 관리자가 자기가 고쳐야 할 미바인딩 건수를 못 보게 된다.
#  ⚠️ 판정을 호출부로 내보내지 않는다. 호출부는 «어떤 종류의 자료인가»만 말한다.
#  ⚠️ 여기 없는 종류를 넘기면 `hidden_envelope` 가 예외를 던진다 — 오타를 조용히
#    «건수 안 줌» 으로 처리하면 관리자가 못 보는 이유를 아무도 찾지 못한다.
#  ★★★ [병합 2026-08-05] 이 딕셔너리와 `hidden_envelope` 는 병합 직후 **파일 안에 두 벌**
#    존재했다. 양쪽 브랜치가 같은 것을 각자 추가했고 git 은 위치가 달라 충돌로 보지 않았다.
#    문법도 임포트도 멀쩡했고, 뒤에 온 정의가 앞을 조용히 덮어 `plan` 규칙만 사라졌다
#    (테스트 20건이 깨져서야 드러났다). **충돌 마커 0건 = 안전이 아니다** — 자동 병합된
#    파일에서 «같은 이름이 두 번 정의됐는가» 를 따로 확인해야 한다.
_EXACT_COUNT_RULES = {
    "standard": lambda s: bool(s.unrestricted or s.can_manage_standard),
    "org": lambda s: bool(s.unrestricted or getattr(s, "can_edit_org", False)),
    # 경영계획은 재무 정보다 — «전사에 계획이 몇 건 있는가» 자체가 정보이므로 경영진과
    # 데이터 관리자에게만 정확한 수를 준다(2026-08-05 Planning 통제).
    "plan": lambda s: bool(s.unrestricted or getattr(s, "can_run_enterprise", False)
                           or s.can_manage_standard),
    # 에이전트·스킬·워크플로우 자산(설계 §8.3 「현재 보는 범위와 숨겨진 자산 수」).
    # AI 관리자가 이 자료의 관리 주체이므로 조직 관리자와 함께 정확한 수를 본다 —
    # 「전사에 에이전트가 몇 개인가」는 그들이 답해야 하는 질문이다.
    "agent": lambda s: bool(s.unrestricted or getattr(s, "is_ai_admin", False)
                            or getattr(s, "can_edit_org", False) or s.can_manage_standard),
}


def may_see_exact_count(p: Principal, exact_for: str = "standard") -> bool:
    """이 사람에게 **자료의 정확한 규모**를 줘도 되는가.

    ★ `hidden_envelope` 과 **같은 규칙**을 쓴다. 규모를 드러내는 값은 「가려진 건수」 말고도
      있고(예: 자산이 어느 프로젝트에 쓰이는지의 목록), 그때마다 라우트가 자기 판정을 만들면
      한쪽만 고쳐졌을 때 **한 화면에서는 막고 다른 화면에서는 새는** 상태가 된다.

    ⚠️ 모르는 종류는 «안 준다» 로 조용히 처리하지 않고 **던진다** — 오타 때문에 관리자가
      못 보게 되면 아무도 원인을 못 찾는다."""
    rule = _EXACT_COUNT_RULES.get(exact_for)
    if rule is None:
        raise ValueError(f"may_see_exact_count: 모르는 자료 종류 '{exact_for}' "
                         f"— {sorted(_EXACT_COUNT_RULES)} 중 하나여야 한다")
    return bool(rule(p.scope))


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
    if hidden and may_see_exact_count(p, exact_for):
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


def governance_block_reason(p: Principal) -> str:
    """★★★ [2026-08-04 이관 5/10 실측 결함] **거버넌스 지표가 익명에게 열려 있었다.**

    실측으로 익명이 받아 본 것:
      · `/api/v1/contracts/evaluate` → 위반 계약 1건과 그 사유
        («생산자 자산이 폐기됐다 — 약속을 지킬 원천이 사라졌다»)
      · `/api/v1/external/readiness` → 지표 6개의 코드·필요 등급·**격차 영향**·다음 행동
        («물량 계획의 외부 근거가 없어 낙관 편향을 검증할 수단이 없습니다»)

    ⚠️ 이건 자료 본문이 아니라 **집계**다. 그래서 «수치일 뿐»으로 보기 쉬운데, 거버넌스 콘솔은
      정의상 «무엇이 안 되어 있는가»를 모아 보여주는 화면이다. 즉 집계 자체가 **취약점 목록**이고,
      익명에게 열려 있으면 어디를 파면 되는지 알려주는 지도가 된다.

    자격: 데이터 표준 관리자·조직 관리자·경영진. 일반 사용자에게는 차단 이유를 말한다 —
    이 화면은 «내 업무»가 아니라 «전사 정비 상태»를 다루므로 막아도 업무가 멈추지 않는다.
    강제가 꺼져 있으면 아무것도 막지 않는다(하위호환 계약).
    """
    if not _enforced():
        return ""
    base = visibility_block_reason(p)
    if base:
        return base
    s = p.scope
    if (s.unrestricted or s.can_manage_standard or getattr(s, "can_edit_org", False)
            or getattr(s, "can_run_enterprise", False)):
        return ""
    return ("전사 정비 상태(거버넌스) 지표는 데이터 관리자·조직 관리자·경영진에게만 표시합니다 "
            "— 어디가 비어 있는지는 그 자체로 보호해야 하는 정보입니다.")


def assert_governance_readable(p: Principal):
    """거버넌스 읽기 자격. 목록형 응답은 `governance_block_reason` 으로 0건 + 이유를 주고,
    단건·평가형 응답은 이 함수로 403 을 던진다(그쪽은 «0건»으로 표현할 형태가 없다)."""
    reason = governance_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)


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


def _assert_identified_for_project(p: Principal, project_id: str, verb: str):
    """★★★ [2026-08-04 이관 7/10] 프로젝트 판정 **앞에** 관문 A 를 세운다.

    아래 두 함수는 «소유권이 기록되지 않은 프로젝트는 통과»라는 하위호환을 갖고 있다
    (`if not own: return`). 그 관대함은 **등록된 사용자 사이의** 것이어야 하는데, 익명까지
    통과시키고 있었다. 그래서 실측에서 익명이 `POST /{id}/hotl/resume` 로 **HOTL 중단점을
    통과**시킬 수 있었다 — 6/10 에서 «중단점을 지우려면 관리자 권한»을 막았지만, 지울 필요
    없이 넘겨 버리면 그 통제는 없는 것과 같다.

    ⚠️ 라우트마다 이 검사를 흩지 않고 **판정 함수 안**에 둔다. 그러면 이 함수를 이미 쓰는
      모든 경로(스프린트 시작·중지·삭제·복제·릴리스·재시뮬레이션)가 함께 보호되고,
      새 라우트가 생겨도 판정을 부르는 순간 같이 걸린다.
    강제가 꺼져 있으면 아무것도 막지 않는다(`visibility_block_reason` 의 계약)."""
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403,
                            detail=f"'{project_id}' 프로젝트를 {verb} 수 없습니다 — {reason}")


def assert_project_readable(p: Principal, project_id: str):
    _assert_identified_for_project(p, project_id, "볼")
    if not _resource_readable(p, "project", project_id):
        _deny(f"'{project_id}' 프로젝트를 볼 권한이 없습니다.")


def assert_project_writable(p: Principal, project_id: str):
    if p.scope.unrestricted:
        return
    _assert_identified_for_project(p, project_id, "바꿀")
    own = org_directory.get_ownership("project", project_id)
    if not own:
        # 소유권 미기록 프로젝트에 대한 관대함 — 단, 위에서 **식별된 사용자**임을 확인했다.
        return
    if own.get("owner_user_id") and own["owner_user_id"] == p.user_id:
        return
    assert_can_write_dept(p, own.get("dept_id", ""))


def assert_release_readable(p: Principal, release_id: str):
    if not _resource_readable(p, "release", release_id):
        _deny(f"'{release_id}' 릴리스를 볼 권한이 없습니다.")


def assert_release_writable(p: Principal, release_id: str):
    """★ [트랙 I · 2026-08-08] 릴리스에 딸린 것을 **바꿀** 자격.

    종전에는 릴리스에 `_readable` 만 있었다. 읽기만 있던 이유는 릴리스가 불변 스냅샷이었기
    때문인데, 트랙 I 로 **생성 앱이 그 릴리스 밑에 업무 데이터를 쌓기** 시작하면서 «이 앱의
    데이터를 바꿀 수 있는가» 라는 질문이 새로 생겼다.

    ⚠️ 이 판정을 라우트에 흩지 않고 여기 두는 이유는 `_assert_identified_for_project` 와 같다 —
      판정 함수 안에 있어야 나중에 생기는 라우트도 부르는 순간 함께 걸린다.

    ★★ **식별을 먼저 요구한다.** `_resource_readable` 은 「소유권 미기록 자원은 막지 않는다」는
      하위호환을 갖고 있어서, 그것만 쓰면 **익명이 남의 앱 데이터에 쓸 수 있다.** 트랙 H 가
      봉합한 «식별만으로 열리는 쓰기» 를 여기서 새로 만들지 않는다.
    강제가 꺼져 있으면 아무것도 막지 않는다(하위호환 계약)."""
    if p.scope.unrestricted:
        return
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403,
                            detail=f"'{release_id}' 앱의 데이터를 바꿀 수 없습니다 — {reason}")
    own = org_directory.get_ownership("release", release_id)
    if not own:
        # 소유권 미기록 릴리스에 대한 관대함 — 단, 위에서 **식별된 사용자**임을 확인했다.
        return
    if own.get("owner_user_id") and own["owner_user_id"] == p.user_id:
        return
    assert_can_write_dept(p, own.get("dept_id", ""))


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
