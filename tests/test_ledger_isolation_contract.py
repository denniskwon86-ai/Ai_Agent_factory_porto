"""★★★ [2026-08-17 사고 · P0-L2] 결정 원장 격리의 **불변 조건**.

## 무슨 일이 있었나

`conftest.py` 에 결정 원장 격리 항목이 **없었다.** 그래서 원장에 쓰는 모든 시험이
운영 `data/decision_ledger.db` 에 직접 썼다 — 11,627행 중 99.64% 가 시험 계정
패턴이었다. Git 미추적 파일이라 status 오염 검사에도, 지문 감시 목록에도 잡히지
않았다. **감시하지 않는 것은 격리되지 않는다.**

거기에 더해 `DecisionLedger.__init__(db_path=_DB_PATH)` 의 기본 인자가 **모듈 로딩
시점에 굳어** 있어서, 나중에 `_DB_PATH` 만 바꿔도 새 인스턴스가 옛 경로를 썼다.

## 이 파일이 지키는 것

「격리했다고 믿는 것」과 「격리된 것」을 가른다. 그래서 **운영 원장을 직접 읽어**
시험 전후가 같은지 본다 — 격리를 격리 코드로 확인하면 같은 실수를 두 번 한다.

⚠️ 파일 해시만 보지 않는다. SQLite 는 checkpoint 만으로도 바이트가 달라질 수 있어
  해시는 «변했다» 를 과잉 보고하고, 반대로 WAL 에만 쓰이면 본체 해시는 그대로라
  «안 변했다» 를 거짓 보고한다. 그래서 **논리적 센티널**(행 수·최대 seq·tail
  hash)을 함께 본다.
"""
import os
import sqlite3

import pytest

from core import decision_ledger as dl
from core.paths import data_path

LIVE = os.path.realpath(data_path("decision_ledger.db"))


#: ★ 판정을 **한 곳**에서 가져온다 — conftest 세션 감시와 이 파일이 같은 눈으로 봐야
#:   「세션은 통과했는데 파일 시험은 실패」 같은 설명 불가능한 상태가 안 생긴다.
from tests.ledger_isolation import live_sentinel as _live_sentinel      # noqa: E402
from tests.ledger_isolation import live_side_files as _live_side_files  # noqa: E402


@pytest.fixture
def live_untouched():
    """이 시험이 도는 동안 **운영 원장이 변하지 않았음**을 앞뒤로 확인한다."""
    before, files_before = _live_sentinel(), _live_side_files()
    yield
    assert _live_sentinel() == before, "시험이 운영 결정 원장을 바꿨다"
    assert _live_side_files() == files_before, "시험이 운영 원장의 WAL/SHM 파일을 만들었다"


# ── ① 인자 없는 생성 ─────────────────────────────────────────────────────
def test_bare_constructor_uses_the_isolated_path(tmp_path):
    """★★★ `DecisionLedger()` — **인자 없이** 만들어도 임시 경로여야 한다.

    ⚠️ 기본 인자를 모듈 로딩 때 굳히면 여기가 조용히 운영 경로가 된다. 그것이
      이번 사고의 절반이다."""
    made = dl.DecisionLedger()
    assert os.path.realpath(made.db_path) != LIVE
    assert os.path.realpath(made.db_path) == os.path.realpath(dl._DB_PATH)
    assert str(tmp_path) in os.path.realpath(made.db_path)


def test_explicit_path_still_wins(tmp_path):
    """명시한 경로는 그대로 쓴다 — 격리가 호출부의 의도를 덮지 않는다."""
    p = tmp_path / "따로.db"
    assert dl.DecisionLedger(db_path=str(p)).db_path == str(p)


# ── ② 이미 import 된 전역 싱글턴 ────────────────────────────────────────
def test_preimported_singleton_writes_to_the_isolated_db(live_untouched):
    """★★★ 소비자 모듈은 `from core.decision_ledger import decision_ledger` 로
    **객체 별칭을 미리 들고 있다.** 모듈 속성만 갈아 끼우면 그 별칭은 옛 객체를
    가리키고, 그 객체는 운영 파일을 연다."""
    from core.decision_ledger import decision_ledger as alias   # 소비자와 같은 방식

    assert os.path.realpath(alias.db_path) != LIVE
    row = alias.append(event_type="WBS_APPROVED", subject_type="wbs_task",
                       subject_id="격리확인", project_id="p_isolated")
    assert row["event_id"]
    #: 임시 원장에 **실제로** 남았는가 — 「어디에도 안 썼다」는 격리가 아니라 고장이다
    found = alias.list_events(subject_type="wbs_task", subject_id="격리확인")
    assert len(found) == 1


