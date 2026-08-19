"""★★★ [I-4 8 / Wave F-3] 종단 카나리 — **한 번 관통시켜서 «실제로 돈다» 를 본다.**

## 왜 이 파일이 다른 시험과 다른가

F-0·F-1·F-2 는 각각 통제를 만들었고, 그때마다 같은 함정이 나왔다 —
**「통제는 만들었는데 그것이 실제로 도는 것을 본 적이 없다」.** 세 번 다 변이 검사나
자체 점검에서야 드러났다.

이 파일은 그 질문에 **구조로** 답한다. 7칸을 한 줄로 이어서 돌리므로, 중간의 어느
배선이 빠지면 **여기서 멈춘다.**

```text
업무키트 적용 → 원천 활성 → 파일 Snapshot 인증
→ 계약 컴파일·승인 → 데이터셋 물질화
→ 후보(Preview) 에서 파일 읽기 + Native 메모 쓰기
→ 승격 → 운영에서 새 세션 실행
```

## 이 파일이 지키는 것

★★★ ① **운영 저장소에 쓰지 않는다.** 모든 DB·파일이 `tmp_path` 안이다.
★★★ ② **허용과 거부를 둘 다 본다.** 「전부 막힘」으로도 초록인 카나리는 아무것도
  증명하지 않는다.
★★★ ③ **지문이 바뀌면 막힌다.** Snapshot 인증을 회수하면 그다음 요청이 멈춘다.
"""
import json

import pytest

from core import app_preview as ap
from core import app_proof
from core import app_runtime_contract as arc
from core import contract_materializer as cm
from core import release_promotion as rp
from core.data_preparation import models as dpm
from core.data_preparation import snapshot_service as ss
from core.data_preparation import source_binding as sb
from core.program_lifecycle import ACTIVE, CANDIDATE, program_lifecycle

TENANT, SCOPE, MODE = "tenant_default", "node_hq", "REAL"
CONTRACT_KEY = "arrivals"
REL = "rel_canary"
PROJECT = "proj_canary"
R = "/api/v1/appdata/runtime"
H = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
     "X-Enterprise-Scope": "node_hq"}

CSV = ("arrived_at,material_code,quantity\n"
       "2026-01-05,M1,10\n"
       "2026-01-06,M2,5\n").encode("utf-8")
ROWS = [{"arrived_at": "2026-01-05", "material_code": "M1", "quantity": "10"},
        {"arrived_at": "2026-01-06", "material_code": "M2", "quantity": "5"}]
FIELDS = [{"name": "quantity", "type": "number", "required": False,
           "classification": "INTERNAL"}]


def _contract():
    """계약을 **실제 컴파일러로** 만든다 — 손으로 적으면 시험만 아는 모양이 생긴다."""
    from core.host_contract_compiler import compile_contract

    r = compile_contract({
        "app_class": "departmental",
        "datasets": [
            {"name": "arrivals", "purpose": "자재가 얼마나 들어왔는가",
             "allowed_actions": ["read"], "data_role": arc.ENTERPRISE_ACTUAL,
             "source_intent": arc.ENTERPRISE_READ,
             "enterprise_contract_key": CONTRACT_KEY,
             "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
             "fields": FIELDS},
            {"name": "memo", "purpose": "원천에 없는 대응 메모",
             "allowed_actions": ["read", "create"],
             "data_role": arc.NATIVE_SUPPLEMENT, "source_intent": arc.AFS_NATIVE,
             "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED,
             "fields": FIELDS},
        ]}, project_id=PROJECT)
    assert r.ok, r.errors
    c = dict(r.contract)
    c["status"] = arc.STATUS_APPROVED
    c["approval"] = {"status": "APPROVED", "approved_by": "u@x",
                     "approved_at": "2026-08-19T00:00:00Z",
                     "decision_ledger_id": "evt_canary"}
    return c


@pytest.fixture
def canary(monkeypatch, tmp_path):
    """구조적으로 분리된 세계 하나. ⚠️ 운영 경로는 **하나도** 쓰지 않는다."""
    import config
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    (lib / REL).mkdir(parents=True)
    (lib / REL / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(program_lifecycle, "db_path", str(tmp_path / "life.db"),
                        raising=False)
    monkeypatch.setattr(program_lifecycle, "_release_exists", lambda rid: True,
                        raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})
    app_capability_tokens._tokens.clear()
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    c.lib = lib
    c.raw = str(tmp_path / "raw")
    return c


