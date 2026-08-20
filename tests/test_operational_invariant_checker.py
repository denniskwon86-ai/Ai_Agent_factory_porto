"""★★★ **검사기 자체를 검증한다.** (2026-08-20 Supervisor 지적)

## 왜 이 파일이 필요한가

`scripts/check_operational_invariants.py` 는 「운영 데이터가 오염됐는가」를 판정하는
게이트다. 그런데 **그 게이트를 검증하는 시험이 없었다.** 그래서 실제로 이런 일이 났다:

    · 존재하지 않는 표(`kits`)를 세고 있었다 → 전후 모두 `unreadable` → **조용히 초록**
    · `source_bindings`·`readiness_evaluations`·`baseline_builds` 를 아예 안 봤다
    · browser 모드가 「상한 0」이라 **1건 → 0건 삭제도 통과**했다

⚠️ 판정하는 것을 판정하지 않으면, 그 판정은 언젠가 아무것도 판정하지 않게 된다.

★ 여기서는 **가짜 운영 폴더**를 만들어 검사기를 그대로 돌린다 — 운영 데이터를 만지지
  않고, 검사기가 실제로 빨강을 내는지 본다.
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/check_operational_invariants.py").resolve()


def _make_db(path: Path, tables: dict) -> None:
    """가짜 저장소 하나. `tables` = {표이름: 행수}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        for name, rows in tables.items():
            conn.execute(f"CREATE TABLE IF NOT EXISTS {name}(id INTEGER PRIMARY KEY)")
            for i in range(rows):
                conn.execute(f"INSERT INTO {name}(id) VALUES(?)", (i + 1,))
        conn.commit()
    finally:
        conn.close()


def _run(workspace: Path, *args: str):
    """검사기를 **그 작업공간에서** 돌린다.

    ⚠️ 검사기는 자기 위치로 뿌리를 정하므로, 사본을 만들어 그 안에서 돌린다 —
      운영 폴더를 건드리지 않기 위해서다."""
    scripts = workspace / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / SCRIPT.name).write_text(SCRIPT.read_text(encoding="utf-8"),
                                       encoding="utf-8")
    return subprocess.run([sys.executable, str(scripts / SCRIPT.name), *args],
                          capture_output=True, text=True, errors="replace",
                          timeout=180, cwd=str(workspace))


@pytest.fixture
def ws(tmp_path):
    """기준선이 잡힌 가짜 작업공간. 업무 표에 행이 하나씩 들어 있다."""
    _make_db(tmp_path / "data" / "data_preparation.db", {
        "kit_instances": 1, "dataset_snapshots": 1, "source_bindings": 1,
        "readiness_evaluations": 1, "baseline_builds": 1,
        "kit_registry_versions": 1})
    out = _run(tmp_path, "capture", "--mode", "browser")
    assert out.returncode == 0, out.stdout + out.stderr
    return tmp_path


def test_아무것도_안_바뀌면_통과한다(ws):
    out = _run(ws, "compare", "--mode", "browser")
    assert out.returncode == 0, out.stdout + out.stderr


@pytest.mark.parametrize("table", ["kit_instances", "dataset_snapshots",
                                   "source_bindings", "readiness_evaluations",
                                   "baseline_builds"])
def test_업무_행이_늘면_browser_에서도_실패한다(ws, table):
    """★★★ 파일 허용이 곧 내용 허용이 아니다.

    ⚠️ 화면 검증이 만들어도 되는 것은 **키트 레지스트리뿐**이다. 업무 행이 늘었는데
      통과하면, 화면 검증 한 번으로 운영에 업무 데이터가 들어와도 초록이 뜬다."""
    conn = sqlite3.connect(str(ws / "data" / "data_preparation.db"))
    conn.execute(f"INSERT INTO {table}(id) VALUES(999)")
    conn.commit()
    conn.close()
    out = _run(ws, "compare", "--mode", "browser")
    assert out.returncode == 1, f"{table} 증가를 잡지 못했다:\n{out.stdout}"
    assert table in out.stdout


