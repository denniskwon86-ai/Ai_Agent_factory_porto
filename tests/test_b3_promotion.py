"""B3 승격 경계의 좁은 메모리 회귀. 실행은 main의 격리 runner 전용이다.

run_checks/promote/data_fingerprint/require_published_release는 실제 함수를
호출한다. 계약/PDP/게시 파일 판독과 정적 검사만 대역이며 DB 연결을 금지한다.
최소 계약 문서는 제어 흐름용으로, 실제 승인·인증·물질화의 종단 증거가 아니다.
사후 검증 실패는 ACTIVE 전이 차단만 증명하며 물질화 롤백을 주장하지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import sqlite3
from types import SimpleNamespace

import pytest


RID = "promotion-unit.test.invalid"
OLDER_RID = "older-unit.test.invalid"
ACTOR = "publisher@promotion.test.invalid"
CONTEXT = {"tenant_id": "unit-tenant", "scope_node_id": "unit-scope", "entity_mode": "REAL"}
# 운영 함수로 기대값을 재생성하지 않고 기존 정렬 집합의 바이트를 독립 고정한다.
V1_FP = hashlib.sha256(b'["snap-a","snap-b"]').hexdigest()
V2_FP = hashlib.sha256(b'["inst-a:key-a=snap-a","inst-b:key-b=snap-b"]').hexdigest()


class _Lifecycle:
    """후보와 기존 운영판을 메모리에 보존하고 실제 전이 호출을 기록한다."""

    def __init__(self, events):
        self.events = events
        self.states = {RID: "candidate", OLDER_RID: "active"}
        self.writes = []

    def get_status(self, release_id):
        return {"release_id": release_id, "status": self.states[release_id]}

    def set_status(self, release_id, status, *, actor="", reason="", data_fingerprint=""):
        row = dict(release_id=release_id, status=status, actor=actor, reason=reason,
                   data_fingerprint=data_fingerprint)
        self.writes.append(row)
        self.states[release_id] = status
        self.events.append("active")
        return row


@pytest.fixture
def promotion(monkeypatch):
    def no_database(*_args, **_kwargs):
        pytest.fail("이 회귀는 실제 DB에 연결하면 안 됩니다.")
    monkeypatch.setattr(sqlite3, "connect", no_database)

    from core import app_contract_gate as gate, app_proof, release_promotion as rp
    from core import studio_release_context as rc
    from core.enterprise_context.process_schema import ProcessError

    release = dict(
        release_id=RID, project_id="unit-project", runtime_document_version="2.0",
        tenant_id="unit-tenant", enterprise_scope_id="unit-scope", entity_mode="REAL",
        requires_host_runtime=True,
        runtime_contract={"schema_version": "2.0", "revision": 1, "status": "APPROVED",
                          "approval": {"status": "APPROVED"}},
    )
    readiness = {"runtime_document_version": "2.0", "status": "READY", "datasets": [
        {"instance_id": "inst-b", "dataset_contract_key": "key-b", "snapshot_id": "snap-b", "state": "READY"},
        {"instance_id": "inst-a", "dataset_contract_key": "key-a", "snapshot_id": "snap-a", "state": "READY"},
    ]}
    h = SimpleNamespace(
        rp=rp, rc=rc, gate=gate, ProcessError=ProcessError, release=release,
        published=copy.deepcopy(release), readiness=readiness, events=[], gate_calls=[],
        fingerprint_calls=[], rights_calls=[], rights_error=None, forbid_v2=False,
        host_fp=V2_FP, rights_result={"permitted_actions": ["RELEASE"]}, plane=object(),
    )
    h.lifecycle = _Lifecycle(h.events)

    def evaluate(value, release_id, plane=None, *, actor="", context=None, for_action="RUN"):
        h.gate_calls.append(dict(release=value, release_id=release_id, plane=plane,
                                 actor=actor, context=context, for_action=for_action))
        return SimpleNamespace(ok=True, reasons=[])

    def host_fingerprint(release_id, plane=None, *, contract=None):
        if h.forbid_v2:
            pytest.fail("1.0 승격에서 2.0 고정 지문 검사를 호출했습니다.")
        h.fingerprint_calls.append(dict(release_id=release_id, plane=plane, contract=contract))
        return h.host_fp

    def read_release(release_id):
        if h.forbid_v2:
            pytest.fail("1.0 승격에서 2.0 게시판 재검증을 호출했습니다.")
        assert release_id == RID
        h.events.append("read_published")
        return h.published

    def current_rights(value, *, release_id="", actor="", context=None, for_action="RUN", **kwargs):
        h.events.append("current_rights")
        h.rights_calls.append((value, dict(release_id=release_id, actor=actor,
                                          context=context, for_action=for_action, **kwargs)))
        if h.rights_error is not None:
            raise h.rights_error
        return h.rights_result

    monkeypatch.setattr(gate, "evaluate", evaluate)
    monkeypatch.setattr(gate, "data_fingerprint", host_fingerprint)
    monkeypatch.setattr(rp, "_check_static", lambda paths, release=None: rp.Check(rp.CHECK_STATIC, True))
    monkeypatch.setattr(app_proof, "read_release", read_release)
    monkeypatch.setattr(rc, "require_release_context", current_rights)
    return h


def _args(h):
    return dict(release=h.release, release_id=RID, lifecycle=h.lifecycle, actor=ACTOR,
                context=CONTEXT, plane=h.plane, readiness_state=h.readiness, code_paths=[])


def _unchanged(h):
    assert h.lifecycle.writes == []
    assert h.lifecycle.states == {RID: "candidate", OLDER_RID: "active"}
    assert "active" not in h.events


def test_v1_fingerprint_keeps_legacy_material_and_no_data_markers(promotion):
    rp = promotion.rp
    ready = copy.deepcopy(promotion.readiness)
    ready.pop("runtime_document_version")
    ready["datasets"].append(copy.deepcopy(ready["datasets"][0]))
    ready["datasets"].append({"snapshot_id": "not-certified", "state": "STALE"})
    assert rp.data_fingerprint(ready) == V1_FP
    ready["datasets"].reverse()
    assert rp.data_fingerprint(ready) == V1_FP
    assert rp.data_fingerprint(rp.NOT_APPLICABLE) == "NOT_APPLICABLE"
    assert rp.data_fingerprint(None) == "" and rp.data_fingerprint({}) == ""


def test_v1_success_keeps_transition_and_does_not_run_v2_checks(promotion):
    h = promotion
    h.release["runtime_document_version"] = "1.0"
    h.release["runtime_contract"]["schema_version"] = "1.0"
    h.readiness.pop("runtime_document_version")
    h.forbid_v2 = True
    out = h.rp.promote(**_args(h), reason="기존 판 승격", on_promote=lambda: h.events.append("materialize"))
    assert h.events == ["materialize", "active"]
    assert out["status"] == "active" and out["data_fingerprint"] == V1_FP
    assert h.lifecycle.writes == [dict(release_id=RID, status="active", actor=ACTOR,
                                       reason="기존 판 승격", data_fingerprint=V1_FP)]
    assert h.lifecycle.states[OLDER_RID] == "active"
    assert h.fingerprint_calls == [] and h.rights_calls == []


def test_v1_unknown_readiness_never_materializes_or_transitions(promotion):
    h = promotion
    h.release["runtime_document_version"] = "1.0"
    h.release["runtime_contract"]["schema_version"] = "1.0"
    h.readiness = None
    h.forbid_v2 = True
    with pytest.raises(h.rp.PromotionError):
        h.rp.promote(**_args(h), on_promote=lambda: h.events.append("materialize"))
    assert h.events == []
    _unchanged(h)


@pytest.mark.parametrize("actual", ["different-fixed-fingerprint", "unreadable"])
def test_v2_readiness_mismatch_or_unreadable_blocks_real_checks_and_promote(promotion, actual):
    h = promotion
    h.host_fp = actual
    verdict = h.rp.run_checks(**_args(h))
    assert not verdict.ok
    assert [check.name for check in verdict.checks] == list(h.rp.CHECK_NAMES)
    assert [(check.name, check.ok) for check in verdict.blocking] == [(h.rp.CHECK_READINESS, False)]
    with pytest.raises(h.rp.PromotionError):
        h.rp.promote(**_args(h), on_promote=lambda: h.events.append("materialize"))
    assert h.events == []
    assert all(call["release_id"] == RID and call["plane"] is h.plane
               and call["contract"] is h.release["runtime_contract"] for call in h.fingerprint_calls)
    _unchanged(h)


def test_v2_success_checks_published_before_and_after_materialization(promotion):
    h = promotion
    out = h.rp.promote(**_args(h), reason="고정 판 승격", on_promote=lambda: h.events.append("materialize"))
    assert h.events == ["read_published", "current_rights", "materialize",
                        "read_published", "current_rights", "active"]
    assert out["status"] == "active" and out["data_fingerprint"] == V2_FP
    assert len(h.lifecycle.writes) == 1 and h.lifecycle.writes[0]["data_fingerprint"] == V2_FP
    assert h.lifecycle.states[OLDER_RID] == "active"
    assert all(call["actor"] == ACTOR and call["context"] == CONTEXT and call["for_action"] == "RELEASE"
               for call in h.gate_calls)
    assert all(kwargs == dict(release_id=RID, actor=ACTOR, context=CONTEXT, for_action="RELEASE")
               for _, kwargs in h.rights_calls)


def test_v2_native_empty_rows_use_host_no_data_and_pass_readiness_check(promotion):
    h = promotion
    h.readiness["datasets"] = []
    h.host_fp = h.gate.NO_DATA
    assert h.rp.data_fingerprint(h.readiness) == h.gate.NO_DATA
    assert h.rp.run_checks(**_args(h)).ok
    _unchanged(h)


def test_v2_missing_published_file_blocks_before_materialization(promotion):
    h = promotion
    h.published = None
    with pytest.raises(h.rp.PromotionError) as exc:
        h.rp.promote(**_args(h), on_promote=lambda: h.events.append("materialize"))
    assert h.events == ["read_published"]
    assert isinstance(exc.value.__cause__, h.ProcessError)
    assert exc.value.__cause__.reason_code == "STUDIO_RELEASE_CHANGED"
    assert h.rights_calls == []
    _unchanged(h)


def test_v2_rights_revoked_after_materialization_never_enters_active(promotion):
    h = promotion
    denied = h.ProcessError("STUDIO_ACTION_FORBIDDEN", "현재 게시 권한 회수", 403)
    def materialize():
        h.events.append("materialize")
        h.rights_error = denied
    with pytest.raises(h.rp.PromotionError) as exc:
        h.rp.promote(**_args(h), on_promote=materialize)
    assert exc.value.__cause__ is denied
    assert h.events == ["read_published", "current_rights", "materialize",
                        "read_published", "current_rights"]
    # 물질화 1회 이후 실패하므로 ACTIVE 미전이만 증명한다. 쓰기 롤백 증거가 아니다.
    _unchanged(h)


def test_v2_materializer_failure_keeps_candidate_and_skips_postcheck(promotion):
    h = promotion
    def broken_materializer():
        h.events.append("materialize")
        raise OSError("합성 물질화 실패")
    with pytest.raises(h.rp.PromotionError, match="물질화"):
        h.rp.promote(**_args(h), on_promote=broken_materializer)
    assert h.events == ["read_published", "current_rights", "materialize"]
    _unchanged(h)


@pytest.mark.parametrize("changed", ["runtime_contract", "enterprise_scope_id"])
def test_published_body_mismatch_is_409_before_current_rights(promotion, changed):
    h = promotion
    if changed == "runtime_contract":
        h.published["runtime_contract"] = {"schema_version": "1.0"}
    else:
        h.published["enterprise_scope_id"] = "other-scope"
    with pytest.raises(h.ProcessError) as exc:
        h.rc.require_published_release(h.release, release_id=RID, actor=ACTOR, context=CONTEXT)
    assert exc.value.reason_code == "STUDIO_RELEASE_CHANGED" and exc.value.status_code == 409
    assert h.events == ["read_published"] and h.rights_calls == []


def test_published_check_forwards_current_body_and_exact_server_context(promotion):
    h = promotion
    h.published["runtime_contract"] = dict(reversed(list(h.published["runtime_contract"].items())))
    h.published["display_note"] = "정체성이 아닌 현재 표시 정보"
    result = h.rc.require_published_release(h.release, release_id=RID, actor=ACTOR, context=CONTEXT)
    assert result is h.rights_result
    assert h.events == ["read_published", "current_rights"]
    value, kwargs = h.rights_calls[0]
    assert value is h.published and value is not h.release
    assert kwargs == dict(release_id=RID, actor=ACTOR, context=CONTEXT, for_action="RELEASE")


def test_published_current_rights_denial_is_not_hidden(promotion):
    h = promotion
    denied = h.ProcessError("STUDIO_ACTION_FORBIDDEN", "현재 게시 권한 없음", 403)
    h.rights_error = denied
    with pytest.raises(h.ProcessError) as exc:
        h.rc.require_published_release(h.release, release_id=RID, actor=ACTOR, context=CONTEXT)
    assert exc.value is denied and exc.value.status_code == 403
    assert h.events == ["read_published", "current_rights"]