def _write_release(client, *, mode=MODE, contract=None):
    """게시가 만들어 놓는 릴리스 파일. **후보 상태는 별도로 기록한다**(게시가 하듯)."""
    body = {
        "release_id": REL, "project_id": PROJECT, "tenant_id": TENANT,
        "entity_mode": mode, "enterprise_scope_id": SCOPE,
        "owner_user_id": "", "owner_dept_id": "hq", "visibility": "dept",
        "artifact_kind": "APP", "runtime_contract_profile": "v1",
        "runtime_contract": contract if contract is not None else _contract(),
        "manifest": {"fingerprint": "fp_canary", "valid": True, "manifest": {
            "version": "1.0", "app_class": "departmental",
            "capabilities": ["arrivals.read", "memo.read", "memo.create"],
            "required_capabilities": []}},
    }
    (client.lib / REL / "release.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return body


def _step_source(dp, raw_root, *, mode=MODE):
    """① 업무키트 적용 → ② 원천 활성 → ③ 파일 Snapshot 인증.

    ★★★ `mode` 가 중요하다. Preview 는 `SYNTHETIC_TEST` 문맥에서만 돌고 Dispatch 는
      매 요청 범위를 대조하므로, **Preview 가 읽을 판은 SYNTHETIC 문맥에 있어야 한다.**
    ⚠️ 그래서 `REAL` 인증판은 Preview 에서 보이지 않는다 — 그것이 「Preview 에서 본
      것은 운영 기준선이 되지 않는다」의 실제 구현이다."""
    inst = dp.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                              tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=mode)
    b = dp.create_binding(instance_id=inst["instance_id"],
                          dataset_contract_key=CONTRACT_KEY,
                          provider=dpm.PROVIDER_FILE_SNAPSHOT,
                          config={"file_name": "a.csv", "column_map": {"a": "A"}},
                          tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=mode)
    for step in ("validate", "approve", "activate"):
        getattr(sb, step)(dp, b["binding_id"])
    snap = ss.ingest(dp, binding=dp.get_binding(b["binding_id"]), payload=CSV,
                     file_name="a.csv", workspace_root=raw_root)
    out = ss.run_pipeline(dp, snap["snapshot_id"], ROWS,
                          ["arrived_at", "material_code", "quantity"],
                          control={"row_count": 2, "sums": {"quantity": 15}})
    assert out["state"] == dpm.DEMO_CERTIFIED, out
    return inst, b, out


def _step_materialize(dp, contract, *, mode=ap.ENTITY_MODE_SYNTHETIC,
                      audience=ap.AUDIENCE_PREVIEW):
    """④ 계약 → 데이터셋 물질화. **그 청중의 평면에** 만든다."""
    return cm.materialize(contract, release_id=REL, actor_id="u@x", store=dp,
                          app_data=ap.app_data_for(audience), tenant_id=TENANT,
                          scope_node_id=SCOPE, entity_mode=mode)


