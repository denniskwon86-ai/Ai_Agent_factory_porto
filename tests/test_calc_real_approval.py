"""★★★ [G2 M0-3.2] **실제 원장 승인으로** 계산이 도는가 — 대역을 걷어낸다.

## 앞 카나리와 무엇이 다른가

앞 카나리는 이렇게 통과했다:

    ledger_verifier=lambda cap: True
    relation_verifier=lambda r, e: True
    relation_approvals={"REL_...": "evt_rel_1"}      ← 호출자가 적어 보낸 값

즉 「승인 → 계산」이 아니라 **「승인 대역 → 계산」**이었다. 그리고 관계·승인 사건은
호출자 자기진술이었다 — 이 저장소가 반복해서 지운 바로 그 패턴이다.

★ 이 파일은 **실제 원장 사건을 만들고**, 서버가 그것을 찾아 요청을 산출하고, 실제
  검증기로 계산이 도는지 본다. 대역은 하나도 없다.

★ [M0-3.2b] `sales_allocation`·`recognition_span_days`·`baseline_recognition`·
  `baseline_id` 도 이제 **봉인된 계산 기준선**에서 온다. 호출자가 넣을 수 없다.

⚠️ 아직 남은 것: 관계 승인 때 봉인한 판이 아니라 **「지금 최신 인증판」**을 쓴다(M1 부채).
"""
import pytest

from core import calc_capability as cc
from core import demo_vertical_slice as dv
from core import path_calculation as pc
from core import path_calculation_service as svc_calc
from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation import store as dp

SCOPE = "plant-afs-smelting-01"
ACTOR = "approver@afs.invalid"
RELATIONS = ("REL_SHIPMENT_AFFECTS_INVENTORY", "REL_INVENTORY_AFFECTS_PLAN",
             "REL_PLAN_AFFECTS_SALES")


@pytest.fixture(scope="module")
def slice_data():
    return dv.build_slice(scope_node_id=SCOPE)


@pytest.fixture
def env(tmp_path, monkeypatch, slice_data):
    """격리 저장소 + **격리 원장.** 실제 사건을 여기에 쌓는다."""
    from core.decision_ledger import decision_ledger
    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)
    tenant, scope = dv.scope_of(slice_data)

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
    return {"store": store, "instance_id": inst["instance_id"], "tenant": tenant,
            "scope": scope, "slice": slice_data, "ledger": decision_ledger}


def _ready(env, monkeypatch=None, relations=RELATIONS):
    """관계 승인 + 기준선 봉인(+선택적으로 계산 능력 승인)."""
    made = _approve_relations(env, relations=relations)
    _seal_baseline(env)
    if monkeypatch is not None:
        _approve_capabilities(env, monkeypatch)
    return made


def _approve_relations(env, relations=RELATIONS):
    """관계 승인 **실제 사건**을 남긴다."""
    out = {}
    for rel in relations:
        ev = env["ledger"].append(
            event_type="ONTOLOGY_RELATION_APPROVED", subject_type="ontology_relation",
            subject_id=rel, actor_type="user", actor_id=ACTOR,
            decision="APPROVED", rationale="첫 수직 경로 관계 승인",
            tenant_id=env["tenant"], entity_mode="REAL")
        out[rel] = ev["event_id"]
    #: ★ 제품에서는 이 결속이 **경로의 간선**에서 온다(온톨로지가 승인 때 묶어 둔다).
    #:   여기서는 경로 없이 코어를 부르므로 방금 만든 사건을 그대로 이어 둔다.
    env["bindings"] = dict(out)
    return out


