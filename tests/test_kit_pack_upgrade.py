"""적용본 판본 업그레이드 — DP 고정 이력(`process_kit_instances`)과 cohort. 격리 runner 전용.

★ 같은 인스턴스 ID 를 유지한 채 새 판본에 고정한다. 원 링크(`kit_process_instances`)와 인스턴스 행은
  바꾸지 않고 `kit_process_instance_upgrades` 에 한 줄을 더한다(갱신·삭제·교체 금지).
합성 조직 문맥(`.invalid`)·tmp DB 만 쓴다. 팩 원본은 읽기만 한다.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.data_preparation import process_kit_instances as pki
from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle
from core.data_preparation.store import DataPreparationStore
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError

V110 = load_bundle(CANDIDATE_MANIFEST.parents[1] / "1.1.0" / "manifest.json")
V120 = load_bundle(CANDIDATE_MANIFEST)
ROOT, SCOPE, TENANT = "node_root_upgrade", "node_a_upgrade", "tenant_default"
ACTOR = "installer@upgrade.invalid"


@pytest.fixture
def store(tmp_path):
    selected = DataPreparationStore(str(tmp_path / "dp.db"))
    assert Path(selected.db_path).resolve().is_relative_to(tmp_path.resolve())
    return selected


def _installed(store):
    boundary = ProcessBoundary(tenant_id=TENANT, context_root_id=ROOT, entity_mode="REAL", scope_node_id=SCOPE)
    return pki.create_or_get(store, operation_id="install-v110", bundle=V110, boundary=boundary, actor=ACTOR)


def _upgrade(store, instance, *, operation_id="upgrade-v120", bundle=V120, expected_from=None):
    return pki.upgrade_or_get(store, operation_id=operation_id, instance_id=instance["instance_id"], bundle=bundle,
                              expected_from=expected_from or V110["artifact_digest"], actor=ACTOR)


def _row(conn, instance_id):
    return dict(conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (instance_id,)).fetchone())


def _history(store, instance_id):
    with store.transaction() as conn:
        return [p["artifact_digest"] for p in pki.pins(conn, _row(conn, instance_id))]


def _raw(store, sql, params=()):
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def test_upgrade_appends_history_and_keeps_the_instance_and_original_link(store):
    instance = _installed(store)
    before_row = _raw(store, "SELECT * FROM kit_instances")
    before_link = _raw(store, "SELECT * FROM kit_process_instances")
    upgraded = _upgrade(store, instance)
    assert upgraded["instance_id"] == instance["instance_id"] and upgraded["pinned_version"] == "1.2.0"
    assert _history(store, instance["instance_id"]) == [V110["artifact_digest"], V120["artifact_digest"]]
    #: 인스턴스 행·원 링크는 그대로다 — 설치 때 고정한 정체성이다.
    assert _raw(store, "SELECT * FROM kit_instances") == before_row
    assert _raw(store, "SELECT * FROM kit_process_instances") == before_link
    with store.transaction() as conn:
        row = _row(conn, instance["instance_id"])
        assert pki.pin_for(conn, row, V110["artifact_digest"])["identity"]["version"] == "1.1.0"
        assert pki.current_pin(conn, row)["identity"]["version"] == "1.2.0"


def test_the_pinned_contract_follows_the_current_pin(store):
    instance = _installed(store)
    with store.transaction() as conn:
        assert pki.pinned_dataset_contract(conn, _row(conn, instance["instance_id"]), "INV-01") is None
    _upgrade(store, instance)
    expected = next(c for c in V120["dataset_contracts"]["contracts"] if c["dataset_contract_key"] == "INV-01")
    with store.transaction() as conn:
        assert pki.pinned_dataset_contract(conn, _row(conn, instance["instance_id"]), "INV-01") == expected
    assert pki.profile_for_instance(store, _raw(store, "SELECT * FROM kit_instances")[0])["version"] == "1.2.0"


def test_the_same_operation_is_idempotent_but_a_target_is_pinned_once(store):
    instance = _installed(store)
    first = _upgrade(store, instance)
    assert _upgrade(store, instance) == first
    with pytest.raises(ProcessError) as caught:
        _upgrade(store, instance, operation_id="upgrade-again", expected_from=V120["artifact_digest"])
    assert caught.value.reason_code == "PROCESS_PACK_UPGRADE_INVALID"
    assert _history(store, instance["instance_id"]) == [V110["artifact_digest"], V120["artifact_digest"]]


def test_a_plan_reviewed_against_another_pin_is_refused(store):
    instance = _installed(store)
    with pytest.raises(ProcessError) as caught:
        _upgrade(store, instance, expected_from="0" * 64)
    assert caught.value.reason_code == "PROCESS_PACK_UPGRADE_CONFLICT"
    assert _history(store, instance["instance_id"]) == [V110["artifact_digest"]]


def test_there_is_no_downgrade(store):
    instance = _installed(store)
    _upgrade(store, instance)
    with pytest.raises(ProcessError) as caught:
        _upgrade(store, instance, operation_id="downgrade", bundle=V110, expected_from=V120["artifact_digest"])
    assert caught.value.reason_code == "PROCESS_PACK_UPGRADE_INVALID"


@pytest.mark.parametrize("statement", [
    "UPDATE kit_process_instance_upgrades SET actor='someone-else'",
    "DELETE FROM kit_process_instance_upgrades",
    "INSERT OR REPLACE INTO kit_process_instance_upgrades SELECT * FROM kit_process_instance_upgrades",
])
def test_the_upgrade_history_is_append_only(store, statement):
    _upgrade(store, _installed(store))
    with pytest.raises(sqlite3.IntegrityError, match="immutable process kit upgrade"):
        _raw(store, statement)


def test_a_broken_history_is_corruption_not_a_shorter_history(store):
    instance = _installed(store)
    _upgrade(store, instance)
    conn = sqlite3.connect(store.db_path)
    try:
        with conn:
            conn.execute("DROP TRIGGER kit_process_upgrade_immutable")
            conn.execute("UPDATE kit_process_instance_upgrades SET from_artifact_digest=?", ("f" * 64,))
    finally:
        conn.close()
    with pytest.raises(ProcessError) as caught:
        _history(store, instance["instance_id"])
    assert (caught.value.reason_code, caught.value.status_code) == ("PROCESS_INSTANCE_CONFLICT", 503)


def test_an_old_release_stays_verifiable_but_is_not_rebuilt_after_upgrade(store):
    """업그레이드 전에 고정된 릴리스는 이력으로 검증되고, 같은 ID 로 다시 만들면 명시적으로 멈춘다."""
    from core.studio_release_cohort import ReleaseCohortError, get_release_cohort, pin_release_cohort
    instance = _installed(store)
    context_key = {"tenant_id": TENANT, "context_root_id": ROOT, "entity_mode": "REAL", "scope_node_id": SCOPE}
    old = pin_release_cohort(store, release_id="kitapp_old_APP-03", instance_id=instance["instance_id"],
                             app_id="APP-03", context_key=context_key)
    assert old["artifact_digest"] == V110["artifact_digest"]
    _upgrade(store, instance)
    assert get_release_cohort(store, "kitapp_old_APP-03")["artifact_digest"] == V110["artifact_digest"]
    with pytest.raises(ReleaseCohortError) as caught:
        pin_release_cohort(store, release_id="kitapp_old_APP-03", instance_id=instance["instance_id"],
                           app_id="APP-03", context_key=context_key)
    assert caught.value.reason_code == "STUDIO_RELEASE_REBUILD_AFTER_UPGRADE_UNSUPPORTED"
    fresh = pin_release_cohort(store, release_id="kitapp_new_APP-03", instance_id=instance["instance_id"],
                               app_id="APP-03", context_key=context_key)
    assert fresh["artifact_digest"] == V120["artifact_digest"]
    assert json.loads(_raw(store, "SELECT identity_json FROM kit_process_release_cohorts WHERE release_id=?",
                           ("kitapp_old_APP-03",))[0]["identity_json"])["instance_id"] == instance["instance_id"]


def test_an_approved_but_not_yet_activated_version_is_told_apart_from_corruption(store):
    """[Codex §19.1] 승인판이 가리키는 더 높은 판본이 이력에 없으면 «활성화 대기» 다 — 손상이 아니다.
    같은 판본·낮은 판본·다른 키트는 대기로 보지 않는다(그건 대기가 아니라 어긋남이다)."""
    instance = _installed(store)
    other_kit = {**V120, "kit_id": "KIT-SOMETHING-ELSE"}
    with store.transaction() as conn:
        row = _row(conn, instance["instance_id"])
        assert pki.activation_pending(conn, row, V120) is True
        assert pki.activation_pending(conn, row, V110) is False
        assert pki.activation_pending(conn, row, other_kit) is False
    _upgrade(store, instance)
    with store.transaction() as conn:
        row = _row(conn, instance["instance_id"])
        assert pki.activation_pending(conn, row, V120) is False
        assert pki.activation_pending(conn, row, V110) is False


def test_each_version_of_an_app_gets_its_own_release_id(store):
    """[Codex §19.2] 설치 원 판본은 종전 ID(이미 게시된 릴리스의 ID 가 바뀌지 않는다), 업그레이드한 판본은
    번들 지문을 넣은 새 ID. 현재 활성 판본이 앱 진입의 ID 다. 이력에 없는 판본은 추측하지 않고 막는다."""
    from core import kit_app_builder as kb
    instance = _installed(store)
    iid = instance["instance_id"]
    legacy = f"kitapp_{iid}_APP-03"
    assert kb.release_id_for(iid, "APP-03") == legacy
    assert kb.release_id_for_version(store, instance, "APP-03", V110["artifact_digest"]) == legacy
    assert kb.current_release_id(store, iid, "APP-03") == legacy
    with pytest.raises(ProcessError):
        kb.release_id_for_version(store, instance, "APP-03", V120["artifact_digest"])
    _upgrade(store, instance)
    upgraded = kb.release_id_for_version(store, instance, "APP-03", V120["artifact_digest"])
    assert upgraded == f"{legacy}_{V120['artifact_digest'][:16]}" != legacy
    assert kb.current_release_id(store, iid, "APP-03") == upgraded
    assert kb.release_id_for_version(store, instance, "APP-03", V110["artifact_digest"]) == legacy
    with pytest.raises(kb.KitAppError):
        kb.release_id_for(iid, "APP-03", "not-a-digest")
