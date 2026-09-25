"""1.1.0 설치본 → 업그레이드(미리보기·명시 적용·승인) → 재인증 → 운영 조회. 격리 runner 전용.

실제 B2 설치 saga·ECM 승인(작성자·설치자·승인자 분리)·DP 고정 이력·B0 인증 관문·실제 Host 경로를 쓴다.
합성은 자료(키트 정본 샘플)뿐이고 조직은 `.invalid` 다.

★ «관문 이전의 서명» 은 지금 코드로는 만들 수 없다(관문이 막는다). 그래서 그 시점만 관문을
  끈 채 서명해 **재현**한다(`_before_the_gate`). 그 뒤 모든 단계는 실제 관문 아래에서 돈다.
"""
from __future__ import annotations

import pytest

from core.data_preparation import certification_subject as cs, models as m, snapshot_service as ss
from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle, pin_bundle
from tests import kit_samples, org_seed as org
from tests.test_b1_process_configuration import approval, proposal  # noqa: F401
from tests.test_b2_installation import _apply, _plan, _prepared, _read, _resume, _start
from tests.test_b3_kit_contract_v2 import (DATA_KEYS, TEMPLATES, database, enforced_org, installation,  # noqa: F401
    sample_certified, workspace)
from tests.test_b3_process_context import build as process_build
from tests.test_r01_app03_real_host_path import RUNTIME, KEY, _ok, _operate, app_fields, host_session, isolate_host

V110 = load_bundle(CANDIDATE_MANIFEST.parents[1] / "1.1.0" / "manifest.json")
V120 = load_bundle(CANDIDATE_MANIFEST)
KITS = ["BK-03", "BK-04"]


def _pins(w):
    from core.data_preparation.process_kit_instances import pins
    with w["store"].transaction() as conn:
        row = dict(conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (w["instance_id"],)).fetchone())
        return [p["identity"]["version"] for p in pins(conn, row)]


