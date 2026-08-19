"""★★★ [G1-B02] **생성 앱에 자격증명·상위 사용자 토큰을 주지 않는다.**

로드맵 G1-B02 의 원문: 「앱에 DB 자격증명·상위 사용자 토큰 전달 금지」.

## 왜 소스 검사인가

이 계약이 깨지는 자리는 **iframe 에 무엇을 실어 보내는가**이고, 그것은 프론트 코드다.
파이썬 단위 테스트로는 «실행된 iframe» 을 볼 수 없다. 그래서 **깨질 수 있는 형태**를
소스에서 금지한다 — 이 저장소가 라우트 권한표를 같은 방식으로 지키고 있다
(`test_route_authority_table.py`).

⚠️ 소스 검사는 보안 경계가 아니다(감사 지적 A: 「정규식 검사는 보안 경계가 아니다」).
  실제 경계는 **브라우저 샌드박스**와 **서버 판정**이다. 이 파일은 그 경계를 무너뜨리는
  변경이 조용히 들어오는 것을 막는 **회귀 잠금**이다.

## 지금 상태(2026-08-13 실측) — 이미 옳다. 그래서 잠근다

· iframe 은 `frontend/src/components/PreviewPanel.tsx` **한 파일**에만 있고 둘 다
  `sandbox="allow-scripts"` 다(= `allow-same-origin` 없음).
· srcDoc 에 세션 토큰·사용자 식별자를 싣지 않는다.
· 생성 앱이 `localStorage` 를 쓰면 **가짜 저장소**로 갈아끼운다 — 부모의 진짜
  `localStorage`(세션 토큰이 있는 곳)에 닿지 못한다.

★ I-3 브리지가 들어올 때 이 셋 중 하나라도 되돌리면 여기서 깨진다.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"

#: iframe 을 만드는 파일. **새 파일이 생기면 자동으로 대상에 들어온다** —
#: 목록을 손으로 관리하면 새 브리지가 조용히 빠진다(`/facts` 가 정확히 그렇게 빠졌다).
_IFRAME_HINT = re.compile(r"<iframe|srcDoc|srcdoc")

#: 앱에게 절대 건너가면 안 되는 것들. 값이 아니라 **가져오는 수단**을 막는다 —
#: 값은 이름을 바꿀 수 있지만 수단은 그렇지 않다.
_FORBIDDEN_IN_APP_PAYLOAD = (
    "getSessionToken",       # 세션 토큰 조회 헬퍼
    "X-Session-Token",       # 세션 헤더 이름
    "X-Factory-User",        # 사용자 식별 헤더
    "app_capability_token",  # 앱 증명(부모가 들고 있어야 한다)
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
)


def _iframe_files():
    return sorted(p for p in FRONTEND.rglob("*.tsx") if _IFRAME_HINT.search(p.read_text("utf-8")))


def test_iframe_을_만드는_파일이_있다():
    """★ 대조군. 대상이 0개면 아래 검사가 전부 **헛되이 통과**한다."""
    files = _iframe_files()
    assert files, "iframe 을 만드는 파일을 찾지 못했다 — 이 파일의 검사가 무의미해졌다"


@pytest.mark.parametrize("attr", ["allow-same-origin", "allow-top-navigation", "allow-popups"])
def test_생성앱_iframe_은_위험한_권한을_받지_않는다(attr):
    """★★★ `allow-same-origin` 이 붙으면 **앱 코드가 부모 DOM 과 `localStorage` 에 닿는다.**

    설계 `design_app_data_plane_2026-08-08.md` §7 이 「여기가 가장 위험하다」고 적었고,
    `AS_IS_화면기능정의서` 는 그때의 `allow-scripts allow-same-origin` 을 두고
    **«완전한 격리 보안 경계가 아니다»** 라고 경고했다. 지금은 제거돼 있다 — 되돌리지 않는다.

    ⚠️ 이것 하나가 뚫리면 트랙 B·G·H 로 봉합한 것이 **앱 하나로** 무력화된다."""
    for f in _iframe_files():
        src = f.read_text("utf-8")
        for m in re.finditer(r'sandbox=\{?"([^"]*)"', src):
            assert attr not in m.group(1), (
                f"{f.name}: iframe sandbox 에 «{attr}» 이 붙었다 — {m.group(1)!r}")


def test_생성앱_iframe_에_sandbox_가_반드시_있다():
    """⚠️ 속성 자체를 빠뜨리면 **제한이 하나도 없는** iframe 이 된다 — `allow-same-origin`
    을 붙이는 것보다 나쁘다."""
    for f in _iframe_files():
        src = f.read_text("utf-8")
        for m in re.finditer(r"<iframe\b([^>]*)>", src, re.S):
            assert "sandbox=" in m.group(1), f"{f.name}: sandbox 없는 iframe 이 있다"


@pytest.mark.parametrize("needle", _FORBIDDEN_IN_APP_PAYLOAD)
def test_앱에게_건너갈_수_있는_코드에_자격증명_수단이_없다(needle):
    """★★ 값이 아니라 **가져오는 수단**을 막는다. 값은 이름을 바꿀 수 있지만 수단은 그렇지 않다.

    ## ⚠️ 2026-08-14 — 이 검사에 구멍이 있었다

    종전 조건은 «그 줄에 백틱이나 `srcDoc` 이 있을 때만» 이었다. 그런데 srcDoc 은 **여러 줄
    짜리 템플릿 리터럴**이고, 그 안쪽 줄에는 백틱이 없다 — 즉 iframe 본문 한가운데에
    자격증명을 넣어도 이 시험은 **통과했다.** I-3 브리지가 그 본문에 100줄 넘게 들어오면서
    구멍이 넓어졌다.

    지금은 **파일 전체**를 본다. iframe 을 만드는 파일들이 실제로 이 이름들을 하나도 쓰지
    않는다는 것을 확인했으므로(실측 0건), 더 좁힐 이유가 없다 — 부모 코드가 자격증명이
    필요해지면 그때는 **별도 모듈로 옮기는 것**이 옳다(그 파일은 iframe 을 만들지 않는다)."""
    for f in _iframe_files():
        for i, line in enumerate(f.read_text("utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue                       # 주석은 실행되지 않는다
            if needle in line:
                pytest.fail(f"{f.name}:{i} 에 «{needle}» 이 있다 — {stripped[:120]}")


def test_생성앱은_부모_localStorage_에_닿지_못한다():
    """★★ 생성 앱이 `localStorage` 를 쓰는 것은 정상이다. 그러나 **부모의 것**을 쓰면
    세션 토큰을 읽는다. 그래서 앱 안에서는 가짜 저장소로 갈아끼운다.

    ⚠️ 이 폴리필을 지우면 `allow-same-origin` 을 다시 붙이고 싶어지고, 그 순간 경계가 사라진다.
      둘은 한 쌍이다."""
    src = "\n".join(f.read_text("utf-8") for f in _iframe_files())
    assert "defineProperty(window, 'localStorage'" in src or \
           'defineProperty(window, "localStorage"' in src, \
        "생성 앱용 localStorage 대체가 사라졌다 — 부모 세션 토큰에 닿을 수 있다"


def test_앱_증명은_판정_경로에서도_전문을_들고_다니지_않는다():
    """★ 서버 쪽 절반. 토큰 전문이 판정 결과에 실리면 그것을 로그·응답에 찍는 코드가 언젠가
    생긴다 — 실제로 그런 유출이 이 저장소의 다른 곳에서 있었다(자체 `API_BASE_URL` 선언)."""
    from core.app_capability_token import AppCapabilityTokenStore
    from core.app_policy import READ

    store = AppCapabilityTokenStore()
    rec = store.issue(actor="u@x", session_id="s1", app_id="a1", release_id="r1",
        audience="operational",
                      capabilities=(READ,), tenant_id="tenant_default",
                      entity_mode="REAL", scope_node_id="node_hq",
                      manifest_fingerprint="fp_1", manifest_version="1.0",
        contract_fingerprint="cfp_1", materialization_fingerprint="mfp_1",
        data_fingerprint="dfp_1")
    resolved = store.resolve(rec["token"])
    assert "token" not in resolved
    assert rec["token"] not in str(resolved)
    assert all(rec["token"] not in str(row) for row in store.active())
