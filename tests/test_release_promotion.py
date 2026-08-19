"""★★★ [I-4 7 / Wave F-2] ACTIVE 원자 승격 — **후보를 운영으로 올리는 단 하나의 문.**

## 이 파일이 막으려는 네 가지

★★★ ① **승인 시점의 사실로 승격하는 것.** 승인은 «그때» 의 사실이고, 그 뒤에 계약이
  개정되거나 물질화가 어긋나거나 원천 인증이 회수될 수 있다.
★★★ ② **부분 승격.** 「대체로 괜찮으니 올리자」는 「운영이라고 적혀 있는데 계약과
  다른 판」을 만들고, 그 상태는 오류를 내지 않는다.
★★★ ③ **실패가 이전 ACTIVE 를 건드리는 것.** 새 판을 올리려다 실패했다고 이미 도는
  앱이 멈추면, 승격을 시도하는 것 자체가 위험한 일이 되고 아무도 안 하게 된다.
★★★ ④ **「보지 못한 것」을 통과로 세는 것.** 검사할 코드가 없거나 준비도를 확인하지
  못했으면 그것은 «깨끗함» 이 아니다.
"""
import pytest

from core import release_promotion as rp
from core.program_lifecycle import ACTIVE, CANDIDATE, DEPRECATED, DISABLED


class _Lifecycle:
    """상태만 들고 있는 최소 대역. **전이를 기록**해 ③ 을 확인할 수 있게 한다."""

    def __init__(self, status=CANDIDATE, fail=False):
        self._status = status
        self.calls = []
        self._fail = fail

    def get_status(self, release_id):
        if self._fail:
            raise RuntimeError("상태 저장소가 응답하지 않습니다")
        return {"release_id": release_id, "status": self._status}

    def set_status(self, release_id, status, actor="", reason=""):
        self.calls.append((release_id, status, actor, reason))
        self._status = status
        return {"release_id": release_id, "status": status}


def _release(**kw):
    """계약·물질화가 맞는 릴리스 하나. 기본은 «전부 통과» 다."""
    base = {
        "release_id": "rel_1", "project_id": "P1",
        "artifact_kind": "REPORT",           # 실행 앱이 아니다 → 계약 검사 면제 경로
        "requires_host_runtime": False,
        "manifest": {"fingerprint": "fp", "valid": True,
                     "manifest": {"version": "1.0", "app_class": "departmental",
                                  "capabilities": [], "required_capabilities": []}},
    }
    base.update(kw)
    return base


def _ok_checks(monkeypatch, *, contract=True, static=True):
    """관심 없는 검사를 통과로 고정한다 — **한 번에 하나만** 어긋내기 위해서."""
    monkeypatch.setattr(rp, "_check_contract",
                        lambda release, rid, plane=None: rp.Check(
                            rp.CHECK_CONTRACT, contract,
                            "" if contract else "어긋남"))
    monkeypatch.setattr(rp, "_check_static",
                        lambda paths: rp.Check(rp.CHECK_STATIC, static,
                                               "" if static else "차단 신호"))


def _promote(monkeypatch, *, lifecycle=None, release=None, readiness=rp.NOT_APPLICABLE,
             **kw):
    _ok_checks(monkeypatch, **kw)
    lc = lifecycle or _Lifecycle()
    return lc, rp.promote(release=release or _release(), release_id="rel_1",
                          lifecycle=lc, actor="u@x", code_paths=["x"],
                          readiness_state=readiness)


# ── 검사 목록이 구현과 갈라지지 않는다 ──────────────────────────────────
def test_the_check_list_is_pinned_literally():
    """★ 이름만 늘리고 구현을 안 하면 「검사했다」는 **거짓 기록**이 된다."""
    assert rp.CHECK_NAMES == ("릴리스 상태", "계약↔물질화", "정적 인증 검사",
                              "계약 승인", "데이터 준비도")


def test_every_named_check_actually_runs(monkeypatch):
    _ok_checks(monkeypatch)
    v = rp.run_checks(release=_release(), release_id="rel_1", lifecycle=_Lifecycle(),
                      code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)
    assert [c.name for c in v.checks] == list(rp.CHECK_NAMES)


