"""★★★ [G1-B01] Host Runtime SDK 계약 — **표면을 늘리지 못하게 잠근다.**

브리지(I-3)는 프론트 코드다. 그런데 «무엇을 열어 주는가» 는 보안 결정이고, 보안 결정이
프론트에만 있으면 리뷰에서 눈으로 찾아야 한다. 그래서 표면을 계약 모듈에 열거하고
여기서 잠근다 — 브리지는 그 목록을 **구현할 뿐 늘리지 못한다.**

## 이 파일이 지키는 네 가지

1. 열린 표면에 **사용자·토큰·임의 fetch 가 없다.**
2. 앱이 보낸 **권한 입력 필드는 지워진다**(검증이 아니라 삭제).
3. 모르는 `op` 는 **쓰기로 취급**되고 행동을 얻지 못한다(fail-closed).
4. 거부 사유가 **앱에게 그대로 새지 않는다** — 기본값이 가장 적게 말하는 쪽이다.
"""
import pytest

import core.app_policy as ap
import core.host_runtime_sdk as sdk


# ── ① 표면 ────────────────────────────────────────────────────────────────

def test_열린_표면에_금지_항목이_섞이지_않았다():
    """★ 두 목록이 겹치면 «금지» 가 이름뿐이 된다."""
    assert not (set(sdk.SDK_SURFACE) & set(sdk.FORBIDDEN_SURFACE))


@pytest.mark.parametrize("banned", ["afs.user", "afs.token", "afs.fetch", "afs.sql",
                                    "afs.localStorage", "afs.env"])
def test_위험한_표면은_금지_목록에_있다(banned):
    """⚠️ 「없으니 안 만들겠지」로 두지 않는다. 이름을 적어 두면 되살아남을 시험이 잡는다.

    특히 `afs.fetch`·`afs.sql` — 그 하나만 열면 앱이 임의 경로·임의 질의를 만들 수 있고,
    그 순간 **정책 결정점이 무의미해진다**(판정 대상이 «무엇을 하려는가» 가 아니라
    «어떤 문자열인가» 가 된다)."""
    assert banned in sdk.FORBIDDEN_SURFACE


def test_표면은_데이터와_문맥과_준비상태뿐이다():
    """★ 열린 것이 무엇인지 한눈에 읽히는지 본다 — 목록이 늘면 이 시험이 먼저 깨진다."""
    roots = {s.split(".")[1] for s in sdk.SDK_SURFACE}
    assert roots == {"version", "ready", "context", "data"}


def test_문맥은_표시값_둘뿐이다():
    """⚠️ `context` 에 사용자·테넌트·조직범위를 넣고 싶어지는 순간이 온다. 넣으면 그것은
    **앱이 아는 사실**이 되고, 앱은 LLM 이 쓴 코드다."""
    ctx = {s for s in sdk.SDK_SURFACE if s.startswith("afs.context.")}
    assert ctx == {"afs.context.app_id", "afs.context.release_id"}


# ── ② 앱이 보낸 권한 입력은 지운다 ────────────────────────────────────────

@pytest.mark.parametrize("field", list(sdk.IGNORED_FROM_APP))
def test_앱이_보낸_권한_입력_필드는_지워진다(field):
    """★★★ 「앱이 안 보내겠지」는 계약이 아니다. 보내온 값을 판정에 쓰는 순간
    **클라이언트가 자기 권한을 정하게 된다.**

    ⚠️ 값을 «검증» 하지 않고 **지운다.** 검증하면 「맞으면 쓴다」가 되고, 그러면 언젠가
      맞는 값을 보내는 코드가 생긴다."""
    out = sdk.sanitize_request({field: "훔친값", "qty": 3})
    assert field not in out
    assert out["qty"] == 3, "정상 필드까지 지웠다"


def test_release_id_는_앱이_말할_수_없다():
    """★★★ 설계 §7-4 — 「이것 하나로 «앱이 남의 데이터를 읽는» 경로가 원천 차단된다」."""
    assert "release_id" in sdk.IGNORED_FROM_APP
    assert "release_id" not in sdk.sanitize_request({"release_id": "rel_남의앱"})


def test_정리는_dict_가_아닌_입력에도_안전하다():
    """⚠️ 앱이 보내는 것은 무엇이든 될 수 있다. 여기서 터지면 브리지가 죽는다."""
    for bad in (None, [], "문자열", 42):
        assert sdk.sanitize_request(bad) == {}


# ── ③ op 는 닫힌 목록이고, 모르면 쓰기다 ──────────────────────────────────

def test_모든_op_가_유효한_정책_행동을_가리킨다():
    for op, (action, _needs_id) in sdk.OPS.items():
        assert action in ap.ACTIONS, f"{op} 이 알 수 없는 행동을 가리킨다: {action}"


