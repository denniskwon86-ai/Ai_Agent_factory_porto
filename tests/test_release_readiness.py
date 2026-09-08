# ==========================================
# [§8.2 / §14 M3] 운영 준비 — 릴리스 체크리스트 · 롤백 · 변경 영향 분석
#
# 이 모듈이 지키는 것:
#   ① 확인하지 못한 것을 "준비됨"으로 두지 않는다 (unverifiable ≠ pass)
#   ② §8.2 판정을 다시 계산하지 않고 **읽는다** (두 곳에서 계산하면 어긋난다)
#   ③ Shadow Mode 는 실운영 연계형에만 요구한다 (전부에 요구하면 게이트가 형식이 된다)
#   ④ 롤백이 하지 못한 일을 했다고 하지 않는다 (배포된 코드는 되돌리지 못한다)
#   ⑤ 영향 분석은 승격 여부를 함께 본다 (파급 규모 오판 방지)
#   ⑥ 수용검수에서 "묻지 않은 것"을 승인으로 치지 않는다
# ==========================================
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_lineage import DataLineage
from core.master_data import MasterData
from core.release_readiness import ReadinessError, ReleaseReadiness
from core.workspace_promotion import WorkspacePromotion

REL = "ready_app_20260729_120000"
PROJ = "ready_app"


@pytest.fixture
def env(tmp_path, monkeypatch):
    # 라이브러리 경로는 단일 지점(`core/library_paths`)이다 — 여기 한 줄이 게시·운영준비·
    #   사용여부 세 모듈 전부를 tmp 로 돌린다. `raising=True`(기본)로 두어, 상수 이름이
    #   바뀌면 **조용히 실로그를 보는 대신 테스트가 즉시 실패**하게 한다.
    from core import library_paths
    lib = tmp_path / "library"
    lib.mkdir()
    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(lib))

    md = MasterData(db_path=str(tmp_path / "m.db"))
    ws = WorkspacePromotion(db_path=str(tmp_path / "ws.db"))
    rd = ReleaseReadiness(db_path=str(tmp_path / "ws.db"))

    import core.quality_telemetry as qt
    monkeypatch.setattr(qt, "_LOG_PATH", str(tmp_path / "q.jsonl"), raising=False)

    # [사용자 결정 2026-07-30] 롤백은 이제 프로그램을 실제로 비활성화한다. 그 경로도 위
    #   `library_paths` 패치를 따라오므로 여기서 따로 맞춰줄 것이 없다 — 모듈마다 경로를
    #   맞춰주던 코드가 있었다면, 그건 어긋남이 남아 있다는 신호다.
    return rd, ws, DataLineage(md), lib, qt, tmp_path