def _approve_capabilities(env, monkeypatch):
    """계산 능력 실행 승인 **실제 사건**을 남기고 등록부를 그 사건에 잇는다.

    ⚠️ 제품 등록부의 `state` 는 건드리지 않는다 — 상태 전환은 배포 결정이다. 여기서는
      「승인이 나면 어떻게 되는가」를 미리 확인한다."""
    approved = {}
    for ref in pc.SEGMENTS:
        base = cc.get(ref)
        rec = svc_calc.approve_capability(
            ref, actor=ACTOR, rationale="MVP 3종 실행 승인",
            tenant_id=env["tenant"], entity_mode="REAL")
        approved[ref] = cc.Capability(**{**base.__dict__, "state": cc.APPROVED,
                                         "blocked_reason": "",
                                         "ledger_event_id": rec["event_id"]})
    monkeypatch.setattr(cc, "get", lambda ref: approved.get(ref) or cc._REGISTRY[ref])
    return approved


def _seal_baseline(env, **over):
    """계산 기준선을 **봉인한다**(저장소 + 원장).

    ⚠️ 앞 판은 배분·인식규칙·기준 인식일을 호출자가 요청에 넣었다 — 지문에 들어가긴
      했지만 「어디서 왔는가」가 없으면 근거가 아니다."""
    from core import calc_baseline as cb
    a = dv.assumptions(env["slice"])
    args = dict(sales_allocation=a["sales_allocation"],
                recognition_span_days=a["recognition_span_days"],
                baseline_recognition=a["baseline_recognition"])
    args.update(over)
    return cb.seal(env["store"], instance_id=env["instance_id"],
                   tenant_id=env["tenant"], entity_mode="REAL",
                   scope_node_id=env["scope"], actor=ACTOR,
                   rationale="첫 수직 경로 시연 기준선", **args)


def _build(env, bindings=None, **kw):
    """★ `relation_bindings` 는 **경로의 간선**에서 온다(`{관계: 승인 사건}`).

    ⚠️ 여기서는 경로 없이 코어를 직접 부르므로 원장에 남긴 사건을 그대로 쓴다. 제품
      경로가 정말 간선에서 뽑는지는 `tests/test_calculation_api.py` 가 고정한다."""
    args = dict(query_id="q-real", path_fingerprint="pf-real",
                relation_bindings=(bindings if bindings is not None
                                   else dict(env.get("bindings")
                                             or {r: "" for r in RELATIONS})),
                instance_id=env["instance_id"],
                tenant_id=env["tenant"], entity_mode="REAL", scope_node_id=env["scope"],
                as_of=dv.AS_OF, actor=ACTOR,
                #: ★ 기준선이 정하지 않는 것만 남긴다(날짜 규칙·예약 가정).
                assumptions={k: v for k, v in dv.assumptions(env["slice"]).items()
                             if k in ("reserved_quantity_zero", "date_only_rule")})
    args.update(kw)
    return svc_calc.build_request(env["store"], **args)


# ── ① 서버가 승인을 원장에서 찾는다 ─────────────────────────────────────

def test_서버가_관계_승인을_원장에서_찾는다(env):
    """★★★ 앞 판은 호출자가 `{관계: 사건}` 을 적어 보냈다 — 사건 id 를 아는 사람이면
    아무 값이나 넣을 수 있었다."""
    made = _approve_relations(env)
    _seal_baseline(env)
    req = _build(env)
    assert req.relation_approvals == made
    assert set(req.required_relation_ids) == set(RELATIONS)


def test_승인이_없는_관계는_목록에_들어오지_않는다(env):
    """⚠️ 없는 승인을 지어내지 않는다. 실행기가 경로 집합과 대조해 `BLOCKED` 로 답한다.

    ★ 승인이 없는 관계는 결속에 **빈 사건**으로 들어온다 — 키는 남고 값이 없다.
      경로에는 있는 관계이기 때문이다."""
    made = _approve_relations(env, relations=RELATIONS[:2])
    _seal_baseline(env)
    req = _build(env, bindings={**{r: "" for r in RELATIONS}, **made})
    assert set(req.relation_approvals) == set(RELATIONS[:2])
    assert set(req.required_relation_ids) == set(RELATIONS), (
        "요구 집합이 함께 줄면 실행기의 일치 검사가 무력해진다")


