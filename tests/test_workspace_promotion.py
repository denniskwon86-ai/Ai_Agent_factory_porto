# ==========================================
# [§9 / §14 M3] 부서 워크스페이스 — 공유 · 복제 · 승격 게이트
#
# §9.3: "부서 앱을 전사 앱으로 승격할 때 **데이터 계약·보안·품질·소유자 승인**을 요구한다."
# 이 게이트는 체크박스가 아니라 **실제 조회**여야 한다. 사람이 "확인했음"에 체크하는 게이트는
# 아무것도 막지 못한다. 그래서 테스트의 대부분이 "이 승격은 거절되는가"를 본다.
#
#   ① 어떤 자산을 쓰는지 모르면 unverifiable — 모르는 것을 안전으로 치지 않는다
#   ② 계약 위반·확인 불가 → 차단
#   ③ 전사 승격에 민감도·PII → 차단
#   ④ 품질 기록 없음 → 차단 (프로젝트를 릴리스 id 에서 추론하지 않는다)
#   ⑤ 데이터 오너 승인 없음 → 차단
#   ⑥ 강제 승격 우회로가 없다
#   ⑦ 공유는 승격이 아니다 / 복제는 계보를 남긴다
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_catalog import DataCatalog
from core.data_contract import DataContracts
from core.data_lineage import DataLineage
from core.master_data import MasterData
from core.workspace_promotion import WorkspaceError, WorkspacePromotion

REL = "app_qc_20260729_120000"
DEPT, OTHER = "node_batt", "node_copper"


@pytest.fixture
def env(tmp_path):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    ws = WorkspacePromotion(db_path=str(tmp_path / "ws.db"))
    return ws, DataCatalog(md), DataContracts(md), DataLineage(md)


def _gate(ws, cat, dc, lin, **kw):
    return ws.evaluate_gate(REL, "enterprise", catalog=cat, contracts=dc, lineage=lin, **kw)


def _state(gate, name):
    return next(c["state"] for c in gate["checks"] if c["check"] == name)


# ── ⑦ 공유는 승격이 아니다 ───────────────────────────────────────────────
def test_share_grants_access_without_promoting(env):
    """★★ 공유와 승격을 한 동작으로 묶으면 '잠깐 보여주려던 것'이 전사 자산이 된다."""
    ws, *_ = env
    ws.share(REL, DEPT, OTHER, "kim", reason="협업")
    assert ws.can_access(REL, OTHER)["allowed"] is True
    assert ws.get_promotion(REL) is None, "공유가 승격 상태를 만들면 안 된다"


def test_non_shared_scope_cannot_access(env):
    ws, *_ = env
    assert ws.can_access(REL, OTHER, owner_scope=DEPT)["allowed"] is False
    assert ws.can_access(REL, DEPT, owner_scope=DEPT)["via"] == "owner"


def test_share_to_self_is_rejected(env):
    ws, *_ = env
    with pytest.raises(WorkspaceError):
        ws.share(REL, DEPT, DEPT, "kim")


def test_revoke_is_soft(env):
    """누가 언제 무엇을 봤나가 감사 대상이라 물리 삭제하지 않는다."""
    ws, *_ = env
    s = ws.share(REL, DEPT, OTHER, "kim")
    assert ws.revoke_share(s["share_id"]) is True
    assert ws.can_access(REL, OTHER)["allowed"] is False
    assert ws.list_shares(release_id=REL, include_revoked=True)


# ── ⑦ 복제는 계보를 남긴다 ───────────────────────────────────────────────
def test_fork_records_lineage(env):
    """★★ 포크가 원본과 무관해지면 원본 기준이 바뀔 때 무엇이 영향받는지 알 수 없다."""
    ws, _cat, _dc, lin = env
    out = ws.fork(REL, "qc_batt_v2", DEPT, "kim", lineage=lin)
    assert out["lineage_edge_id"]
    imp = lin.impact_of("release", REL)
    assert any(n["node_id"] == "qc_batt_v2" for n in imp["impacted"])
    assert ws.list_forks(REL)[0]["new_project_id"] == "qc_batt_v2"