def _tok(client):
    r = client.post(R + "/proof", json={"release_id": REL}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _h(tok):
    return {**H, "X-App-Proof": tok}


@pytest.fixture
def dp():
    from core.data_preparation.store import data_preparation_store

    return data_preparation_store


# ── 관통 ────────────────────────────────────────────────────────────────
def test_the_whole_path_runs_end_to_end(canary, dp, monkeypatch):
    """★★★ **7칸을 한 줄로 관통한다.** 중간 배선이 빠지면 여기서 멈춘다.

    ⚠️ 이 시험이 초록이라는 것은 「각 조각이 있다」가 아니라 **「이어져 있다」**는 뜻이다.
      F-0·F-1·F-2 에서 세 번 반복된 함정이 바로 그 차이였다."""
    import api.routes.app_data_runtime as ard

    contract = _contract()
    #: Preview 가 읽을 판은 **SYNTHETIC 문맥**에 있어야 한다(범위 대조 때문에)
    inst, binding, snap = _step_source(dp, canary.raw,
                                       mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)

    # ④ 물질화 — 계약이 데이터셋을 만든다
    out = _step_materialize(dp, contract)
    assert {d["name"] for d in out.datasets} == {"arrivals", "memo"}

    # ⑤ 후보로 기록 — 게시가 하는 일
    program_lifecycle.set_status(REL, CANDIDATE, actor="u@x", reason="카나리")

    # ⑥ Preview 에서 파일 읽기 + Native 메모 쓰기
    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": TENANT,
                                   "entity_mode": ap.ENTITY_MODE_SYNTHETIC,
                                   "scope_node_id": SCOPE}, raising=False)
    tok = _tok(canary)

    read = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert read.status_code == 200, read.text
    assert read.json()["data"]["total"] == 2
    assert read.json()["data"]["as_of"], "「언제 것인가」가 없다"

    memo = canary.post(R + "/datasets/memo/records", headers=_h(tok),
                       json={"payload": {"quantity": 1}})
    assert memo.status_code == 200, memo.text

    # ★★★ ② 거부 표본 — 파일 판에는 쓸 수 없다
    blocked = canary.post(R + "/datasets/arrivals/records", headers=_h(tok),
                          json={"payload": {"quantity": 1}})
    assert blocked.status_code == 403, "파일 판에 쓰기가 통과했다"

    # ⑦ 승격 → 운영
    #
    # ★★★ 검사는 **후보가 사는 평면**(Preview)으로 하고, 승격하면서 **운영 평면에도
    #   물질화**한다. 그 물질화가 실패하면 상태를 바꾸지 않는다 — 그러지 않으면
    #   「운영이라고 적혀 있는데 읽을 데이터가 없는 판」이 생긴다.
    # ⚠️ 운영 물질화는 **REAL 원천**을 요구한다. 후보를 확인할 때 쓴 SYNTHETIC 판은
    #   운영 기준선이 되지 않는다 — 그것이 이 경계의 요점이다.
    _step_source(dp, canary.raw, mode=MODE)
    rel_body = json.loads((canary.lib / REL / "release.json").read_text(encoding="utf-8"))
    promoted = rp.promote(
        release=rel_body, release_id=REL, lifecycle=program_lifecycle, actor="u@x",
        code_paths=[str(canary.lib / REL)], readiness_state=rp.NOT_APPLICABLE,
        reason="카나리 승격",
        plane=ap.app_data_for(ap.AUDIENCE_PREVIEW),
        on_promote=lambda: _step_materialize(dp, contract, mode=MODE,
                                             audience=ap.AUDIENCE_OPERATIONAL))
    assert promoted["status"] == ACTIVE

    #: ★ 운영 평면에 실제로 생겼는가 — 승격이 «상태만» 바꾸지 않았다는 증거
    from core.app_data import app_data_service
    assert app_data_service.find_dataset(REL, "arrivals"),         "승격했는데 운영 평면에 데이터셋이 없다"

    # ★★★ 승격 뒤 **옛 Preview 증명은 더 이상 통하지 않는다**
    stale = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert stale.status_code == 401, \
        "승격 뒤에도 Preview 증명이 통했다: " + str(stale.status_code)


def test_a_new_session_after_promotion_uses_the_operational_plane(canary, dp,
                                                                  monkeypatch):
    """★★★ ⑦ **새 세션 실행** — 승격 뒤에는 운영 평면을 읽는다.

    ⚠️ 승격했는데 여전히 Preview 평면을 읽으면, 사용자는 「미리보기에서 넣은 메모가
      운영에도 있다」고 믿게 된다."""
    import api.routes.app_data_runtime as ard
    from core.app_data import app_data_service

    contract = _contract()
    _step_source(dp, canary.raw)
    _write_release(canary, contract=contract)
    program_lifecycle.set_status(REL, ACTIVE, actor="u@x", reason="이미 운영")

    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": TENANT, "entity_mode": MODE,
                                   "scope_node_id": SCOPE}, raising=False)
    #: 운영 평면에 물질화한다 — 승격 뒤의 상태를 재현
    _step_materialize(dp, contract, mode=MODE,
                      audience=ap.AUDIENCE_OPERATIONAL)
    assert app_data_service.find_dataset(REL, "arrivals"), "운영 평면 준비 실패"

    tok = _tok(canary)
    r = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total"] == 2

    #: Preview 평면에는 그 데이터셋이 **없어야** 한다
    preview = ap.app_data_for(ap.AUDIENCE_PREVIEW)
    assert preview.find_dataset(REL, "arrivals") is None, \
        "운영 실행이 Preview 평면을 만졌다"


