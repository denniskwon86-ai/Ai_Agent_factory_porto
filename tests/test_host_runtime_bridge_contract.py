"""★★★ [I-3] 브리지가 **계약을 구현할 뿐 늘리지 못하게** 잠근다.

교차검토: 「프론트 구현자가 임의로 결정하면 보안 계약이 다시 프론트에 분산됩니다.」

계약 정본은 `core/host_runtime_wire.py`(+`host_runtime_sdk.py`) 이고, 프론트 사본은
`frontend/src/lib/hostRuntimeWire.ts` 다. **두 파일이 어긋나면 여기서 깨진다.**

⚠️ 소스 검사는 보안 경계가 아니다(감사 지적 A). 실제 경계는 브라우저 샌드박스와 서버
  판정이다. 이 파일은 그 경계를 무너뜨리는 변경이 **조용히** 들어오는 것을 막는 회귀 잠금이다.

## 왜 파이썬으로 프론트를 검사하는가

이 저장소에는 JS 테스트 러너가 없다. 새로 들이는 것보다, 이미 같은 방식으로 라우트 권한표와
iframe 자격증명을 지키고 있는 **소스 검사**를 쓴다 — 러너가 늘면 「어느 쪽에서 돌렸는가」에
따라 초록이 달라지고, 그 차이는 아무도 안 본다.
"""
import os
import re
from pathlib import Path

import pytest

import core.host_runtime_sdk as sdk
import core.host_runtime_wire as wire

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
TS_WIRE = FRONTEND / "lib" / "hostRuntimeWire.ts"
TS_BRIDGE = FRONTEND / "lib" / "hostRuntimeBridge.ts"
TSX_PREVIEW = FRONTEND / "components" / "PreviewPanel.tsx"


@pytest.fixture(scope="module")
def ts():
    return TS_WIRE.read_text("utf-8")


@pytest.fixture(scope="module")
def bridge():
    return TS_BRIDGE.read_text("utf-8")


@pytest.fixture(scope="module")
def shim():
    """srcDoc 안에 들어가는 `window.afs` 블록만 떼어낸다."""
    src = TSX_PREVIEW.read_text("utf-8")
    i = src.index("window.afs = {")
    return src[i:src.index("})();", i)]


def _num(src: str, name: str) -> int:
    m = re.search(rf"export const {name} = (\d+);", src)
    assert m, f"TS 사본에 {name} 이 없다"
    return int(m.group(1))


def _arr(src: str, name: str):
    m = re.search(rf"export const {name}(?::[^=]+)? = \[(.*?)\]", src, re.S)
    assert m, f"TS 사본에 {name} 배열이 없다"
    return [x for x in re.findall(r"'([^']*)'", m.group(1))]


def _obj_of_lists(src: str, name: str):
    m = re.search(rf"export const {name}(?::[^=]+)? = \{{(.*?)\n\}};", src, re.S)
    assert m, f"TS 사본에 {name} 객체가 없다"
    out = {}
    for k, body in re.findall(r"'([\w.]+)':\s*\[([^\]]*)\]", m.group(1)):
        out[k] = tuple(re.findall(r"'([^']*)'", body))
    return out


# ── ① 한계값이 어긋나지 않는다 ────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "MAX_REQUEST_BYTES", "MAX_RESPONSE_BYTES", "MAX_PAGE_LIMIT", "DEFAULT_PAGE_LIMIT",
    "REQUEST_TIMEOUT_MS", "READY_TIMEOUT_MS", "MAX_INFLIGHT", "MAX_CALLS_PER_MINUTE",
    "MAX_ID_LEN", "IDEMPOTENCY_TTL_MS", "MAX_IDEMPOTENCY_ENTRIES",
])
def test_한계값이_정본과_같다(ts, name):
    """★★★ 브리지가 자기 상한을 갖는 순간 계약이 둘이 된다. 그리고 둘 중 느슨한 쪽이
    실제 동작이 된다 — 누구도 그것을 의도하지 않았는데."""
    assert _num(ts, name) == getattr(wire, name), f"{name} 이 정본과 다르다"


def test_SDK_판이_같다(ts):
    assert _num(ts, "SDK_VERSION") == sdk.SDK_VERSION


# ── ② 목록이 어긋나지 않는다 ──────────────────────────────────────────────