@pytest.mark.parametrize("table", ["kit_instances", "dataset_snapshots"])
def test_업무_행이_줄어도_실패한다(ws, table):
    """★★★ **삭제도 이상한 일이다.** 「상한 0」만 보면 1건 → 0건이 통과한다 —
    사라진 것도 누가 지웠는지 물어야 한다."""
    conn = sqlite3.connect(str(ws / "data" / "data_preparation.db"))
    conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    out = _run(ws, "compare", "--mode", "browser")
    assert out.returncode == 1, f"{table} 감소를 잡지 못했다:\n{out.stdout}"


def test_존재하지_않는_표를_세고_있지_않다():
    """★★★ 없는 표를 세면 전후 모두 `unreadable` 이라 **조용히 초록**이다.

    ⚠️ 실제로 `kits` 를 세고 있었고, 그래서 아무것도 지키지 않으면서 지키는 것처럼
      보였다. 감시 목록의 표가 **실재하는지** 여기서 못박는다."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert '"kits"' not in src, "존재하지 않는 표 `kits` 를 아직 세고 있다"
    for must in ("kit_registry_versions", "source_bindings",
                 "readiness_evaluations", "baseline_builds"):
        assert must in src, f"감시 목록에 `{must}` 가 없다"


def test_기준선을_조용히_덮어쓰지_않는다(ws):
    """★★★ 오염 뒤에 `capture` 를 다시 돌리면 **오염이 새 «정상»** 이 된다."""
    out = _run(ws, "capture", "--mode", "browser")
    assert out.returncode == 2, out.stdout
    assert "force" in out.stdout


def test_다른_모드의_기준선과_비교하지_않는다(ws):
    out = _run(ws, "compare", "--mode", "tests")
    assert out.returncode == 2, out.stdout


def test_새_파일이_생기면_tests_모드에서_실패한다(tmp_path):
    """⚠️ 시험만 돌린 상태에서 저장소가 생기면 그것이 격리 결함이다."""
    _make_db(tmp_path / "data" / "decision_ledger.db", {"decision_ledger_events": 0})
    assert _run(tmp_path, "capture", "--mode", "tests").returncode == 0
    _make_db(tmp_path / "data" / "ontology.db", {"semantic_relations": 0})
    out = _run(tmp_path, "compare", "--mode", "tests")
    assert out.returncode == 1, out.stdout
    assert "ontology.db" in out.stdout


def test_원장_행이_늘면_어느_모드에서도_실패한다(ws):
    """★★★ 원장 오염은 **어떤 모드에서도** 봐주지 않는다."""
    _make_db(ws / "data" / "decision_ledger.db", {"decision_ledger_events": 0})
    assert _run(ws, "capture", "--mode", "browser", "--force").returncode == 0
    conn = sqlite3.connect(str(ws / "data" / "decision_ledger.db"))
    conn.execute("INSERT INTO decision_ledger_events(id) VALUES(1)")
    conn.commit()
    conn.close()
    out = _run(ws, "compare", "--mode", "browser")
    assert out.returncode == 1, out.stdout
    assert "decision_ledger_events" in out.stdout


def test_기준선에_HEAD_와_모드가_기록된다(ws):
    meta = json.loads((ws / ".invariant_baseline.json").read_text(encoding="utf-8"))
    assert meta["_meta"]["mode"] == "browser"
    assert "at" in meta["_meta"] and "workspace" in meta["_meta"]


# ── 내용 지문 (2026-08-20 재감사 P0-2) ──────────────────────────────────
def _make_rich(path: Path) -> None:
    """실제와 비슷한 모양 — 상태·지문·범위 열이 있다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript("""
            CREATE TABLE kit_instances(
                id TEXT PRIMARY KEY, scope_node_id TEXT, entity_mode TEXT);
            CREATE TABLE source_bindings(id TEXT PRIMARY KEY, state TEXT);
            CREATE TABLE dataset_snapshots(id TEXT PRIMARY KEY, checksum TEXT);
            CREATE TABLE readiness_evaluations(id TEXT PRIMARY KEY, status TEXT);
            CREATE TABLE baseline_builds(id TEXT PRIMARY KEY, fingerprint TEXT);
            CREATE TABLE kit_registry_versions(id TEXT PRIMARY KEY);
        """)
        conn.execute("INSERT INTO kit_instances VALUES('ki_1','node_hq','REAL')")
        conn.execute("INSERT INTO source_bindings VALUES('b_1','ACTIVE')")
        conn.execute("INSERT INTO dataset_snapshots VALUES('ds_1','abc123')")
        conn.execute("INSERT INTO readiness_evaluations VALUES('r_1','READY')")
        conn.execute("INSERT INTO baseline_builds VALUES('bl_1','fp_aaa')")
        conn.execute("INSERT INTO kit_registry_versions VALUES('kv_1')")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def rich(tmp_path):
    _make_rich(tmp_path / "data" / "data_preparation.db")
    out = _run(tmp_path, "capture", "--mode", "browser")
    assert out.returncode == 0, out.stdout + out.stderr
    return tmp_path