def test_all_failures_are_reported_at_once(monkeypatch):
    """⚠️ 첫 실패에서 멈추면 사용자가 같은 화면을 다섯 번 본다."""
    _ok_checks(monkeypatch, contract=False, static=False)
    v = rp.run_checks(release=_release(), release_id="rel_1",
                      lifecycle=_Lifecycle(status=ACTIVE), code_paths=["x"],
                      readiness_state=None)
    assert not v.ok
    #: 상태·계약·정적·준비도 넷이 동시에 막혀야 한다
    assert len(v.blocking) == 4, [c.name for c in v.blocking]


# ── ① 승격 «시점» 에 다시 본다 ──────────────────────────────────────────
@pytest.mark.parametrize("state", [ACTIVE, DEPRECATED, DISABLED, "", "아무거나"])
def test_only_a_candidate_can_be_promoted(monkeypatch, state):
    """⚠️ 이미 운영인 판을 다시 올리면 이력에 «두 번 올렸다» 가 남고, 어느 쪽이 지금
    도는 판인지 흐려진다."""
    _ok_checks(monkeypatch)
    with pytest.raises(rp.PromotionError):
        rp.promote(release=_release(), release_id="rel_1",
                   lifecycle=_Lifecycle(status=state), actor="u@x",
                   code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)


def test_an_unreadable_state_is_not_a_pass(monkeypatch):
    """★★★ 「못 읽었으니 통과」가 곧 통제 없음이다."""
    _ok_checks(monkeypatch)
    with pytest.raises(rp.PromotionError) as e:
        rp.promote(release=_release(), release_id="rel_1",
                   lifecycle=_Lifecycle(fail=True), actor="u@x",
                   code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)
    assert "읽을 수 없습니다" in str(e.value)


def test_a_contract_mismatch_blocks_promotion(monkeypatch):
    with pytest.raises(rp.PromotionError):
        _promote(monkeypatch, contract=False)


def test_a_static_block_signal_blocks_promotion(monkeypatch):
    with pytest.raises(rp.PromotionError):
        _promote(monkeypatch, static=False)


# ── ③ 실패는 상태를 건드리지 않는다 ─────────────────────────────────────
@pytest.mark.parametrize("kw", [{"contract": False}, {"static": False}])
def test_a_failed_promotion_changes_nothing(monkeypatch, kw):
    """★★★ 실패해도 **이전 ACTIVE 는 그대로다.**

    ⚠️ 실패가 상태를 건드리면 승격을 시도하는 것 자체가 위험한 일이 되고, 그러면
      아무도 안 한다."""
    _ok_checks(monkeypatch, **kw)
    lc = _Lifecycle()
    with pytest.raises(rp.PromotionError):
        rp.promote(release=_release(), release_id="rel_1", lifecycle=lc, actor="u@x",
                   code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)
    assert lc.calls == [], "실패했는데 상태를 바꿨다"
    assert lc._status == CANDIDATE


def test_a_successful_promotion_moves_to_active(monkeypatch):
    """⚠️ 대조군 — 위 시험들이 「전부 막힘」으로도 통과하지 않게 한다."""
    lc, out = _promote(monkeypatch)
    assert out["status"] == ACTIVE
    assert len(lc.calls) == 1 and lc.calls[0][1] == ACTIVE
    assert lc.calls[0][2] == "u@x", "누가 올렸는지 남지 않았다"


def test_promotion_without_an_actor_is_refused(monkeypatch):
    """⚠️ 누가 운영으로 올렸는지 모르는 승격은 감사 대상이 될 수 없다."""
    _ok_checks(monkeypatch)
    with pytest.raises(rp.PromotionError) as e:
        rp.promote(release=_release(), release_id="rel_1", lifecycle=_Lifecycle(),
                   actor="  ", code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)
    assert "식별" in str(e.value)


