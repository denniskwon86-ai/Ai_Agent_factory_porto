"""★★★ 계약형 시연 데이터 **다섯 종 승격**을 검증한다. (§7 2단계)

## 이 파일이 지키는 것

    ① 무결성 검사가 **빨강이 될 수 있는가** — 8가지 고장을 각각 심어 본다
    ② 운영 폴더로는 **절대 돌지 않는가**
    ③ 인증 결과가 `DEMO_CERTIFIED` · `DEMO/SYNTHETIC` 인가
    ④ 실적 승격이 **상태 기계로** 막히는가 (깃발이 아니라)

⚠️⚠️ ①이 이 파일의 존재 이유다. 실제 데이터로 한 번 초록을 본 것은 「검사가 있다」의
  증거일 뿐 「검사가 잡는다」의 증거가 아니다. 늘 초록인 검사는 아무것도 지키지 않는다.

⚠️ 특히 `LOG-02.po_line_id → PRC-02` 는 **주문행** 단위여야 한다. 헤더 단위로 보면
  다품목 주문이 들어오는 순간부터 조용히 잘못 연결되고, 행 수는 그대로다.
"""
import copy
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.data_preparation import models as m

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "promote_ontology_vertical_v1.py"

#: ⚠️ 승격 스크립트 원문에 **있어서는 안 되는** 조각. 검사에 필요한 이 한 자리 말고는
#:   주석·docstring 에도 적지 않는다 — 예시로 적어 두면 언젠가 기본값이 된다.
_REAL_ACCOUNT_PREFIX = "hikwon@"