def test_작업별_인자가_정본과_같다(ts):
    assert _obj_of_lists(ts, "OP_FIELDS") == {k: tuple(v) for k, v in wire.OP_FIELDS.items()}


def test_작업별_필수인자가_정본과_같다(ts):
    """★★ 여기가 어긋나면 **멱등키 없는 쓰기**가 프론트에서 통과한다."""
    assert _obj_of_lists(ts, "OP_REQUIRED") == {k: tuple(v) for k, v in wire.OP_REQUIRED.items()}


@pytest.mark.parametrize("name,expected", [
    ("REQ_REQUIRED", "REQ_REQUIRED"), ("RES_FIELDS", "RES_FIELDS"),
    ("NOT_YET_HONORED", "NOT_YET_HONORED"),
    ("DATASET_PUBLIC_FIELDS", "DATASET_PUBLIC_FIELDS"),
    ("RECORD_PUBLIC_FIELDS", "RECORD_PUBLIC_FIELDS"),
])
def test_목록이_정본과_같다(ts, name, expected):
    assert tuple(_arr(ts, name)) == tuple(getattr(wire, expected)), f"{name} 이 정본과 다르다"


def test_앱이_보내면_안_되는_필드가_정본과_같다(ts):
    """★★★ 이 목록이 짧아지면 **앱이 자기 권한을 정하는** 필드가 하나 열린다."""
    assert tuple(_arr(ts, "IGNORED_FROM_APP")) == tuple(sdk.IGNORED_FROM_APP)


def test_앱_오류_코드가_정본과_같다(ts):
    """⚠️ 이 배열은 문자열이 아니라 **상수 이름**으로 적혀 있다. 이름을 값으로 풀어서 본다 —
    풀지 않으면 빈 목록이 나오고, 그러면 이 시험은 **아무것도 검사하지 않으면서 통과**한다
    (실제로 그렇게 한 번 걸렸다)."""
    consts = dict(re.findall(r"export const (ERR_\w+) = '([^']+)';", ts))
    m = re.search(r"export const APP_ERROR_CODES = \[(.*?)\]", ts, re.S)
    assert m, "APP_ERROR_CODES 를 찾지 못했다"
    names = [n.strip() for n in m.group(1).replace("\n", "").split(",") if n.strip()]
    assert names, "목록이 비었다 — 시험이 헛돌고 있다"
    assert tuple(consts[n] for n in names) == tuple(sdk.APP_ERROR_CODES)


def test_메시지_종류가_정본과_같다(ts):
    for name in ("MSG_HELLO", "MSG_INIT", "MSG_REQ", "MSG_RES"):
        m = re.search(rf"export const {name} = '([^']+)';", ts)
        assert m and m.group(1) == getattr(wire, name), f"{name} 이 정본과 다르다"


# ── ③ 전달 실패가 「없다」로 접히지 않는다 ────────────────────────────────

def test_HTTP_상태_접힘이_존재를_새게_하지_않는다(ts):
    """★★★ 5xx·네트워크 실패(0)가 `NOT_FOUND` 로 접히면 앱은 **서버에 있는 레코드를
    화면에서 지운다.** 쓰기였다면 더 나쁘다 — 만들어졌는데 실패로 알고 다시 만든다."""
    body = ts[ts.index("export function errorCodeForStatus"):]
    body = body[:body.index("\n}")]
    assert "status === 404) return ERR_NOT_FOUND" in body
    assert "status === 403) return ERR_FORBIDDEN" in body
    #: ★ 401(만료)과 410(앱 선언 변경)이 **같은 앱 오류**로 접힌다 — 앱이 할 일은 같다.
    #:   다르게 행동하는 것은 부모이고, 그 구분은 상태코드로 한다.
    assert "status === 401 || status === STATUS_STALE_APP) return ERR_EXPIRED" in body
    #: 마지막 줄(기본값)이 UNAVAILABLE 이어야 한다 — 여기가 요점이다.
    assert body.rstrip().endswith("return ERR_UNAVAILABLE;")


# ── ④ 브리지는 기본이 «꺼짐» 이다 ─────────────────────────────────────────

