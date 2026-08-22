"""★★★ [G2 M0-3 카나리] **시연 데이터 → 인증판 → 승인 → 계산** 종단.

## 이 파일이 답하는 질문

「정본 파이프라인을 그대로 지나서, 실제로 숫자가 나오는가?」

앞선 회귀들은 각 층을 따로 시험한다(산식·실행기·투영). 이 파일은 **층을 잇는다** —
그리고 이 저장소에서 층 사이가 끊긴 채 각 층이 초록이던 일이 여러 번 있었다:

  · 계산 모델의 말로 fixture 를 써서, 정본으로는 한 줄도 안 돌았다
  · 통제는 있는데 부르는 경로가 없었다(Dispatch·소유권 API)

⚠️ 그래서 여기서는 **제품이 실제로 쓰는 것**만 쓴다: `data_preparation_store` 싱글턴,
  `snapshot_service.ingest/run_pipeline`, `calc_dataset_loader.load_sealed`,
  `path_calculation.calculate`. 시험 전용 지름길을 하나도 두지 않는다.

⚠️ 운영 DB 를 건드리지 않는다 — 저장소·원장·조직도·RAW 뿌리를 전부 `tmp_path` 로 격리한다.
"""
import pytest

from core import calc_capability as cc
from core import calc_dataset_loader as loader
from core import demo_seed_vertical as seed
from core import path_calculation as pc
from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation import store as dp

SCOPE = "MNM_BATTERY"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """시연 자료를 **제품 파이프라인으로** 적재하고 인증까지 마친다.

    ★ `create_instance → create_binding → transition → ingest → run_pipeline` 은
      제품이 파일을 받을 때 그대로 지나는 길이다."""
    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    raw_root = str(tmp_path / "raw")

    inst = store.create_instance(
        kit_id="KIT-VERTICAL", version="1.0.0", kit_fingerprint="fp-vertical",
        tenant_id=seed.TENANT, scope_node_id=SCOPE, entity_mode=seed.ENTITY_MODE)

    seals = {}
    for key, columns, _rows in seed.DATASETS:
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=seed.TENANT, scope_node_id=SCOPE, entity_mode=seed.ENTITY_MODE)
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        rows = seed.rows_for(key)
        snap = svc.ingest(store, binding=b, payload=seed.csv_for(key),
                          file_name=f"{key}.csv", workspace_root=raw_root)
        final = svc.run_pipeline(store, snap["snapshot_id"], rows, list(columns),
                                 control={"row_count": len(rows)})
        seals[key] = final["snapshot_id"]
    return {"store": store, "instance_id": inst["instance_id"], "seals": seals}


def _approved(monkeypatch):
    """계산 능력 3종을 **승인된 상태로** 세운다(격리 — 등록부를 고치지 않는다).

    ⚠️ 제품 등록부는 여전히 `IMPLEMENTED_UNAPPROVED` 다. 실행 승인은 사람의 결정이고,
      이 시험은 「승인이 나면 실제로 도는가」를 미리 확인하는 것이다."""
    approved = {}
    for ref in pc.SEGMENTS:
        base = cc.get(ref)
        approved[ref] = cc.Capability(**{**base.__dict__, "state": cc.APPROVED,
                                         "blocked_reason": "",
                                         "ledger_event_id": f"evt_{ref}"})
    monkeypatch.setattr(cc, "get", lambda ref: approved.get(ref) or cc._REGISTRY[ref])


def _request(seals, **kw):
    args = dict(
        query_id="q-canary", path_fingerprint="pf-canary", tenant_id=seed.TENANT,
        entity_mode=seed.ENTITY_MODE, scope_node_id=SCOPE, as_of=seed.AS_OF,
        baseline_id="BL-2026-08", baseline_fingerprint="blfp-2026-08",
        sealed_snapshots=dict(seals),
        #: 경로가 요구하는 관계 — 상세설계 §관계표의 계산 간선 셋.
        required_relation_ids=("REL_SHIPMENT_AFFECTS_INVENTORY",
                               "REL_INVENTORY_AFFECTS_PLAN",
                               "REL_PLAN_AFFECTS_SALES"),
        relation_approvals={"REL_SHIPMENT_AFFECTS_INVENTORY": "evt_rel_1",
                            "REL_INVENTORY_AFFECTS_PLAN": "evt_rel_2",
                            "REL_PLAN_AFFECTS_SALES": "evt_rel_3"},
        assumptions=seed.assumptions())
    args.update(kw)
    return pc.PathCalculationRequest(**args)


def _load(demo):
    return loader.load_sealed(
        demo["store"], sealed_snapshots=demo["seals"], tenant_id=seed.TENANT,
        entity_mode=seed.ENTITY_MODE, scope_node_id=SCOPE)


# ── ① 적재가 실제로 됐는가 ───────────────────────────────────────────────