# ── ③ 지문이 바뀌면 막힌다 ──────────────────────────────────────────────
def test_revoking_the_certified_snapshot_stops_the_read(canary, dp, monkeypatch):
    """★★★ Gate F — **snapshot 변경 stale 차단.**

    ⚠️ 인증이 회수됐는데 계속 읽히면, 그 화면의 숫자는 «아무도 보증하지 않는 값» 이
      된다. 그리고 그 화면은 오류를 내지 않는다."""
    import api.routes.app_data_runtime as ard

    contract = _contract()
    _step_source(dp, canary.raw, mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)
    program_lifecycle.set_status(REL, CANDIDATE, actor="u@x", reason="카나리")
    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": TENANT,
                                   "entity_mode": ap.ENTITY_MODE_SYNTHETIC,
                                   "scope_node_id": SCOPE}, raising=False)
    tok = _tok(canary)
    assert canary.get(R + "/datasets/arrivals/records",
                      headers=_h(tok)).status_code == 200

    #: 인증을 회수한다
    snaps = [s for s in dp.list_snapshots(
        dp.list_instances(tenant_id=TENANT,
                          entity_mode=ap.ENTITY_MODE_SYNTHETIC,
                          scope_node_ids=[SCOPE])[0]["instance_id"])
        if s["state"] == dpm.DEMO_CERTIFIED]
    dp.advance_snapshot(snaps[0]["snapshot_id"], dpm.REVOKED)

    after = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert after.status_code != 200,         "인증 회수 뒤에도 읽혔다: " + str(after.status_code)

    #: ★★★ [§4.2 이후] **증명이 먼저 죽는다.** 회수는 「이 앱이 읽는 판 집합」을 바꾸고,
    #:   그 지문은 증명에 봉인돼 있다 — 그래서 dispatch 에 닿기 전에 프레임이 닫힌다.
    #:   ⚠️ 이것을 「막혔으니 됐다」로 넘기지 않는다. 봉인이 먼저 걸리면 사용자에게 가는
    #:     말이 「앱을 다시 여십시오」가 되므로, **다시 연 뒤에도 진짜 사유가 남아
    #:     있는지**까지 봐야 한다. 아니면 다시 열면 그냥 읽히는 셈이 된다.
    assert after.status_code == 404, (
        "봉인 대조가 아니라 다른 이유로 막혔다: " + str(after.status_code))

    #: 앱을 다시 연다 — 새 증명은 «지금» 의 판 집합으로 봉인된다.
    fresh = _tok(canary)
    again = canary.get(R + "/datasets/arrivals/records", headers=_h(fresh))
    assert again.status_code == 503, (
        "다시 연 뒤에는 «아직 준비되지 않았다» 가 나와야 한다 — 회수된 판이 다시 "
        "읽히거나 사유가 사라졌다: " + str(again.status_code))


def test_retiring_the_source_binding_stops_the_read(canary, dp, monkeypatch):
    """★★★ Gate F — **binding 변경 stale 차단.**"""
    import api.routes.app_data_runtime as ard

    contract = _contract()
    inst, binding, _ = _step_source(dp, canary.raw,
                                    mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)
    program_lifecycle.set_status(REL, CANDIDATE, actor="u@x", reason="카나리")
    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": TENANT,
                                   "entity_mode": ap.ENTITY_MODE_SYNTHETIC,
                                   "scope_node_id": SCOPE}, raising=False)
    tok = _tok(canary)
    assert canary.get(R + "/datasets/arrivals/records",
                      headers=_h(tok)).status_code == 200

    #: ⚠️ `ACTIVE → BLOCKED` 는 표가 허용하지 않는다(가능한 다음 상태는 `RETIRED`).
    #:   원천을 «바꾸는» 일은 종료이지 차단이 아니다 — 표가 그렇게 말한다.
    dp.transition(binding["binding_id"], dpm.RETIRED)
    after = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert after.status_code == 503, \
        "결속이 막혔는데 읽혔다: " + str(after.status_code)