def test_a_missing_actor_is_checked_before_anything_else(monkeypatch):
    """★ 행위자 없는 요청은 **검사를 돌리기도 전에** 막는다 — 검사가 부수효과를 낼
    수 있고, 누가 시켰는지 모르는 채로 그것을 하면 안 된다."""
    _ok_checks(monkeypatch)
    lc = _Lifecycle()
    with pytest.raises(rp.PromotionError):
        rp.promote(release=_release(), release_id="rel_1", lifecycle=lc, actor="",
                   code_paths=["x"], readiness_state=rp.NOT_APPLICABLE)
    assert lc.calls == []


# ── ④ 보지 못한 것은 통과가 아니다 ──────────────────────────────────────
@pytest.mark.parametrize("paths", [None, [], ()])
def test_no_code_to_scan_is_not_a_pass(paths):
    """★★★ 「볼 것이 없었다」와 「봤는데 깨끗했다」는 **다른 사실**이다.

    ⚠️ 전자를 통과로 읽으면 이 게이트는 장식이 된다."""
    c = rp._check_static(paths)
    assert not c.ok and "보지 못한" in c.reason


def test_an_unknown_readiness_is_not_a_pass():
    """★★★ 확인하지 못한 것을 «준비됨» 으로 세지 않는다."""
    c = rp._check_readiness(None)
    assert not c.ok


def test_not_applicable_is_different_from_unknown():
    """★★★ 「이 앱은 업무 데이터를 안 쓴다」와 「확인하지 못했다」는 다르다.

    ⚠️ 같은 값(`None`)으로 두면 확인 실패가 조용히 면제가 된다."""
    assert rp._check_readiness(rp.NOT_APPLICABLE).ok is True
    assert rp._check_readiness(None).ok is False
    assert rp.NOT_APPLICABLE is not None


@pytest.mark.parametrize("status", ["PARTIAL", "BLOCKED", "", "아무거나"])
def test_an_unready_dataset_blocks_promotion(status):
    """⚠️ 준비되지 않은 데이터 위에 운영 앱을 올리면 첫날부터 「읽을 수 없음」을
    그리고, 사용자는 앱이 고장 났다고 본다 — 원인은 데이터인데."""
    c = rp._check_readiness({"status": status, "blocked_outputs": []})
    assert not c.ok


def test_a_ready_dataset_passes():
    """⚠️ 대조군."""
    assert rp._check_readiness({"status": "READY"}).ok


# ── 계약 승인 — 레거시 면제를 쓰지 않는다 ───────────────────────────────
def test_an_executable_app_without_an_approved_contract_cannot_be_promoted():
    """★★★ 레거시 면제는 **이미 도는 판을 지키기 위한 것**이지 새로 올리기 위한
    것이 아니다."""
    rel = _release(artifact_kind="APP", requires_host_runtime=True)
    c = rp._check_review(rel)
    assert not c.ok and "레거시 면제" in c.reason


def test_an_unapproved_contract_cannot_be_promoted():
    rel = _release(artifact_kind="APP", requires_host_runtime=True,
                   runtime_contract={"approval": {"status": "PENDING"}})
    assert not rp._check_review(rel).ok


def test_a_non_executable_artifact_needs_no_contract():
    """⚠️ 대조군 — 보고서·문서는 계약을 지날 일이 없다."""
    assert rp._check_review(_release()).ok


# ── 운영 경로가 실제로 후보를 만드는가 ──────────────────────────────────
#
# ★★★ F-0·F-1 에서 두 번 반복된 함정 — 통제는 만들었는데 그것을 부르는 운영 경로가
#   없는 상태. 여기서 **게시가 후보를 만든다**는 것을 배선 수준에서 못 박는다.
import api.routes.factory_control as fc                              # noqa: E402


def test_the_publish_path_records_the_candidate_state():
    """★★★ 게시가 `CANDIDATE` 를 **기록한다.**

    ⚠️ 이것이 없으면 Preview 청중은 운영에서 한 번도 발급되지 않는다(F-1 이 그 상태
      였고, 변이 검사가 7건을 놓쳐서야 드러났다)."""
    import inspect

    src = inspect.getsource(fc.create_release)
    assert "CANDIDATE" in src, "게시가 후보 상태를 기록하지 않는다"
    assert "set_status(" in src
    assert "lifecycle_state" in src, "결과를 릴리스에 남기지 않는다"