def test_봉인_판을_저장소에서_산출한다(env):
    """★ 호출자가 판 id 를 적어 보내지 않는다 — 그러면 남의 판을 적을 수 있다."""
    _approve_relations(env)
    _seal_baseline(env)
    req = _build(env)
    assert set(req.sealed_snapshots) == set(pc.REQUIRED_DATASETS)
    for sid in req.sealed_snapshots.values():
        row = env["store"].get_snapshot(sid)
        assert row["state"] == m.DEMO_CERTIFIED
        assert row["scope_node_id"] == env["scope"]


# ── ② 실제 검증기로 계산이 돈다 ─────────────────────────────────────────

def test_실제_원장_승인으로_계산이_완주한다(env, monkeypatch):
    """★★★ **M0-3.2 의 증거.** 대역이 하나도 없다."""
    _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    assert got["result_fingerprint"]


def test_계산_능력_승인이_없으면_BLOCKED_다(env):
    """★★★ **대조군.** 관계는 승인됐지만 산식 실행 승인이 없다 — 둘은 다른 결정이다."""
    _approve_relations(env)
    _seal_baseline(env)
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}


def test_관계_승인이_철회되면_BLOCKED_다(env, monkeypatch):
    """★★★ 승인은 **지금도 유효한가**를 매번 묻는다 — 철회는 등록부를 고치지 않는다."""
    made = _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    assert svc_calc.run(env["store"], _build(env), actor=ACTOR)["status"] == pc.COMPLETE

    rel = RELATIONS[0]
    env["ledger"].append(
        event_type="ONTOLOGY_APPROVAL_REVOKED", subject_type="ontology_relation",
        subject_id=rel, actor_type="user", actor_id=ACTOR, decision="REVOKED",
        rationale="근거 미비", parent_event_id=made[rel],
        tenant_id=env["tenant"], entity_mode="REAL")
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED, "철회했는데 계속 계산된다"


def test_산식이_바뀌면_실행_승인이_죽는다(env, monkeypatch):
    """★★★ 대상은 **참조 + 산식 판의 지문**이다.

    ⚠️ 참조 이름만 대상으로 삼으면 산식을 고쳐도 옛 승인이 유효해 보인다 — 그것이
      「같은 이름 다른 계산」이고, 검증 없는 숫자가 승인 아래 숨는 길이다."""
    _approve_relations(env)
    _seal_baseline(env)
    approved = _approve_capabilities(env, monkeypatch)
    assert svc_calc.run(env["store"], _build(env), actor=ACTOR)["status"] == pc.COMPLETE

    #: 산식 판만 올린다 — 승인 사건은 그대로다.
    ref = pc.SEGMENTS[0]
    bumped = cc.Capability(**{**approved[ref].__dict__, "model_version": "1.0.1"})
    monkeypatch.setattr(cc, "get",
                        lambda r: (bumped if r == ref
                                   else approved.get(r) or cc._REGISTRY[r]))
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED, "산식이 바뀌었는데 옛 승인으로 계산된다"


def test_실행_승인이_철회되면_BLOCKED_다(env, monkeypatch):
    _approve_relations(env)
    _seal_baseline(env)
    approved = _approve_capabilities(env, monkeypatch)
    ref = pc.SEGMENTS[0]
    env["ledger"].append(
        event_type=svc_calc.CAPABILITY_REVOKED, subject_type=svc_calc.CAPABILITY_SUBJECT,
        subject_id=svc_calc.capability_subject(approved[ref]), actor_type="user", actor_id=ACTOR,
        decision="REVOKED", rationale="재검토",
        parent_event_id=approved[ref].ledger_event_id,
        tenant_id=env["tenant"], entity_mode="REAL")
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED


