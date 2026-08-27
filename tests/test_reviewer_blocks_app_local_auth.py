"""★★★ 앱이 **자기 로그인을 만들면 빌드 중에 막힌다.** (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

실제 가동이 만든 앱의 첫 화면이 이랬다:

    거래처 관리 시스템 / 사용자 아이디 / 비밀번호 / 로그인
    App.tsx:61  (u) => u.username === loginUsername && u.password_hash === loginPassword

이 앱은 회사 호스트 **안에서** 열린다(앱인앱). 사용자는 이미 인증돼 있다. 그런데 앱이
자기 로그인 화면에 막혀 **데이터 평면을 한 번도 부르지 않았다** — 7/7 완주했고, 계약
승인됐고, 게시됐고, 화면에 뜨는데, 아무것도 못 한다.

## ⚠️ 검사기는 이미 있었다 — 부르는 곳이 없었을 뿐이다

`platform_auth_checker` 는 게시 때 워크스페이스를 훑어 차단 3건을 찾고 `release.json` 에
`ok: false` 로 적어 두기까지 했다. 그런데 **빌드 중에 부르는 곳이 0곳**이었다. 코드가 다
만들어진 뒤에야 말하니 그때는 고칠 사람이 없다.

    고지문(`app_runtime_brief`)  = 설득 — 모델이 안 들으면 아무 일도 안 일어난다
    이 게이트                     = 차단 — 안 들으면 재작업이 돈다

★ 그래서 이 파일은 **실제로 생성된 앱 코드**를 대조군으로 쓴다. 내가 지어낸 문자열로
  시험하면 「내 정규식이 내 예제를 잡는다」만 증명하게 된다.
"""
import inspect

import pytest

from nodes.utils import platform_auth_checker as pac


#: 실제 가동이 만든 코드에서 그대로 가져온 두 줄. **바꾸지 않는다.**
_REAL_LOGIN_CHECK = (
    "const found = users.find(\n"
    "  (u) => u.username === loginUsername && u.password_hash === loginPassword\n"
    ");\n")
_REAL_PASSWORD_FIELD = (
    '<label className="block text-sm font-medium text-slate-700 mb-1">비밀번호</label>\n'
    '<input\n'
    '  type="password"\n'
    '  value={loginPassword}\n'
    '/>\n')


def _blocks(code: str):
    return [h for h in pac.scan_text(code, path="src/App.tsx")
            if h.get("severity") == "block"]


def test_실제로_생성된_로그인_코드가_차단_신호를_낸다():
    """★★★ **이 파일의 요지.** 제품이 실제로 만든 것을 잡아야 게이트다."""
    hits = _blocks(_REAL_LOGIN_CHECK + _REAL_PASSWORD_FIELD)
    signals = {h["signal"] for h in hits}
    assert "password_storage" in signals, f"비밀번호 비교를 못 잡는다: {signals}"
    assert "local_login_form" in signals, f"비밀번호 입력 필드를 못 잡는다: {signals}"


def test_업무_화면은_걸리지_않는다():
    """★★★ 대조군. 오탐이 나면 개발자가 이 검사를 끄고, 꺼진 검사는 없는 것과 같다."""
    ok_code = (
        "const [accounts, setAccounts] = useState([]);\n"
        "useEffect(() => { afs.list('accounts').then(setAccounts)"
        "  .catch(() => setLoadError('데이터를 불러오지 못했습니다')); }, []);\n"
        "return <table>{accounts.map(a => <tr key={a.account_id}>"
        "<td>{a.company_name}</td></tr>)}</table>;\n")
    assert _blocks(ok_code) == [], _blocks(ok_code)


# ── 게이트가 **실제로 걸려 있는가** ───────────────────────────────────────

def test_리뷰어가_빌드_중에_이_검사를_부른다():
    """⚠️⚠️ 결함의 본체는 정규식이 아니라 **부르는 곳이 없었다**는 것이다.

    ★ 검사기가 훌륭해도 아무도 안 부르면 없는 것과 같다 — 이 저장소가 반복해 온 모양."""
    import nodes.execution as ex

    reviewer_src = inspect.getsource(ex.run_reviewer)
    helper_src = inspect.getsource(ex._platform_auth_blocks)
    assert "_platform_auth_blocks" in reviewer_src and "platform_auth_checker" in helper_src, (
        "리뷰어가 자체 인증 검사를 부르지 않는다 — 검사기가 있어도 소용없다")


def test_차단이면_재작업으로_돌려보낸다():
    """★ 「경고를 붙이고 통과」가 아니라 **REWORK_DEV** 여야 한다.

    ⚠️ 권고로 두면 리뷰어 LLM 이 판단에 섞어 버리고, 그러면 통과할 때가 생긴다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("app_local_auth")
    around = src[max(0, i - 1400):i + 400]
    assert "REWORK_DEV" in around, "차단 신호를 재작업으로 돌려보내지 않는다"


def test_프런트와_백엔드를_함께_본다():
    """⚠️ 로그인 화면만 막고 `/login` 라우트를 남기면 절반만 막은 것이다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    assert "_platform_auth_blocks(fe_files, be_files)" in src, (
        "프런트만 검사한다 — 서버측 로그인 라우트가 그대로 남는다")


