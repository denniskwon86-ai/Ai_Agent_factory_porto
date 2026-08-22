"""★★★ [B2 / M0-3.3] 경로 계산 **제품 경로** 종단 — 라우트로 들어와서 계산이 돈다.

## 이 파일이 존재하는 이유

계산기·서비스 층은 `tests/test_calc_real_approval.py` 가 이미 시험한다. 여기서 고정하는
것은 **배선**이다 — 이 저장소에서 「코어가 있는 것」과 「제품이 호출하는 것」의 차이로
두 번 지적받았고, 계산 층은 바로 전까지 **시험만이 부르는 코드**였다.

고정하는 것:

  ① 라우트로 들어와서 **실제로 계산이 돈다**(대역 없음 — 원장·봉인·인증판 전부 실물)
  ② 호출자가 **승인·판·기준선·문맥을 넣을 수 없다** — 넣어도 서버 값이 이긴다
  ③ 관계 목록이 **경로의 간선**에서 나온다 — 빈 목록을 보내 관문을 비울 수 없다
  ④ 실패가 셋으로 갈린다: 장애 503 · 미승인 200+BLOCKED · 없는 경로 404
  ⑤ [G5] 계산 결속이 **안건 근거에 봉인**된다. `BLOCKED` 로는 안건이 안 만들어진다

## 주체를 세우는 방식

`app.dependency_overrides[current_principal]` + **실제 `resolve_scope()`**.
⚠️ `AccessScope` 를 손으로 만들지 않는다 — 그러면 판정기가 아니라 내가 답을 정한다
  (4.1c-B P1-1 에서 지적받은 패턴이다).
"""
import pytest

from core import app_policy
from core import calc_capability as cc
from core import demo_readiness as dr
from core import demo_vertical_slice as dv
from core import ontology_resolve
from core import path_calculation as pc
from core import path_calculation_service as svc_calc
from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation import store as dp
from core.ontology_runtime import ObjectRef, OntologyRuntime

SCOPE = "plant-afs-smelting-01"
DEPT = "smelting"
ACTOR = "runner@afs.invalid"
APPROVER = "approver@afs.invalid"

#: 첫 수직 경로 — 출하가 재고에, 재고가 계획에, 계획이 판매에 영향을 준다.
_CHAIN = (("shipment", "SHP-001", "inventory-snapshot", "INV-001"),
          ("inventory-snapshot", "INV-001", "production-plan", "PLAN-001"),
          ("production-plan", "PLAN-001", "sales-order", "SO-001"))


@pytest.fixture(scope="module")
def slice_data():
    return dv.build_slice(scope_node_id=SCOPE)


def _contract():
    return {
        "contract_id": "G2-FIRST-VERTICAL-ONTOLOGY", "contract_version": "1.0.0",
        "status": "APPROVED",
        "relation_types": [{"id": "AFFECTS", "name_ko": "영향을 줌",
                            "inverse": "AFFECTED_BY", "quantitative": True}],
        "constraints": [
            {"subject": f"dataset:{s}", "relation": "AFFECTS",
             "object": f"dataset:{o}", "evidence": ["승인된 지연 모형"],
             "calculation_ref": ref}
            for (s, _si, o, _oi), ref in zip(_CHAIN, pc.SEGMENTS)],
        "approval": {"approved_by": APPROVER, "decision_ledger_id": "ledger-model-v1",
                     "effective_from": "2026-01-01T00:00:00Z"},
    }