def test_승인자가_아닌_사람도_계산할_수_있다(env, monkeypatch):
    """★★★ [2026-08-22] **앞 판은 여기서 정반대를 고정하고 있었다.**

    종전 시험의 이름은 「다른 사람의 관계 승인은 인정되지 않는다」였고, 실제로
    `relation_approvals == {}` 를 요구했다. 그 규칙대로면 **관계를 직접 승인한 사람만
    계산할 수 있다** — 제품 라우트를 처음 돌렸을 때 모든 계산이 그것으로 막혔다.

    ⚠️⚠️ 왜 그때는 옳아 보였나: `product_approval_resolver` 의 ④ 는 「승인 사건의
      행위자가 이 사람인가」를 본다. 그 판정기는 **승인 행위를 기록할 때** 쓰라고 만든
      것이고, 거기서는 요청자 = 승인자다. 계산은 승인 행위가 아니다 — 묻는 것은
      「이 관계가 승인됐는가」이지 「내가 승인했는가」가 아니다.

    ★ 같은 판단이 `capability_verifier` 머리말에는 이미 적혀 있었다(④를 넣지 않는 이유).
      옆 함수가 반대로 하고 있었고, 이 시험이 그것을 계약으로 굳혀 두었다."""
    _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    req = _build(env, actor="남@afs.invalid")
    assert set(req.relation_approvals) == set(RELATIONS), (
        "승인자 본인만 계산할 수 있으면 제품에서 아무도 계산하지 못한다")


def test_다른_관계의_승인_사건은_인정되지_않는다(env, monkeypatch):
    """★★★ 행위자 대조를 뺀 자리를 **무엇이 대신하는가.**

    ⚠️ 판정기는 사건의 `subject_id` 가 그 관계인지 본다. 그래서 결속을 바꿔 넣어도
      「같은 관계의 다른 살아 있는 승인」밖에 넣을 수 없다."""
    made = _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    #: 첫 관계 자리에 **셋째 관계의 승인 사건**을 넣는다.
    req = _build(env, bindings={**made, RELATIONS[0]: made[RELATIONS[2]]})
    assert RELATIONS[0] not in req.relation_approvals, (
        "다른 관계의 승인이 이 관계의 근거가 됐다")


def test_승인_아닌_사건은_인정되지_않는다(env, monkeypatch):
    """⚠️ 목적 전용 유형이 아니면 승인이 아니다 — 범용 결정 사건을 재사용하지 않는다."""
    made = _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    other = env["ledger"].append(
        event_type="ONTOLOGY_RELATION_RETIRED", subject_type="ontology_relation",
        subject_id=RELATIONS[0], actor_type="user", actor_id=ACTOR,
        decision="RETIRED", rationale="폐기", tenant_id=env["tenant"],
        entity_mode="REAL")
    req = _build(env, bindings={**made, RELATIONS[0]: other["event_id"]})
    assert RELATIONS[0] not in req.relation_approvals