def test_real_consumer_modules_share_the_isolated_object(live_untouched):
    """★ 제품 소비자들은 함수 안에서 `from core.decision_ledger import decision_ledger`
    로 **같은 객체**를 집어 온다. 그 객체가 임시 경로를 봐야 한다.

    ⚠️ 특정 기능(계약 게이트 등)에 묶어 시험하지 않는다 — 그러면 그 기능이 없는
      판본에서 이 격리 회귀 자체가 깨지고, 격리 커밋을 따로 낼 수 없게 된다."""
    import importlib

    for name in ("core.app_delivery", "core.decision_case", "core.publication"):
        mod = importlib.import_module(name)
        assert mod is not None
    from core.decision_ledger import decision_ledger as consumer_view

    assert consumer_view is dl.decision_ledger, "소비자가 다른 객체를 본다"
    assert os.path.realpath(consumer_view.db_path) != LIVE


# ── ③ 격리 경로의 정체 ──────────────────────────────────────────────────
def test_isolated_path_is_not_under_the_live_data_dir(tmp_path):
    """⚠️ 경로 계산이 틀려 운영 `data/` 아래로 해석되면 격리는 이름뿐이다."""
    resolved = os.path.realpath(dl._DB_PATH)
    assert resolved != LIVE
    assert not resolved.startswith(os.path.dirname(LIVE) + os.sep)
    assert resolved.startswith(os.path.realpath(str(tmp_path)))


@pytest.mark.parametrize("bad,why", [
    ("", "비어"),
    (LIVE, "운영 원장 자체"),
    (os.path.join(os.path.dirname(LIVE), "tmp0", "decision_ledger.db"), "data/ 아래"),
    (os.path.dirname(LIVE), "data/ 아래"),
])
def test_the_path_guard_itself_rejects_live_paths(bad, why):
    """★★★ 경로 판정 **자체**를 시험한다.

    ⚠️ conftest 안에만 두면 이 규칙은 한 번도 검사되지 않는다 — 변이 검사에서
      그 자리를 통째로 지워도 아무 시험도 깨지지 않았다. 규칙이 있는 것과, 규칙이
      지켜지는지 **확인할 수 있는 것**은 다르다.
    ⚠️ 「운영 파일 자체」만 막으면 부족하다. 경로 계산이 틀어졌을 때 흔한 결과는
      `data/tmp0/…` 처럼 운영 뿌리 «안쪽»에 만드는 것이고, 그것도 오염이다."""
    from tests.ledger_isolation import isolation_path_error

    msg = isolation_path_error(bad)
    assert msg, f"{bad!r} 를 통과시켰다"
    assert why in msg


def test_the_path_guard_accepts_a_tmp_path(tmp_path):
    from tests.ledger_isolation import isolation_path_error

    assert isolation_path_error(str(tmp_path / "decision_ledger.db")) == ""


def test_singleton_and_module_default_agree(tmp_path):
    """세 곳(모듈 기본값·전역 싱글턴·새 인스턴스)이 **같은 임시 파일**을 봐야 한다.
    하나만 어긋나도 그 경로로 흘러간 기록은 운영에 남는다."""
    assert os.path.realpath(dl.decision_ledger.db_path) == os.path.realpath(dl._DB_PATH)
    assert os.path.realpath(dl.DecisionLedger().db_path) == os.path.realpath(dl._DB_PATH)


# ── ④ 운영 원장 불변 ────────────────────────────────────────────────────
def test_live_ledger_is_untouched_by_a_write_heavy_test(live_untouched):
    """★ 여러 번 써도 운영 원장의 행 수·최대 seq·tail hash 가 그대로여야 한다."""
    for i in range(5):
        dl.decision_ledger.append(event_type="WBS_APPROVED", subject_type="wbs_task",
                                  subject_id=f"T{i}", project_id="p_isolated")
    assert len(dl.decision_ledger.list_events(subject_type="wbs_task", limit=50)) >= 5


def test_live_sentinel_reader_does_not_create_side_files():
    """⚠️ 확인하는 행위 자체가 운영 파일을 건드리면 안 된다 — 그러면 이 시험이
    「변했다」를 스스로 만들어 낸다."""
    before = _live_side_files()
    _live_sentinel()
    assert _live_side_files() == before