@pytest.fixture
def env(tmp_path, monkeypatch, slice_data):
    """격리 저장소 + 격리 원장 + **실제 조직도** + 실제 온톨로지 런타임.

    ⚠️ 조직도를 세우지 않으면 `resolve_scope()` 가 부트스트랩 예외로 미등록 사용자에게도
      전권을 준다 — 그 상태에서는 권한 시험이 전부 통과하고 아무것도 지키지 못한다."""
    import api.deps as deps
    import api.routes.baseline_control as bc
    import api.routes.calculation_control as cal
    import api.routes.data_preparation_control as dpc
    import core.org_directory as orgmod
    import core.scope_policy as sp
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory

    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)

    tenant, scope = dv.scope_of(slice_data)
    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    org.create_department(DEPT, "제련", scope_node_id=scope)
    org.upsert_user(ACTOR, "실행자", primary_dept_id=DEPT, actor="seed")
    org.set_user_roles(ACTOR, {DEPT: "member"}, actor="seed")
    org.upsert_user("viewer@afs.invalid", "열람자", primary_dept_id=DEPT, actor="seed")
    org.set_user_roles("viewer@afs.invalid", {DEPT: "viewer"}, actor="seed")
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": True})
    monkeypatch.setattr(orgmod, "org_directory", org)
    monkeypatch.setattr(deps, "org_directory", org)

    #: 문맥은 G1-C3 판정기가 이미 시험한다 — 여기서 두 벌로 시험하지 않는다.
    ctx = {"tenant_id": tenant, "entity_mode": "REAL", "scope_node_id": scope}
    monkeypatch.setattr(dpc, "viewing_context", lambda p: ctx)
    monkeypatch.setattr(cal, "viewing_context", lambda p: ctx)
    #: ⚠️ `baseline_control` 은 **자기 몫의 `_instance_or_404`** 를 들고 있다 — 같은 판정의
    #:   두 번째 사본이다. 그래서 문맥도 따로 패치해야 한다(사본이 있다는 증거이기도 하다).
    monkeypatch.setattr(bc, "viewing_context", lambda p: ctx)
    monkeypatch.setattr(cal, "visibility_block_reason", lambda p: "")

    #: ── 온톨로지 런타임(실물) ──────────────────────────────────────────
    def resolver(ref, rctx):
        return ontology_resolve.found(app_policy.ResourceScope(
            tenant_id=tenant, entity_mode="REAL", scope_node_id=scope,
            owner_dept_id=DEPT, binding_state=app_policy.BOUND))

    #: ★★★ 승인 판정기도 **제품 것**을 쓴다. 대역을 쓰면 「승인 → 계산」이 아니라
    #:   「승인 대역 → 계산」이 되고, 그것이 M0-3.2 에서 걷어낸 바로 그 모양이다.
    from core.ontology_resolvers import product_approval_resolver

    runtime = OntologyRuntime(str(tmp_path / "ontology.db"), resolver,
                              product_approval_resolver)
    #: 모형 계약 설치도 **실제 원장 사건**으로 승인한다. 대상은 계약 지문이다.
    contract = _contract()
    fp = runtime.validate_model_contract(contract)["contract_fingerprint"]
    model_ev = decision_ledger.append(
        event_type="ONTOLOGY_MODEL_APPROVED", subject_type="ontology_model_contract",
        subject_id=fp, actor_type="user", actor_id=APPROVER, decision="APPROVED",
        rationale="첫 수직 온톨로지 계약 승인", tenant_id=tenant, entity_mode="REAL")
    contract["approval"]["decision_ledger_id"] = model_ev["event_id"]
    runtime.install_model_contract(contract, APPROVER)
    monkeypatch.setattr(cal, "ontology_runtime", runtime)

    #: ── 자료(실물 정본 키트) ───────────────────────────────────────────
    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=tenant, scope_node_id=scope, entity_mode="REAL")
    for key in dv.SLICE_KEYS:
        rows, cols = slice_data[key]
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id=tenant,
            scope_node_id=scope, entity_mode="REAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv", workspace_root=str(tmp_path / "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})

    return {"store": store, "org": org, "ledger": decision_ledger, "runtime": runtime,
            "instance_id": inst["instance_id"], "tenant": tenant, "scope": scope,
            "slice": slice_data, "cal": cal}


def _client(env, user_id=ACTOR):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.deps import Principal, current_principal

    scope = env["org"].resolve_scope(user_id)
    app = FastAPI()
    app.include_router(env["cal"].router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id, scope=scope, requested_scope_node_id=env["scope"],
        session_id="sess-calc")
    return TestClient(app)


def _graph(env, approve=True):
    """관계 셋을 제안·상신·(선택적으로) 승인한다.

    ★★★ 승인은 **실제 원장 사건**으로 한다. 문자열 상수를 쓰면 온톨로지의 승인 관문이
      대역 위에서 통과하고, 계산기가 대조할 「묶인 사건」도 가짜가 된다."""
    rt = env["runtime"]
    subject = app_policy.Subject(user_id=APPROVER,
                                 scope=env["org"].resolve_scope(ACTOR),
                                 ctx={"tenant_id": env["tenant"], "entity_mode": "REAL",
                                      "scope_node_id": env["scope"]},
                                 session_id="sess-graph", blocked_reason="")
    from core.ontology_runtime import RelationProposal

    ids = []
    for (s_type, s_id, o_type, o_id), calc_ref in zip(_CHAIN, pc.SEGMENTS):
        prop = RelationProposal(
            subject=ObjectRef("dataset", s_type, s_id), relation_type_id="AFFECTS",
            object=ObjectRef("dataset", o_type, o_id), tenant_id=env["tenant"],
            enterprise_scope_id=env["scope"], entity_mode="REAL",
            owner_organization_id=DEPT, effective_from="2026-01-01T00:00:00Z",
            origin="derived", evidence_refs=("SNAPSHOT:LOG-02:v1",),
            #: ★ 승인된 산식 참조가 있어야 관계가 선다 — 계약이 그렇게 정한다.
            calculation_ref=calc_ref)
        made = rt.propose_relation(prop, "proposer@afs.invalid", subject)
        rid = made["relation_id"]
        rt.submit(rid, "proposer@afs.invalid", subject)
        if approve:
            #: ★ 원장에 **실제 승인 사건**을 남기고, 그 사건으로 승인한다. 온톨로지가
            #:   그것을 관계에 묶고(`ledger_correlation_id`), 계산기는 그 사건만 본다.
            ev = env["ledger"].append(
                event_type="ONTOLOGY_RELATION_APPROVED",
                subject_type="ontology_relation", subject_id=rid, actor_type="user",
                actor_id=APPROVER, decision="APPROVED",
                rationale="첫 수직 경로 관계 승인", tenant_id=env["tenant"],
                entity_mode="REAL")
            rt.approve(rid, APPROVER, ev["event_id"], subject)
        ids.append(rid)
    return ids


def _approve_capabilities(env, monkeypatch=None):
    """★★★ [M0-0] **실제 승인 경로**로 승인한다 — `cc.get` 을 패치하지 않는다.

    ⚠️⚠️ 앞 판은 `monkeypatch.setattr(cc, "get", ...)` 로 등록부를 갈아 끼웠다. 그것은
      「승인됐다면 어떻게 되는가」를 본 것이지 **승인 경로가 도는가**를 본 것이 아니다.
      대상 지문·유효기간·범위 결속은 하나도 검사되지 않았다.

    ⚠️ 격리된 저장소·원장에서만 부른다. 운영 등록부의 상태는 건드리지 않는다 —
      `cea.approve` 는 등록부 상수를 고치지 않고 **승인 기록**만 남긴다."""
    from core import calc_execution_approval as cea

    out = {}
    prop = cea.proposal(env["store"], instance_id=env["instance_id"],
                        tenant_id=env["tenant"], entity_mode="REAL",
                        scope_node_id=env["scope"])
    for item in prop["items"]:
        assert item["approvable"], item
        out[item["ref"]] = cea.approve(
            env["store"], ref=item["ref"], bound=item["binding"], actor=APPROVER,
            rationale="시연 한정 실행 승인")
    return out

def _seal_baseline(env):
    from core import calc_baseline as cb
    a = dv.assumptions(env["slice"])
    return cb.seal(env["store"], instance_id=env["instance_id"], tenant_id=env["tenant"],
                   entity_mode="REAL", scope_node_id=env["scope"], actor=APPROVER,
                   rationale="첫 수직 경로 시연 기준선",
                   sales_allocation=a["sales_allocation"],
                   recognition_span_days=a["recognition_span_days"],
                   baseline_recognition=a["baseline_recognition"])


def _body(env, **kw):
    body = {"roots": [{"namespace": "dataset", "object_type": "shipment",
                       "object_id": "SHP-001"}],
            "target_types": ["sales-order"], "relation_types": ["AFFECTS"],
            "as_of": dv.AS_OF, "instance_id": env["instance_id"],
            "assumptions": {k: v for k, v in dv.assumptions(env["slice"]).items()
                            if k in ("reserved_quantity_zero", "date_only_rule")}}
    body.update(kw)
    return body


def _decision_body(env, **kw):
    """[G5] 안건 입력. ★ 경영 수치는 **시뮬레이션**이 낸다 — 경로 계산의 지표를 그 칸에
    넣지 않는다(다른 집합이고, 넣으면 숫자를 지어내는 것이다)."""
    snaps = [s["snapshot_id"] for s in env["store"].list_snapshots(env["instance_id"])
             if s["state"] == m.DEMO_CERTIFIED]
    body = _body(env, title="구매 지연 영향", owner=ACTOR, due="2026-07-01",
                 snapshot_ids=sorted(snaps),
                 base_values={"production_qty": 100.0, "ending_inventory": 20.0,
                              "purchase_payment": 40.0, "ending_cash": 50.0,
                              "operating_profit": 12.0, "power_cost": 8.0,
                              "period_days": 30.0},
                 scenario_assumptions={"lead_time_days": 7.0})
    body.update(kw)
    return body


def _data(res):
    """★ 봉투를 벗긴다 — `{status, data}` 를 그대로 읽으면 `None` 이 나온다."""
    assert res.status_code == 200, f"{res.status_code} {res.text[:400]}"
    body = res.json()
    assert body.get("status") == "success", body
    return body["data"]


def _ready(env, monkeypatch):
    ids = _graph(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    return ids


# ── ① 라우트로 들어와서 실제로 계산이 돈다 ────────────────────────────────

def test_라우트로_들어와서_계산이_돈다(env, monkeypatch):
    """★★★ **이 파일의 존재 이유.** 종전에는 이 요청 자체가 없었다 — 계산 층은
    시험만이 부르는 코드였다."""
    ids = _ready(env, monkeypatch)
    got = _data(_client(env).post("/api/v1/calculation/path", json=_body(env)))

    assert got["status"] == pc.COMPLETE, got.get("blocked")
    #: ★ 정체성·지문·봉인 판이 응답에 실린다 — 「이 숫자는 무엇으로 만들었나」에 답한다.
    assert got["request_fingerprint"] and got["result_fingerprint"]
    assert set(got["used_snapshots"]) == set(pc.REQUIRED_DATASETS)
    assert set(got["segment_model_versions"]) == set(pc.SEGMENTS)
    #: ★★★ **관계 목록이 경로의 간선에서 나왔다** — 호출자는 하나도 적지 않았다.
    assert set(got["required_relation_ids"]) == set(ids)


def test_능력_승인이_없으면_막히고_그것은_오류가_아니다(env):
    """★ 「승인이 없다」는 **답**이다 — 200 + `BLOCKED` + 사유. 오류로 답하면 화면이
    다음에 무엇을 해야 하는지 말할 수 없다.

    ★ 관계는 승인됐지만 **산식 실행 승인**이 없는 상태다. 이것이 지금 제품의 실제
      상태이기도 하다(등록부 3종은 `IMPLEMENTED_UNAPPROVED`)."""
    _graph(env)
    _seal_baseline(env)
    got = _data(_client(env).post("/api/v1/calculation/path", json=_body(env)))
    assert got["status"] == pc.BLOCKED
    assert got["blocked"], "무엇이 없는지 말하지 않으면 「영향 없음」과 구별되지 않는다"


def test_관계_승인이_없으면_경로가_보이지_않는다(env, monkeypatch):
    """★★★ 승인 전 관계는 **그래프에 서지 않는다** — 계산 이전에 경로가 없다.

    ⚠️ 이것을 「계산이 막혔다」와 섞지 않는다. 둘은 다른 상태이고, 사용자가 해야 할
      일도 다르다(관계를 승인할 것인가 / 산식을 승인할 것인가)."""
    _graph(env, approve=False)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    res = _client(env).post("/api/v1/calculation/path", json=_body(env))
    assert res.status_code == 404, res.text[:300]


def test_철회된_관계_승인은_계산을_막는다(env, monkeypatch):
    """★★★ **철회는 온톨로지 행을 고치지 않는다.** 경로는 그대로 서 있고, 원장만 죽어
    있다 — 그 차이를 계산기가 봐야 한다."""
    ids = _ready(env, monkeypatch)
    row = env["runtime"].relation_evidence(
        app_policy.Subject(user_id=ACTOR, scope=env["org"].resolve_scope(ACTOR),
                           ctx={"tenant_id": env["tenant"], "entity_mode": "REAL",
                                "scope_node_id": env["scope"]},
                           session_id="s", blocked_reason=""),
        ids[0], dv.AS_OF)
    env["ledger"].append(
        event_type="ONTOLOGY_APPROVAL_REVOKED", subject_type="ontology_relation",
        subject_id=ids[0], actor_type="user", actor_id=APPROVER, decision="REVOKED",
        rationale="오류 발견", tenant_id=env["tenant"], entity_mode="REAL",
        parent_event_id=row["ledger_correlation_id"])
    got = _data(_client(env).post("/api/v1/calculation/path", json=_body(env)))
    assert got["status"] == pc.BLOCKED, "철회된 승인으로 계산이 돌면 안 된다"


def test_없는_경로_지문은_404다(env, monkeypatch):
    """⚠️ 경로를 지어낼 수 없다. 지문을 만들어 보내면 **없는 자원**이다."""
    _ready(env, monkeypatch)
    res = _client(env).post("/api/v1/calculation/path",
                            json=_body(env, path_fingerprint="fp-지어낸것"))
    assert res.status_code == 404, res.text[:300]


def test_기준선_봉인이_없으면_계산하지_않는다(env, monkeypatch):
    """⚠️⚠️ 빈 기준선으로 계산하면 모든 판매행이 `missing_baseline` 이 되고, 그것이
    화면에서 **「영향 없음」**으로 읽힌다. 그래서 요청 자체를 만들지 않는다."""
    _graph(env)
    _approve_capabilities(env, monkeypatch)
    res = _client(env).post("/api/v1/calculation/path", json=_body(env))
    assert res.status_code == 422, res.text[:300]
    assert "기준선" in res.text


# ── ② 호출자가 넣을 수 없는 것들 ──────────────────────────────────────────

def test_호출자는_승인_판_기준선_문맥을_넣을_수_없다(env, monkeypatch):
    """★★★ 이 라우트 설계의 전부다. **넣어도 무시된다** — 무시되는 것으로 끝나지 않고,
    서버가 파생한 값이 실제로 쓰였는지까지 본다."""
    _ready(env, monkeypatch)
    body = _body(env, relation_ids=[], relation_approvals={"REL_X": "evt_forged"},
                 sealed_snapshots={"INV-01": "ds_남의것"}, baseline_id="bl_남의것",
                 tenant_id="tenant_남의것", entity_mode="VIRTUAL",
                 scope_node_id="plant_남의것", path_model_version="0.0.1")
    got = _data(_client(env).post("/api/v1/calculation/path", json=body))

    assert got["status"] == pc.COMPLETE, got.get("blocked")
    #: ★ 관계는 경로에서 나왔다 — 빈 목록을 보냈는데도 셋이 요구된다.
    assert len(got["required_relation_ids"]) == len(_CHAIN)
    #: ★ 판은 저장소 인증판이다.
    assert "ds_남의것" not in set(got["used_snapshots"].values())
    #: ★ 판 버전은 계산기 상수다.
    assert got["path_model_version"] != "0.0.1"


def test_봉인된_가정은_호출자_값이_이기지_못한다(env, monkeypatch):
    """★ 배분·인식 규칙을 보내도 **봉인이 이긴다.** 「어느 기준선과 비교했는가」는
    주장이 아니라 봉인이어야 한다."""
    _ready(env, monkeypatch)
    c = _client(env)
    plain = _data(c.post("/api/v1/calculation/path", json=_body(env)))
    a = dict(_body(env)["assumptions"])
    a.update({"recognition_span_days": 999, "sales_allocation": {}})
    loud = _data(c.post("/api/v1/calculation/path", json=_body(env, assumptions=a)))

    assert plain["status"] == pc.COMPLETE and loud["status"] == pc.COMPLETE
    #: ★ 요청 지문까지 같다 — 호출자의 값이 **요청에 들어가지도 않았다**.
    assert loud["request_fingerprint"] == plain["request_fingerprint"]
    assert loud["result_fingerprint"] == plain["result_fingerprint"]


def test_남의_인스턴스는_404다(env, monkeypatch):
    """★★★ **문맥을 호출자가 주면 봉인 대조가 자기일관해진다** — 남의 조직 값을 함께
    적어 보내면 대조는 통과한다(대조는 불일치를 막지 허가를 주지 않는다).

    ⚠️ 그래서 문맥은 인스턴스 행에서 읽고, 인스턴스는 **보이는 범위 안에서만** 찾는다.
      없는 것과 못 보는 것을 같은 404 로 답한다."""
    _ready(env, monkeypatch)
    other = env["store"].create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(env["store"]),
        tenant_id=env["tenant"], scope_node_id="plant-남의공장", entity_mode="REAL")
    res = _client(env).post("/api/v1/calculation/path",
                            json=_body(env, instance_id=other["instance_id"]))
    assert res.status_code == 404, res.text[:300]


def test_열람자는_계산을_돌릴_수_없다(env, monkeypatch):
    """★ 승인된 자료로 경영 판단용 숫자를 내는 일이다 — viewer 가 눌러 만들 것이 아니다."""
    _ready(env, monkeypatch)
    res = _client(env, "viewer@afs.invalid").post("/api/v1/calculation/path",
                                                  json=_body(env))
    assert res.status_code == 403, f"{res.status_code} {res.text[:200]}"


# ── ③ [G5] 계산 결속이 안건까지 간다 ──────────────────────────────────────

def test_계산_결속이_안건_근거에_봉인된다(env, monkeypatch):
    """★★★ [B2→G5] 런타임 경로 + 숫자 안건은 **전면 차단**이었다(B1.2-1b). 차단을
    푸는 유일한 근거가 「계산기가 봉인한 결과」이고, 이 요청이 그 종단이다."""
    _ready(env, monkeypatch)
    got = _data(_client(env).post("/api/v1/calculation/path/decision",
                                  json=_decision_body(env)))

    assert got["calculation"]["status"] == pc.COMPLETE
    pkg = got["decision"]
    assert pkg and pkg["title"] == "구매 지연 영향"
    bound = pkg["evidence"]["calculation"]
    assert bound["result_fingerprint"] == got["calculation"]["result_fingerprint"]
    assert set(bound["used_snapshots"]) == set(pc.REQUIRED_DATASETS)
    assert pkg["briefing"], "안건은 사람이 읽을 수 있어야 한다"


def test_막힌_계산으로는_안건이_만들어지지_않는다(env):
    """⚠️⚠️ 계산되지 않은 경로 옆에 숫자를 놓으면 그 숫자가 답으로 읽힌다.

    ★ 그래도 **오류가 아니다** — 왜 막혔는지를 그대로 돌려 준다."""
    _graph(env)
    _seal_baseline(env)
    got = _data(_client(env).post("/api/v1/calculation/path/decision",
                                  json=_decision_body(env, title="x")))
    assert got["decision"] is None
    assert got["calculation"]["status"] == pc.BLOCKED
    assert got["calculation"]["blocked"]


# ── ④ 장애는 503 — 「자료 없음」으로 접지 않는다 ──────────────────────────

def test_인증판_원본이_바뀌면_503이다(env, monkeypatch):
    """★★★ 체크섬이 다르면 **읽지 못한 것**이다. 이것을 「자료 없음」으로 접으면 화면이
    「영향 없음」을 보여 주고, 확인되지 않은 상태가 확인된 답으로 바뀐다."""
    import io as _io

    _ready(env, monkeypatch)
    seals = svc_calc.loader.active_seals(env["store"], instance_id=env["instance_id"],
                                         contract_keys=pc.REQUIRED_DATASETS)
    row = env["store"].get_snapshot(sorted(seals.values())[0])
    with _io.open(row["raw_path"], "a", encoding="utf-8") as fh:
        fh.write("\n")
    res = _client(env).post("/api/v1/calculation/path", json=_body(env))
    assert res.status_code == 503, f"{res.status_code} {res.text[:200]}"


def test_온톨로지_장애는_503이다(env, monkeypatch):
    """⚠️ 경로를 못 읽었는데 「경로 없음」으로 답하면 승인된 관계를 지운 것과 같다."""
    from core.ontology_runtime import OntologyIntegrityError

    _ready(env, monkeypatch)

    def boom(*a, **kw):
        raise OntologyIntegrityError("scope store unavailable")

    monkeypatch.setattr(env["runtime"], "find_paths", boom)
    res = _client(env).post("/api/v1/calculation/path", json=_body(env))
    assert res.status_code == 503, f"{res.status_code} {res.text[:200]}"


# ── ⑤ [M0-5] 왜 지금 계산이 안 도는가 — 실패와 0건을 가른다 ────────────────

def _readiness(env, **q):
    from urllib.parse import urlencode
    return _data(_client(env).get("/api/v1/calculation/readiness?" + urlencode(q)))


def test_준비도가_관문별로_다음_할_일을_말한다(env):
    """★★★ [M0-5] 계산이 막히면 실행기가 사유를 주지만, 그것은 **시도한 뒤**에야 나온다.
    운영자가 시연 전에 「지금 무엇이 빠졌나」를 물을 곳이 필요했다."""
    got = _readiness(env, instance_id=env["instance_id"])
    by = {g["gate"]: g for g in got["gates"]}
    assert by["kit"]["state"] == dr.READY
    assert by["instance"]["state"] == dr.READY
    assert by["snapshots"]["state"] == dr.READY
    #: 아직 봉인·승인 전이다 — **사람이 할 일이 남았다**(장애가 아니다).
    assert by["baseline"]["state"] == dr.NOT_YET
    assert got["status"] == dr.NOT_YET
    #: ★ 다음에 할 일 **하나**를 뽑아 준다 — 목록만 주면 어디부터인지 모른다.
    assert got["next_action"]


def test_다_갖추면_준비됨이다(env, monkeypatch):
    _ready(env, monkeypatch)
    got = _readiness(env, instance_id=env["instance_id"])
    assert got["status"] == dr.READY, got["gates"]
    assert got["counts"]["not_yet"] == 0 and got["counts"]["failed"] == 0


def test_앞_관문이_안_서면_뒤는_판정하지_않는다(env):
    """⚠️ 확인하지 않은 것을 「아직 안 했다」로 적지 않는다 — 앞 관문을 풀면 이미 서
    있을 수도 있다. 그것을 결론으로 적으면 화면이 없는 일을 시킨다."""
    got = _readiness(env)          # instance_id 없음
    by = {g["gate"]: g for g in got["gates"]}
    assert by["instance"]["state"] == dr.NOT_YET
    for gate in ("snapshots", "baseline", "capabilities"):
        assert by[gate]["state"] == "UNKNOWN", by[gate]
    #: ★ 확인하지 않은 관문은 **남은 수에 넣지 않는다** — 그 수는 사실이 아니다.
    assert got["counts"]["not_yet"] == 1
    assert got["counts"]["unknown"] == 3


def test_원장을_못_읽으면_미승인이_아니라_실패다(env, monkeypatch):
    """★★★ **이 파일에서 가장 중요한 회귀.** 장애를 「승인 없음」으로 접으면 운영자는
    승인을 다시 요청하고, 몇 번을 해도 같다 — 아무도 저장소를 보러 가지 않는다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger

    _ready(env, monkeypatch)

    def boom(*a, **kw):
        raise DecisionLedgerError("ledger unavailable")

    monkeypatch.setattr(decision_ledger, "get_event_strict", boom)
    got = _readiness(env, instance_id=env["instance_id"])
    by = {g["gate"]: g for g in got["gates"]}
    #: 원장을 처음 읽는 관문(기준선)에서 드러난다 — 「봉인 없음」이 아니다.
    assert by["baseline"]["state"] == dr.FAILED, by["baseline"]
    assert "다시 시도" in by["baseline"]["next_action"]
    assert got["status"] == dr.FAILED, "하나라도 실패면 전체가 실패다"
    #: ★ 그리고 뒤 관문은 **판정하지 않는다** — 원장을 못 읽는데 승인을 논할 수 없다.
    assert by["capabilities"]["state"] == "UNKNOWN", by["capabilities"]


def test_실행_승인_확인_실패도_미승인이_아니다(env, monkeypatch):
    """⚠️ 「승인이 없다」와 「승인을 확인하지 못했다」를 가른다 — 운영자가 할 일이 다르다."""
    _ready(env, monkeypatch)

    def boom(ref, verifier=None):
        raise RuntimeError("ledger index unreadable")

    monkeypatch.setattr(dr.cc, "assert_executable", boom)
    got = _readiness(env, instance_id=env["instance_id"])
    by = {g["gate"]: g for g in got["gates"]}
    assert by["capabilities"]["state"] == dr.FAILED, by["capabilities"]
    assert got["status"] == dr.FAILED


def test_인증판을_못_세면_0건이_아니라_실패다(env, monkeypatch):
    """⚠️ 「인증판 0건」과 「인증판을 세지 못했다」는 다른 답이다."""
    _ready(env, monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("snapshot table unreadable")

    monkeypatch.setattr(svc_calc.loader, "active_seals", boom)
    got = _readiness(env, instance_id=env["instance_id"])
    by = {g["gate"]: g for g in got["gates"]}
    assert by["snapshots"]["state"] == dr.FAILED
    #: ★ 그리고 뒤 관문은 **판정하지 않는다** — 자료를 못 읽었는데 기준선을 논할 수 없다.
    assert by["baseline"]["state"] == "UNKNOWN"


def test_남의_인스턴스_준비도는_404다(env):
    """★ 준비도 응답으로 남의 자원의 존재를 알려 주지 않는다."""
    other = env["store"].create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(env["store"]),
        tenant_id=env["tenant"], scope_node_id="plant-남의공장", entity_mode="REAL")
    res = _client(env).get(
        f"/api/v1/calculation/readiness?instance_id={other['instance_id']}")
    assert res.status_code == 404, res.text[:200]


# ── ⑥ [M0-0] 승인 경로 — 사람이 누르기 전까지 아무것도 승인되지 않는다 ────

def _admin(env):
    """시스템 관리자 주체. ★ 실제 `resolve_scope()` 가 돌려주는 값을 쓴다."""
    env["org"].upsert_user("sysadmin@afs.invalid", "시스템관리자", primary_dept_id=DEPT,
                           is_admin=True, actor="seed")
    return _client(env, "sysadmin@afs.invalid")


def test_제안서는_아무것도_승인하지_않는다(env):
    """★★★ [M0-0] 이 화면은 **제안서**다. 부작용이 없고, 계산은 계속 `BLOCKED` 다."""
    from core import calc_execution_approval as cea

    _graph(env)
    _seal_baseline(env)
    got = _data(_admin(env).get(
        f"/api/v1/calculation/capabilities?instance_id={env['instance_id']}"))

    assert {i["ref"] for i in got["items"]} == set(pc.SEGMENTS)
    #: ★ 기본 범위는 시연 한정 — `DEMO/SYNTHETIC · VIRTUAL · 30일`.
    assert got["scope"]["data_kind"] == cea.DEFAULT_DATA_KIND
    assert got["scope"]["entity_mode"] == cea.DEFAULT_ENTITY_MODE
    assert got["valid_days"] == cea.DEFAULT_VALID_DAYS
    #: ★ 화면이 보여 줄 것 — 정의·단위·부호.
    first = got["items"][0]
    assert first["definition"]["outputs"][0]["unit"] in cc.UNITS
    assert first["definition"]["outputs"][0]["direction"] in cc.DIRECTIONS
    assert first["state"] == cc.IMPLEMENTED_UNAPPROVED
    assert first["binding_fingerprint"]
    #: ★★★ **아무것도 승인되지 않았다.**
    assert got["approvals"] == []
    assert cea.list_approvals(env["store"]) == []
    assert _data(_client(env).post("/api/v1/calculation/path",
                                   json=_body(env)))["status"] == pc.BLOCKED


def test_제안서도_시스템_관리자만_본다(env):
    """★ 제안서는 결속 지문·인증판 id 를 보여 준다 — 관리자 화면이다."""
    _graph(env)
    _seal_baseline(env)
    url = f"/api/v1/calculation/capabilities?instance_id={env['instance_id']}"
    env["org"].upsert_user("dataadmin3@afs.invalid", "데이터관리자", primary_dept_id=DEPT,
                           is_data_admin=True, actor="seed")
    for who in ("dataadmin3@afs.invalid", ACTOR, "viewer@afs.invalid"):
        res = _client(env, who).get(url)
        assert res.status_code == 403, f"{who}: {res.status_code} {res.text[:160]}"
    assert _admin(env).get(url).status_code == 200


def test_시스템_관리자만_누를_수_있다(env):
    """★★★ 데이터 관리자·조직 관리자·프로젝트 관리자는 못 누른다.

    ⚠️ 「이 산식으로 만든 숫자를 회의에 올려도 되는가」를 정하는 일이고, 되돌려도 이미
      그 숫자를 본 사람이 있다."""
    _graph(env)
    _seal_baseline(env)
    env["org"].upsert_user("dataadmin@afs.invalid", "데이터관리자", primary_dept_id=DEPT,
                           is_data_admin=True, actor="seed")
    env["org"].upsert_user("orgadmin@afs.invalid", "조직관리자", primary_dept_id=DEPT,
                           actor="seed")
    env["org"].set_user_roles("orgadmin@afs.invalid", {DEPT: "manager"}, actor="seed")
    body = {"instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인"}
    for who in ("dataadmin@afs.invalid", "orgadmin@afs.invalid", ACTOR,
                "viewer@afs.invalid"):
        res = _client(env, who).post("/api/v1/calculation/capabilities/approve",
                                     json=body)
        assert res.status_code == 403, f"{who}: {res.status_code} {res.text[:160]}"
    #: ★ 그리고 아무 승인도 안 남았다 — 403 이 났는데 사건이 남으면 안 된다.
    from core import calc_execution_approval as cea
    assert cea.list_approvals(env["store"]) == []


def test_누르면_능력마다_별도_원장_사건이_남는다(env):
    """★★★ 화면에서 셋을 한 번에 골라도 원장에는 **셋**으로 남는다.

    ⚠️ 하나를 철회할 때 나머지가 함께 죽으면 안 되고, 「무엇을 승인했나」가 능력별로
      답해져야 한다."""
    from core import calc_execution_approval as cea

    _graph(env)
    _seal_baseline(env)
    got = _data(_admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "entity_mode": "REAL"}))

    assert len(got["approved"]) == len(pc.SEGMENTS)
    events = env["ledger"].list_events(event_type=cea.APPROVED_EVENT)
    assert len(events) == len(pc.SEGMENTS), "능력별로 갈라 남기지 않았다"
    #: ★ 대상이 서로 다르다 — 하나의 사건이 셋을 덮지 않는다.
    assert len({e["subject_id"] for e in events}) == len(pc.SEGMENTS)
    #: ★ 사유·행위자가 남는다.
    assert all(e["actor_id"] == "sysadmin@afs.invalid" for e in events)
    assert all("시연" in str(e["rationale"]) for e in events)


def test_사유_없이는_누를_수_없다(env):
    _graph(env)
    _seal_baseline(env)
    res = _admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "  "})
    assert res.status_code == 422, res.text[:200]


def test_재시도는_멱등이다(env):
    """⚠️ 재시도가 승인 사건을 쌓으면 원장이 「몇 번 승인했나」로 오염된다."""
    from core import calc_execution_approval as cea

    _graph(env)
    _seal_baseline(env)
    c = _admin(env)
    body = {"instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
            "entity_mode": "REAL"}
    first = _data(c.post("/api/v1/calculation/capabilities/approve", json=body))
    again = _data(c.post("/api/v1/calculation/capabilities/approve", json=body))
    assert all(a["idempotent"] for a in again["approved"])
    assert ([a["ledger_event_id"] for a in again["approved"]]
            == [a["ledger_event_id"] for a in first["approved"]])
    assert len(env["ledger"].list_events(event_type=cea.APPROVED_EVENT)) == len(pc.SEGMENTS)


def test_화면이_본_조건이_바뀌면_거부한다(env):
    """★★★ 사람이 읽고 누르는 사이에 판이 새로 인증될 수 있다 — 그때 승인되는 것은
    **읽은 것이 아니다.**"""
    _graph(env)
    _seal_baseline(env)
    res = _admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "seen_fingerprints": {pc.SEGMENTS[0]: "옛지문"}})
    assert res.status_code == 409, res.text[:200]


def test_승인하면_계산이_돈다(env):
    """★★★ [M0-0 → B2] **승인 직후 실제 계산.** 사용자 지시의 검증 ②."""
    _graph(env)
    _seal_baseline(env)
    assert _data(_client(env).post("/api/v1/calculation/path",
                                   json=_body(env)))["status"] == pc.BLOCKED
    _data(_admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "entity_mode": "REAL"}))
    got = _data(_client(env).post("/api/v1/calculation/path", json=_body(env)))
    assert got["status"] == pc.COMPLETE, got.get("blocked")


def test_철회하면_즉시_다시_막힌다(env):
    _graph(env)
    _seal_baseline(env)
    c = _admin(env)
    made = _data(c.post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "entity_mode": "REAL"}))["approved"]
    assert _data(_client(env).post("/api/v1/calculation/path",
                                   json=_body(env)))["status"] == pc.COMPLETE
    res = c.post(f"/api/v1/calculation/capabilities/{made[0]['approval_id']}/revoke",
                 json={"reason": "재검토"})
    assert res.status_code == 200, res.text[:200]
    assert _data(_client(env).post("/api/v1/calculation/path",
                                   json=_body(env)))["status"] == pc.BLOCKED


def test_시스템_관리자만_철회할_수_있다(env):
    """★★★ 철회도 시스템 관리자만. 남이 켠 계산을 아무나 끄면 시연 도중에 화면이
    멈추고, 「누가 껐나」에 답할 수 없다."""
    _graph(env)
    _seal_baseline(env)
    made = _data(_admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "entity_mode": "REAL"}))["approved"]
    url = f"/api/v1/calculation/capabilities/{made[0]['approval_id']}/revoke"
    env["org"].upsert_user("dataadmin2@afs.invalid", "데이터관리자", primary_dept_id=DEPT,
                           is_data_admin=True, actor="seed")
    for who in ("dataadmin2@afs.invalid", ACTOR, "viewer@afs.invalid"):
        res = _client(env, who).post(url, json={"reason": "임의 철회"})
        assert res.status_code == 403, f"{who}: {res.status_code} {res.text[:160]}"
    #: ★ 그리고 계산은 그대로 돈다 — 403 이 났는데 철회가 걸리면 안 된다.
    assert _data(_client(env).post("/api/v1/calculation/path",
                                   json=_body(env)))["status"] == pc.COMPLETE


def test_철회_사유_없이는_철회할_수_없다(env):
    _graph(env)
    _seal_baseline(env)
    c = _admin(env)
    made = _data(c.post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": env["instance_id"], "rationale": "시연 한정 실행 승인",
        "entity_mode": "REAL"}))["approved"]
    res = c.post(f"/api/v1/calculation/capabilities/{made[0]['approval_id']}/revoke",
                 json={"reason": ""})
    assert res.status_code == 422, res.text[:200]


def test_없는_인스턴스로는_승인할_수_없다(env):
    """★ 승인은 **어느 자료로 계산할지**가 정해진 뒤에만 가능하다.

    ⚠️ 플랫폼 관리자는 설계상 `unrestricted` 다 — 범위로는 걸리지 않는다. 여기서 막는
      것은 「그런 인스턴스가 없다」이고, 범위 통제는 일반 사용자 경로가 진다."""
    _graph(env)
    _seal_baseline(env)
    res = _admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": "ki_없는것", "rationale": "시연 한정 실행 승인"})
    assert res.status_code == 404, res.text[:200]


def test_인증판이_없으면_승인할_수_없다(env):
    """★★★ 무엇으로 계산할지 모르는 채 승인하면 그 승인은 **아무 판에나** 붙는다."""
    _graph(env)
    _seal_baseline(env)
    other = env["store"].create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(env["store"]),
        tenant_id=env["tenant"], scope_node_id="plant-빈공장", entity_mode="REAL")
    res = _admin(env).post("/api/v1/calculation/capabilities/approve", json={
        "instance_id": other["instance_id"], "rationale": "시연 한정 실행 승인"})
    assert res.status_code == 422, res.text[:200]
    assert "인증판" in res.text