# ── ① 운영 저장소를 건드리지 않는다 ─────────────────────────────────────
def test_the_canary_never_touches_operational_storage(canary, dp, monkeypatch):
    """★★★ **운영 DB 에 카나리 쓰기 금지**(설계서 §I-4 8).

    ⚠️ 카나리는 «전부» 를 돌리는 시험이라 오염 위험이 가장 크다. 그래서 여기서
      **경로 자체**를 확인한다 — 「안 썼겠지」가 아니라 「쓸 수 없는 곳을 보고 있다」."""
    import os

    from core.app_data import app_data_service
    from core.paths import DATA_DIR

    contract = _contract()
    _step_source(dp, canary.raw, mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)

    real = os.path.realpath(DATA_DIR)
    for name, path in (("업무 데이터", dp.db_path),
                       ("앱 데이터", app_data_service._store.db_path),
                       ("Preview", ap.app_data_for(ap.AUDIENCE_PREVIEW)._store.db_path),
                       ("생명주기", program_lifecycle.db_path)):
        assert not os.path.realpath(path).startswith(real), \
            f"{name} 저장소가 운영 영역을 가리킨다: {path}"


def test_certifying_a_newer_snapshot_closes_the_open_frame(canary, dp, monkeypatch):
    """★★★ [§4.2] **판이 «교체» 돼도 프레임이 닫혀야 한다** — 회수와 다른 사건이다.

    회수는 읽기가 멈추므로 언젠가는 티가 난다. 그런데 **새 판이 인증되면** 계약도
    결속도 그대로이고, 앱은 다음 요청부터 조용히 **다른 숫자**를 읽는다. 아무 오류도
    나지 않고, 「그 화면이 어느 판을 보고 있었나」에 답할 수 없게 된다.

    ⚠️ 이 시험이 없으면 봉인이 회수만 잡고 교체를 놓쳐도 초록이다."""
    import api.routes.app_data_runtime as ard

    contract = _contract()
    inst, binding, _first = _step_source(dp, canary.raw, mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)
    program_lifecycle.set_status(REL, CANDIDATE, actor="u@x", reason="카나리")
    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": TENANT,
                                   "entity_mode": ap.ENTITY_MODE_SYNTHETIC,
                                   "scope_node_id": SCOPE}, raising=False)
    tok = _tok(canary)
    first = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert first.status_code == 200, first.text[:200]

    #: ★ 같은 결속에 **새 파일**을 올려 인증한다. 계약도 결속도 그대로다.
    newer = ss.ingest(dp, binding=dp.get_binding(binding["binding_id"]), payload=CSV,
                      file_name="a2.csv", workspace_root=canary.raw)
    out = ss.run_pipeline(dp, newer["snapshot_id"], ROWS,
                          ["arrived_at", "material_code", "quantity"],
                          control={"row_count": 2, "sums": {"quantity": 15}})
    assert out["state"] == dpm.DEMO_CERTIFIED, out
    assert newer["snapshot_id"] != _first["snapshot_id"], "같은 판을 두 번 셌다"

    after = canary.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert after.status_code == 404, (
        "판이 교체됐는데 옛 증명으로 계속 읽힌다 — 그 화면이 무엇을 보고 있었는지 "
        "답할 수 없다: " + str(after.status_code))

    #: ★★★ 대조군 — 다시 열면 읽힌다. 이것이 없으면 「그냥 다 막혔다」를 통제로 읽는다.
    fresh = _tok(canary)
    again = canary.get(R + "/datasets/arrivals/records", headers=_h(fresh))
    assert again.status_code == 200, (
        "다시 열어도 안 읽힌다 — 시험이 통제가 아니라 고장을 보고 있다: "
        + str(again.status_code))


def test_an_app_without_business_data_seals_a_marker_not_a_blank(canary, dp, monkeypatch):
    """★★★ 「업무 데이터를 안 읽는다」와 「봉인하지 않았다」는 **다른 사실**이다.

    ⚠️ 둘 다 빈 값이면 판정이 「양쪽 다 비었으니 같다」로 통과하고, 나중에 업무 데이터
      결속이 생겨도 이미 도는 앱이 그대로 살아남는다."""
    from core import app_contract_gate as gate

    #: 결속을 하나도 만들지 않은 릴리스 — 업무 데이터를 읽지 않는다.
    assert gate.data_fingerprint("rel_없는것") == gate.NO_DATA
    assert gate.NO_DATA and gate.NO_DATA != ""