def test_시연_자료_일곱_종이_인증판으로_올라간다(demo):
    """★ 색인 0행이던 자리에 실제 인증판이 선다."""
    assert sorted(demo["seals"]) == sorted(pc.REQUIRED_DATASETS)
    for key, sid in demo["seals"].items():
        row = demo["store"].get_snapshot(sid)
        assert row["state"] == m.DEMO_CERTIFIED, f"{key}: {row['state']}"
        assert row["data_kind"] == "DEMO/SYNTHETIC", f"{key}: 합성 표시가 없다"
        assert row["row_count"] == len(seed.rows_for(key))


def test_봉인된_판에서_정본_열_그대로_읽힌다(demo):
    """★★★ 로더가 **정본 열 이름**을 그대로 돌려줘야 투영이 받을 수 있다."""
    data = _load(demo)
    assert set(data) == set(pc.REQUIRED_DATASETS)
    #: LOG-03 은 `event_type`·`actual_at` 이다(계산 모델의 말이 아니다).
    assert {"event_type", "actual_at", "shipment_id"} <= set(data["LOG-03"][0])
    #: 모든 행에 봉인 판 id 가 붙는다.
    for key, rows in data.items():
        assert all(r["__snapshot_id__"] == demo["seals"][key] for r in rows)


# ── ② 층을 이어 실제로 계산된다 ──────────────────────────────────────────

def test_승인이_있으면_정본_자료로_계산이_완주한다(demo, monkeypatch):
    """★★★ **이 파일의 존재 이유.** 시드 → 인증 → 로더 → 투영 → 계산이 한 번에 흐른다.

    ⚠️ 이 시험이 빨개지는 방식은 두 가지다: 산식이 틀렸거나, **층 사이가 끊겼거나.**
      뒤엣것은 각 층의 회귀가 전부 초록이어도 일어난다."""
    _approved(monkeypatch)
    got = pc.calculate(_request(demo["seals"]), datasets=_load(demo),
                       ledger_verifier=lambda cap: True,
                       relation_verifier=lambda r, e: True)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    assert got["request_fingerprint"] and got["result_fingerprint"]
    assert set(got["metrics"]) == {"in_transit_quantity", "available_quantity",
                                   "shortage_quantity", "producible_quantity",
                                   "revenue_shift_days"}


def test_시연_이야기가_숫자로_성립한다(demo, monkeypatch):
    """★★★ 자료가 **이야기를 만드는지** 확인한다.

    ⚠️ 숫자를 아무렇게나 넣으면 「지연은 있는데 부족은 없는」 자료가 되어 시연이 밋밋해진다.
      그리고 그때 사람들은 계산이 고장났다고 생각한다 — 실은 자료가 밋밋한 것인데."""
    _approved(monkeypatch)
    got = pc.calculate(_request(demo["seals"]), datasets=_load(demo),
                       ledger_verifier=lambda cap: True,
                       relation_verifier=lambda r, e: True)
    mx = got["metrics"]

    #: ① 리튬이 운송 중이다 — 지연된 SHP-0001(600) + 아직 예정 전 SHP-0002(400).
    assert mx["in_transit_quantity"] == {seed.MAT_LI: 1000.0}, mx["in_transit_quantity"]
    #: ② 도착한 배(SHP-0003)와 미출발(SHP-0004)은 운송 중이 아니다.
    assert seed.MAT_NI not in mx["in_transit_quantity"], \
        "status 열을 믿으면 도착한 배가 운송 중으로 세어진다"
    #: ③ 리튬이 모자라 **뒤 계획행이 계획량을 못 채운다** — 배분 순서가 보인다.
    prod = mx["producible_quantity"]
    assert prod["PPL-0001"] == 300.0, prod
    assert 0 < prod["PPL-0002"] < 300.0, f"뒤 계획행이 온전히 생산 가능하다: {prod}"
    #: ④ 그래서 부족량이 있다.
    assert seed.MAT_LI in mx["shortage_quantity"], mx["shortage_quantity"]
    #: ⑤ 그 계획행에 배분된 판매행의 인식일이 밀린다.
    shift = mx["revenue_shift_days"]
    assert shift["SOL-0001"] == 0, shift
    assert shift["SOL-0002"] > 0, f"생산이 모자란데 매출 이연이 없다: {shift}"


def test_같은_자료_세_번이면_결과_지문이_같다(demo, monkeypatch):
    """★★★ M0 출구 조건 — 표준 시나리오 3회 연속 같은 결과."""
    _approved(monkeypatch)
    fps = set()
    for _ in range(3):
        got = pc.calculate(_request(demo["seals"]), datasets=_load(demo),
                           ledger_verifier=lambda cap: True,
                           relation_verifier=lambda r, e: True)
        assert got["status"] == pc.COMPLETE
        fps.add(got["result_fingerprint"])
    assert len(fps) == 1