def test_브리지는_환경변수와_릴리스가_모두_있어야_켜진다(bridge):
    """★★★ 교차검토 지시 — 「I-3 를 Shadow/비활성 상태로 구현하고 격리 카나리에서 종단
    검증한 뒤 전환한다.」

    ⚠️ 기본값이 «켜짐» 이면 「끄는 것을 잊었다」가 곧 사고가 된다."""
    assert "VITE_AFS_HOST_RUNTIME" in bridge
    assert "?? '') === '1'" in bridge, "플래그가 없을 때 꺼지는지 읽어서 알 수 없다"
    assert "HOST_RUNTIME_FLAG && !!(deps.releaseId" in bridge, \
        "릴리스 없이도 켜질 수 있다 — 무엇에 대한 권한인지 비어 있는 요청이 된다"


def test_브리지가_스스로_소스_동일성을_본다(bridge):
    """★★★ `event.origin` 은 `"null"` 이고 **아무 샌드박스 프레임이나** 같은 값을 낸다.
    유일한 1차 경계는 `event.source === iframe.contentWindow` 동일성이다.

    ⚠️ 호출부(`PreviewPanel`)가 이미 보지만 브리지도 **자기 안에서 다시** 본다 —
      호출 순서가 바뀌는 날 경계가 사라지면 안 된다."""
    assert "event.source !== frame" in bridge


def test_브리지가_토큰을_다루지_않는다(bridge):
    """★★ 자격증명은 전역 인터셉터가 붙인다. 브리지가 토큰을 읽는 순간 그것을 로그·응답에
    찍는 코드가 언젠가 생긴다."""
    #: ⚠️ 주석은 뺀다. 「여기 두지 않는다」고 **적어 두는 것**까지 금지하면 그 이유를 적을
    #:   자리가 없어지고, 그러면 다음 사람이 왜 없는지 모른다.
    code = "\n".join(l for l in bridge.splitlines()
                     if not l.strip().startswith(("//", "*", "/*")))
    for needle in ("getSessionToken", "X-Session-Token", "localStorage", "Authorization"):
        assert needle not in code, f"브리지가 «{needle}» 을 다룬다"


def test_브리지는_전용_런타임_경로만_부른다(bridge):
    """★★★ [G1-B 3.5] 관리 API 는 **사람의 표면**이다. 브리지가 그쪽을 부르면 「증명 없으면
    세션으로」 폴백을 넣고 싶어지고, 그 순간 앱이 **헤더 하나를 생략해** 사람의 넓은 권한으로
    데이터를 만질 수 있다."""
    code = "\n".join(l for l in bridge.splitlines()
                     if not l.strip().startswith(("//", "*", "/*")))
    assert "'/api/v1/appdata/runtime'" in code
    #: 관리 경로 문자열이 코드에 남아 있으면 안 된다.
    assert "/api/v1/appdata/datasets" not in code, "관리 API 를 부르고 있다"
    assert "X-App-Proof" in code


def test_증명이_없으면_아예_부르지_않는다(bridge):
    """⚠️ 「증명 없이 한 번 시도해 보고 안 되면」은 서버가 폴백을 가질 때만 뜻이 있는데,
    서버는 폴백을 갖지 않는다 — 그 시도는 요청 하나를 낭비하고 감사에 거부를 남길 뿐이다."""
    assert "if (!proof) return { status: 0, json: null };" in bridge


def test_브리지가_증명_결속_응답의_HTTP_캐시를_쓰지_않는다(bridge):
    """이전 410을 새 증명에 재사용하면 «목록에서 다시 열기»가 영구 실패한다."""
    assert "cache: 'no-store'" in bridge


def test_세대가_바뀌면_증명을_버린다(bridge):
    """⚠️ 프레임이 바뀌면 «지금 그 앱을 열고 있다» 는 사실도 새로 세워야 한다."""
    m = re.search(r"function resetGeneration\(\) \{(.*?)\n  \}", bridge, re.S)
    assert m and "proof = ''" in m.group(1), "세대 초기화가 증명을 버리지 않는다"


def test_브리지가_응답을_투영해서만_돌려준다(bridge):
    """★★★ 서버는 행 전체를 준다 — `owner_dept_id`·`scope_node_id`·`created_by` 포함.
    그대로 넘기면 SDK 가 `afs.user` 를 막아 놓고 **데이터로 같은 것을 흘리는** 셈이다.

    ⚠️ 응답은 불투명 출처로 가므로 `targetOrigin` 을 지정할 수 없다(`'*'`). 그래서 필수다."""
    #: 성공 응답을 만드는 자리마다 투영 함수를 거쳐야 한다.
    successes = re.findall(r"return \{ ok: true, data: ([^}]+) \};", bridge)
    assert successes, "성공 응답 경로를 찾지 못했다 — 이 시험이 무의미해졌다"
    for expr in successes:
        assert "project" in expr or "records" in expr, f"투영 없이 그대로 넘긴다: {expr[:60]}"
    assert "projectRecord" in bridge and "projectDataset" in bridge