# ── §4.2 봉인의 «막는 성질» — 변이 검사가 놓친 자리들 ────────────────────
def _break_snapshots(monkeypatch):
    """**data_preparation 저장소만** 못 읽게 만든다.

    ★★★ 판독 실패는 두 갈래다 — 결속 표(물질화와 같은 저장소)와 **인증판 저장소**.
      앞의 것은 물질화 검사가 먼저 잡으므로, 데이터 축의 「모르니까 통과」를 시험하려면
      **뒤의 것**을 끊어야 한다. 앞을 끊고 초록을 보면 시험이 다른 통제를 보고 있는 것이다."""
    from core.data_preparation.store import data_preparation_store as dp_store

    def boom(*a, **kw):
        raise RuntimeError("원천 저장소가 응답하지 않습니다")

    monkeypatch.setattr(dp_store, "list_snapshots", boom)


def test_an_unreadable_data_store_is_not_read_as_no_data(canary, dp, monkeypatch):
    """★★★ 「못 읽었다」와 「업무 데이터를 안 쓴다」는 **다른 사실**이다.

    ⚠️ 못 읽은 것을 «없음» 표식으로 접으면, 저장소가 흔들리는 동안 발급된 증명이
      「데이터를 안 읽는 앱」으로 봉인되고 그 뒤로 무엇이 바뀌어도 통한다."""
    from core import app_contract_gate as gate

    contract = _contract()
    _step_source(dp, canary.raw, mode=ap.ENTITY_MODE_SYNTHETIC)
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)
    plane = ap.app_data_for(ap.AUDIENCE_PREVIEW)

    #: ★ 대조군 — 끊기 전에는 진짜 지문이 나온다.
    before = gate.data_fingerprint(REL, plane=plane)
    assert before not in (gate.UNREADABLE, gate.NO_DATA, ""), before

    _break_snapshots(monkeypatch)
    got = gate.data_fingerprint(REL, plane=plane)
    assert got == gate.UNREADABLE, f"판독 실패를 {got!r} 로 접었다"
    assert got != gate.NO_DATA


def test_an_unreadable_data_store_blocks_issuance(canary, dp, monkeypatch):
    """★★★ 판독 실패로는 **발급하지 않는다** — 「모르니까 통과」가 곧 승인 없는 권한이다."""
    from core import app_contract_gate as gate

    contract = _contract()
    _step_source(dp, canary.raw, mode=ap.ENTITY_MODE_SYNTHETIC)
    rel = _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)
    plane = ap.app_data_for(ap.AUDIENCE_PREVIEW)

    #: ★ 대조군 — 끊기 전에는 발급된다. 없으면 「원래 안 되는 것」을 통제로 읽는다.
    ok = gate.evaluate(app_proof.read_release(REL), REL, plane=plane)
    assert ok.ok, f"끊기 전에도 막힌다 — 시험이 통제가 아니라 고장을 본다: {ok.reasons}"

    _break_snapshots(monkeypatch)
    verdict = gate.evaluate(app_proof.read_release(REL), REL, plane=plane)
    assert not verdict.ok, "데이터 판 상태를 못 읽는데 발급을 허용했다"
    assert any("업무 데이터" in r for r in verdict.reasons), verdict.reasons


def test_a_dataset_with_no_certified_snapshot_still_counts(canary, dp):
    """★★★ 인증판이 **아직 없는 자리**를 지문에서 빼면, 첫 인증이 지문을 안 바꾼다.

    ⚠️ 그러면 「데이터가 하나도 없을 때 열어 둔 프레임」이 첫 판이 인증된 뒤에도 그대로
      살아 있고, 앱은 갑자기 숫자를 그리기 시작한다 — 아무도 그것을 고장으로 안 본다."""
    from core import app_contract_gate as gate

    contract = _contract()
    #: 결속만 만들고 **판은 올리지 않는다.**
    inst = dp.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                              tenant_id=TENANT, scope_node_id=SCOPE,
                              entity_mode=ap.ENTITY_MODE_SYNTHETIC)
    b = dp.create_binding(instance_id=inst["instance_id"],
                          dataset_contract_key=CONTRACT_KEY,
                          provider=dpm.PROVIDER_FILE_SNAPSHOT,
                          config={"file_name": "a.csv", "column_map": {"a": "A"}},
                          tenant_id=TENANT, scope_node_id=SCOPE,
                          entity_mode=ap.ENTITY_MODE_SYNTHETIC)
    for step in ("validate", "approve", "activate"):
        getattr(sb, step)(dp, b["binding_id"])
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)

    plane = ap.app_data_for(ap.AUDIENCE_PREVIEW)
    empty = gate.data_fingerprint(REL, plane=plane)
    #: ★ 「결속은 있는데 판이 없다」는 «업무 데이터를 안 쓴다» 가 아니다.
    assert empty not in (gate.NO_DATA, gate.UNREADABLE, ""), empty

    #: 첫 판을 인증한다 — 지문이 **달라져야** 한다.
    snap = ss.ingest(dp, binding=dp.get_binding(b["binding_id"]), payload=CSV,
                     file_name="a.csv", workspace_root=canary.raw)
    out = ss.run_pipeline(dp, snap["snapshot_id"], ROWS,
                          ["arrived_at", "material_code", "quantity"],
                          control={"row_count": 2, "sums": {"quantity": 15}})
    assert out["state"] == dpm.DEMO_CERTIFIED, out
    assert gate.data_fingerprint(REL, plane=plane) != empty, (
        "첫 인증이 지문을 바꾸지 않았다 — 판 없는 자리를 지문에서 뺐다")