def test_the_promotion_route_exists_and_is_the_only_way_up():
    """★★★ 승격 라우트가 있고, **목적지가 하나**다.

    ⚠️ 요청이 `status` 를 고르게 하면 「후보로 되돌리기」·「폐기」가 같은 문으로
      들어오고, 그 문에는 승격용 검사만 걸려 있다."""
    assert set(fc.PromoteRequest.model_fields) == {"reason", "no_business_data"}

    import inspect

    src = inspect.getsource(fc.promote_release)
    assert "release_promotion.promote(" in src
    assert "409" in src, "상태 불일치를 409 로 답하지 않는다"


def test_the_dry_run_route_uses_the_same_checks():
    """⚠️ 미리보기 검사와 실제 검사가 다르면 「눌러 보니 다른 이유로 막혔다」가 된다."""
    import inspect

    assert "run_checks(" in inspect.getsource(fc.promotion_check)


def test_publish_and_promote_landed_in_the_same_commit():
    """★★★ 게시 기본값 전환과 승격 경로는 **한 커밋**이어야 한다.

    ⚠️ 나누면 그 사이에 만들어진 릴리스가 전부 후보로 갇히고, 올릴 방법이 없다.
    ★ 여기서는 «둘 다 존재하는가» 로 그 규칙을 지킨다 — 하나만 있는 상태로는 이
      시험이 빨갛다."""
    assert hasattr(fc, "promote_release"), "게시만 바꾸고 승격 경로가 없다"
    import inspect

    assert "CANDIDATE" in inspect.getsource(fc.create_release), \
        "승격 경로만 있고 게시가 후보를 안 만든다"


# ── 진짜 구현을 태운다 ──────────────────────────────────────────────────
#
# ⚠️⚠️ [변이 검사 실측] 위 시험들은 `_ok_checks()` 로 `_check_contract`·`_check_static`
#   을 **통째로 스텁으로 덮고** 있었다. 그래서 그 두 함수의 진짜 구현이 한 번도
#   실행되지 않았고, 변이 5건이 살아남았다.
#
# ★ F-1 의 「격리 스텁이 막는 함수의 성질을 없앴다」와 **같은 병**이다 — 이번엔
#   시험 헬퍼가 범인이었다. 스텁은 «관심 없는 것» 을 덮는 도구이지 «검사 대상» 을
#   덮는 도구가 아니다.
def test_the_contract_check_actually_reads_the_gate(monkeypatch):
    """★★★ `_check_contract` 의 **진짜 구현**을 태운다."""
    from core import app_contract_gate

    monkeypatch.setattr(app_contract_gate, "evaluate",
                        lambda release, rid, plane=None: app_contract_gate.GateVerdict(
                            ok=False, reasons=["계약에 없는 결속이 있습니다: ['x']"]))
    c = rp._check_contract(_release(), "rel_1")
    assert not c.ok
    assert "계약에 없는 결속" in c.reason, "게이트 사유가 전달되지 않았다"


def test_a_gate_that_raises_is_not_a_pass(monkeypatch):
    """★★★ 「판정할 수 없었다」를 통과로 세면 게이트가 장식이 된다."""
    from core import app_contract_gate

    def _boom(release, rid, plane=None):
        raise RuntimeError("결속 표를 읽을 수 없습니다")

    monkeypatch.setattr(app_contract_gate, "evaluate", _boom)
    c = rp._check_contract(_release(), "rel_1")
    assert not c.ok and "판정할 수 없습니다" in c.reason


def test_a_clean_gate_passes(monkeypatch):
    """⚠️ 대조군 — 위 둘이 「전부 막힘」으로도 통과하지 않게 한다."""
    from core import app_contract_gate

    monkeypatch.setattr(app_contract_gate, "evaluate",
                        lambda release, rid, plane=None:
                            app_contract_gate.GateVerdict(ok=True))
    assert rp._check_contract(_release(), "rel_1").ok