def test_원장_장애는_BLOCKED_가_아니라_장애다(env, monkeypatch):
    """★★★ 「못 읽었다」를 「승인 없음」으로 접으면 장애 중에 모든 계산이 「아직 준비되지
    않았다」로 보이고, 아무도 저장소를 보러 가지 않는다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    req = _build(env)

    def _boom(*a, **k):
        raise DecisionLedgerError("원장 장애(주입)")

    monkeypatch.setattr(decision_ledger, "get_event_strict", _boom, raising=False)
    with pytest.raises(Exception) as e:
        svc_calc.run(env["store"], req, actor=ACTOR)
    assert "원장" in str(e.value) or "확인하지 못했" in str(e.value)


def test_승인_사유_없이는_실행_승인을_남길_수_없다(env):
    """⚠️ 「왜 이 산식으로 계산해도 되는가」에 답할 수 없는 승인은 나중에 아무도 뒤집을
    수 없다."""
    with pytest.raises(svc_calc.PathRequestError, match="사유"):
        svc_calc.approve_capability(pc.SEGMENTS[0], actor=ACTOR, rationale="",
                                    tenant_id=env["tenant"])


def test_배분과_기준선은_봉인에서만_온다(env):
    """★★★ [M0-3.2b] 호출자가 배분·기준선을 넣을 수 **없다.**

    ⚠️ 앞 판은 요청에 그대로 실렸다. 지문에 들어가긴 했지만 「어디서 왔는가」가 없으면
      근거가 아니다 — 이 저장소가 반복해서 지운 자기진술이다."""
    _approve_relations(env)
    sealed = _seal_baseline(env)
    req = _build(env)
    assert req.baseline_id == sealed["build_id"]
    assert req.baseline_fingerprint == sealed["fingerprint"]
    a = dv.assumptions(env["slice"])
    assert req.assumptions["sales_allocation"] == a["sales_allocation"]
    assert req.assumptions["recognition_span_days"] == a["recognition_span_days"]


def test_호출자가_배분을_밀어넣어도_봉인이_이긴다(env):
    """★★★ 겹치면 **기준선이 이긴다** — 봉인의 뜻이 그것이다.

    ⚠️ 호출자 값이 이기면 봉인은 장식이 된다."""
    _approve_relations(env)
    _seal_baseline(env)
    req = _build(env, assumptions={"sales_allocation": {"SO-가짜": "PPL-가짜"},
                                   "reserved_quantity_zero": True})
    assert "SO-가짜" not in req.assumptions["sales_allocation"]


def test_봉인된_기준선이_없으면_계산_요청을_만들지_않는다(env):
    """★★★ 빈 기준선으로 계산하면 모든 판매행이 `missing_baseline` 이 되고, 그것이
    화면에서 **「영향 없음」**으로 읽힌다."""
    _approve_relations(env)
    with pytest.raises(svc_calc.PathRequestError, match="계산 기준선이 없습니다"):
        _build(env)


def test_기준선_행을_직접_고치면_봉인이_깨진_것이다(env):
    """★★★ 지문을 다시 계산해 대조한다 — 행을 직접 고치는 경로는 실제로 있다
    (마이그레이션·시드·직접 SQL)."""
    from core import calc_baseline as cb
    _approve_relations(env)
    sealed = _seal_baseline(env)
    with env["store"].transaction() as conn:
        conn.execute(
            "UPDATE baseline_builds SET detail_json=json_set(detail_json,"
            " '$.recognition_span_days.\"SO-001999-10\"', '999') WHERE build_id=?",
            (sealed["build_id"],))
    with pytest.raises(cb.BaselineError, match="봉인 지문과 다릅니다"):
        cb.active(env["store"], instance_id=env["instance_id"],
                  tenant_id=env["tenant"], entity_mode="REAL",
                  scope_node_id=env["scope"])


def test_기준선을_철회하면_계산_요청을_만들지_않는다(env):
    """⚠️ 행만 내리면 원장에는 봉인만 남아 여전히 유효해 보인다 — 자식 사건을 남긴다."""
    from core import calc_baseline as cb
    _approve_relations(env)
    sealed = _seal_baseline(env)
    assert _build(env).baseline_id == sealed["build_id"]
    assert cb.revoke(env["store"], build_id=sealed["build_id"], actor=ACTOR,
                     reason="배분 재검토")
    with pytest.raises(svc_calc.PathRequestError, match="계산 기준선이 없습니다"):
        _build(env)


def test_반쪽_기준선은_봉인할_수_없다(env):
    """★★★ 배분에 있는 판매행은 인식 기간과 기준 인식일이 **함께** 있어야 한다.

    ⚠️ 반쪽으로 봉인하면 계산이 그 행을 `missing_baseline` 으로 답하고, 그때는 봉인
      자체가 반쪽이었던 것이다 — 셋은 함께 검토되고 함께 승인된다."""
    from core import calc_baseline as cb
    with pytest.raises(cb.BaselineError, match="반쪽"):
        _seal_baseline(env, recognition_span_days={})


def test_사유_없이는_기준선을_봉인할_수_없다(env):
    from core import calc_baseline as cb
    a = dv.assumptions(env["slice"])
    with pytest.raises(cb.BaselineError, match="사유"):
        cb.seal(env["store"], instance_id=env["instance_id"], tenant_id=env["tenant"],
                entity_mode="REAL", scope_node_id=env["scope"], actor=ACTOR,
                rationale="", sales_allocation=a["sales_allocation"],
                recognition_span_days=a["recognition_span_days"],
                baseline_recognition=a["baseline_recognition"])


def test_새_기준선을_봉인하면_옛_것은_내려간다(env):
    """⚠️ 둘이 살아 있으면 어느 것으로 계산했는지 말할 수 없다."""
    from core import calc_baseline as cb
    _approve_relations(env)
    first = _seal_baseline(env)
    a = dv.assumptions(env["slice"])
    bumped = {k: "45" for k in a["recognition_span_days"]}
    second = _seal_baseline(env, recognition_span_days=bumped)
    assert first["build_id"] != second["build_id"]
    got = cb.active(env["store"], instance_id=env["instance_id"],
                    tenant_id=env["tenant"], entity_mode="REAL",
                    scope_node_id=env["scope"])
    assert got["build_id"] == second["build_id"]
    assert _build(env).baseline_fingerprint == second["fingerprint"]


def test_다른_조직의_기준선은_쓰지_않는다(env):
    from core import calc_baseline as cb
    _seal_baseline(env)
    with pytest.raises(cb.BaselineError, match="이 문맥의 것이 아닙니다"):
        cb.active(env["store"], instance_id=env["instance_id"],
                  tenant_id=env["tenant"], entity_mode="REAL",
                  scope_node_id="plant-afs-other-99")


def test_철회_사건으로_승인을_주장할_수_없다(env, monkeypatch):
    """★★★ [변이 시험에서 발견] 승인 사건 **유형** 검사를 지워도 잡히지 않았다 — 지문
    대조가 뒤에서 걸렀기 때문이다(등가).

    ⚠️ 판별력은 **같은 지문을 가진 다른 유형의 사건**에서 생긴다. 철회 사건의 대상 지문은
      원 승인과 같으므로, 유형을 보지 않으면 **철회 사건 id 로 승인을 주장**할 수 있다.
      「이 산식은 철회됐다」는 기록이 「이 산식은 승인됐다」로 읽히는 것이다."""
    _approve_relations(env)
    _seal_baseline(env)
    approved = _approve_capabilities(env, monkeypatch)
    ref = pc.SEGMENTS[0]
    subject = svc_calc.capability_subject(approved[ref])
    revoke = env["ledger"].append(
        event_type=svc_calc.CAPABILITY_REVOKED, subject_type=svc_calc.CAPABILITY_SUBJECT,
        subject_id=subject, actor_type="user", actor_id=ACTOR, decision="REVOKED",
        rationale="재검토", parent_event_id=approved[ref].ledger_event_id,
        tenant_id=env["tenant"], entity_mode="REAL")

    #: 철회 사건 id 를 승인으로 내민다.
    faked = cc.Capability(**{**approved[ref].__dict__,
                             "ledger_event_id": revoke["event_id"]})
    monkeypatch.setattr(cc, "get",
                        lambda r: (faked if r == ref
                                   else approved.get(r) or cc._REGISTRY[r]))
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED, "철회 사건으로 승인이 인정됐다"


# ── ③ [변이 시험에서 발견] 앞선 관문이 가리던 자리 ──────────────────────

def test_행은_살아_있는데_원장에_철회가_있으면_쓰지_않는다(env):
    """★★★ [변이 0건에서 발견] 「원장 철회 확인」을 통째로 지워도 잡히지 않았다 —
    `revoke()` 가 저장소 행도 내리므로 `status=ACTIVE` 조회에서 먼저 걸렸기 때문이다.

    ⚠️ 판별력은 **부분 실패**에서 생긴다: 원장에는 철회가 남았는데 행 갱신이 실패한
      경우다. 그때 원장 확인이 없으면 **철회된 기준선으로 계산**한다.
    ★ 소유권 결속에서 이미 같은 모양을 고쳤다(`ledger_mismatches`)."""
    from core import calc_baseline as cb
    _approve_relations(env)
    sealed = _seal_baseline(env)
    #: 원장에만 철회를 남기고 행은 ACTIVE 로 되돌린다(정본 갱신 실패 재현).
    cb.revoke(env["store"], build_id=sealed["build_id"], actor=ACTOR, reason="재검토")
    with env["store"].transaction() as conn:
        conn.execute("UPDATE baseline_builds SET status=? WHERE build_id=?",
                     (cb.ACTIVE, sealed["build_id"]))
    got = cb.active(env["store"], instance_id=env["instance_id"],
                    tenant_id=env["tenant"], entity_mode="REAL",
                    scope_node_id=env["scope"])
    assert got is None, "행을 되살려 철회된 기준선이 쓰였다"


def test_봉인은_살아_있는_기준선을_하나만_남긴다(env):
    """★★★ [변이 0건에서 발견] 「옛 기준선을 내린다」를 지워도 잡히지 않았다 —
    `active()` 가 최신 하나만 뽑기 때문이다.

    ⚠️ 그러나 둘이 `ACTIVE` 로 남으면 `created_at` 이 같은 순간에 **어느 것이 뽑힐지
      모른다.** 같은 질문에 다른 답을 주는 상태를 남기지 않는다."""
    _approve_relations(env)
    _seal_baseline(env)
    a = dv.assumptions(env["slice"])
    _seal_baseline(env, recognition_span_days={k: "45" for k in a["recognition_span_days"]})
    with env["store"].transaction() as conn:
        alive = conn.execute(
            "SELECT COUNT(*) FROM baseline_builds WHERE instance_id=? AND status='active'",
            (env["instance_id"],)).fetchone()[0]
    assert alive == 1, f"살아 있는 기준선이 {alive}건 — 어느 것으로 계산할지 모른다"


def test_기준선이_정하는_값은_호출자_가정에서_제거된다(env):
    """★★★ [변이 0건에서 발견] 「봉인이 이긴다」를 대입만으로 시험하면, 제거 로직이
    이미 걸러 주므로 대입을 `setdefault` 로 바꿔도 잡히지 않는다.

    ★ 두 줄이 **한 통제**다: ① 호출자 가정에서 세 키를 지운다 ② 봉인 값을 넣는다.
      ①이 사라지면 호출자 값이 남고, 그때 ②가 `setdefault` 면 호출자가 이긴다."""
    _approve_relations(env)
    _seal_baseline(env)
    req = _build(env, assumptions={
        "sales_allocation": {"SO-가짜": "PPL-가짜"},
        "recognition_span_days": {"SO-가짜": "999"},
        "baseline_recognition": {"SO-가짜": "2099-01-01T00:00:00+00:00"},
        "reserved_quantity_zero": True})
    for key in ("sales_allocation", "recognition_span_days", "baseline_recognition"):
        assert "SO-가짜" not in req.assumptions[key], f"{key} 에 호출자 값이 남았다"
    #: ★ 기준선이 정하지 않는 가정은 그대로 살아 있어야 한다(대조군).
    assert req.assumptions["reserved_quantity_zero"] is True


# ── ④ [B2] 실제 계산 결과가 G5 안건까지 결속된다 ────────────────────────

def test_실제_계산_결과가_안건_근거에_봉인된다(env, monkeypatch):
    """★★★ **B2 의 종단 증거.** 손으로 만든 dict 가 아니라 **계산기가 실제로 낸 결과**를
    G5 에 넘긴다.

    ⚠️⚠️ 앞서 G5 쪽 회귀는 `calc = {...}` 를 손으로 적었다. 그래서 계산기가 경로
      정체성을 **싣지 않아도** 잡히지 않았다(변이 0건) — 「fixture 가 계약을 대신
      정의하는」 패턴이 또 나온 것이다.
    ★ 여기서는 실제 결과를 그대로 넘긴다. 계산기가 `query_id`·`path_fingerprint` 를
      싣지 않으면 G5 대조에서 막힌다."""
    from core import decision_package as dp
    from core import calc_graph as cg

    _approve_relations(env)
    _seal_baseline(env)
    _approve_capabilities(env, monkeypatch)
    req = _build(env)
    got = svc_calc.run(env["store"], req, actor=ACTOR)
    assert got["status"] == pc.COMPLETE, got.get("blocked")

    #: ★ 계산기가 낸 정체성이 요청과 같아야 한다 — 이것이 G5 대조의 근거다.
    assert got["query_id"] == req.query_id
    assert got["path_fingerprint"] == req.path_fingerprint

    #: 런타임 경로 근거(어댑터가 만드는 모양).
    path_evidence = {"query_id": got["query_id"],
                     "path_fingerprint": got["path_fingerprint"],
                     "path": [], "missing_evidence": [], "missing_steps": [],
                     "calculation_blocked": False}
    base = cg.Result(
        baseline_fingerprint="bl_fp", calc_version="1.0.0", assumptions={},
        fingerprint="fp_base", data_kind="DEMO/SYNTHETIC",
        values={"production_qty": 100.0, "ending_inventory": 10.0,
                "purchase_payment": 5.0, "ending_cash": 5.0, "operating_profit": 1.0})
    scenario = cg.Result(
        baseline_fingerprint="bl_fp", calc_version="1.0.0", assumptions={"d": 1},
        fingerprint="fp_scn", data_kind="DEMO/SYNTHETIC",
        values={"production_qty": 90.0, "ending_inventory": 12.0,
                "purchase_payment": 6.0, "ending_cash": 6.0, "operating_profit": 2.0})

    pkg = dp.build(title="구매 지연 영향", owner=ACTOR, due="2026-07-01",
                   base=base, scenario=scenario, path=path_evidence, calculation=got)
    bound = pkg.evidence["calculation"]
    #: ★★★ 계산 결속이 **근거에 봉인**된다 — 원장·발간까지 따라간다.
    assert bound["result_fingerprint"] == got["result_fingerprint"]
    assert bound["request_fingerprint"] == got["request_fingerprint"]
    assert bound["used_snapshots"] == got["used_snapshots"]
    assert bound["metrics"] == got["metrics"]
    #: ★ 그리고 그 봉인으로 「이 숫자는 무엇으로 만들었나」에 답할 수 있다.
    assert set(bound["segment_model_versions"]) == set(pc.SEGMENTS)


def test_막힌_계산_결과는_안건이_되지_않는다(env):
    """★★★ 실제 `BLOCKED` 결과를 넘긴다 — 승인이 없으니 계산이 막힌 상태다.

    ⚠️ 막힌 계산 옆에 숫자를 놓으면 그 숫자가 답으로 읽힌다."""
    from core import decision_package as dp
    from core import calc_graph as cg
    import pytest as _pytest

    _approve_relations(env)
    _seal_baseline(env)
    got = svc_calc.run(env["store"], _build(env), actor=ACTOR)
    assert got["status"] == pc.BLOCKED

    path_evidence = {"query_id": got["query_id"],
                     "path_fingerprint": got["path_fingerprint"],
                     "path": [], "missing_evidence": [], "missing_steps": [],
                     "calculation_blocked": True}
    base = cg.Result(baseline_fingerprint="bl", calc_version="1.0.0",
                     assumptions={}, fingerprint="a", data_kind="DEMO/SYNTHETIC",
                     values={"production_qty": 100.0})
    scenario = cg.Result(baseline_fingerprint="bl", calc_version="1.0.0",
                         assumptions={"d": 1}, fingerprint="b",
                         data_kind="DEMO/SYNTHETIC",
                         values={"production_qty": 90.0})
    with _pytest.raises(dp.DecisionError):
        dp.build(title="x", owner=ACTOR, due="2026-07-01", base=base,
                 scenario=scenario, path=path_evidence, calculation=got)