def _write_release(lib, complete=True, trace=True, rid=REL):
    d = lib / rid
    d.mkdir(exist_ok=True)
    body = {"release_id": rid, "project_id": PROJ, "project_name": PROJ}
    if complete:
        body.update({"prd_summary": "요구", "architecture_summary": "아키",
                     "tech_spec_summary": "명세", "frontend_code_summary": "코드"})
    if trace:
        body["traceability_summary"] = "REQ-1 ↔ FR-1"
    (d / "release.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return rid


def _step(cl, name):
    return next(s["state"] for s in cl["steps"] if s["step"] == name)


def _gate(qt, tmp_path, verdict="PASS", accepted=None):
    class _S:
        project_name = PROJ
        workspace_root = str(tmp_path)
    qt.record_gate(_S(), gate_name="QA", artifact_type="app", verdict=verdict, score=0.9)
    if accepted is not None:
        qt.record_human_decision(_S(), gate_name="QA", accepted=accepted)


# ── ① 확인 못 한 것은 준비됨이 아니다 ────────────────────────────────────
def test_missing_release_fails(env):
    rd, *_ = env
    cl = rd.checklist("no_such_release")
    assert _step(cl, "artifacts") == "fail" and cl["operations_ready"] is False


def test_incomplete_artifacts_fail(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib, complete=False)
    cl = rd.checklist(REL, PROJ)
    assert _step(cl, "artifacts") == "fail"


def test_missing_traceability_is_unverifiable_not_pass(env):
    """★ 추적성 없이는 '무엇을 구현했는지' 증명할 수 없다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib, trace=False)
    cl = rd.checklist(REL, PROJ)
    assert _step(cl, "traceability") == "unverifiable"
    assert cl["operations_ready"] is False


def test_unverifiable_blocks_readiness(env):
    """★★ 관통 원칙 — 기록이 없으면 준비됨이 아니다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    cl = rd.checklist(REL, PROJ)
    assert cl["unverifiable"] and cl["operations_ready"] is False
    assert "통과가 아니라" in cl["note"]


# ── ⑥ 수용검수: 묻지 않은 것 ≠ 승인 ──────────────────────────────────────
def test_no_human_decision_is_unverifiable(env):
    """★★ D-015 와 같은 원칙 — '안 물어봤다'와 '승인받았다'는 다른 사실이다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    _gate(qt, tp, "PASS")                     # 사람 판정 없이 게이트만 통과
    cl = rd.checklist(REL, PROJ)
    assert _step(cl, "tests") == "pass"
    assert _step(cl, "acceptance") == "unverifiable"
    why = next(s["why"] for s in cl["steps"] if s["step"] == "acceptance")
    assert "묻지 않은 것" in why


def test_revision_requested_only_fails_acceptance(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    _gate(qt, tp, "PASS", accepted=False)
    assert _step(rd.checklist(REL, PROJ), "acceptance") == "fail"


def test_accepted_passes(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    _gate(qt, tp, "PASS", accepted=True)
    cl = rd.checklist(REL, PROJ)
    assert _step(cl, "acceptance") == "pass" and _step(cl, "tests") == "pass"


def test_failed_gate_fails_tests(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    _gate(qt, tp, "ROLLBACK")
    assert _step(rd.checklist(REL, PROJ), "tests") == "fail"


# ── ③ Shadow Mode 는 실운영 연계형에만 ───────────────────────────────────
def test_shadow_not_required_by_default(env):
    """★★ 전부에 요구하면 게이트가 형식이 되고 사람들은 우회한다(§8.2)."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    assert _step(rd.checklist(REL, PROJ), "shadow_mode") == "not_required"


def test_shadow_required_for_live_integration(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    cl = rd.checklist(REL, PROJ, requires_live_integration=True)
    assert _step(cl, "shadow_mode") == "unverifiable"


def test_steps_follow_the_spec_chain_order(env):
    """★★ §8.2 의 체인은 **진행 순서**다. 검사 코드는 같은 원천을 쓰는 것끼리 묶여 있어
    추가 순서가 체인 순서와 어긋난다(테스트·수용검수가 한 블록) — 화면에 ⑤가 ④보다 먼저
    나오면 체인이 잘못된 것처럼 보인다. 상수를 선언만 하고 쓰지 않으면 없는 것과 같다."""
    from core.release_readiness import GATE_STEPS
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    _gate(qt, tp, "PASS", accepted=True)
    cl = rd.checklist(REL, PROJ)
    got = [s["step"] for s in cl["steps"]]
    assert got == [s for s in GATE_STEPS if s in got], f"체인 순서와 어긋남: {got}"
    assert got.index("permission_contract") < got.index("acceptance")


def test_not_required_does_not_block(env):
    """`not_required` 는 failed/unverifiable 어디에도 들어가지 않는다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    cl = rd.checklist(REL, PROJ)
    assert "shadow_mode" not in cl["failed"] and "shadow_mode" not in cl["unverifiable"]


# ── ② 판정을 다시 계산하지 않는다 ────────────────────────────────────────
def test_permission_contract_reuses_promotion_gate(env):
    """★ 같은 판정을 두 곳에서 계산하면 반드시 어긋난다 — §9.3 게이트를 읽는다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    calls = []

    class _Spy:
        def evaluate_gate(self, *a, **k):
            calls.append((a, k))
            return {"checks": [
                {"check": "data_contract", "state": "pass", "why": "ok"},
                {"check": "security", "state": "pass", "why": "ok"}]}

        def get_promotion(self, *a, **k):
            return None
    cl = rd.checklist(REL, PROJ, workspace_impl=_Spy())
    assert calls, "승격 게이트를 호출하지 않았다"
    assert _step(cl, "permission_contract") == "pass"


def test_release_approval_reads_promotion(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    assert _step(rd.checklist(REL, PROJ, workspace_impl=ws), "release_approval") == "unverifiable"
    ws.request_promotion(REL, "node_batt", "kim", project_id=PROJ)
    ws.owner_approve(REL, "lee")
    assert _step(rd.checklist(REL, PROJ, workspace_impl=ws), "release_approval") == "pass"


# ── ④ 롤백이 하지 못한 일을 했다고 하지 않는다 ───────────────────────────
def test_rollback_requires_actor_and_reason(env):
    rd, *_ = env
    with pytest.raises(ReadinessError):
        rd.rollback(REL, "", "사유")
    with pytest.raises(ReadinessError):
        rd.rollback(REL, "kim", "")


def test_rollback_disables_the_program_and_keeps_the_record(env):
    """★★ [사용자 결정 2026-07-30] 되돌리지는 못해도 **사용은 막을 수 있다.**

    삭제하지 않는 이유: 다른 사용자가 이 프로그램을 근거로 남긴 기록이 고아가 된다."""
    from core.program_lifecycle import ProgramLifecycleError, program_lifecycle
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    out = rd.rollback(REL, "kim", "결과 오류 발견", workspace_impl=ws)
    assert out["program_disabled"] is True, out.get("disable_error")
    assert out["revoked_promotion"] is False
    # 사용은 막히고, 기록은 남는다.
    with pytest.raises(ProgramLifecycleError):
        program_lifecycle.assert_usable(REL)
    assert program_lifecycle.get_status(REL)["reason"].startswith("롤백:")


def test_rollback_states_its_limitation(env):
    """★★ "롤백했다"가 실제보다 크게 읽히면 아무도 후속 조치를 하지 않는다.

    사용 중단까지 했더라도 **이미 실행 중인 인스턴스·외부 배포본**은 여전히 못 되돌린다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    out = rd.rollback(REL, "kim", "결과 오류 발견", workspace_impl=ws)
    assert "배포된 코드 자체를 되돌리지는" in out["limitation"]
    assert "삭제하지 않았습니다" in out["limitation"]


def test_rollback_reports_disable_failure_instead_of_claiming_success(env, monkeypatch):
    """★★ "롤백했는데 여전히 쓸 수 있다"가 최악이다 — 실패를 조용히 넘기지 않는다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)

    class _Broken:
        def get_status(self, *a, **k):
            return {'status': 'active'}

        def disable(self, *a, **k):
            raise RuntimeError("db locked")
    out = rd.rollback(REL, "kim", "결과 오류", workspace_impl=ws, lifecycle_impl=_Broken())
    assert out["program_disabled"] is False
    assert "db locked" in out["disable_error"]
    assert out['outcome'] == 'failed'
    assert '확인하지 못했습니다' in out['message']
    assert rd.rollback_history(REL)[0]['outcome'] == 'failed'


def test_rollback_revokes_promotion(env):
    """실제로 할 수 있는 것 — 전사 승격 철회."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    ws.request_promotion(REL, "node_batt", "kim", project_id=PROJ)
    ws.owner_approve(REL, "lee")
    # 게이트를 우회하지 않고 상태만 promoted 로 만든다(승격 경로는 별도 테스트가 검증).
    with ws._connect() as conn:
        conn.execute("UPDATE release_promotions SET status='promoted' WHERE release_id=?", (REL,))
    out = rd.rollback(REL, "park", "전사 배포 후 오류", workspace_impl=ws)
    assert out["revoked_promotion"] is True
    pr = ws.get_promotion(REL)
    # ★ `rejected`(아직 안 올라감)가 아니라 `revoked`(올라갔다가 내려옴)다. 두 상태를 같게
    #   두면 "전사에 열려 있던 기간이 있었다"는 사실이 사라진다.
    assert pr["status"] == "revoked"
    assert pr["promoted_by"] == "", "승격 경로를 안 탔으니 승격자는 비어 있다"
    assert "철회" in pr["rejected_reason"]
    assert "전사 승격 철회" in out["limitation"]


def test_rollback_to_unknown_release_is_rejected(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    with pytest.raises(ReadinessError):
        rd.rollback(REL, "kim", "사유", to_release_id="없는릴리스")


def test_rollback_history_is_kept(env):
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    rd.rollback(REL, "kim", "1차", workspace_impl=ws)
    rd.rollback(REL, "kim", "2차", workspace_impl=ws)
    h = rd.rollback_history(REL)
    assert len(h) == 2 and {x["reason"] for x in h} == {"1차", "2차"}


# ── ⑤ 영향 분석은 승격 여부를 함께 본다 ──────────────────────────────────
def test_change_impact_marks_enterprise_blast_radius(env):
    """★★ "3개 노드 영향"과 "전사 승격된 앱 2개 영향"은 완전히 다른 정보다."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    lin.add_edge("master", "RM-MHP-001", "asset", "da_x", "references")
    lin.add_edge("asset", "da_x", "release", REL, "feeds")

    imp = rd.change_impact("master", "RM-MHP-001", lineage=lin, workspace_impl=ws)
    assert imp["blast_radius"] == "department"
    assert [r["release_id"] for r in imp["releases"]] == [REL]
    assert imp["enterprise_releases"] == []

    ws.request_promotion(REL, "node_batt", "kim", project_id=PROJ)
    ws.owner_approve(REL, "lee")
    with ws._connect() as conn:
        conn.execute("UPDATE release_promotions SET status='promoted' WHERE release_id=?", (REL,))
    imp2 = rd.change_impact("master", "RM-MHP-001", lineage=lin, workspace_impl=ws)
    assert imp2["blast_radius"] == "enterprise"
    assert imp2["enterprise_releases"][0]["release_id"] == REL


def test_change_impact_of_unknown_node_is_none_not_safe(env):
    """★ 영향 0건이 안전을 뜻하지 않는다는 한계를 응답에 남긴다."""
    rd, ws, lin, lib, qt, tp = env
    imp = rd.change_impact("master", "NEVER-REGISTERED", lineage=lin, workspace_impl=ws)
    assert imp["blast_radius"] == "none" and imp["impacted_count"] == 0
    assert "안전을 뜻하지 않는다" in imp["limitation"]
    assert "사용 여부의 지표가 아닙니다" in imp["limitation"]


def test_change_impact_includes_forked_projects(env):
    """포크한 프로젝트도 영향 목록에 나와야 한다(§14 M3 영향 분석)."""
    rd, ws, lin, lib, qt, tp = env
    _write_release(lib)
    ws.fork(REL, "forked_proj", "node_copper", "kim", lineage=lin)
    lin.add_edge("master", "RM-X", "release", REL, "references")
    imp = rd.change_impact("master", "RM-X", lineage=lin, workspace_impl=ws)
    assert [p["project_id"] for p in imp["projects"]] == ["forked_proj"]
