"""1.1.0 설치본 → 업그레이드(미리보기·명시 적용·승인 뒤 활성화) → 재인증 → 운영 조회. 격리 runner 전용.

실제 B2 설치 saga·ECM 승인(작성자·설치자·승인자 분리)·DP 고정 이력·B0 인증 관문·실제 Host 경로를 쓴다.
합성은 자료(키트 정본 샘플)뿐이고 조직은 `.invalid` 다.

★ «관문 이전» 의 서명과 게시물은 지금 코드로는 만들 수 없다(인증 관문과 운영 계약 대조가 막는다).
  그래서 그 시점만 두 검사를 끈 채 서명·게시·운영 조회해 **재현**한다(`before_the_gate`). 그 뒤 모든
  단계는 실제 검사 아래에서 돈다.
★ [Codex §19.1] 명시 적용은 승인 대기일 뿐이다 — 새 판본은 **승인 뒤에** 활성화된다. 반려하면 옛 판본이
  그대로다. 승인 직후 활성화가 끊기면 운영은 막히고, 같은 승인을 다시 요청하면 잇는다.
★ [Codex §19.2] 새 판본의 앱은 번들 지문을 넣은 **새 릴리스 ID** 다. 옛 게시물은 옛 ID 로 이력에 남는다.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.data_preparation import certification_subject as cs, models as m, snapshot_service as ss
from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle, pin_bundle
from core.enterprise_context.process_schema import ProcessError
from tests import kit_samples, org_seed as org
from tests.test_b1_process_configuration import approval, proposal  # noqa: F401
from tests.test_b2_installation import _apply, _db, _get, _plan, _read, _resume, _start
from tests.test_b3_kit_contract_v2 import (DATA_KEYS, TEMPLATES, database, enforced_org, installation,  # noqa: F401
    sample_certified, workspace)
from tests.test_b3_process_context import build as process_build
from tests.test_r01_app03_real_host_path import (APP, RUNTIME, KEY, _ok, _operate, app_fields, host_session,
    isolate_host)

V110 = load_bundle(CANDIDATE_MANIFEST.parents[1] / "1.1.0" / "manifest.json")
V120 = load_bundle(CANDIDATE_MANIFEST)
KITS = ["BK-03", "BK-04"]
PERIOD = dict(period_from="2026-08-01", period_to="2026-08-31")


def _row(conn, w):
    return dict(conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (w["instance_id"],)).fetchone())


def _pins(w):
    from core.data_preparation.process_kit_instances import pins
    with w["store"].transaction() as conn:
        return [p["identity"]["version"] for p in pins(conn, _row(conn, w))]


def _active(w):
    """지금 활성 판본이 인증·프로필에 주는 것 — INV-01 계약(없으면 None)과 프로필."""
    from core.data_preparation.process_kit_instances import pinned_dataset_contract, profile_for_instance
    with w["store"].transaction() as conn:
        row = _row(conn, w)
        contract = pinned_dataset_contract(conn, row, KEY)
    return contract, profile_for_instance(w["store"], row)


def _versions(w):
    """[Codex §19.3] 실제 적용본 목록 API 가 보여 주는 이 적용본 한 줄(제품 세션)."""
    h = w["old_host"]
    rows = _ok(h["client"].get("/api/v1/data-preparation/instances", headers=h["session"](org.MEMBER_A)))["instances"]
    return next(row for row in rows if row["instance_id"] == w["instance_id"])


def _source(w):
    return next(s for s in _read(w)["payload"]["template_sources"] if s["kit_instance_ref"] == w["instance_id"])


def _sign(w, sid):
    args = dict(actor=org.MANAGER_A, context=w["context"], use_kind="OPERATIONAL", **PERIOD)
    preview = cs.preview(w["store"], sid, **args)
    signed = cs.sign(w["store"], sid, **args, review_kind="DATA_OWNER",
                     reconciliation_evidence="합성 원천 총계와 재인증 판 대사 일치 확인", subject_id=preview["subject_id"],
                     expected_subject_digest=preview["digest"], client_request_id="recertify-" + sid)
    assert signed["certified"]
    return preview


def _blockers(fixed):
    return {b["reason_code"] for b in fixed["blockers"]}


def _records(h, headers):
    from core import kit_app_builder as kb
    return h["client"].get(f"{RUNTIME}/datasets/{kb.runtime_name(KEY)}/records", headers=headers)


def _refused(h, headers, release_id):
    """운영 조회가 막혔다 — 사유 코드를 돌려준다.

    앱에는 사유를 숨긴 404 다(`host_runtime_wire`: 「요청한 데이터를 찾을 수 없습니다」, 사유는 감사에만).
    사유는 조회 경로가 매 요청 부르는 **같은 제품 함수**(`require_release_context`)를 같은 열람자로 불러
    확인한다. 같은 증명·같은 상태에서 관문 이전(재현)에는 200 이었다 — 막는 것은 계약 대조다."""
    from core import app_proof
    from core.studio_release_context import require_release_context
    response = _records(h, headers)
    assert response.status_code == 404, response.text[:400]
    with pytest.raises(ProcessError) as caught:
        require_release_context(app_proof.read_release(release_id), release_id=release_id, actor=org.VIEWER_A,
                                context=h["context"], for_action="RUN")
    assert caught.value.status_code == 409
    return caught.value.reason_code


def _upgrade_plan(w, key):
    wv = {**w, "bundle": V120}
    planned = _plan(wv, business_kit_ids=KITS, instance_id=w["instance_id"],
                    upgrade_from_artifact_digest=V110["artifact_digest"],
                    reason="데이터셋 계약을 싣는 1.2.0 으로 같은 적용본을 올린다")
    return wv, planned, _resume(wv, _start(wv, planned, key=key))


@pytest.fixture
def published(installation, monkeypatch, tmp_path):
    """① 1.1.0 실제 설치 → ② 관문 이전 코드로 서명·게시·운영 조회(재현). 옛 게시물이 있는 1.1.0 적용본."""
    from core import library_paths
    from core.data_preparation import certification_authority as ca
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_context import ProcessContextService
    isolated = isolate_host(monkeypatch, tmp_path)

    # ① 1.1.0 설치 — 실제 B2 saga(계획 → 시작 → 설치자 재개 → 별도 승인자).
    assert pin_bundle(installation["store"], V110)["artifact_digest"] == V110["artifact_digest"]
    w = {**installation, "bundle": V110}
    w["approved"] = _apply(w, _resume(w, _start(w, _plan(w, business_kit_ids=KITS))))
    doc = _read(w)["payload"]
    w.update(instance_id=doc["template_sources"][0]["kit_instance_ref"],
             ids={n["template_key"]: n["process_id"] for n in doc["nodes"]}, installed_doc=doc,
             ctx=ProcessContextService(w["svc"].repo, w["store"]), isolated=isolated)
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

    # ② 관문 이전(재현) — 그 시점 코드에는 인증의 계약 대조도, 운영 사용의 계약 지문 대조도 없었다.
    with monkeypatch.context() as before_the_gate:
        before_the_gate.setattr(cs, "_conforming_contract", lambda conn, row: "")
        before_the_gate.setattr(ProcessContextService, "_signed_against_current_contract",
                                staticmethod(lambda conn, row, payload: None))
        old = {key: sample_certified(w, key) for key in DATA_KEYS}
        w.update(data=old, old=old)
        w["fixed"] = process_build(w, [w["ids"][key] for key in TEMPLATES])
        assert "GENERATE" in w["fixed"]["permitted_actions"]
        h = host_session(w, isolated)
        old_release, _, old_headers, _ = _operate(h)
        then = _records(h, old_headers)
        assert then.status_code == 200 and then.json()["data"]["total"] > 0, then.text[:300]

    # 지금 코드: 옛 서명은 운영 근거가 아니다 — 새 문맥도, 옛 게시물의 운영 조회도 막힌다. 이력은 남는다.
    before = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "CONTRACT_NOT_PINNED" in _blockers(before)
    assert not {"GENERATE", "RUN", "RELEASE"} & set(before["permitted_actions"])
    assert {"READ", "DRAFT"} <= set(before["permitted_actions"])
    assert _refused(h, old_headers, old_release) == "CONTRACT_NOT_PINNED"
    assert cs.read(w["store"], old[KEY]["snapshot_id"], actor=org.MANAGER_A,
                   context=w["context"])["review_status"] == "CERTIFIED"
    w.update(old_release=old_release, old_headers=old_headers, old_host=h,
             old_release_bytes=Path(library_paths.release_json(old_release)).read_bytes())
    yield w


@pytest.fixture
def upgraded(published, monkeypatch):
    """③ 사용자 수정 → ④ 미리보기 → ⑤ 명시 적용(승인 대기) → ⑥ 승인(직후 활성화 장애 → 복구) → ⑦ 재인증."""
    from core.data_preparation import certification_authority as ca, process_kit_instances as pki
    w = published

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

    # ⑤ 명시 적용(설치자 재개) = 승인 대기 기록. 활성 판본·계약·프로필은 그대로다.
    operation = _resume(wv, _start(wv, planned, key="upgrade-to-1.2.0"))
    assert operation["stage"] == "AWAITING_APPROVAL" and operation["upgrade"]["activation"] == "AWAITING_APPROVAL"
    assert _pins(w) == ["1.1.0"] and _active(w) == (None, V110["profile"])
    waiting = _versions(w)
    assert (waiting["version"], waiting["installed_version"]) == ("1.1.0", "1.1.0")
    assert (waiting["pending_upgrade"]["state"], waiting["pending_upgrade"]["version"]) == ("AWAITING_APPROVAL", "1.2.0")

    # ⑥ 승인 — 커밋 직후 활성화가 끊긴다(DP 저장 장애 주입).
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")
    with monkeypatch.context() as outage:
        outage.setattr(pki, "upgrade_or_get", unavailable)
        with pytest.raises(ProcessError) as raised:
            _apply(wv, operation)
    assert (raised.value.status_code, raised.value.reason_code) == (503, "PROCESS_UPGRADE_ACTIVATION_PENDING")
    #: 승인은 기록됐다(업무판은 1.2.0) — 그러나 활성 판본은 아직 1.1.0 이고, 그 사이 운영은 막힌다.
    assert (_source(w)["artifact_digest"], _source(w)["kit_version"]) == (V120["artifact_digest"], "1.2.0")
    assert _pins(w) == ["1.1.0"] and _active(w) == (None, V110["profile"])
    pending = _get(w, operation)
    assert (pending["stage"], pending["upgrade"]["activation"], pending["upgrade"]["activation_error"]) == (
        "APPLIED", "ACTIVATION_PENDING", "PROCESS_STORAGE_UNAVAILABLE")
    assert (pending["upgrade"]["from_version"], pending["upgrade"]["to_version"]) == ("1.1.0", "1.2.0")
    #: [Codex §20] 복구는 같은 승인자의 같은 승인 재요청뿐 — 다시 보낼 값은 그 승인자에게만 준다.
    assert "retry" not in pending["upgrade"]
    change = operation["change"]
    assert _get(w, operation, actor=org.MANAGER_ROOT)["upgrade"]["retry"] == {
        "change_id": change["change_id"], "expected_head_version": change["base_head_version"],
        "draft_digest": change["draft_digest"], "reason": "독립 검토 시험"}
    stuck = _versions(w)
    assert stuck["version"] == "1.1.0" and stuck["pending_upgrade"]["state"] == "ACTIVATION_PENDING"
    assert stuck["pending_upgrade"]["activation_error"] == "PROCESS_STORAGE_UNAVAILABLE"
    #: 새로 승인된 업무판(1.2.0)으로는 문맥 자체가 막히고(활성화 대기), 옛 업무판(1.1.0)으로 만든
    #: 문맥은 초안·열람만 된다(1.1.0 에는 고정 계약이 없다) — 어느 쪽으로도 운영 행동은 없다.
    with pytest.raises(ProcessError) as blocked:
        process_build(w, [w["ids"][key] for key in TEMPLATES], profile_id=_read(w)["profile_id"])
    assert (blocked.value.status_code, blocked.value.reason_code) == (409, "PROCESS_UPGRADE_ACTIVATION_PENDING")
    previous = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "CONTRACT_NOT_PINNED" in _blockers(previous)
    assert not {"GENERATE", "RUN", "RELEASE"} & set(previous["permitted_actions"])
    #: 같은 승인을 다시 요청하면 끊긴 활성화를 잇는다(같은 operation, 멱등).
    w["approved"] = _apply(wv, operation)
    assert _pins(w) == ["1.1.0", "1.2.0"]
    done = _get(w, operation)
    assert (done["stage"], done["upgrade"]["activation"]) == ("APPLIED", "ACTIVE")
    assert "activation_error" not in done["upgrade"]
    #: 감사 기록 — 승인 → 활성화 실패(사유) → 활성화(승인자). 불변 설치 행은 고치지 않았다.
    #:   (같은 초 안의 사건은 시각으로 순서를 가를 수 없어 모음으로 대조한다.)
    with _db(w) as conn:
        trail = sorted((row["event_type"], json.loads(row["payload_json"]).get("reason_code", ""),
                        json.loads(row["payload_json"])["actor"])
                       for row in conn.execute("SELECT * FROM enterprise_process_outbox WHERE change_id=?",
                                               (operation["change"]["change_id"],)))
    assert trail == sorted([("PROCESS_CONFIGURATION_APPROVED", "", org.MANAGER_ROOT),
                            ("PROCESS_UPGRADE_ACTIVATION_FAILED", "PROCESS_STORAGE_UNAVAILABLE", org.MANAGER_ROOT),
                            ("PROCESS_UPGRADE_ACTIVATED", "", org.MANAGER_ROOT)])
    active = _versions(w)
    assert (active["version"], active["installed_version"], active["pending_upgrade"]) == ("1.2.0", "1.1.0", None)
    contract, profile = _active(w)
    assert contract == next(c for c in V120["dataset_contracts"]["contracts"] if c["dataset_contract_key"] == KEY)
    assert profile == V120["profile"]
    #: 같은 적용본·같은 업무 대응·사용자 수정 보존.
    installed = next(s for s in w["installed_doc"]["template_sources"] if s["kit_instance_ref"] == w["instance_id"])
    assert _source(w)["template_process_ids"] == installed["template_process_ids"]
    assert next(n for n in _read(w)["payload"]["nodes"] if n["process_id"] == renamed)["label"] == "현업 재고 확인(업그레이드 전 수정)"
    #: 옛 서명은 이력으로 남고, 운영에는 재인증을 요구한다.
    stale = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "CERTIFICATION_RECERTIFICATION_REQUIRED" in _blockers(stale)
    assert not {"GENERATE", "RUN"} & set(stale["permitted_actions"])
    assert cs.read(w["store"], w["old"][KEY]["snapshot_id"], actor=org.MANAGER_A,
                   context=w["context"])["review_status"] == "CERTIFIED"

    # ⑦ 재인증 — 같은 봉인 원문·같은 원천 합계로 새 판을 올리고 현재 고정 계약으로 서명한다.
    fresh = {}
    for key in DATA_KEYS:
        old_sid = w["old"][key]["snapshot_id"]
        row = ss.reissue_for_recertification(w["store"], old_sid, workspace_root=kit_samples.raw_root(),
                                             created_by=org.MANAGER_A)
        assert row["state"] == m.RECONCILED and row["checksum"] == w["store"].get_snapshot(old_sid)["checksum"]
        subject = _sign(w, row["snapshot_id"])
        assert subject["payload"]["dataset_contract_digest"] == ca.digest(next(
            c for c in V120["dataset_contracts"]["contracts"] if c["dataset_contract_key"] == key))
        fresh[key] = {"binding": w["old"][key]["binding"], "snapshot_id": row["snapshot_id"]}
    w["data"] = fresh
    w["fixed"] = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "GENERATE" in w["fixed"]["permitted_actions"]
    refs = {ref["contract_key"]: ref["snapshot_id"] for ref in w["fixed"]["verified_binding_refs"]}
    assert refs == {key: fresh[key]["snapshot_id"] for key in DATA_KEYS}
    yield host_session(w, w["isolated"])


def test_upgraded_and_recertified_install_reads_operationally_under_a_new_release(upgraded):
    """★★★ 끝 — 새 판본의 앱은 새 릴리스 ID 로 게시·승격되고 운영 조회된다. 앱 진입은 새 ID 를 가리킨다."""
    from core import kit_app_builder as kb
    h = upgraded
    new_id = kb.release_id_for(h["instance_id"], APP, V120["artifact_digest"])
    assert new_id != h["old_release"] and V120["artifact_digest"][:16] in new_id
    release_id, ds, headers, _ = _operate(h, expected_revision=1, release_id=new_id)
    names = app_fields(KEY)
    source = [{k: v for k, v in row.items() if k in names}
              for row in kit_samples.sample_table(KEY, h["context"])[1]]
    served = _ok(_records(h, headers))
    assert [{k: str(v) for k, v in r["payload"].items()} for r in served["records"]] == source
    assert h["operational"].binding_for(release_id, ds["dataset_id"])["enterprise_contract_key"] == KEY
    listed = _ok(h["client"].get(f"/api/v1/data-preparation/instances/{h['instance_id']}/apps",
                                 headers=h["session"](org.MEMBER_A)))
    app = next(a for a in listed["apps"] if a["app_id"] == APP)
    assert app["release_id"] == new_id
    assert [(r["release_id"], r["kit_version"]) for r in app["release_history"]] == [(h["old_release"], "1.1.0")]


def test_the_old_release_stays_as_history_next_to_the_new_one(upgraded):
    """옛 게시물은 옛 ID 로 그대로 남고 자기 판본(1.1.0)으로 검증된다 — 다만 운영 근거는 아니다."""
    from core import kit_app_builder as kb, library_paths
    from core.studio_release_cohort import get_release_cohort
    h = upgraded
    new_id, _, _, _ = _operate(h, expected_revision=1,
                               release_id=kb.release_id_for(h["instance_id"], APP, V120["artifact_digest"]))
    assert Path(library_paths.release_json(h["old_release"])).read_bytes() == h["old_release_bytes"]
    assert get_release_cohort(h["store"], h["old_release"])["artifact_digest"] == V110["artifact_digest"]
    assert get_release_cohort(h["store"], new_id)["artifact_digest"] == V120["artifact_digest"]
    assert [item["release_id"] for item in kb.release_history(h["store"], h["instance_id"], APP)] == [h["old_release"], new_id]
    #: 옛 게시물의 운영 조회는 막힌다 — 1.2.0 계약으로 재인증한 판이 아니라 옛 서명에 묶여 있다.
    assert _refused(h, h["old_headers"], h["old_release"]) == "CERTIFICATION_RECERTIFICATION_REQUIRED"


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


def test_a_rejected_upgrade_leaves_the_active_version_contract_and_certification_as_they_were(published):
    """[Codex §19.1] 반려 → 활성 판본·계약·프로필·인증 기준 모두 1.1.0 그대로. DP 에는 아무것도 쓰지 않았다."""
    w = published
    head_before = _read(w)
    _, _, operation = _upgrade_plan(w, "upgrade-rejected")
    assert operation["stage"] == "AWAITING_APPROVAL" and _pins(w) == ["1.1.0"]
    change = operation["change"]
    rejected = w["svc"].reject(change_id=change["change_id"], actor=org.MANAGER_ROOT, context=w["context"],
                               expected_head_version=change["base_head_version"], draft_digest=change["draft_digest"],
                               reason="데이터셋 계약 검토 전 보류")
    assert rejected["status"] == "REJECTED"
    assert _pins(w) == ["1.1.0"] and _active(w) == (None, V110["profile"])
    assert _read(w)["head_version"] == head_before["head_version"]
    assert _source(w)["artifact_digest"] == V110["artifact_digest"]
    after = _get(w, operation)
    assert (after["stage"], after["upgrade"]["activation"]) == ("FAILED_BLOCKED", "NOT_ACTIVATED")
    versions = _versions(w)
    assert (versions["version"], versions["pending_upgrade"]) == ("1.1.0", None)
    #: 인증은 여전히 1.1.0 기준이다 — 1.2.0 계약으로 대조하지 않고, 고정 계약이 없어 막는다.
    from core.data_preparation.certification_authority import CertificationError
    fresh = ss.reissue_for_recertification(w["store"], w["old"][KEY]["snapshot_id"],
                                           workspace_root=kit_samples.raw_root(), created_by=org.MANAGER_A)
    with pytest.raises(CertificationError) as gate:
        cs.preview(w["store"], fresh["snapshot_id"], actor=org.MANAGER_A, context=w["context"],
                   use_kind="OPERATIONAL", **PERIOD)
    assert gate.value.reason_code == "CONTRACT_NOT_PINNED"
    #: 새 문맥도 그대로 계약 없음으로 막히고, 옛 게시물의 운영 조회도 그대로 막힌다.
    assert "CONTRACT_NOT_PINNED" in _blockers(process_build(w, [w["ids"][key] for key in TEMPLATES]))
    assert _refused(w["old_host"], w["old_headers"], w["old_release"]) == "CONTRACT_NOT_PINNED"
