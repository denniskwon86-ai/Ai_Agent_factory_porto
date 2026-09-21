"""[P2] 서빙 준비도 + 배포 상태 원장 — 승격 관문을 **실행되는 검사**로 잠근다.

⚠️ 격리 러너는 저장소 `conftest.py` 를 읽지 않는다. 여기서는 **전부 `tmp_path`** 위에서
  논다 — `DeployLedger()` 를 인자 없이 부르면 운영 `data/` 를 연다. 그래서 절대 부르지 않는다.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import threading

import pytest

from ops_control import deploy_ledger as dl
from core import serving_readiness as sr


# ═══ 서빙 준비도 ═════════════════════════════════════════════════════════
def test_unknown_is_not_a_promotion_reason():
    """★★ 「모른다」는 「됐다」가 아니다. 그리고 「안 됐다」도 아니다."""
    ready = sr.build_report([sr.Check("a", sr.READY)])
    unknown = sr.build_report([sr.Check("a", sr.READY), sr.Check("b", sr.UNKNOWN)])
    failed = sr.build_report([sr.Check("a", sr.FAIL)])
    assert (ready.verdict, unknown.verdict, failed.verdict) == (
        sr.READY, sr.UNKNOWN, sr.FAIL)
    assert sr.may_promote(ready) is True
    assert sr.may_promote(unknown) is False
    assert sr.may_promote(failed) is False


def test_fail_wins_over_unknown():
    report = sr.build_report([sr.Check("a", sr.UNKNOWN), sr.Check("b", sr.FAIL)])
    assert report.verdict == sr.FAIL


def test_looking_at_nothing_is_not_ready():
    """⚠️ 검사를 하나도 돌리지 않고 «준비됨» 을 돌려주면 관문이 없는 것과 같다."""
    assert sr.build_report([]).verdict == sr.UNKNOWN


# ── ⚠️⚠️ 준비도 점검이 저장소를 «만들면» 그 점검이 곧 사고다 ────────────
def test_schema_check_never_creates_a_missing_database(tmp_path):
    """★★ `sqlite3.connect(path)` 는 **없는 파일을 만든다.**

    준비도가 빈 DB 를 만들어 두면 다음 점검은 「표가 없다」가 아니라 「DB 는 있는데
    비었다」가 되고, 그 위에 기동 DDL 이 돌아 **아무도 의도하지 않은 저장소**가 생긴다."""
    missing = str(tmp_path / "not_there.db")
    check = sr.check_schema({"x": {"t": ()}}, lambda k: missing)
    assert check.verdict == sr.FAIL
    assert check.reason == sr.REASON_SCHEMA_STORE_ABSENT
    assert not os.path.exists(missing), "준비도 점검이 DB 파일을 만들었다"


def test_bounded_query_never_creates_a_missing_database(tmp_path):
    missing = str(tmp_path / "gone.db")
    check = sr.check_bounded_query([("x", "t")], lambda k: missing)
    assert check.verdict == sr.FAIL
    assert not os.path.exists(missing), "준비도 점검이 DB 파일을 만들었다"


def test_the_readonly_open_is_actually_read_only(tmp_path):
    """★★ 두 층을 «따로» 증명한다.

    ⚠️ 위의 두 시험은 사실 `isfile` 관문만 보고 있었다 — 파일이 없으면 거기서 돌아서
      연결 코드에 **도달하지 않는다**. 실제로 읽기 전용을 일반 연결로 바꿔 보니 전부
      «그대로 초록»이었다. 통제가 자기가 막을 것에 기대면 그건 층이 아니다.

    ⚠️ 그리고 «없는 파일에 연결해 본다» 로 증명하지 않는다 — 그건 부작용을 보는 것이고,
      격리 러너가 그 시도 자체를 차단으로 센다. **성질**(쓰기가 거부되는가)을 본다.
      쓰기가 막히는 연결은 파일도 만들지 않는다."""
    path = _make_db(tmp_path, name="ro.db")
    conn = sr._open_readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (?,?)", ("x", "y"))
    finally:
        conn.close()


def test_the_readonly_open_handles_awkward_paths(tmp_path):
    """⚠️ `f"file:{path}?mode=ro"` 로 이어 붙이면 Windows 역슬래시에서 URI 가 아니고,

    경로에 `#` 가 있으면 거기서부터 잘린다. 실제로 격리 러너가 이것을 막아 냈다."""
    folder = tmp_path / "a b#c"
    folder.mkdir()
    path = str(folder / "s.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(a TEXT)")
    conn.commit()
    conn.close()
    opened = sr._open_readonly(path)
    try:
        assert opened.execute("SELECT count(*) FROM t").fetchone()[0] == 0
    finally:
        opened.close()


def _make_db(tmp_path, name="s.db", ddl="CREATE TABLE t(a TEXT, b TEXT)", rows=()):
    path = str(tmp_path / name)
    conn = sqlite3.connect(path)
    conn.execute(ddl)
    for row in rows:
        conn.execute("INSERT INTO t VALUES (?,?)", row)
    conn.commit()
    conn.close()
    return path


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_schema_present_is_ready(tmp_path):
    path = _make_db(tmp_path)
    assert sr.check_schema({"x": {"t": ("a", "b")}}, lambda k: path).verdict == sr.READY


def test_missing_table_is_a_schema_failure(tmp_path):
    """★ [Z05] 「Green 준비 실패 · DB schema 불일치」의 판정 지점."""
    path = _make_db(tmp_path)
    check = sr.check_schema({"x": {"absent_table": ()}}, lambda k: path)
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_SCHEMA_OBJECTS_MISSING)


def test_missing_column_is_a_schema_failure(tmp_path):
    """⚠️ 표만 보면 통과한다 — **열이 없으면 첫 요청에서 죽는다.**"""
    path = _make_db(tmp_path)
    check = sr.check_schema({"x": {"t": ("a", "b", "c")}}, lambda k: path)
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_SCHEMA_OBJECTS_MISSING)


def test_unreadable_store_is_unknown_not_ready(tmp_path):
    """⚠️ 읽지 못한 것을 «통과» 로도 «실패» 로도 접지 않는다."""
    path = str(tmp_path / "broken.db")
    io.open(path, "w", encoding="utf-8").write("이건 SQLite 파일이 아니다")
    check = sr.check_schema({"x": {"t": ()}}, lambda k: path)
    assert check.verdict == sr.UNKNOWN
    assert check.reason == sr.REASON_SCHEMA_UNREADABLE


def test_bounded_query_reads_without_changing_the_store(tmp_path):
    """⚠️ 준비도 확인이 자료를 남기면 그건 더 이상 «확인» 이 아니다."""
    path = _make_db(tmp_path, rows=[("1", "2")])
    before = _sha(path)
    assert sr.check_bounded_query([("x", "t")], lambda k: path).verdict == sr.READY
    assert _sha(path) == before, "제한 조회가 저장소를 바꿨다"


def test_bounded_query_on_a_missing_table_fails(tmp_path):
    path = _make_db(tmp_path)
    check = sr.check_bounded_query([("x", "nope")], lambda k: path)
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_STORE_QUERY_FAILED)


# ── 공유 저장소 ─────────────────────────────────────────────────────────
def test_shared_storage_absent_fails(tmp_path):
    check = sr.check_shared_storage([str(tmp_path / "nowhere")])
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_SHARED_STORAGE_ABSENT)


def test_shared_storage_without_a_marker_is_unknown_not_ready(tmp_path):
    """⚠️ 「아마 공유겠지」로 승격하면 전환 뒤 한쪽 노드만 파일을 못 보는 사고가

    **조용히** 생긴다. 쓰기로 확인하지 않고 설치가 놓는 표식으로 말한다."""
    folder = tmp_path / "shared"
    folder.mkdir()
    check = sr.check_shared_storage([str(folder)])
    assert check.verdict == sr.UNKNOWN
    assert check.reason == sr.REASON_SHARED_STORAGE_UNVERIFIED


def test_shared_storage_with_marker_is_ready(tmp_path):
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / sr.SHARED_MARKER).write_text("", encoding="utf-8")
    assert sr.check_shared_storage([str(folder)]).verdict == sr.READY


# ── 설치 문맥 — 읽기 검증만 (DEP-05) ────────────────────────────────────
def test_install_context_matching_is_ready():
    check = sr.check_install_context("p", lambda p: {"tenant_id": "T1"}, "T1")
    assert check.verdict == sr.READY


def test_install_context_mismatch_fails():
    """⚠️ 선언한 tenant 와 저장소가 갈리면 권한·조회·SSE 문맥이 통째로 어긋난다."""
    check = sr.check_install_context("p", lambda p: {"tenant_id": "T1"}, "T2")
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_INSTALL_CONTEXT_MISMATCH)


def test_install_context_absent_is_not_ready():
    check = sr.check_install_context("p", lambda p: {}, "T1")
    assert (check.verdict, check.reason) == (sr.FAIL, sr.REASON_INSTALL_CONTEXT_ABSENT)


def test_install_context_unreadable_is_unknown():
    def boom(_):
        raise RuntimeError("읽지 못했다")

    check = sr.check_install_context("p", boom, "T1")
    assert check.verdict == sr.UNKNOWN


def test_install_context_check_never_applies_settings():
    """⚠️⚠️ `apply_settings` 는 `organization_nodes` 를 **다시 쓴다.**

    준비도 점검이 그것을 부르면 점검이 조직을 바꾼다. 읽기 함수만 불러야 한다."""
    called = []

    def reader(path):
        called.append(path)
        return {"tenant_id": "T1"}

    sr.check_install_context("p", reader, "T1")
    assert called == ["p"], "읽기 함수를 정확히 한 번만 불러야 한다"


def test_roles_not_started_fails():
    assert sr.check_roles(("api", "worker"), ("api",)).verdict == sr.FAIL
    assert sr.check_roles(("api",), ("api", "worker")).verdict == sr.READY


# ── 응답에 내부 구조를 싣지 않는다 ──────────────────────────────────────
def test_report_carries_no_paths_or_sql(tmp_path):
    """⚠️ 준비도 응답은 승격 자동화가 읽는 곳이다. 거기에 경로를 실으면 정찰 창구가 된다."""
    secret_path = str(tmp_path / "very_specific_name.db")
    report = sr.build_report([
        sr.check_schema({"x": {"t": ()}}, lambda k: secret_path),
        sr.check_shared_storage([str(tmp_path / "nope")]),
    ], artifact_digest="d", config_fingerprint="c")
    body = json.dumps(report.as_dict(), ensure_ascii=False)
    assert "very_specific_name" not in body
    assert str(tmp_path) not in body
    assert "SELECT" not in body.upper()


def test_release_identity_absent_is_unknown_and_mismatch_is_fail():
    assert sr.check_release_identity("", "").verdict == sr.UNKNOWN
    assert sr.check_release_identity("d", "c").verdict == sr.READY
    assert sr.check_release_identity("d", "c", expected_digest="other").verdict == sr.FAIL
    assert sr.check_release_identity("d", "c", expected_config="other").verdict == sr.FAIL


# ── 배선 — «부를 수 있는가» 까지 본다 ───────────────────────────────────
#: ⚠️ 운영 `data/` 를 열지 않는다. 전부 합성 트리다.
def _synthetic_node(tmp_path, tenant="T1", node_tenant=None, marker=True):
    """준비도가 READY 를 낼 수 있는 최소 노드 한 대를 만든다."""
    auth = str(tmp_path / "auth.db")
    conn = sqlite3.connect(auth)
    conn.execute("CREATE TABLE auth_credential(user_id TEXT PRIMARY KEY, "
                 "salt TEXT, hash TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE auth_session(session_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE auth_sse_ticket(token_hash TEXT PRIMARY KEY, "
                 "consumed_at TEXT, audience TEXT, expires_at TEXT)")
    conn.commit(); conn.close()

    ecm = str(tmp_path / "enterprise_context.db")
    conn = sqlite3.connect(ecm)
    conn.execute("CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE organization_nodes(node_id TEXT PRIMARY KEY, "
                 "entity_id TEXT, tenant_id TEXT)")
    conn.execute("INSERT INTO organization_nodes VALUES ('N1','E1',?)",
                 (node_tenant or tenant,))
    conn.commit(); conn.close()

    shared = tmp_path / "library"
    shared.mkdir()
    if marker:
        (shared / sr.SHARED_MARKER).write_text("", encoding="utf-8")

    settings = {"tenant_id": tenant, "company_name": "합성",
                "organization": {"entity_id": "E1", "legal_node_id": "N1"}}
    return {"stores": {"auth": auth, "enterprise_context": ecm},
            "shared": [str(shared)], "settings": settings}


def _collect(node, **over):
    kwargs = dict(settings_path="instance.json", shared_dirs=node["shared"],
                  declared_roles=("api",), started_roles=("api",),
                  running_digest="sha-A", running_config="cfg-1",
                  stores=node["stores"], load_settings=lambda p: node["settings"])
    kwargs.update(over)
    return sr.collect(**kwargs)


def test_collect_is_ready_on_a_healthy_synthetic_node(tmp_path):
    """★ 「배선이 있는가」가 아니라 **「부를 수 있는가」**를 본다."""
    report = _collect(_synthetic_node(tmp_path))
    assert report.verdict == sr.READY, report.as_dict()
    assert {c.name for c in report.checks} == {
        "release_identity", "schema", "bounded_query", "shared_storage",
        "install_context", "roles"}


def test_collect_catches_a_node_bound_to_another_tenant(tmp_path):
    """★ [DEP-05] 설치 설정은 T1 을 말하는데 법인 홈 노드가 T2 에 묶여 있다 —

    화면은 멀쩡해 보이고 **권한·조회·SSE 문맥만** 갈린다."""
    node = _synthetic_node(tmp_path, tenant="T1", node_tenant="T2")
    report = _collect(node)
    assert report.verdict == sr.FAIL
    bad = [c for c in report.checks if c.name == "install_context"][0]
    assert bad.reason == sr.REASON_INSTALL_CONTEXT_MISMATCH


def test_collect_without_identity_is_unknown_not_ready(tmp_path):
    """⚠️ 무엇을 들고 서 있는지 말하지 못하는 노드를 승격하지 않는다."""
    report = _collect(_synthetic_node(tmp_path), running_digest="", running_config="")
    assert report.verdict == sr.UNKNOWN
    assert sr.may_promote(report) is False


def test_collect_never_creates_the_stores_it_cannot_find(tmp_path):
    node = _synthetic_node(tmp_path)
    ghost = {"auth": str(tmp_path / "ghost_auth.db"),
             "enterprise_context": str(tmp_path / "ghost_ecm.db")}
    report = _collect(node, stores=ghost)
    assert report.verdict == sr.FAIL
    assert not os.path.exists(ghost["auth"])
    assert not os.path.exists(ghost["enterprise_context"])


def test_collect_reads_settings_but_never_applies_them(tmp_path):
    """⚠️⚠️ 준비도가 `apply_settings` 를 부르면 점검이 조직을 다시 쓴다."""
    node = _synthetic_node(tmp_path)
    seen = []

    def reader(path):
        seen.append(path)
        return node["settings"]

    _collect(node, load_settings=reader)
    assert seen and all(s == "instance.json" for s in seen)


# ── 탐침 CLI — 승격 자동화가 읽는 것은 «종료 코드» 다 ────────────────────
import importlib.util as _ilu  # noqa: E402

_PROBE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "serving_readiness_probe.py")
_pspec = _ilu.spec_from_file_location("_probe_under_test", _PROBE)
probe = _ilu.module_from_spec(_pspec)
_pspec.loader.exec_module(probe)


def _run_probe(monkeypatch, node, argv, digest="sha-A", config="cfg-1"):
    monkeypatch.setattr(sr, "default_store_paths", lambda: node["stores"])
    monkeypatch.setattr(probe.sr, "default_store_paths", lambda: node["stores"])
    monkeypatch.setenv(probe.ENV_DIGEST, digest)
    monkeypatch.setenv(probe.ENV_CONFIG, config)
    real_collect = sr.collect

    def patched(**kw):
        kw["load_settings"] = lambda p: node["settings"]
        return real_collect(**kw)

    monkeypatch.setattr(probe.sr, "collect", patched)
    return probe.main(argv)


def test_probe_exit_codes_tell_ready_fail_and_unknown_apart(tmp_path, monkeypatch,
                                                            capsys):
    """★★ `0 / 1` 둘로 접으면 「모른다」가 성공 쪽으로 새거나 원인을 잃는다."""
    node = _synthetic_node(tmp_path)
    argv = ["--shared-dir", node["shared"][0], "--role", "api", "--started", "api"]
    assert _run_probe(monkeypatch, node, argv) == 0
    capsys.readouterr()

    #: digest 를 못 말하면 UNKNOWN → **2** (0 이 아니다)
    assert _run_probe(monkeypatch, node, argv, digest="") == 2
    capsys.readouterr()

    #: 요구 digest 와 다르면 FAIL → 1
    assert _run_probe(monkeypatch, node, argv + ["--expect-digest", "other"]) == 1
    capsys.readouterr()


def test_probe_without_declared_roles_is_not_a_free_pass(tmp_path, monkeypatch,
                                                         capsys):
    """⚠️ 빈 집합끼리 비교하면 공짜 초록이 나온다 — 그 공짜가 관문을 무력화한다."""
    node = _synthetic_node(tmp_path)
    code = _run_probe(monkeypatch, node, ["--shared-dir", node["shared"][0]])
    capsys.readouterr()
    assert code == 2


def test_probe_refuses_a_verdict_it_does_not_know(monkeypatch, capsys):
    """★ 나중에 네 번째 판정값이 생겼을 때 **성공 쪽으로 새지 않는다.**

    ⚠️ 이 분기는 지금은 «도달하지 않는다»(판정값이 닫힌 집합이다). 그래서 변이를 걸어도
      아무 시험이 안 물렸다 — 그건 통제가 없다는 뜻이 아니라 **증명한 적이 없다**는 뜻이다."""
    class Odd:
        verdict = "SOMETHING_NEW"

        @staticmethod
        def as_dict():
            return {"verdict": "SOMETHING_NEW"}

    monkeypatch.setattr(probe.sr, "collect", lambda **kw: Odd())
    code = probe.main([])
    capsys.readouterr()
    assert code != 0, "모르는 판정을 «준비됨» 으로 접었다"


def test_probe_output_carries_no_paths(tmp_path, monkeypatch, capsys):
    node = _synthetic_node(tmp_path)
    _run_probe(monkeypatch, node, ["--shared-dir", node["shared"][0],
                                   "--role", "api", "--started", "api"])
    printed = capsys.readouterr().out
    assert str(tmp_path) not in printed
    assert "auth.db" not in printed


# ═══ 배포 상태 원장 ══════════════════════════════════════════════════════
def _ledger(tmp_path, name="dl.db"):
    return dl.DeployLedger(db_path=str(tmp_path / name))


def _open(ledger, plan_id="P1", env=dl.STAGING, digest="sha-A", config="cfg-1",
          actor="ops@example.invalid", migration=""):
    return ledger.open_plan(plan_id, env, digest, config, actor, migration)


def test_unknown_environment_is_refused(tmp_path):
    """⚠️ 오타로 «새 환경» 이 생기면 **환경 잠금이 통째로 우회된다.**"""
    ledger = _ledger(tmp_path)
    with pytest.raises(dl.DeployLedgerError):
        _open(ledger, env="stagign")


def test_reopening_the_same_plan_does_not_run_it_again(tmp_path):
    """★ 응답이 유실되면 사람도 스크립트도 다시 누른다 — 두 번째는 **현재 상태**다."""
    ledger = _ledger(tmp_path)
    first = _open(ledger)
    again = _open(ledger)
    assert first["created"] is True and again["created"] is False
    assert again["plan"]["state"] == dl.PLANNED
    assert len(ledger.history("P1")) == 1, "다시 열면서 이력이 늘었다"


def test_same_plan_id_with_different_content_is_refused(tmp_path):
    """⚠️ 같은 이름에 다른 내용을 붙이면 원장이 거짓말을 시작한다."""
    ledger = _ledger(tmp_path)
    _open(ledger)
    with pytest.raises(dl.DeployLedgerError):
        _open(ledger, digest="sha-B")


def test_one_environment_holds_one_in_flight_plan(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger, plan_id="P1")
    with pytest.raises(dl.DeployLedgerError) as caught:
        _open(ledger, plan_id="P2", digest="sha-B")
    assert "P1" in str(caught.value), "막을 때 무엇이 막고 있는지 말해야 한다"


def test_a_held_plan_releases_the_environment_lock(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger, plan_id="P1")
    ledger.hold("P1", "준비 실패", "ops@example.invalid")
    assert _open(ledger, plan_id="P2", digest="sha-B")["created"] is True


def test_holding_without_a_reason_is_refused(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger)
    with pytest.raises(dl.DeployLedgerError):
        ledger.hold("P1", "", "ops@example.invalid")


def test_actor_is_required_for_a_state_change(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger)
    with pytest.raises(dl.DeployLedgerError):
        ledger.record_readiness("P1", "READY", "")


def test_readiness_ready_advances_and_unknown_holds(tmp_path):
    """★★ `UNKNOWN` 도 승격 사유가 아니다 — 보류로 «이유와 함께» 남는다."""
    ledger = _ledger(tmp_path)
    _open(ledger, plan_id="P1")
    assert ledger.record_readiness("P1", "READY", "ops@example.invalid")["state"] == \
        dl.READY_CHECKED

    other = _ledger(tmp_path, "dl2.db")
    _open(other, plan_id="P9")
    held = other.record_readiness("P9", "UNKNOWN", "ops@example.invalid")
    assert held["state"] == dl.HELD
    assert "UNKNOWN" in held["reason"]


def test_approval_requires_a_passed_readiness(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger)
    with pytest.raises(dl.DeployLedgerError):
        ledger.approve("P1", "approver@example.invalid")


def _through_approval(ledger, plan_id="P1", digest="sha-A", env=dl.STAGING):
    _open(ledger, plan_id=plan_id, digest=digest, env=env)
    ledger.record_readiness(plan_id, "READY", "ops@example.invalid")
    ledger.approve(plan_id, "approver@example.invalid")
    return ledger


def test_promotion_happy_path(tmp_path):
    ledger = _through_approval(_ledger(tmp_path))
    promoted = ledger.promote("P1", "ops@example.invalid")
    assert promoted["state"] == dl.PROMOTED
    assert ledger.current_serving(dl.STAGING)["plan_id"] == "P1"


def test_promoting_supersedes_the_previous_serving_plan(tmp_path):
    ledger = _ledger(tmp_path)
    _through_approval(ledger, "P1", "sha-A")
    ledger.promote("P1", "ops@example.invalid")
    _through_approval(ledger, "P2", "sha-B")
    ledger.promote("P2", "ops@example.invalid")
    assert ledger.get_plan("P1")["state"] == dl.SUPERSEDED
    assert ledger.current_serving(dl.STAGING)["plan_id"] == "P2"


def test_z05_a_failed_green_never_touches_the_serving_plan(tmp_path):
    """★★ [Z05] Green 준비 실패 → 승격 없음 · **Blue 계속 서비스** · 원장에 이유.

    ⚠️ 여기서 지키는 것은 「새 것이 안 올라갔다」가 아니라 **「돌던 것이 그대로다」**이다."""
    ledger = _ledger(tmp_path)
    _through_approval(ledger, "BLUE", "sha-blue")
    ledger.promote("BLUE", "ops@example.invalid")
    blue_before = ledger.get_plan("BLUE")

    _open(ledger, plan_id="GREEN", digest="sha-green")
    held = ledger.record_readiness("GREEN", "FAIL", "ops@example.invalid",
                                   "schema_mismatch")

    assert held["state"] == dl.HELD
    assert any(h["reason"] == "schema_mismatch" for h in ledger.history("GREEN")), \
        "실패 이유가 원장에 남지 않았다"

    #: 그리고 보류된 계획을 다시 밀어도 **소리 내어 거절**한다.
    with pytest.raises(dl.DeployLedgerError):
        ledger.promote("GREEN", "ops@example.invalid")

    #: ★ 여기가 본체다 — 「새 것이 안 올라갔다」가 아니라 «돌던 것이 그대로다».
    assert ledger.current_serving(dl.STAGING)["plan_id"] == "BLUE"
    assert ledger.get_plan("BLUE") == blue_before, "서비스 중인 계획이 건드려졌다"


def test_promotion_without_approval_is_held(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger)
    ledger.record_readiness("P1", "READY", "ops@example.invalid")
    result = ledger.promote("P1", "ops@example.invalid")
    assert (result["state"], result["reason"]) == (dl.HELD, "approval_not_bound")


def test_an_approval_dies_when_what_it_approved_changes(tmp_path):
    """★★ 승인은 «무엇에 대한» 승인인지 묶인다. 승인 뒤 digest·설정·마이그레이션

    계획이 하나라도 바뀌면 **그 승인으로는 못 넘어간다.**"""
    path = str(tmp_path / "dl.db")
    ledger = _through_approval(dl.DeployLedger(db_path=path))
    #: 승인 뒤에 마이그레이션 계획이 바뀐 상황을 만든다.
    conn = sqlite3.connect(path)
    conn.execute("UPDATE deploy_plan SET migration_plan=? WHERE plan_id=?",
                 ("추가 이관 1건", "P1"))
    conn.commit()
    conn.close()

    result = ledger.promote("P1", "ops@example.invalid")
    assert (result["state"], result["reason"]) == (dl.HELD, "approval_not_bound")
    assert ledger.current_serving(dl.STAGING) is None


def test_promotion_rechecks_readiness_inside_the_transaction(tmp_path):
    """★★ 승격 관문은 «지금 이 순간의 행» 을 본다.

    ⚠️ 이 검사는 평소엔 상태 기계에 **가려져 있다** — 정상 흐름으로는 도달하지 않는다.
      (실제로 이 관문을 지우고 변이를 돌렸더니 46건이 그대로 초록이었다.)
      그래도 남겨 두는 이유는 **원장 행이 바깥에서 바뀔 수 있기** 때문이다. 승인까지
      끝난 계획의 준비도 판정이 뒤집혔다면 그 승격은 막혀야 한다.
      통제가 자기가 막을 것에 기대면 그건 층이 아니다."""
    path = str(tmp_path / "dl.db")
    ledger = _through_approval(dl.DeployLedger(db_path=path))
    conn = sqlite3.connect(path)
    conn.execute("UPDATE deploy_plan SET readiness_verdict=? WHERE plan_id=?",
                 ("FAIL", "P1"))
    conn.commit()
    conn.close()

    result = ledger.promote("P1", "ops@example.invalid")
    assert (result["state"], result["reason"]) == (dl.HELD, "readiness_not_ready")
    assert ledger.current_serving(dl.STAGING) is None


def test_approval_fingerprint_separates_its_parts():
    """⚠️ 붙여 쓰면 `("ab","c")` 와 `("a","bc")` 가 같은 지문이 된다."""
    assert dl.approval_fingerprint("staging", "ab", "c", "") != \
        dl.approval_fingerprint("staging", "a", "bc", "")


# ── 복귀는 «관측값» 없이 적지 않는다 ────────────────────────────────────
def test_rollback_needs_an_observation(tmp_path):
    ledger = _through_approval(_ledger(tmp_path))
    ledger.promote("P1", "ops@example.invalid")
    with pytest.raises(dl.DeployLedgerError):
        ledger.rollback("P1", "ops@example.invalid", "장애", "")


def test_rollback_refuses_while_the_same_artifact_is_still_serving(tmp_path):
    """⚠️⚠️ 명령이 0 으로 끝났다고 «복귀했다» 고 적지 않는다(§6-4).

    관측값이 이 계획의 digest 와 «같으면» 아직 안 끝난 것이다."""
    ledger = _through_approval(_ledger(tmp_path))
    ledger.promote("P1", "ops@example.invalid")
    with pytest.raises(dl.DeployLedgerError):
        ledger.rollback("P1", "ops@example.invalid", "장애", "sha-A")
    assert ledger.get_plan("P1")["state"] == dl.PROMOTED


def test_rollback_refuses_when_the_observation_does_not_match_the_target(tmp_path):
    ledger = _ledger(tmp_path)
    _through_approval(ledger, "BLUE", "sha-blue")
    ledger.promote("BLUE", "ops@example.invalid")
    _through_approval(ledger, "GREEN", "sha-green")
    ledger.promote("GREEN", "ops@example.invalid")
    with pytest.raises(dl.DeployLedgerError):
        ledger.rollback("GREEN", "ops@example.invalid", "장애",
                        "sha-somethingelse", restored_plan_id="BLUE")
    assert ledger.get_plan("GREEN")["state"] == dl.PROMOTED


def test_rollback_restores_the_previous_plan_when_observed(tmp_path):
    ledger = _ledger(tmp_path)
    _through_approval(ledger, "BLUE", "sha-blue")
    ledger.promote("BLUE", "ops@example.invalid")
    _through_approval(ledger, "GREEN", "sha-green")
    ledger.promote("GREEN", "ops@example.invalid")
    assert ledger.get_plan("BLUE")["state"] == dl.SUPERSEDED

    ledger.rollback("GREEN", "ops@example.invalid", "오류율 증가",
                    "sha-blue", restored_plan_id="BLUE")
    assert ledger.get_plan("GREEN")["state"] == dl.ROLLED_BACK
    assert ledger.current_serving(dl.STAGING)["plan_id"] == "BLUE"


def test_a_transition_from_the_wrong_state_is_refused(tmp_path):
    ledger = _ledger(tmp_path)
    _open(ledger)
    with pytest.raises(dl.DeployLedgerError):
        ledger.rollback("P1", "ops@example.invalid", "x", "sha-Z")


def test_history_keeps_every_transition_with_its_reason(tmp_path):
    ledger = _through_approval(_ledger(tmp_path))
    ledger.promote("P1", "ops@example.invalid")
    states = [h["to_state"] for h in ledger.history("P1")]
    assert states == [dl.PLANNED, dl.READY_CHECKED, dl.APPROVED, dl.PROMOTED]


def test_two_processes_cannot_both_open_a_plan_in_one_environment(tmp_path):
    """★ 「읽고 → 없으면 → 쓰기」로 나누면 둘 다 통과한다.

    ⚠️ 응용 메모리 lock 없이 성립해야 한다 — 다중 인스턴스에는 그런 lock 이 없다."""
    path = str(tmp_path / "race.db")
    dl.DeployLedger(db_path=path)  #: 스키마를 먼저 만들어 둔다.
    outcome: list = []
    gate = threading.Barrier(2)

    def opener(plan_id, digest):
        ledger = dl.DeployLedger(db_path=path)
        gate.wait()
        try:
            ledger.open_plan(plan_id, dl.TRIAL, digest, "cfg", "ops@example.invalid")
            outcome.append(plan_id)
        except dl.DeployLedgerError:
            pass

    threads = [threading.Thread(target=opener, args=(p, d))
               for p, d in (("A", "sha-A"), ("B", "sha-B"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert len(outcome) == 1, f"한 환경에 두 계획이 열렸다 — {outcome}"