@pytest.mark.parametrize("sql,why", [
    ("UPDATE source_bindings SET state='RETIRED'", "결속 상태 변조"),
    ("UPDATE dataset_snapshots SET checksum='다른값'", "Snapshot 지문 교체"),
    ("UPDATE readiness_evaluations SET status='BLOCKED'", "준비도 판정 조작"),
    ("UPDATE baseline_builds SET fingerprint='fp_bbb'", "기준선 지문 갈아끼움"),
    ("UPDATE kit_instances SET scope_node_id='node_남의조직'", "조직 범위 변조"),
])
def test_행_수가_같아도_내용이_바뀌면_실패한다(rich, sql, why):
    """★★★ [2026-08-20 재감사 P0-2] **행 수만 비교하면 변조를 놓친다.**

    ⚠️ 특히 마지막 것이 나쁘다 — 남의 조직 데이터가 우리 것으로 보이게 되는데
      **행 수는 그대로**다. browser 모드는 파일 변경을 허용하므로 그대로 통과했다."""
    conn = sqlite3.connect(str(rich / "data" / "data_preparation.db"))
    conn.execute(sql)
    conn.commit()
    conn.close()
    out = _run(rich, "compare", "--mode", "browser")
    assert out.returncode == 1, f"{why} 를 잡지 못했다:\n{out.stdout}"
    #: ★ 어느 표가 걸렸는지까지 본다 — 종료코드만 보면 «다른 이유로 빨강» 을 못 가른다.
    #: ⚠️ 하위 프로세스 출력의 한글은 콘솔 코드페이지에서 깨진다 — **ASCII 조각**으로만 대조한다.
    table = sql.split()[1]
    assert table in out.stdout, f"{why}: {table} 이 사유에 없다 / {out.stdout}"


def test_아무것도_안_바꾸면_내용_비교도_통과한다(rich):
    """★ 대조군 — 늘 빨강인 검사는 아무도 보지 않게 된다."""
    out = _run(rich, "compare", "--mode", "browser")
    assert out.returncode == 0, out.stdout + out.stderr


def test_키트_레지스트리_증가는_browser_에서_허용된다(rich):
    """★ 화면 검증이 실제로 만드는 것은 이것뿐이다 — 여기서 막으면 검사가 늑대를 외친다."""
    conn = sqlite3.connect(str(rich / "data" / "data_preparation.db"))
    conn.execute("INSERT INTO kit_registry_versions VALUES('kv_2')")
    conn.commit()
    conn.close()
    out = _run(rich, "compare", "--mode", "browser")
    assert out.returncode == 0, out.stdout