@pytest.mark.parametrize("side", ["frontend", "backend"])
def test_한쪽_산출물만_있어도_자체_인증을_검사한다(side):
    """프런트 전용은 크래시하지 않고, 백엔드 전용은 검사를 건너뛰지 않는다."""
    import nodes.execution as ex

    frontend = [{"file_path": "src/App.tsx", "code": _REAL_PASSWORD_FIELD}]
    backend = [{"file_path": "api.py",
                "code": '@app.post("/login")\ndef login(): return {}\n'}]
    hits = ex._platform_auth_blocks(
        frontend if side == "frontend" else [],
        backend if side == "backend" else [])
    assert hits, f"{side} 전용 산출물의 자체 인증을 찾지 못했다"


# ── 승격 게이트도 같은 사실을 봐야 한다 ──────────────────────────────────

def test_승격_검사가_0건_스캔을_통과로_세지_않는다():
    """★★★ 「빈 결과」와 「깨끗한 결과」는 다르다.

    ⚠️ 실측: 승격 검사가 라이브러리 릴리스 디렉터리(`release.json` 하나뿐)를 훑어
      **0개 파일**을 보고 `ok=True` 를 냈다. 그래서 자체 로그인이 든 앱이 운영으로
      승격됐다 — 게시 때 같은 검사기가 이미 차단 3건을 찾아 둔 상태에서."""
    from core import release_promotion as rp

    src = inspect.getsource(rp._check_static)
    assert "scanned" in src, "검사한 파일 수를 보지 않는다"


def test_승격_검사가_게시와_같은_코드를_본다():
    """★★★ 같은 질문에 출처가 둘이면 둘이 다른 답을 한다."""
    import inspect as _i

    import api.routes.factory_control as fc

    src = _i.getsource(fc._release_code_paths)
    assert "workspace_path" in src, (
        "승격 검사가 프로젝트 워크스페이스를 안 본다 — 생성 코드는 거기 있다")

# ── 문구가 **걸린 신호에 맞는가** (2026-08-27 실측) ─────────────────────

_DATA_HIT = {"signal": "direct_appdata_call",
             "description": "앱 데이터 API 를 직접 호출한다(브리지를 거치지 않는다)",
             "path": "src/hooks/useCustomers.ts", "line": 38,
             "evidence": "const data = await window.afs.data.list(datasetName);"}
_AUTH_HIT = {"signal": "local_login_form", "description": "로그인 폼 또는 비밀번호 입력 필드",
             "path": "src/App.tsx", "line": 187, "evidence": 'type="password"'}


def test_데이터_신호에_인증_문구를_주지_않는다():
    """★★★ [2026-08-27 실측 — 내가 만든 결함] `CRM003` E2E-05 가 이것으로 죽었다.

    ⚠️⚠️ `platform_auth_checker` 는 이름과 달리 **인증만 보지 않는다** — 11개 신호 중
      인증은 6개이고 나머지는 데이터 평면·저장소다. 그런데 게이트는 무엇이 걸렸든
      「앱이 자체 인증을 만들었습니다」라고 말했다. 실제로 걸린 것은

          src/hooks/useCustomers.ts:38 — 어댑터를 거치지 않은 window.afs.data 직접 호출

      인데 개발자는 **없는 로그인을 지우라는 지시**를 받고 8왕복을 태웠다.
    ★ 거절이 행동으로 이어지지 않으면 그것은 통제가 아니라 교착이다."""
    from nodes.execution import _platform_auth_review_text

    text = _platform_auth_review_text([_DATA_HIT])
    assert "자체 인증" not in text, "인증이 아닌데 인증 문구를 준다"
    assert "어댑터만" in text, "무엇을 쓰라는 지시가 없다"
    assert "generated/afs-contract" in text, "import 예시가 없다"


def test_인증_신호에는_인증_문구를_준다():
    """★ 대조군 — 반대쪽이 없으면 위 시험은 「항상 인증 문구 없음」만 증명한다."""
    from nodes.execution import _platform_auth_review_text

    text = _platform_auth_review_text([_AUTH_HIT])
    assert "자체 인증" in text
    assert "어댑터만" not in text, "인증 문제에 데이터 지시가 섞인다"


def test_둘_다_걸리면_둘_다_말한다():
    from nodes.execution import _platform_auth_review_text

    text = _platform_auth_review_text([_DATA_HIT, _AUTH_HIT])
    assert "자체 인증" in text and "어댑터만" in text


def test_근거_줄을_함께_준다():
    """⚠️ 근거가 없으면 개발자가 어디를 고칠지 모르고, 반박도 못 한다."""
    from nodes.execution import _platform_auth_review_text

    text = _platform_auth_review_text([_DATA_HIT])
    assert "useCustomers.ts:38" in text
    assert "window.afs.data.list" in text