class _UnqueryablePlane:
    """결속 표를 못 읽는 평면. ★ 판독 실패의 **첫 갈래**를 곧장 지난다.

    ⚠️ `evaluate()` 로는 이 갈래를 볼 수 없다 — 같은 저장소를 쓰는 물질화 검사가 먼저
      막기 때문이다. 그래서 `data_fingerprint()` 를 직접 부른다."""

    class _Store:
        def query(self, *a, **kw):
            raise RuntimeError("결속 표를 읽을 수 없습니다")

    _store = _Store()


def test_an_unqueryable_binding_table_is_unreadable_not_no_data():
    """★★★ 결속 표를 **못 읽은 것**을 「업무 데이터를 안 쓴다」로 접지 않는다.

    ⚠️ 접으면 저장소가 흔들리는 동안 발급된 증명이 「데이터를 안 읽는 앱」으로 봉인되고,
      그 뒤로 무엇이 바뀌어도 통한다."""
    from core import app_contract_gate as gate

    got = gate.data_fingerprint(REL, plane=_UnqueryablePlane())
    assert got == gate.UNREADABLE, f"판독 실패를 {got!r} 로 접었다"
    assert got != gate.NO_DATA


def test_an_empty_slot_does_not_collapse_to_an_empty_set(canary, dp):
    """★★★ 인증판이 **아직 없는 자리**도 지문에 자리를 차지해야 한다.

    ⚠️ 빼면 「결속은 있는데 판이 없다」가 「결속이 하나도 없다」와 같은 값이 된다.
      그러면 계약에 데이터셋이 늘어도 지문이 안 바뀌고, 그 자리가 생기기 전에 열어 둔
      프레임이 그대로 살아 있다.
    ★ 이것은 「첫 인증이 지문을 바꾸는가」와 **다른 시험**이다 — 그쪽은 자리를 빼도
      통과한다(빈 목록 → 채워진 목록으로 어차피 달라지므로). 변이 검사가 실제로
      그렇게 통과했다(2026-08-19)."""
    from core import app_contract_gate as gate
    from core.baseline_build import fingerprint_for

    contract = _contract()
    inst = dp.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                              tenant_id=TENANT, scope_node_id=SCOPE,
                              entity_mode=ap.ENTITY_MODE_SYNTHETIC)
    b = dp.create_binding(instance_id=inst["instance_id"],
                          dataset_contract_key=CONTRACT_KEY,
                          provider=dpm.PROVIDER_FILE_SNAPSHOT,
                          config={"file_name": "a.csv", "column_map": {"a": "A"}},
                          tenant_id=TENANT, scope_node_id=SCOPE,
                          entity_mode=ap.ENTITY_MODE_SYNTHETIC)
    for step in ("validate", "approve", "activate"):
        getattr(sb, step)(dp, b["binding_id"])
    _write_release(canary, mode=ap.ENTITY_MODE_SYNTHETIC, contract=contract)
    _step_materialize(dp, contract)

    plane = ap.app_data_for(ap.AUDIENCE_PREVIEW)
    got = gate.data_fingerprint(REL, plane=plane)
    assert got not in (gate.NO_DATA, gate.UNREADABLE, ""), got
    #: ★★★ 빈 집합의 지문과 **같으면 안 된다** — 같다면 그 자리를 세지 않은 것이다.
    assert got != fingerprint_for([]), (
        "판이 없는 자리를 지문에서 뺐다 — 「결속은 있는데 판이 없다」가 "
        "「결속이 하나도 없다」와 같은 값이 됐다")