@pytest.mark.parametrize("op,expected", [
    ("data.list", ap.READ), ("data.get", ap.READ), ("data.schema", ap.READ),
    ("data.create", ap.WRITE), ("data.update", ap.WRITE), ("data.remove", ap.DELETE),
])
def test_op_가_기대한_행동으로_매핑된다(op, expected):
    assert sdk.action_for(op) == expected


def test_모르는_op_는_행동을_얻지_못한다():
    """⚠️ 여기서 기본 행동을 돌려주면 「모르면 읽기」가 되고, 그것이 곧 통제 우회다."""
    assert sdk.action_for("data.exfiltrate") == ""
    assert sdk.action_for("") == ""


def test_모르는_op_는_쓰기로_취급한다():
    """★ fail-closed. 새 op 가 생겼을 때 쓰기 통제를 건너뛰지 않게 한다."""
    assert sdk.is_mutating("data.exfiltrate") is True
    assert sdk.is_mutating("data.list") is False
    assert sdk.is_mutating("data.remove") is True


# ── ④ 거부 사유가 앱에게 새지 않는다 ──────────────────────────────────────

def test_모르는_사유는_가장_적게_말하는_쪽으로_접힌다():
    """★★★ 기본값이 `NOT_FOUND` 인 것이 요점이다.

    새 거부 사유가 생겼을 때 아무도 이 표를 갱신하지 않아도 **가장 적게 말하는 쪽**으로
    떨어진다 — 반대로 두면 새 사유가 그대로 앱에 노출된다."""
    assert sdk.app_error_code("BRAND_NEW_REASON_2027") == sdk.ERR_NOT_FOUND
    assert sdk.app_error_code("") == sdk.ERR_NOT_FOUND


@pytest.mark.parametrize("reason", [
    ap.DENY_SCOPE, ap.DENY_CONTEXT, ap.DENY_UNBOUND,
    ap.DENY_TOKEN_APP_MISMATCH, ap.DENY_TOKEN_SCOPE_MISMATCH,
    ap.DENY_TOKEN_CONTEXT_MISMATCH, ap.DENY_TOKEN_ACTOR_MISMATCH,
    ap.DENY_TOKEN_SESSION_MISMATCH,
])
def test_남의_자원의_존재를_알리는_사유는_전부_NOT_FOUND_로_접힌다(reason):
    """★★★ 「어느 조직 범위 밖」·「다른 회사 문맥」·「남의 앱」은 **볼 수 없는 자원이
    존재한다**는 사실이다. 그것을 앱(=LLM 이 쓴 코드와 그 화면을 보는 사람)에게 주면
    존재가 사유 모양으로 새어나간다.

    G2 온톨로지 설계 §6.2 가 같은 이유로 `blocked` 개수를 응답에서 뺐다 — 같은 규칙이다."""
    assert sdk.app_error_code(reason) == sdk.ERR_NOT_FOUND


@pytest.mark.parametrize("reason", [
    ap.DENY_TOKEN_CAPABILITY, ap.DENY_MANIFEST_CAPABILITY, ap.DENY_PERSONAL,
    ap.DENY_UNIDENTIFIED, ap.DENY_PRINCIPAL_BLOCKED,
])
def test_앱_자신에_대한_사실은_알려_준다(reason):
    """★ 「이 앱에 그 권한이 없다」·「로그인이 필요하다」는 **앱 자신 또는 사용자 자신**의
    사실이라 알려도 새지 않는다 — 오히려 알려 줘야 개발자가 매니페스트를 고치고
    사용자가 로그인한다.

    ⚠️ 전부 숨기면 「왜 안 되는지 아무도 모르는 앱」이 되고, 그것도 실패다."""
    assert sdk.app_error_code(reason) == sdk.ERR_FORBIDDEN


def test_만료는_다시_열면_된다는_뜻으로_따로_말한다():
    assert sdk.app_error_code(ap.DENY_TOKEN_EXPIRED) == sdk.ERR_EXPIRED


def test_앱_오류_코드는_넷뿐이다():
    """⚠️ 코드가 늘면 그만큼 사유가 새어나간다. 앱이 할 수 있는 일은 넷뿐이므로
    코드도 넷이면 충분하다 — 늘리려면 «앱이 그것으로 무엇을 다르게 하는가» 에 답해야 한다."""
    assert len(sdk.APP_ERROR_CODES) == 4
    mapped = set(sdk._ERROR_MAP.values()) | {sdk.app_error_code("모르는사유")}
    assert mapped <= set(sdk.APP_ERROR_CODES)


def test_모든_PDP_사유가_코드로_접힌다():
    """★ 대조군 — 사유가 늘어도 반드시 넷 중 하나로 떨어지는지 전수 확인한다."""
    reasons = [v for k, v in vars(ap).items() if k.startswith("DENY_")]
    assert reasons, "PDP 사유를 하나도 찾지 못했다 — 이 시험이 무의미해졌다"
    for r in reasons:
        assert sdk.app_error_code(r) in sdk.APP_ERROR_CODES