# ── ① 자산 연결을 모르면 안전이 아니다 ───────────────────────────────────
def test_unknown_assets_block_the_gate(env):
    """★★ 모르는 것을 안전으로 치면 게이트가 장식이 된다."""
    ws, cat, dc, lin = env
    g = _gate(ws, cat, dc, lin)
    assert _state(g, "asset_linkage") == "unverifiable"
    assert _state(g, "data_contract") == "unverifiable"
    assert _state(g, "security") == "unverifiable"
    assert g["promotable"] is False


def test_unverifiable_is_not_a_pass(env):
    """★★ 이 저장소의 관통 원칙. 승격은 되돌리기 가장 어려운 행위다."""
    ws, cat, dc, lin = env
    g = _gate(ws, cat, dc, lin)
    assert g["failed"] or g["unverifiable"]
    assert g["promotable"] is False
    assert "통과가 아니라" in g["note"]


# ── ② 데이터 계약 ────────────────────────────────────────────────────────
def _linked_asset(cat, lin, **kw):
    a = cat.create_asset(kw.pop("name", "QC 실적"), owner_dept_id="p",
                         refresh_cadence="daily", **kw)
    lin.add_edge("asset", a["asset_id"], "release", REL, "feeds", origin="user")
    return a


def test_breached_contract_blocks(env):
    ws, cat, dc, lin = env
    a = _linked_asset(cat, lin)
    c = dc.create(name="QC 공급", producer_asset_id=a["asset_id"], consumer="app",
                  schema={"fields": [{"name": "없는필드"}]}, catalog=cat)
    dc.activate(c["contract_id"], "kim", catalog=cat, allow_breached=True)
    g = _gate(ws, cat, dc, lin)
    assert _state(g, "data_contract") == "fail" and g["promotable"] is False


def test_no_contract_is_unverifiable_not_pass(env):
    """★ 전사 승격은 소비자와의 약속을 전제로 한다 — 계약이 없으면 통과가 아니다."""
    ws, cat, dc, lin = env
    _linked_asset(cat, lin)
    assert _state(_gate(ws, cat, dc, lin), "data_contract") == "unverifiable"


def test_kept_contract_passes(env):
    ws, cat, dc, lin = env
    a = _linked_asset(cat, lin)
    cat.upsert_field(a["asset_id"], "qty", logical_type="int")
    cat.record_quality_profile(a["asset_id"], method="measured", completeness=0.99,
                               evidence_ref="run1")
    cat.update_asset(a["asset_id"], last_refreshed_at="2026-07-29T09:00:00+00:00")
    c = dc.create(name="QC 공급", producer_asset_id=a["asset_id"], consumer="app",
                  schema={"fields": [{"name": "qty", "type": "int"}]}, catalog=cat)
    dc.activate(c["contract_id"], "kim", catalog=cat)
    assert _state(_gate(ws, cat, dc, lin), "data_contract") == "pass"


# ── ③ 보안 ───────────────────────────────────────────────────────────────
def test_confidential_asset_blocks_enterprise_promotion(env):
    """★★ 전사에 한 번 열면 되돌릴 수 없다."""
    ws, cat, dc, lin = env
    _linked_asset(cat, lin, sensitivity="confidential")
    g = _gate(ws, cat, dc, lin)
    assert _state(g, "security") == "fail"
    assert "되돌릴 수 없" in next(c["suggested_action"] for c in g["checks"]
                              if c["check"] == "security")


def test_pii_field_blocks_enterprise_promotion(env):
    ws, cat, dc, lin = env
    a = _linked_asset(cat, lin)
    cat.upsert_field(a["asset_id"], "worker_name", pii_classification="pii")
    assert _state(_gate(ws, cat, dc, lin), "security") == "fail"