def test_the_static_check_actually_scans(tmp_path):
    """★★★ `_check_static` 의 **진짜 구현**을 태운다 — 실제 파일을 훑는다."""
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    assert rp._check_static([str(clean)]).ok, "깨끗한 코드가 막혔다"


def test_a_blocking_signal_in_the_code_stops_promotion(tmp_path):
    """⚠️ 생성 코드가 플랫폼 인증을 **직접** 만지면 올리지 않는다."""
    from nodes.utils import platform_auth_checker as checker

    bad = tmp_path / "bad"
    bad.mkdir()
    #: 검사기가 실제로 차단하는 본문을 만든다 — 지어내지 않고 검사기에게 물어본다
    sample = 'fetch("/api/v1/auth/login", {method: "POST"})'
    if not [f for f in checker.scan_text(sample, path="x.js")
            if f["severity"] == "block"]:
        pytest.skip("검사기의 차단 신호 예시가 바뀌었다 — 시험을 갱신해야 한다")
    (bad / "app.js").write_text(sample, encoding="utf-8")

    c = rp._check_static([str(bad)])
    assert not c.ok and "차단 신호" in c.reason


def test_an_unreadable_file_is_not_a_pass(tmp_path, monkeypatch):
    """★★★ 「읽지 못했다」와 「읽었는데 깨끗했다」는 **다른 사실**이다."""
    from nodes.utils import platform_auth_checker as checker

    monkeypatch.setattr(checker, "scan_paths",
                        lambda paths: {"ok": True, "unreadable": ["x.js"],
                                       "blocking": [], "warnings": [], "scanned": 0})
    c = rp._check_static(["x"])
    assert not c.ok and "읽지 못한" in c.reason


def test_a_scanner_that_raises_is_not_a_pass(monkeypatch):
    from nodes.utils import platform_auth_checker as checker

    def _boom(paths):
        raise RuntimeError("검사기가 죽었다")

    monkeypatch.setattr(checker, "scan_paths", _boom)
    c = rp._check_static(["x"])
    assert not c.ok and "검사할 수 없습니다" in c.reason


def test_an_unknown_readiness_says_it_could_not_check(monkeypatch):
    """★★★ **사유까지 본다.**

    ⚠️ [변이 검사 실측] `assert not c.ok` 만 보면 「확인 못함」 분기를 지워도 그
      아래 「준비 안 됨」 분기가 잡아서 통과한다 — 막히긴 하지만 **사유가 틀린다.**
      사용자는 데이터를 준비하러 가는데, 실제 문제는 확인 자체가 안 된 것이다."""
    c = rp._check_readiness(None)
    assert not c.ok
    assert "확인하지 못했습니다" in c.reason, c.reason
    assert "아직 준비되지 않았습니다" not in c.reason, "확인 실패가 «미준비» 로 답해졌다"


# ── 승격 라우트를 **실제 라우터로** 태운다 ──────────────────────────────
#
# ⚠️⚠️ 위의 `inspect.getsource` 시험들은 **문자열 존재**만 본다. 게이트를 건너뛰는
#   변이가 그대로 살아남았다(실측). 여기서는 진짜 요청을 보낸다.
import json                                                          # noqa: E402


@pytest.fixture
def promo(monkeypatch, tmp_path):
    """실제 앱 + 후보 릴리스 하나."""
    import config
    import core.library_paths as library_paths
    from core.org_directory import org_directory
    from core.program_lifecycle import program_lifecycle

    lib = tmp_path / "library"
    (lib / "rel_p").mkdir(parents=True)
    (lib / "rel_p" / "release.json").write_text(json.dumps({
        "release_id": "rel_p", "project_id": "P1", "tenant_id": "tenant_default",
        "entity_mode": "REAL", "enterprise_scope_id": "node_hq",
        "owner_dept_id": "hq", "visibility": "dept",
        "artifact_kind": "REPORT", "requires_host_runtime": False,
    }, ensure_ascii=False), encoding="utf-8")
    #: 정적 검사가 볼 파일 하나 — «볼 것이 없으면 차단» 이므로 반드시 있어야 한다
    (lib / "rel_p" / "app.js").write_text("export const x = 1;\n", encoding="utf-8")

    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", False, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(program_lifecycle, "db_path",
                        str(tmp_path / "lifecycle.db"), raising=False)
    monkeypatch.setattr(program_lifecycle, "_release_exists", lambda rid: True,
                        raising=False)
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: True)
    program_lifecycle.set_status("rel_p", CANDIDATE, actor="u@x", reason="시험용 후보")

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