def test_브리지가_권한_필드를_지우고_보낸다(bridge):
    """⚠️ 값을 «검증» 하지 않고 지운다. 검증하면 「맞으면 쓴다」가 되고, 그러면 언젠가
    맞는 값을 보내는 코드가 생긴다."""
    assert "function stripIgnored" in bridge
    for call in re.findall(r"payload: ([^}]+) \}", bridge):
        assert "stripIgnored" in call, f"payload 를 그대로 보낸다: {call[:60]}"


def test_브리지가_응답을_잘라서_주지_않는다(bridge):
    """★ 상한을 넘으면 **오류**다. 자르면 앱은 그것을 «전부» 로 읽고, 그것이 조용한 거짓말이다."""
    assert "function tooLarge" in bridge
    assert "tooLarge(data)" in bridge


def test_브리지가_다른_세대의_메시지에_답하지_않는다(bridge):
    """★★ 오류로 답하면 그 답 자체가 「여기 부모가 있고 sid 가 틀렸다」는 정보다."""
    assert "VERDICT_DROP" in bridge
    m = re.search(r"if \(v\.verdict === VERDICT_DROP\) \{(.*?)\n    \}", bridge, re.S)
    assert m, "세대 불일치 처리를 찾지 못했다"
    assert "reply(" not in m.group(1), "버려야 할 메시지에 답하고 있다"


# ── ⑤ 앱이 보는 표면이 SDK 계약 그대로다 ──────────────────────────────────

def test_앱_표면이_계약과_정확히_같다(shim):
    """★★★ 브리지는 표면을 **구현할 뿐 늘리지 못한다.**"""
    roots = set(re.findall(r"^\s{14}(\w+):", shim, re.M))
    assert roots == {"version", "ready", "context", "data"}, roots
    methods = set(re.findall(r"^\s{16}(\w+): function", shim, re.M))
    assert methods == {"schema", "list", "get", "create", "update", "remove"}, methods
    for op in sdk.OPS:
        assert f"'{op}'" in shim, f"{op} 을 부르지 않는다"


def test_앱_표면에_금지된_이름이_없다(shim):
    """⚠️ 「없으니 안 만들겠지」로 두지 않는다 — 이름을 적어 두면 되살아남을 시험이 잡는다."""
    for banned in ("token", "session", "user_id", "sql", "localStorage"):
        assert banned not in shim, f"앱 표면에 «{banned}» 이 있다"


def test_앱_문맥은_표시값_둘뿐이다(shim):
    """⚠️ `context` 에 테넌트·조직범위를 넣고 싶어지는 순간이 온다. 넣으면 그것은 **앱이
    아는 사실**이 되고, 앱은 LLM 이 쓴 코드다."""
    src = TSX_PREVIEW.read_text("utf-8")
    m = re.search(r"var ctx = \{([^}]*)\};", src)
    assert m, "문맥 초기화를 찾지 못했다"
    keys = set(re.findall(r"(\w+):", m.group(1)))
    assert keys == {"app_id", "release_id"}, keys


def test_앱_쪽도_시간_상한을_갖는다():
    """★ 응답이 오지 않으면 **영원히 매달린다** — 앱은 로딩 화면에서 멈춘다.
    ⚠️ 그리고 그 시간 초과는 «없다» 가 아니라 «알 수 없다» 여야 한다."""
    src = TSX_PREVIEW.read_text("utf-8")
    assert f"}}, {wire.REQUEST_TIMEOUT_MS});" in src, "호출 시간 상한이 정본과 다르다"
    assert f"}}, {wire.READY_TIMEOUT_MS});" in src, "악수 시간 상한이 정본과 다르다"
    assert "reject(mkErr('UNAVAILABLE'" in src