def _run(*args):
    """스크립트를 하위 프로세스로 돌린다.

    ⚠️⚠️ `PYTHONIOENCODING` 을 반드시 준다. 없으면 파이프로 잡은 출력이 콘솔 코드페이지로
      나가면서 한글·«»·✗ 에서 `UnicodeEncodeError` 가 나고 **종료코드가 1** 이 된다 —
      그러면 「막혔다(2)」와 「검증 실패(1)」와 「출력이 깨졌다(1)」가 구별되지 않는다.
    ★ 실제로 이 시험이 처음에 그 이유로 빨강이었다. 통제는 멀쩡했다."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(ROOT),
                          capture_output=True, text=True, errors="replace",
                          timeout=900, env=env)


def _module():
    spec = importlib.util.spec_from_file_location("_promote_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                 # type: ignore[union-attr]
    return mod


P = _module()


@pytest.fixture(scope="module")
def data():
    """생성기 산출물 그대로. ⚠️ **읽기만 한다** — 시험이 키트를 고치면 안 된다."""
    out = {}
    for key in P.VERTICAL:
        payload, rows, columns = P._read("quick", key)
        out[key] = {"payload": payload, "rows": rows, "columns": columns}
    return out


def _copy(data):
    return {k: {"payload": v["payload"], "columns": v["columns"],
                "rows": copy.deepcopy(v["rows"])} for k, v in data.items()}


# ── ① 대조군과 8가지 고장 ────────────────────────────────────────────────

def test_실제_데이터는_통과한다(data):
    """★ 대조군 — 늘 빨강인 검사는 아무도 보지 않게 된다."""
    assert P.verify(_copy(data)) == []


def test_기본키가_중복되면_잡는다(data):
    d = _copy(data)
    d["PRC-02"]["rows"][1]["po_line_id"] = d["PRC-02"]["rows"][0]["po_line_id"]
    bad = P.verify(d)
    assert any("중복" in b for b in bad), bad


def test_기본키가_비면_잡는다(data):
    d = _copy(data)
    d["INV-01"]["rows"][3]["snapshot_id"] = ""
    assert any("snapshot_id" in b for b in P.verify(d)), P.verify(d)


def test_필수_열이_비면_잡는다(data):
    """⚠️ 열쇠만 보면 「연결은 되는데 뜻이 없는」 행이 통과한다."""
    d = _copy(data)
    d["SLS-01"]["rows"][5]["due_date"] = ""
    assert any("due_date" in b for b in P.verify(d)), P.verify(d)


def test_범위가_없으면_잡는다(data):
    """★★★ 범위 없는 행은 권한 필터에서 «미기록» 이 되어 **통제 밖**에 놓인다."""
    d = _copy(data)
    d["MFG-01"]["rows"][2]["scope_node_id"] = ""
    assert any("scope_node_id" in b for b in P.verify(d)), P.verify(d)


def test_다른_tenant_가_섞이면_잡는다(data):
    """⚠️ 남의 조직 자료가 우리 경로에 들어오는 자리다."""
    d = _copy(data)
    d["LOG-02"]["rows"][4]["tenant_id"] = "tenant-남의회사"
    assert any("tenant" in b for b in P.verify(d)), P.verify(d)


def test_짝이_없는_선적을_잡는다(data):
    """★ 선적이 가리키는 주문행이 없으면 그 경로는 **첫 홉에서 끊긴다.**"""
    d = _copy(data)
    d["LOG-02"]["rows"][0]["po_line_id"] = "PO-없는행-99"
    assert any("짝이 없는" in b for b in P.verify(d)), P.verify(d)


def test_주문행이_둘이면_잡는다(data):
    """★★★ **이 시험이 낟알을 지킨다.**

    ⚠️ 주문 **헤더** 단위로 보면 한 주문에 품목이 둘일 때 선적이 어느 행에 붙는지
      알 수 없다. 그런데 행 수는 그대로이고 화면도 멀쩡해 보인다 — 조용히 틀린다."""
    d = _copy(data)
    #: ⚠️ 첫 판은 아무 주문행이나 복제했다. 그러면 **기본키 중복**만 걸리고 낟알 규칙은
    #:   한 번도 실행되지 않는다 — 초록이었지만 지키는 것이 없었다.
    #: ★ 그래서 **선적이 실제로 가리키는** 주문행을 복제한다.
    referenced = str(d["LOG-02"]["rows"][0]["po_line_id"]).strip()
    twin = copy.deepcopy(next(r for r in d["PRC-02"]["rows"]
                              if str(r["po_line_id"]).strip() == referenced))
    d["PRC-02"]["rows"].append(twin)
    bad = P.verify(d)
    assert any("둘 이상" in b for b in bad), f"낟알 규칙이 실행되지 않았다: {bad}"
    #: ★ 기본키 중복도 함께 걸린다 — 두 겹으로 막는다.
    assert any("중복" in b for b in bad), bad


def test_주문보다_이른_출항을_잡는다(data):
    """⚠️ 선적이 주문보다 먼저면 「지연 영향」이라는 질문 자체가 성립하지 않는다."""
    d = _copy(data)
    d["LOG-02"]["rows"][0]["etd"] = "1999-01-01"
    assert any("이른 출항" in b for b in P.verify(d)), P.verify(d)


# ── ② 운영 폴더 차단 ─────────────────────────────────────────────────────

def test_운영_폴더로는_돌지_않는다(tmp_path):
    """★★★ 「무효 payload 일 예정이니 괜찮다」는 판단이 과거에 세 번 틀렸다.

    ⚠️ 하위 폴더까지 막는다 — `data/demo` 같은 이름이 예외가 되면 그 예외가 곧 구멍이다."""
    for target in ("data", "data/sub"):
        out = _run("--data-dir", target)
        assert out.returncode == 2, (
            f"{target} 로 실행됐다(exit={out.returncode}): {out.stdout} {out.stderr}")


def test_검증만_하면_아무것도_쓰지_않는다(tmp_path):
    """★ 「검증만」이 실제로 아무것도 안 만드는지 본다 — 이름만 그런 옵션이면 위험하다."""
    #: ⚠️ `tmp_path` 자체를 쓰면 안 된다 — conftest 의 격리 fixture 들이 거기에 이미
    #:   저장소를 만들어 둔다. 그것을 「스크립트가 만든 것」으로 세면 **거짓 빨강**이다.
    target = tmp_path / "verify_only_probe"
    out = _run("--data-dir", str(target), "--verify-only")
    assert out.returncode == 0, out.stdout + out.stderr
    assert not target.exists(), "«검증만» 인데 폴더가 생겼다"


# ── ③ 인증 결과 ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def promoted(tmp_path_factory, data):
    out = P.promote(_copy(data), tmp_path_factory.mktemp("vertical"), "quick",
                    P.SYNTHETIC_OWNER)
    return out


def test_다섯_종이_모두_합성_인증된다(promoted):
    assert set(promoted["snapshots"]) == set(P.VERTICAL)
    for key, snap in promoted["snapshots"].items():
        assert snap["state"] == m.DEMO_CERTIFIED, f"{key}: {snap['state']}"
        assert snap["data_kind"] == m.DATA_KIND_DEMO, f"{key}: {snap['data_kind']}"


def test_행_수가_원천과_같다(promoted, data):
    """⚠️ 대사 없이 인증하면 「몇 건을 인증했는가」에 아무도 답할 수 없다."""
    for key, snap in promoted["snapshots"].items():
        assert snap["row_count"] == len(data[key]["rows"]), key


def test_범위_세_값이_행에서_온다(promoted, data):
    """★ 여기서 지어내면 그 순간 자료와 갈라진다."""
    src = data["PRC-02"]["rows"][0]
    assert promoted["tenant"] == src["tenant_id"]
    assert promoted["scope"] == src["scope_node_id"]
    for snap in promoted["snapshots"].values():
        assert snap["tenant_id"] == src["tenant_id"]
        assert snap["entity_mode"] == "VIRTUAL", "가상회사 자료가 REAL 로 섰다"


def test_같은_원천이면_같은_내용_지문(promoted, data):
    """★★★ 같은 seed·같은 프로필이면 **같은 지문**이어야 한다.

    ⚠️ Snapshot ID 는 매번 달라진다(새 판은 새 기록이다). 같아야 하는 것은 **내용**이다."""
    for key, snap in promoted["snapshots"].items():
        expect = P.hashlib.sha256(data[key]["payload"]).hexdigest()
        assert snap["content_fingerprint"] == expect, key


# ── ④ 실적 승격 금지가 상태 기계인가 ────────────────────────────────────

def test_실적_인증_상태는_존재하지_않는다():
    """★★★ **깃발이 아니라 상태 기계**로 막는다.

    ⚠️ `promotable=false` 같은 깃발은 누군가 `True` 로 바꾸면 끝난다. 여기서는 애초에
      갈 곳이 없다 — 평범한 `CERTIFIED` 라는 상태 자체가 없다."""
    assert "CERTIFIED" not in m.SNAPSHOT_STATES
    assert m.DEMO_CERTIFIED in m.SNAPSHOT_STATES


def test_인증_뒤에는_철회_말고_갈_곳이_없다():
    assert m.SNAPSHOT_TRANSITIONS[m.DEMO_CERTIFIED] == (m.REVOKED,)
    for target in (m.RAW, m.PROFILED, m.STANDARDIZED, m.RECONCILED):
        assert not m.can_snapshot_transition(m.DEMO_CERTIFIED, target), target


def test_승격_대상은_다섯_종뿐이다():
    """⚠️ 전체를 정본으로 올리면, 아직 Resolver·관계·계산이 없는 데이터까지
    「공식 경영 의미망에 편입됐다」고 오해하게 된다."""
    assert list(P.VERTICAL) == ["PRC-02", "LOG-02", "INV-01", "MFG-01", "SLS-01"]


def test_기존_파일럿_시드를_건드리지_않는다():
    """★ 2단계는 **병행**이다 — 기존 화면·시험의 기본 프로필을 바꾸지 않는다."""
    src = SCRIPT.read_text(encoding="utf-8")
    #: ⚠️ 문서에서 이름을 «언급» 하는 것은 괜찮다. 막아야 하는 것은 **부르는 것**이다.
    for forbidden in ("import pilot_demo_seed", "from scripts.pilot_demo_seed",
                      "pilot_demo_seed."):
        assert forbidden not in src, f"승격 스크립트가 낡은 시드를 부른다: {forbidden}"
    pilot = (ROOT / "scripts" / "pilot_demo_seed.py").read_text(encoding="utf-8")
    assert P.PROFILE_NAME not in pilot, "낡은 시드가 새 프로필을 참조한다"


def test_인증_행위자가_실존_계정이_아니다():
    """★★★ **가상회사 인증 원장에 실존 인물의 행위를 적지 않는다.**

    ⚠️ 실측용 단일 계정을 쓰는 규칙은 «사람이 쓰는 화면» 을 위한 것이다.
      인증 원장은 다르다 — **행위의 기록**이므로, 나중에 그 사람이 「이 숫자를
      인증했다」고 읽히게 된다.
    ★ `.invalid` 는 예약 도메인이라 절대 실재하지 않는다(RFC 2606)."""
    assert P.SYNTHETIC_OWNER.endswith(".invalid"), P.SYNTHETIC_OWNER
    src = SCRIPT.read_text(encoding="utf-8")
    assert _REAL_ACCOUNT_PREFIX not in src, "승격 스크립트가 실존 계정을 기본값으로 쓴다"