# ── 보정 ① 빈 문자열은 폴백하지 않는다 ─────────────────────────────────
def test_blank_path_is_not_silently_replaced():
    """★★★ `db_path=""` 를 「지정하지 않음」으로 읽으면 **운영 원장으로 떨어진다.**

    ⚠️ 운영에서는 `_DB_PATH` 가 곧 운영 파일이다. 경로 계산이 빈 값을 낸 바로 그
      순간 운영 파일이 열린다 — 그리고 아무 오류도 나지 않는다.
    ★ `None` 만 「지정하지 않음」이다. 빈 문자열은 **잘못된 값**이고, 잘못된 값의
      올바른 결말은 폴백이 아니라 실패다(여기서는 그 값을 그대로 들고 있다가
      첫 사용에서 실패한다)."""
    assert dl.DecisionLedger(db_path="").db_path == "", (
        "빈 경로가 기본 경로로 바뀌었다 — 운영에서는 그것이 운영 원장이다")
    assert dl.DecisionLedger(db_path=None).db_path == dl._DB_PATH


# ── 보정 ② 수집 시점 ────────────────────────────────────────────────────
def test_constructing_does_not_open_any_file(tmp_path):
    """★★★ **만드는 것만으로 파일을 열지 않는다.**

    ⚠️ 예전에는 `__init__` 이 `_init_db()` 를 불렀다. 모듈 끝의 전역 싱글턴이
      **import 되는 순간** 운영 파일을 만들고 열었고, autouse fixture 는 그보다
      늦다 — 수집 단계에서 이미 늦은 것이다."""
    target = tmp_path / "아직없음.db"
    made = dl.DecisionLedger(db_path=str(target))
    assert made._prepared_for is None, "생성만으로 스키마를 준비했다"
    assert not target.exists(), "생성만으로 파일이 생겼다"
    made.append(event_type="WBS_APPROVED", subject_type="wbs_task", subject_id="T")
    assert target.exists() and made._prepared_for == str(target)


def test_import_time_isolation_holds_without_any_fixture(tmp_path):
    """★★★ **fixture 없이** — 별도 프로세스에서 conftest 를 import 한 직후의 상태를
    본다. 이것이 「수집 시점」을 실제로 재현하는 유일한 방법이다.

    ⚠️ 이 시험을 fixture 안에서 하면 의미가 없다. autouse fixture 가 이미 격리를
      다시 걸어 놓았기 때문에, 수집 시점 격리를 통째로 지워도 초록이 된다."""
    import json
    import subprocess
    import sys

    code = (
        "import json, os, sys;"
        "sys.path.insert(0, os.getcwd());"
        "import tests.conftest;"
        "import core.decision_ledger as dl;"
        "print(json.dumps({'default': os.path.realpath(dl._DB_PATH),"
        " 'singleton': os.path.realpath(dl.decision_ledger.db_path),"
        " 'prepared': dl.decision_ledger._prepared_for}))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])

    assert got["default"] != LIVE, "conftest import 후에도 모듈 기본값이 운영 원장이다"
    assert got["singleton"] != LIVE, "conftest import 후에도 전역 싱글턴이 운영 원장이다"
    assert got["prepared"] is None, "import 만으로 스키마를 준비했다"


# ── 보정 ③ 세션 감시와 WAL ──────────────────────────────────────────────
def test_sentinel_sees_rows_that_live_only_in_the_wal(tmp_path):
    """★★★ `immutable=1` 은 WAL 을 **아예 보지 않는다.**

    ⚠️ 그래서 활성 WAL 에 최신 행이 있으면 확인 도구가 못 본 채로 「안 변했다」고
      말한다 — 오염을 감시하려고 만든 것이 **거짓 안심**을 준다."""
    import sqlite3

    from tests.ledger_isolation import read_sentinel

    p = tmp_path / "wal.db"
    keeper = sqlite3.connect(str(p))          # ★ 열어 둔다 — 그래야 WAL 이 남는다
    keeper.execute("PRAGMA journal_mode=WAL")
    keeper.execute("CREATE TABLE decision_ledger_events (seq INTEGER, event_hash TEXT)")
    keeper.execute("INSERT INTO decision_ledger_events VALUES (1, 'h1')")
    keeper.execute("INSERT INTO decision_ledger_events VALUES (2, 'h2')")
    keeper.commit()
    try:
        assert os.path.exists(str(p) + "-wal"), "이 시험의 전제(활성 WAL)가 성립하지 않았다"
        got = read_sentinel(str(p))
        assert got == {"rows": 2, "max_seq": 2, "tail_hash": "h2"}, (
            f"WAL 에만 있는 행을 놓쳤다: {got}")
    finally:
        keeper.close()