def test_승인이_없으면_같은_자료로도_계산되지_않는다(demo):
    """★★★ **대조군.** 자료가 다 있어도 승인 전에는 숫자가 나오지 않는다.

    ⚠️ 이 시험이 빨개지는 날은 실행 승인이 난 날이어야 한다."""
    got = pc.calculate(_request(demo["seals"]), datasets=_load(demo),
                       ledger_verifier=lambda cap: True,
                       relation_verifier=lambda r, e: True)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}


# ── ③ 로더가 지켜야 하는 것 ──────────────────────────────────────────────

def test_다른_조직의_판은_봉인_목록에_적어도_읽히지_않는다(demo):
    """★★★ 봉인은 「무엇을 읽었는가」의 기록이지 **「무엇을 읽어도 되는가」의 허가가
    아니다.** 실행기는 봉인 목록을 주어진 것으로 보므로, 범위 대조는 로더가 한다."""
    with pytest.raises(loader.SealedDatasetError, match="이 문맥의 것이 아닙니다"):
        loader.load_sealed(demo["store"], sealed_snapshots=demo["seals"],
                           tenant_id=seed.TENANT, entity_mode=seed.ENTITY_MODE,
                           scope_node_id="MNM_OTHER")


def test_인증_전_판은_읽지_않는다(demo):
    """⚠️ 인증 전 자료로 만든 숫자는 검증되지 않았다 — 그런데 화면에서는 구분되지 않는다."""
    store = demo["store"]
    b = store.create_binding(
        instance_id=demo["instance_id"], dataset_contract_key="INV-01",
        provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id=seed.TENANT,
        scope_node_id=SCOPE, entity_mode=seed.ENTITY_MODE)
    for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        b = store.transition(b["binding_id"], target)
    raw = store.get_snapshot(demo["seals"]["INV-01"])
    snap = svc.ingest(store, binding=b, payload=seed.csv_for("INV-01"),
                      file_name="INV-01.csv",
                      workspace_root=str(raw["raw_path"]).rsplit("raw", 1)[0] + "raw")
    with pytest.raises(loader.SealedDatasetError, match="인증 상태가 아닙니다"):
        loader.load_sealed(store, sealed_snapshots={"INV-01": snap["snapshot_id"]},
                           tenant_id=seed.TENANT, entity_mode=seed.ENTITY_MODE,
                           scope_node_id=SCOPE)


def test_원본이_바뀌면_읽지_않는다(demo):
    """★★★ RAW 는 디스크에 있고 디스크는 바뀔 수 있다. **인증한 그 파일인가**는
    체크섬만이 답한다.

    ⚠️ 바뀐 파일로 계산하면 지문은 멀쩡한데 숫자가 다르다 — 재현 검증이 통과하면서
      틀린 답을 준다."""
    import io as _io
    store = demo["store"]
    sid = demo["seals"]["INV-01"]
    path = store.get_snapshot(sid)["raw_path"]
    with _io.open(path, "a", encoding="utf-8") as fh:
        fh.write("STK-9999,MAT-LIOH,WH-POHANG,2026-08-20T00:00:00+00:00,99999,0,0,KG\n")
    with pytest.raises(loader.SealedDatasetError, match="체크섬이 다릅니다"):
        loader.load_sealed(store, sealed_snapshots={"INV-01": sid},
                           tenant_id=seed.TENANT, entity_mode=seed.ENTITY_MODE,
                           scope_node_id=SCOPE)


def test_다른_계약키의_판을_그_자리에_넣을_수_없다(demo):
    """⚠️ 열이 통째로 다르다 — 투영이 「필수 열 없음」으로 막겠지만, 그 전에 여기서
    막는 편이 원인을 정확히 말한다."""
    seals = dict(demo["seals"])
    seals["INV-01"] = demo["seals"]["MFG-01"]
    with pytest.raises(loader.SealedDatasetError, match="다른 계약키"):
        loader.load_sealed(demo["store"], sealed_snapshots=seals,
                           tenant_id=seed.TENANT, entity_mode=seed.ENTITY_MODE,
                           scope_node_id=SCOPE)


def test_없는_판을_가리키면_빈_목록이_아니라_오류다(demo):
    """★★★ 빈 목록으로 접으면 실행기가 「자료가 아직 없다」(BLOCKED)로 답한다 —
    실제로는 **읽지 못한 것**인데 「아직 준비 안 됨」으로 보인다."""
    with pytest.raises(loader.SealedDatasetError, match="찾을 수 없습니다"):
        loader.load_sealed(demo["store"], sealed_snapshots={"INV-01": "ds_없음"},
                           tenant_id=seed.TENANT, entity_mode=seed.ENTITY_MODE,
                           scope_node_id=SCOPE)


def test_최신_인증판_목록을_만들_수_있다(demo):
    """★ 봉인 목록을 만드는 편의 함수. ⚠️ 「지금 최신」이지 「승인 때 봉인된 것」이 아니다."""
    got = loader.active_seals(demo["store"], instance_id=demo["instance_id"],
                              contract_keys=pc.REQUIRED_DATASETS)
    assert got == demo["seals"]