def test_internal_asset_without_pii_passes_security(env):
    ws, cat, dc, lin = env
    a = _linked_asset(cat, lin, sensitivity="internal")
    cat.upsert_field(a["asset_id"], "qty", logical_type="int")
    assert _state(_gate(ws, cat, dc, lin), "security") == "pass"


# ── ④ 품질 ───────────────────────────────────────────────────────────────
def test_missing_project_id_is_unverifiable_not_guessed(env):
    """★★ 릴리스 id 에서 프로젝트명을 추론하면 명명 규칙이 바뀔 때 **조용히 틀린다.**"""
    ws, cat, dc, lin = env
    g = _gate(ws, cat, dc, lin)                      # project_id 미지정
    assert _state(g, "quality") == "unverifiable"
    why = next(c["why"] for c in g["checks"] if c["check"] == "quality")
    assert "project_id" in why


def test_no_quality_record_blocks(env):
    ws, cat, dc, lin = env
    g = _gate(ws, cat, dc, lin, project_id="app_qc")
    assert _state(g, "quality") == "unverifiable"


# ── ⑤ 소유자 승인 ────────────────────────────────────────────────────────
def test_owner_approval_is_required(env):
    ws, cat, dc, lin = env
    assert _state(_gate(ws, cat, dc, lin), "data_owner_approval") == "fail"

    ws.request_promotion(REL, DEPT, "kim", project_id="app_qc")
    ws.owner_approve(REL, "data_owner_lee")
    assert _state(_gate(ws, cat, dc, lin), "data_owner_approval") == "pass"


def test_owner_approval_requires_identity(env):
    ws, *_ = env
    ws.request_promotion(REL, DEPT, "kim")
    with pytest.raises(WorkspaceError):
        ws.owner_approve(REL, "")


def test_owner_approve_without_request_is_rejected(env):
    ws, *_ = env
    with pytest.raises(WorkspaceError):
        ws.owner_approve(REL, "lee")


def test_rejection_requires_a_reason(env):
    """사유 없는 반려는 신청자가 무엇을 고쳐야 할지 알 수 없다."""
    ws, *_ = env
    ws.request_promotion(REL, DEPT, "kim")
    with pytest.raises(WorkspaceError):
        ws.reject_promotion(REL, "lee", "")
    out = ws.reject_promotion(REL, "lee", "PII 정리 후 재신청")
    assert out["status"] == "rejected" and "PII" in out["rejected_reason"]


# ── ⑥ 강제 승격 우회로가 없다 ────────────────────────────────────────────
def test_promotion_is_blocked_until_every_check_passes(env):
    """★★ Shadow Mode 의 allow_breached 와 다른 판단 — 여기서는 되돌릴 수 없다."""
    ws, cat, dc, lin = env
    ws.request_promotion(REL, DEPT, "kim", project_id="app_qc")
    ws.owner_approve(REL, "lee")
    with pytest.raises(WorkspaceError) as e:
        ws.promote(REL, "kim", catalog=cat, contracts=dc, lineage=lin)
    assert "게이트를 통과하지 못했습니다" in str(e.value)
    assert "확인하지 못한 항목도 통과가 아닙니다" in str(e.value)


def test_cannot_promote_rejected(env):
    ws, cat, dc, lin = env
    ws.request_promotion(REL, DEPT, "kim")
    ws.reject_promotion(REL, "lee", "보류")
    with pytest.raises(WorkspaceError):
        ws.promote(REL, "kim", catalog=cat, contracts=dc, lineage=lin)


def test_cannot_promote_without_request(env):
    ws, cat, dc, lin = env
    with pytest.raises(WorkspaceError):
        ws.promote(REL, "kim", catalog=cat, contracts=dc, lineage=lin)