H = {"X-Factory-User": "u@x"}
URL = "/api/v1/factory/P1/releases/rel_p"


def test_the_route_actually_runs_the_gate(promo, monkeypatch):
    """★★★ 게이트가 막으면 **라우트도 막힌다.**

    ⚠️ 소스 문자열 검사로는 「게이트를 부르는 척하고 건너뛰는」 변이를 못 잡는다."""
    monkeypatch.setattr(rp, "run_checks",
                        lambda **kw: rp.Verdict(
                            ok=False, checks=[rp.Check(rp.CHECK_STATE, False, "막힘")]))
    r = promo.post(URL + "/promote", json={"no_business_data": True}, headers=H)
    assert r.status_code == 409, r.text
    assert "막힘" in r.text


def test_a_release_that_passes_is_promoted(promo):
    """⚠️ 대조군 — 위 시험이 「전부 409」로도 통과하지 않게 한다."""
    from core.program_lifecycle import ACTIVE, program_lifecycle

    r = promo.post(URL + "/promote", json={"no_business_data": True}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == ACTIVE
    assert program_lifecycle.get_status("rel_p")["status"] == ACTIVE


def test_promoting_twice_is_refused(promo):
    """★★★ 이미 운영인 판을 또 올리면 이력이 흐려진다."""
    assert promo.post(URL + "/promote", json={"no_business_data": True},
                      headers=H).status_code == 200
    again = promo.post(URL + "/promote", json={"no_business_data": True}, headers=H)
    assert again.status_code == 409, again.text


def test_the_dry_run_does_not_change_anything(promo):
    """★★★ 사전 확인은 **바꾸지 않고** 본다."""
    from core.program_lifecycle import program_lifecycle

    r = promo.get(URL + "/promotion-check", params={"no_business_data": True}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["ok"] is True
    assert program_lifecycle.get_status("rel_p")["status"] == CANDIDATE, \
        "사전 확인이 상태를 바꿨다"


def test_the_dry_run_uses_the_same_verdict_as_the_real_thing(promo, monkeypatch):
    """★★★ 미리보기 검사와 실제 검사가 다르면 「눌러 보니 다른 이유로 막혔다」가 된다.

    ⚠️ 소스에 `run_checks(` 가 적혀 있는지만 봐서는 **다른 값으로 덮는** 변이를 못
      잡는다 — 실제로 그 변이가 살아남았다."""
    monkeypatch.setattr(rp, "run_checks",
                        lambda **kw: rp.Verdict(
                            ok=False, checks=[rp.Check(rp.CHECK_STATIC, False, "차단됨")]))
    r = promo.get(URL + "/promotion-check", params={"no_business_data": True}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["ok"] is False, "사전 확인이 게이트를 안 쓴다"
    assert "차단됨" in r.text


def test_business_data_must_be_declared_not_assumed(promo):
    """★★★ `no_business_data` 를 안 적으면 **확인하지 못한 것**이고, 그것은 통과가 아니다.

    ⚠️ 이 릴리스에는 물질화 기록이 없다 — 그러면 준비도는 `None`(확인 못함)이다."""
    r = promo.post(URL + "/promote", json={}, headers=H)
    assert r.status_code == 409, r.text
    assert "확인하지 못했습니다" in r.text


def test_another_projects_release_is_not_promotable(promo):
    """⚠️ 경로만으로 남의 판을 올리지 못한다."""
    r = promo.post("/api/v1/factory/P_other/releases/rel_p/promote",
                   json={"no_business_data": True}, headers=H)
    assert r.status_code == 404, r.text