def test_앱이_먼저_말한다():
    """★ 부모는 프레임이 언제 듣기 시작하는지 모른다 — 부모가 먼저 던지면 그 첫 메시지가
    자주 유실되고 `ready` 가 영원히 걸린다."""
    src = TSX_PREVIEW.read_text("utf-8")
    assert "post({ type: 'afs.hello'" in src


def test_iframe_안_스크립트가_문법적으로_유효하다():
    """★★★ srcDoc 의 인라인 스크립트는 **어떤 파이썬 시험도, tsc 도 보지 않는다** —
    그것은 타입스크립트가 아니라 템플릿 문자열 안의 문자열이다.

    그런데 이 블록에 문법 오류가 하나 나면 **모든 미리보기가 통째로 죽는다**(스크립트가
    통으로 파싱 실패한다). I-3 로 100줄 넘게 들어왔으므로 여기서 잡는다.

    ⚠️ 백틱 하나로 템플릿 리터럴이 그 자리에서 끊기는 사고가 실제로 있었다(파일 주석 참조).
      그 사고도 이 검사에 걸린다."""
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    assert node, "node 를 찾지 못했습니다 — 이 저장소는 프론트를 빌드합니다."

    src = TSX_PREVIEW.read_text("utf-8")
    start = src.index("<script>", src.index("const htmlTemplate")) + len("<script>")
    body = src[start:src.index("</script>", start)]
    assert "window.afs" in body, "추출한 구간에 브리지가 없다 — 엉뚱한 블록을 봤다"
    assert "${" not in body, ("스크립트 구간에 템플릿 보간이 생겼다 — 이 검사가 그것을 "
                             "문법 오류로 오판한다. 검사 방식을 함께 고칠 것.")

    #: ⚠️ 소스에 적힌 것과 **실행되는 것**은 다르다. 이 구간은 템플릿 리터럴 안이라
    #:   `\\.` 은 실행 시 `\.` 이 된다. 풀지 않고 검사하면 정상 정규식을 문법 오류로 읽는다
    #:   (첫 시도에서 실제로 그렇게 걸렸다 — 검사기가 검사 대상을 잘못 본 것이다).
    runtime = re.sub(r"\\([\\`$])", r"\1", body)

    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "iframe_body.js")
        Path(f).write_text(runtime, encoding="utf-8")
        r = subprocess.run([node, "--check", f], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"srcDoc 스크립트에 문법 오류가 있다:\n{(r.stderr or '')[-1200:]}"


def test_재시도용_멱등키를_오류에_실어_준다():
    """★★ 이 계약은 `UNAVAILABLE` 을 받으면 재시도하라고 말한다. 키 없이 재시도하면
    **계약이 스스로 중복 쓰기를 만든다.**

    ⚠️ 키를 «내용으로» 만들지 않는다 — 그러면 일부러 같은 값을 두 번 넣는 정상 입력이
      조용히 하나로 합쳐진다."""
    src = TSX_PREVIEW.read_text("utf-8")
    assert "e.retryKey = key" in src
    assert "function autoKey" in src
    body = src[src.index("function autoKey"):]
    body = body[:body.index("\n            }")]
    assert "JSON.stringify" not in body, "내용으로 키를 만들면 정상 중복 입력이 사라진다"


# ── ⑥ [교차검토 83] 재발급 범위와 화면 전달 ──────────────────────────────

def test_재발급은_Preview_수명이_아니라_요청마다_한_번이다(bridge):
    """★★★ 지적 4 — 종전에는 재발급 횟수를 **Preview 수명 전체**로 셌다. 그러면 두 번째
    정상 만료부터 앱이 **영구적으로 실패**한다. 증명은 15분짜리이므로 조금만 오래 열어 두면
    반드시 도달하는 상태다.

    「루프를 막는다」와 「한 번 쓰고 버린다」는 다른 말이고, 종전 코드는 뒤쪽이었다.
    ★ 폭주는 여전히 막힌다: 재발급도 호출 예산을 쓰고, 한 요청은 재시도를 한 번만 한다."""
    m = re.search(r"async function runWithProof.*?\n  \}", bridge, re.S)
    assert m, "재발급 경로를 찾지 못했다"
    body = m.group(0)
    #: ⚠️⚠️ **이름이 아니라 «조건» 을 못박는다.** 종전 시험은 `reissued` 라는 **이름**이
    #:   없는지만 봤고, 그래서 다른 이름으로 같은 전역 플래그를 두면 그대로 통과했다
    #:   (변이 검사에서 생존했다). 재시도 여부는 **이번 응답(`first`)만** 보고 정해져야 한다.
    assert "const step = nextStep(first);" in body and "step === STEP_RETURN" in body, \
        "재시도 조건이 이번 요청의 결과 말고 다른 상태에 달려 있다"
    assert "withinBudget()" in body, "재발급이 호출 예산을 쓰지 않는다 — 폭주를 막지 못한다"
    assert body.count("fetchProof()") == 2, "한 요청에서 재발급을 한 번만 해야 한다"


def test_서버가_사용자에게_할_말을_화면으로_올린다(bridge):
    """★★★ 지적 5 — 서버는 409 와 정확한 안내를 돌려주는데 화면이 그것을 버리면 사용자는
    **일반 연결 실패**만 본다. 조직 범위를 고르면 되는 상황인데 아무도 그것을 모른다."""
    assert "needsScope" in bridge and "r.json?.detail" in bridge
    m = re.search(r"async function fetchProof.*?\n  \}", bridge, re.S)
    assert m and "onActivity" in m.group(0)


def test_화면이_안내와_재시도를_함께_준다():
    """⚠️ 안내만 하고 다시 시도할 방법을 주지 않으면 사용자는 새로고침하는 수밖에 없다.

    ⚠️⚠️ 주석을 뺀 **코드만** 본다. 종전에는 「다시 시도할 방법을」이라고 적어 둔 주석이
      검사를 통과시켰다 — 단추를 지워도 초록이었다(변이 검사에서 생존했다)."""
    src = "\n".join(l for l in TSX_PREVIEW.read_text("utf-8").splitlines()
                    if not l.strip().startswith(("//", "*", "/*", "#:")))
    assert "onActivity:" in src, "브리지 훅이 화면에 연결되지 않았다"
    assert "needsScope" in src
    assert re.search(r"<button[\s\S]*?>\s*다시 시도\s*</button>", src), "재시도 단추가 없다"
    #: 서버 문장은 부모 화면에만 간다 — iframe 으로 넘기지 않는다.
    assert "info.message" in src


# ── ⑦ [교차검토 84] 낡은 앱이 새 증명으로 살아남지 않는다 ───────────────

def test_앱_선언이_바뀌면_재발급하지_않는다(bridge):
    """★★★ **이것이 결속을 우회하던 전체 흐름이다.**

    매니페스트 불일치를 일반 만료처럼 다루면 부모가 새 증명을 받아 오고, **기존 iframe 이
    그대로 계속 실행**된다. 즉 「그때 그 앱에 묶는다」가 무의미해진다.

    ⚠️ 프레임만 다시 만드는 것으로도 부족하다 — 같은 낡은 코드가 새 증명을 받을 뿐이다.
      그래서 표시(`staleApp`)는 `resetGeneration()` 으로 지워지지 않고, 사용자가 목록에서
      앱을 다시 열어야 새 브리지(=새 릴리스)가 만들어진다."""
    m = re.search(r"async function runWithProof.*?\n  \}", bridge, re.S)
    assert m, "재발급 경로를 찾지 못했다"
    body = m.group(0)
    #: 낡은 앱이면 재발급 앞에서 되돌아가야 한다.
    stale_at = body.index("step === STEP_STALE")
    reissue_at = body.index("fetchProof()", body.index("const first"))
    assert stale_at < reissue_at, "선언 변경을 확인하기 전에 재발급한다"
    assert "staleApp = true" in body
    #: ⚠️ 내부 표시만 세우고 **화면에 알리지 않으면** 사용자는 앱이 조용히 멈춘 것으로 본다.
    #:   변이 검사에서 이 칸이 비어 있었다 — 알림을 지워도 초록이었다.
    assert "staleApp: true" in body, "낡은 앱을 화면에 알리지 않는다"

    #: ★★★ [교차검토 85] 들고 있던 증명도 **즉시 버린다.** 남겨 두면 진행 중인 다른
    #:   호출들이 그것으로 계속 서버를 두드려 410 과 거부 감사가 쌓인다 — 아무 소용도 없이.
    stale_block = body[body.index("step === STEP_STALE"):]
    assert "proof = '';" in stale_block[:stale_block.index("return first;")],         "낡은 앱을 확인하고도 증명을 들고 있다 — 반복 410 과 거부 감사가 쌓인다"

    #: 발급 함수 자체도 막는다 — 프레임 재생성 시 악수→발급이 돌기 때문이다.
    f = re.search(r"async function fetchProof.*?\n  \}", bridge, re.S)
    assert f and "if (staleApp) return false;" in f.group(0), \
        "낡은 앱에 새 증명이 나갈 수 있다 — 프레임을 다시 만들면 옛 앱이 되살아난다"

    #: ⚠️ 세대 초기화가 이 표시를 지우면 안 된다.
    g = re.search(r"function resetGeneration\(\) \{(.*?)\n  \}", bridge, re.S)
    assert g and "staleApp" not in g.group(1), \
        "프레임을 다시 만들면 낡은 앱 표시가 사라진다 — 그 순간 옛 코드가 되살아난다"


def test_서버와_브리지가_같은_상태코드를_본다(bridge):
    """⚠️ 「앱 선언이 바뀌었다」를 서버는 410 으로, 브리지는 다른 숫자로 보면 그 통제는 없다."""
    from core import host_runtime_wire as pywire
    assert "STATUS_STALE_APP" in bridge
    ts = TS_WIRE.read_text("utf-8")
    m = re.search(r"export const STATUS_STALE_APP = (\d+);", ts)
    assert m and int(m.group(1)) == 410
    #: 서버 쪽 숫자도 같은지 본다(라우터가 그 값을 쓴다).
    rt = (FRONTEND.parents[1] / "api" / "routes" / "app_data_runtime.py").read_text("utf-8")
    assert "status=(410 if decision.reason in _STALE_APP_REASONS" in rt
    #: ★★★ [I-4 3단계] 「이 판은 사라졌다」로 답할 사유가 **셋**이다 — 앱 선언·계약 원문·
    #:   DB 물질화. ⚠️ 하나라도 빠지면 그 축이 바뀌어도 낡은 프레임이 계속 돈다.
    from api.routes import app_data_runtime as rt_mod
    from core import app_policy
    assert set(rt_mod._STALE_APP_REASONS) == {
        app_policy.DENY_TOKEN_MANIFEST_MISMATCH,
        app_policy.DENY_TOKEN_CONTRACT_MISMATCH,
        app_policy.DENY_TOKEN_MATERIALIZATION_MISMATCH,
    }
    assert pywire  # 계약 모듈이 살아 있다는 확인


def test_성공하면_이전_오류_문구를_지운다():
    """⚠️ 범위를 고르고 나서도 「조직을 선택하십시오」가 그대로 떠 있으면 사용자는
    **아직 안 된다고 읽는다.**"""
    src = TSX_PREVIEW.read_text("utf-8")
    m = re.search(r"onActivity: \(info\) => \{(.*?)\n      \},", src, re.S)
    assert m, "브리지 훅을 찾지 못했다"
    ok_branch = m.group(1)[:m.group(1).index("if (info.message)")]
    assert "setBridgeNote(" in ok_branch, "성공했는데 이전 문구를 그대로 둔다"
    assert "setNeedsScope(false)" in ok_branch
    #: ★★★ [교차검토 85] 성공이 **`staleApp` 을 풀면 안 된다.** 병렬로 나가 있던 다른
    #:   호출의 «늦은 성공» 이 도착하면 방금 세운 안내가 지워지고, 사용자는 낡은 판이
    #:   계속 도는 것을 모른 채 쓰게 된다. 해제는 **새 릴리스를 열 때만** 한다.
    assert "setStaleApp(false)" not in ok_branch, \
        "늦은 성공 하나가 낡은 앱 안내를 지운다"
    assert re.search(r"bridgeRef\.current = b;.*?setStaleApp\(false\)", src, re.S), \
        "새 릴리스를 열 때 낡은 앱 표시가 풀리지 않는다"
    #: ⚠️ 화면이 «낡은 앱» 을 실제로 **읽는지**도 본다. 브리지가 보내도 화면이 버리면
    #:   사용자는 앱이 조용히 멈춘 것으로 보고, 새로고침만 반복한다.
    assert "info.staleApp" in m.group(1), "화면이 낡은 앱 알림을 읽지 않는다"
    assert re.search(r"staleApp && \(", src), "낡은 앱 안내가 화면에 없다"