# ── 반려(아직 안 올라감) vs 철회(올라갔다가 내려옴) ──────────────────────
def test_reject_and_revoke_are_different_doors(env):
    """★★ 한 함수로 뭉개면 둘 중 하나가 반드시 막힌다 — 실제로 롤백이 승격을 철회할 수
    없었다(`reject_promotion` 이 `status<>'promoted'` 로 막아서)."""
    ws, cat, dc, lin = env
    ws.request_promotion(REL, DEPT, "kim", project_id="app_qc")
    # 승격 전에는 철회할 수 없다 — 올라간 적이 없다
    with pytest.raises(WorkspaceError) as e:
        ws.revoke_promotion(REL, "lee", "사유")
    assert "승격 상태가 아닙니다" in str(e.value)
    assert "reject_promotion" in str(e.value), "올바른 문을 알려줘야 한다"


def test_revoke_requires_actor_and_reason(env):
    ws, *_ = env
    with pytest.raises(WorkspaceError):
        ws.revoke_promotion(REL, "", "사유")
    with pytest.raises(WorkspaceError):
        ws.revoke_promotion(REL, "lee", "")


def test_revoke_keeps_promotion_history(env):
    """★ 승격 이력을 지우지 않는다 — "전사에 열려 있던 기간"이 감사 대상이다."""
    ws, cat, dc, lin = env
    ws.request_promotion(REL, DEPT, "kim", project_id="app_qc")
    ws.owner_approve(REL, "lee")
    with ws._connect() as conn:
        conn.execute("UPDATE release_promotions SET status='promoted', promoted_by='park', "
                     "promoted_at='2026-07-29T00:00:00+00:00' WHERE release_id=?", (REL,))
    out = ws.revoke_promotion(REL, "choi", "결과 오류")
    assert out["status"] == "revoked"
    assert out["promoted_by"] == "park" and out["promoted_at"], "승격 이력이 남아야 한다"
    assert "철회 choi" in out["rejected_reason"]


def test_full_pass_promotes_and_snapshots_the_gate(env, monkeypatch, tmp_path):
    """★ 승격 시점의 게이트 판정을 **스냅샷**으로 남긴다 — 나중에 기준이 바뀌어도
    '그때 무엇을 근거로 승격했나'가 재현돼야 한다."""
    ws, cat, dc, lin = env
    a = _linked_asset(cat, lin, sensitivity="internal")
    cat.upsert_field(a["asset_id"], "qty", logical_type="int")
    cat.record_quality_profile(a["asset_id"], method="measured", completeness=0.99,
                               evidence_ref="r1")
    cat.update_asset(a["asset_id"], last_refreshed_at="2026-07-29T09:00:00+00:00")
    c = dc.create(name="QC 공급", producer_asset_id=a["asset_id"], consumer="app",
                  schema={"fields": [{"name": "qty", "type": "int"}]}, catalog=cat)
    dc.activate(c["contract_id"], "kim", catalog=cat)

    # 품질 게이트 통과 기록을 주입한다(실제 파이프라인 대신).
    from core import quality_telemetry as qt
    monkeypatch.setattr(qt, "_LOG_PATH", str(tmp_path / "q.jsonl"), raising=False)

    class _S:
        project_name = "app_qc"
        workspace_root = str(tmp_path)
    qt.record_gate(_S(), gate_name="QA", artifact_type="app", verdict="PASS", score=0.95)

    ws.request_promotion(REL, DEPT, "kim", project_id="app_qc")
    ws.owner_approve(REL, "lee")
    g = _gate(ws, cat, dc, lin, project_id="app_qc")
    assert g["promotable"] is True, g

    out = ws.promote(REL, "park", catalog=cat, contracts=dc, lineage=lin)
    assert out["status"] == "promoted" and out["promoted_by"] == "park"
    assert out["gate_snapshot"]["promotable"] is True
    assert out["gate_snapshot"]["linked_assets"] == [a["asset_id"]]