def _sign(w, sid):
    args = dict(actor=org.MANAGER_A, context=w["context"], use_kind="OPERATIONAL",
                period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(w["store"], sid, **args)
    signed = cs.sign(w["store"], sid, **args, review_kind="DATA_OWNER",
                     reconciliation_evidence="합성 원천 총계와 재인증 판 대사 일치 확인", subject_id=preview["subject_id"],
                     expected_subject_digest=preview["digest"], client_request_id="recertify-" + sid)
    assert signed["certified"]
    return preview


def _blockers(fixed):
    return {b["reason_code"] for b in fixed["blockers"]}


@pytest.fixture
def upgraded(installation, monkeypatch, tmp_path):
    """1.1.0 실제 설치 → 관문 이전 서명(재현) → 사용자 수정 → 업그레이드 → 재인증. 단계마다 단언한다."""
    from core.data_preparation import certification_authority as ca
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_context import ProcessContextService
    isolated = isolate_host(monkeypatch, tmp_path)

    # ① 1.1.0 설치 — 실제 B2 saga(계획 → 시작 → 설치자 재개 → 별도 승인자).
    assert pin_bundle(installation["store"], V110)["artifact_digest"] == V110["artifact_digest"]
    w = {**installation, "bundle": V110}
    w["approved"] = _apply(w, _prepared(w, _plan(w, business_kit_ids=KITS)))
    doc = _read(w)["payload"]
    w.update(instance_id=doc["template_sources"][0]["kit_instance_ref"],
             ids={n["template_key"]: n["process_id"] for n in doc["nodes"]},
             ctx=ProcessContextService(w["svc"].repo, w["store"]))
    assert _pins(w) == ["1.1.0"]
    monkeypatch.setattr(decision_ledger, "db_path", str(w["root"] / "upgrade-ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    policy = {"required_reviews": {"OPERATIONAL": ["DATA_OWNER"], "MANAGEMENT": ["DATA_OWNER", "EXECUTIVE"]},
        "grants": {"DATA_OWNER": [{"dept_id": org.DEPT_A, "role": "manager", "scope_node_id": org.NODES[org.DEPT_A]}],
                   "EXECUTIVE": [{"dept_id": org.DEPT_ROOT, "role": "viewer", "scope_node_id": org.NODES[org.DEPT_ROOT]}]},
        "delegations": [], "allow_same_actor": False, "min_evidence_length": 10}
    ca.approve_policy(w["store"], tenant_id=w["context"]["tenant_id"], entity_mode="REAL",
        context_root_id=w["boundary"].context_root_id, actor=org.ADMIN,
        evidence_ref="test-only-upgrade-policy", document=policy)

    # ② 관문 이전의 서명(재현) — 그 시점 코드에는 계약 대조가 없었다.
    with monkeypatch.context() as before_the_gate:
        before_the_gate.setattr(cs, "_conforming_contract", lambda conn, row: "")
        old = {key: sample_certified(w, key) for key in DATA_KEYS}
    #: 운영은 막히고(고정 계약이 없다) 초안·열람은 된다 — 역사 조회와 운영 사용을 가른다.
    before = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "CONTRACT_NOT_PINNED" in _blockers(before)
    assert not {"GENERATE", "RUN", "RELEASE"} & set(before["permitted_actions"])
    assert {"READ", "DRAFT"} <= set(before["permitted_actions"])
    history = cs.read(w["store"], old[KEY]["snapshot_id"], actor=org.MANAGER_A, context=w["context"])
    assert history["review_status"] == "CERTIFIED"

    # ③ 사용자 수정 — 업그레이드가 지우면 안 된다.
    renamed = w["ids"]["inventory.availability"]
    w["approved"] = approval(w, proposal(w, [{"op": "RENAME", "process_id": renamed,
                                              "label": "현업 재고 확인(업그레이드 전 수정)"}], "rename-before-upgrade"))

    # ④ 업그레이드 미리보기 — 아무것도 바꾸지 않는다.
    head_before = _read(w)
    wv = {**w, "bundle": V120}
    planned = _plan(wv, business_kit_ids=KITS, instance_id=w["instance_id"],
                    upgrade_from_artifact_digest=V110["artifact_digest"],
                    reason="데이터셋 계약을 싣는 1.2.0 으로 같은 적용본을 올린다")
    summary = planned[1]["upgrade"]
    assert (summary["from"]["version"], summary["to"]["version"]) == ("1.1.0", "1.2.0")
    assert summary["process_ids_preserved"] is True and summary["templates_kept"] > 0
    assert summary["blueprint_suggestions_updated"] > 0 and summary["dataset_contracts"] == 35
    assert "RECERTIFICATION_REQUIRED" in planned[1]["warnings"]
    assert _pins(w) == ["1.1.0"] and _read(w)["head_version"] == head_before["head_version"]

    # ⑤ 명시 적용(설치자 재개) → 별도 승인자 승인.
    operation = _resume(wv, _start(wv, planned, key="upgrade-to-1.2.0"))
    assert operation["stage"] == "AWAITING_APPROVAL" and _pins(w) == ["1.1.0", "1.2.0"]
    w["approved"] = _apply(wv, operation)
    after = _read(w)["payload"]
    source = next(s for s in after["template_sources"] if s["kit_instance_ref"] == w["instance_id"])
    assert source["artifact_digest"] == V120["artifact_digest"] and source["kit_version"] == "1.2.0"
    assert source["template_process_ids"] == next(
        s for s in doc["template_sources"] if s["kit_instance_ref"] == w["instance_id"])["template_process_ids"]
    assert next(n for n in after["nodes"] if n["process_id"] == renamed)["label"] == "현업 재고 확인(업그레이드 전 수정)"
    #: 옛 서명은 이력으로 남고, 운영에는 재인증을 요구한다.
    stale = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "CERTIFICATION_RECERTIFICATION_REQUIRED" in _blockers(stale)
    assert not {"GENERATE", "RUN"} & set(stale["permitted_actions"])
    assert cs.read(w["store"], old[KEY]["snapshot_id"], actor=org.MANAGER_A,
                   context=w["context"])["review_status"] == "CERTIFIED"

    # ⑥ 재인증 — 같은 봉인 원문·같은 원천 합계로 새 판을 올리고 현재 고정 계약으로 서명한다.
    fresh = {}
    for key in DATA_KEYS:
        row = ss.reissue_for_recertification(w["store"], old[key]["snapshot_id"], workspace_root=kit_samples.raw_root(),
                                             created_by=org.MANAGER_A)
        assert row["state"] == m.RECONCILED and row["checksum"] == w["store"].get_snapshot(old[key]["snapshot_id"])["checksum"]
        subject = _sign(w, row["snapshot_id"])
        assert subject["payload"]["dataset_contract_digest"] == ca.digest(next(
            c for c in V120["dataset_contracts"]["contracts"] if c["dataset_contract_key"] == key))
        fresh[key] = {"binding": old[key]["binding"], "snapshot_id": row["snapshot_id"]}
    w.update(data=fresh, old=old)
    w["fixed"] = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "GENERATE" in w["fixed"]["permitted_actions"]
    refs = {ref["contract_key"]: ref["snapshot_id"] for ref in w["fixed"]["verified_binding_refs"]}
    assert refs == {key: fresh[key]["snapshot_id"] for key in DATA_KEYS}
    yield host_session(w, isolated)


def test_upgraded_and_recertified_install_reads_operationally(upgraded):
    """★★★ 끝 — 업그레이드·재인증한 같은 적용본으로 앱을 게시·승격하고 운영 조회한다."""
    from core import kit_app_builder as kb
    h = upgraded
    release_id, ds, headers, _ = _operate(h)
    assert release_id == kb.release_id_for(h["instance_id"], "APP-03")
    names = app_fields(KEY)
    source = [{k: v for k, v in row.items() if k in names}
              for row in kit_samples.sample_table(KEY, h["context"])[1]]
    served = _ok(h["client"].get(f"{RUNTIME}/datasets/{kb.runtime_name(KEY)}/records", headers=headers))
    assert [{k: str(v) for k, v in r["payload"].items()} for r in served["records"]] == source
    binding = h["operational"].binding_for(release_id, ds["dataset_id"])
    assert binding["enterprise_contract_key"] == KEY


def test_the_old_signature_stays_as_history_but_backs_no_operational_context(upgraded):
    """옛 서명은 그대로 남는다(판·서명·상태) — 다만 계약 지문이 없어 운영 문맥의 근거가 되지 않는다."""
    h = upgraded
    for key in DATA_KEYS:
        old_sid = h["old"][key]["snapshot_id"]
        assert h["store"].get_snapshot(old_sid)["state"] == m.OWNER_CERTIFIED
        assert cs.read(h["store"], old_sid, actor=org.MANAGER_A, context=h["context"])["review_status"] == "CERTIFIED"
        with h["store"].transaction() as conn:
            head = cs._head(conn, old_sid)
        assert head and not head["payload"].get("dataset_contract_digest")
    used = {ref["snapshot_id"] for ref in h["fixed"]["verified_binding_refs"]}
    assert not used & {h["old"][key]["snapshot_id"] for key in DATA_KEYS}
