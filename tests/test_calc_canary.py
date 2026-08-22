"""★★★ [G2 M0-3.1 카나리] **정본 스타터 키트 → 인증판 → 계산** 종단.

## 앞 판과 무엇이 다른가

앞 판은 시연 자료를 **손으로 썼고** 키트도 `KIT-VERTICAL/fp-vertical` 로 임의 생성했다.
그러면 「정본 열을 썼다」가 증거가 되지 못한다 — 실제로 `snapshot_at` 이라고 썼는데
정본은 `snapshot_date` 였고, 회귀는 전부 초록이었다.

★ 이제 **정본 CSV 에서 행만 골라낸다**(`core/demo_vertical_slice.py`). 열 이름은 고를
  여지가 없으므로 「fixture 가 계약을 대신 정의하는」 사고가 구조적으로 불가능하다.

    starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/samples/full/*.csv

## ⚠️ 정본 자료의 결함 두 건 — 이 파일이 드러낸다

1. `MFG-01.material_requirement` 가 BOM 재계산과 **200건 전부** 어긋난다
   (예: 저장 137.78 vs 재계산 139.745). 계약 §7.2 대로 그대로 넣으면 `BLOCKED` 다.
2. `INV-01` 의 `RM-CU-CONC` 원료 창고 재고가 2024-07 이후 **음수**다(25건).

⚠️ 둘 다 **계산이 덮을 문제가 아니다.** 1은 정본 규칙(BOM)으로 파생값을 복원해 쓰고,
  2는 그대로 흘려보내 «이미 초과 사용» 이라는 사실이 숫자로 보이게 한다 — 0 으로
  접으면 「재고가 없다」와 「이미 모자라게 썼다」가 같은 값이 된다.

## ⚠️ 아직 승인 대역이다

`ledger_verifier`·`relation_verifier` 는 여기서 참을 돌려주는 대역이고,
`required_relation_ids`·`sales_allocation`·`baseline_recognition` 은 호출자가 넣는다.
**그것을 서버가 실제 원장·저장소에서 산출하게 만드는 것이 M0-3.2 다.** 이 파일은
「자료와 배선이 흐르는가」까지만 답한다.
"""
import pytest

from core import calc_capability as cc
from core import calc_dataset_loader as loader
from core import demo_vertical_slice as dv
from core import path_calculation as pc
from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation import store as dp

#: 정본에서 `FG-CATHODE` BOM 이 실재하는 조직 노드(실측).
SCOPE = "plant-afs-smelting-01"


@pytest.fixture(scope="module")
def slice_data():
    return dv.build_slice(scope_node_id=SCOPE)


@pytest.fixture
def demo(tmp_path, monkeypatch, slice_data):
    """정본 부분집합을 **제품 파이프라인으로** 적재하고 인증까지 마친다."""
    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    tenant, scope = dv.scope_of(slice_data)

    #: ★★★ [M0-3.1 ④] **정본 키트를 등록부에 올리고 그 지문으로** 인스턴스를 만든다.
    #: ⚠️ 앞 판은 `fp-vertical` 같은 임의 지문을 적었다 — 등록부와 한 번도 대조하지 않았다.
    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=tenant, scope_node_id=scope, entity_mode="REAL")
    seals = {}
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
        final = svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                                 control={"row_count": len(rows)})
        seals[key] = final["snapshot_id"]
    return {"store": store, "instance_id": inst["instance_id"], "seals": seals,
            "tenant": tenant, "scope": scope, "slice": slice_data}


def _approved(monkeypatch):
    """계산 능력 3종을 **승인 대역**으로 세운다(제품 등록부는 건드리지 않는다).

    ⚠️ 이것은 승인이 아니라 대역이다. 실제 승인은 원장 사건이고 사람의 결정이다."""
    approved = {}
    for ref in pc.SEGMENTS:
        base = cc.get(ref)
        approved[ref] = cc.Capability(**{**base.__dict__, "state": cc.APPROVED,
                                         "blocked_reason": "",
                                         "ledger_event_id": f"evt_{ref}"})
    monkeypatch.setattr(cc, "get", lambda ref: approved.get(ref) or cc._REGISTRY[ref])


def _request(demo, **kw):
    args = dict(
        query_id="q-canary", path_fingerprint="pf-canary", tenant_id=demo["tenant"],
        entity_mode="REAL", scope_node_id=demo["scope"], as_of=dv.AS_OF,
        baseline_id="BL-CANARY", baseline_fingerprint="blfp-canary",
        sealed_snapshots=dict(demo["seals"]),
        required_relation_ids=("REL_SHIPMENT_AFFECTS_INVENTORY",
                               "REL_INVENTORY_AFFECTS_PLAN",
                               "REL_PLAN_AFFECTS_SALES"),
        relation_approvals={"REL_SHIPMENT_AFFECTS_INVENTORY": "evt_rel_1",
                            "REL_INVENTORY_AFFECTS_PLAN": "evt_rel_2",
                            "REL_PLAN_AFFECTS_SALES": "evt_rel_3"},
        assumptions=dv.assumptions(demo["slice"]))
    args.update(kw)
    return pc.PathCalculationRequest(**args)


def _load(demo):
    return loader.load_sealed(demo["store"], sealed_snapshots=demo["seals"],
                              tenant_id=demo["tenant"], entity_mode="REAL",
                              scope_node_id=demo["scope"])


def _run(demo):
    return pc.calculate(_request(demo), datasets=_load(demo),
                        ledger_verifier=lambda cap: True,
                        relation_verifier=lambda r, e: True)


# ── ① 정본 키트를 쓴다 ───────────────────────────────────────────────────

def test_정본_키트에서_행만_골라낸다(slice_data):
    """★★★ 열 이름을 고를 여지가 없어야 한다 — 그것이 이 방식의 존재 이유다."""
    assert dv.KIT_ID == "KIT-MFG-NONFERROUS-PROCUREMENT"
    #: 정본 헤더가 그대로 있다(임의로 만든 열이 아니다).
    inv_cols = slice_data["INV-01"][1]
    assert "snapshot_date" in inv_cols and "unrestricted_quantity" in inv_cols
    assert "snapshot_at" not in inv_cols, "앞 판이 쓰던 이름이 되살아났다"
    log3_cols = slice_data["LOG-03"][1]
    assert "event_type" in log3_cols and "actual_at" in log3_cols
    #: 정본은 범위 열을 이미 갖고 있다 — 시드가 붙이는 것이 아니다.
    assert {"tenant_id", "scope_node_id"} <= set(inv_cols)


def test_부분집합은_한_조직_안에_있다(slice_data):
    """⚠️ 여러 조직이 섞이면 경계를 넘은 계산이 된다."""
    tenant, scope = dv.scope_of(slice_data)
    assert scope == SCOPE and tenant


def test_부분집합은_결정론적이다():
    """★ 같은 규칙으로 두 번 뽑으면 같은 행이어야 한다 — 파일 순서에 기대면 자료가
    재생성될 때 다른 집합이 나온다."""
    a = dv.build_slice(scope_node_id=SCOPE)
    b = dv.build_slice(scope_node_id=SCOPE)
    assert {k: v[0] for k, v in a.items()} == {k: v[0] for k, v in b.items()}


def test_배분_순서를_보여_줄_계획행이_둘_이상이다(slice_data):
    """⚠️ 계획행이 하나면 재고 배분 순서가 결과에 나타나지 않는다."""
    assert len(slice_data["MFG-01"][0]) >= 2


# ── ② 정본 자료의 결함을 드러낸다 ────────────────────────────────────────

def test_정본의_소요량은_BOM_재계산과_어긋난다():
    """★★★ [M0-3.1 실측] 이 범위의 `MFG-01` **200건 전부**가 불일치다.

    ⚠️ 계약 §7.2 는 「하나를 임의로 고르지 않고 실패」로 정했다. 그래서 원본을 그대로
      넣으면 경로가 `BLOCKED` 된다 — **계약대로 작동한 것이지 결함이 아니다.**
    ★ 이 시험은 그 사실을 못박는다. 정본 자료가 고쳐지면 여기가 빨개지고, 그때
      `_reconcile_requirement` 를 지울 수 있다."""
    from decimal import ROUND_HALF_UP, Decimal
    bom, _ = dv._read("MDM-05")
    plan, _ = dv._read("MFG-01")
    qpo, yld = {}, {}
    for b in bom:
        if str(b.get("component_role", "")).upper() != "INPUT":
            continue
        k = (b["output_material_id"], b["input_material_id"])
        qpo[k] = qpo.get(k, Decimal(0)) + Decimal(b["quantity_per_output"])
        yld[k] = Decimal(b["standard_yield"])
    mismatched = 0
    checked = 0
    for p in plan:
        if p.get("scope_node_id") != SCOPE:
            continue
        keys = [k for k in qpo if k[0] == p["product_id"]]
        if not keys or not p.get("material_requirement"):
            continue
        checked += 1
        rec = sum(Decimal(p["plan_quantity"]) * qpo[k] / yld[k] for k in keys)
        q = Decimal("0.001")
        if Decimal(p["material_requirement"]).quantize(q, rounding=ROUND_HALF_UP) != \
                rec.quantize(q, rounding=ROUND_HALF_UP):
            mismatched += 1
    assert checked > 0
    assert mismatched == checked, (
        f"정본 자료가 고쳐졌다(불일치 {mismatched}/{checked}) — 부분집합의 대사 보정을 "
        f"다시 볼 것")


def test_부분집합은_BOM_정본으로_소요량을_복원한다(slice_data):
    """★ 「하나를 고르는」 것이 아니라 **정본 규칙으로 파생값을 복원**하는 것이다.
    ⚠️ 원본 파일은 고치지 않는다 — 보정은 부분집합에만 적용된다."""
    from decimal import Decimal
    bom = slice_data["MDM-05"][0]
    qpo = sum(Decimal(b["quantity_per_output"]) for b in bom
              if str(b.get("component_role", "")).upper() == "INPUT")
    yld = Decimal(next(b["standard_yield"] for b in bom
                       if str(b.get("component_role", "")).upper() == "INPUT"))
    for row in slice_data["MFG-01"][0]:
        want = Decimal(row["plan_quantity"]) * qpo / yld
        assert abs(Decimal(row["material_requirement"]) - want) < Decimal("0.01"), row


def test_음수_재고를_0_으로_접지_않는다(demo, monkeypatch):
    """★★★ 정본의 `RM-CU-CONC` 원료 창고 재고는 2024-07 이후 **음수**다(25건).

    ⚠️ 음수를 0 으로 접으면 「재고가 없다」와 「이미 모자라게 썼다」가 같은 값이 된다.
      뒤엣것은 지금 라인이 서고 있다는 뜻이고, 앞엣것보다 훨씬 급한 사실이다."""
    _approved(monkeypatch)
    got = _run(demo)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    avail = got["metrics"]["available_quantity"]
    assert any(v < 0 for v in avail.values()), (
        f"음수 재고가 사라졌다 — 0 으로 접혔을 수 있다: {avail}")


# ── ③ 층을 이어 실제로 계산된다 ──────────────────────────────────────────

def test_정본_자료로_경로가_완주한다(demo, monkeypatch):
    """★★★ **이 파일의 존재 이유.** 정본 키트 → 인증 → 로더 → 투영 → 계산이 흐른다.

    ⚠️ 앞 판은 손으로 쓴 자료로 이 시험을 통과했고, 정본을 넣자 `milestone_code` 누락으로
      즉시 실패했다."""
    _approved(monkeypatch)
    got = _run(demo)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    assert got["request_fingerprint"] and got["result_fingerprint"]
    assert set(got["metrics"]) == {"in_transit_quantity", "available_quantity",
                                   "shortage_quantity", "producible_quantity",
                                   "revenue_shift_days"}


def test_같은_자료_세_번이면_결과_지문이_같다(demo, monkeypatch):
    """★★★ M0 출구 조건 — 표준 시나리오 3회 연속 같은 결과."""
    _approved(monkeypatch)
    assert len({_run(demo)["result_fingerprint"] for _ in range(3)}) == 1


def test_승인이_없으면_같은_자료로도_계산되지_않는다(demo):
    """★★★ **대조군.** 이 시험이 빨개지는 날은 실행 승인이 난 날이어야 한다."""
    got = _run(demo)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}


def test_날짜만_적힌_값을_규칙대로_읽는다(demo, monkeypatch):
    """★★★ 정본의 `snapshot_date`·`plan_date`·`eta`·`due_date` 는 **날짜만**이다.

    ⚠️ 규칙이 없으면 비교하는 쪽이 추측하고, 그 추측은 서버 시간대에 따라 달라진다 —
      배포 환경이 바뀌면 같은 자료가 다른 답을 낸다."""
    from core import calc_models as cm
    assert cm.DATE_ONLY_RULE == "date_only_is_midnight_utc"
    _approved(monkeypatch)
    assert _run(demo)["status"] == pc.COMPLETE
    #: 규칙이 가정에 실려 지문에 들어간다.
    assert dv.assumptions(demo["slice"])["date_only_rule"] == cm.DATE_ONLY_RULE


def test_정본에는_ATD_가_없고_ETD_의_실적시각을_쓴다(slice_data):
    """★★★ [실측] `LOG-03.event_type` 은 BOOKED/PICKED_UP/ETD/ETA/ATA/UNLOADED 다.

    ★ `LOG-03` 은 milestone 마다 `planned_at`·`actual_at` 쌍을 갖는다. `ETD` 행의
      `actual_at` 이 **실제로 떠난 시각**이다 — 이름은 예정이지만 값은 실적이다.
    ⚠️ `planned_at` 을 쓰면 「예정대로 떠났을 것」이라는 가정이 계산에 들어간다."""
    from core import calc_models as cm
    kinds = {r["event_type"] for r in slice_data["LOG-03"][0]}
    assert "ATD" not in kinds, "정본에 ATD 가 생겼다 — 상수를 다시 볼 것"
    assert "ETD" in kinds
    assert "ETD" in cm.DEPARTED_MILESTONES


def test_BOM_의_반환_역할은_소요로_세지_않는다():
    """⚠️ `RETURN`(반환·부산물 회수)을 소요로 세면 필요량이 부풀고 없는 부족이 생긴다."""
    from core import calc_models as cm
    assert cm.BOM_INPUT_ROLES == ("INPUT",)
    bom, _ = dv._read("MDM-05")
    assert {r["component_role"] for r in bom} >= {"INPUT", "RETURN"}


# ── ④ 로더가 지켜야 하는 것 ──────────────────────────────────────────────

def test_다른_조직의_판은_봉인_목록에_적어도_읽히지_않는다(demo):
    """★★★ 봉인은 「무엇을 읽었는가」의 기록이지 **허가가 아니다.**"""
    with pytest.raises(loader.SealedDatasetError, match="이 문맥의 것이 아닙니다"):
        loader.load_sealed(demo["store"], sealed_snapshots=demo["seals"],
                           tenant_id=demo["tenant"], entity_mode="REAL",
                           scope_node_id="plant-afs-other-99")


def test_원본이_바뀌면_읽지_않는다(demo):
    """★★★ 바뀐 파일로 계산하면 지문은 멀쩡한데 숫자가 다르다 — 재현 검증이 통과하면서
    틀린 답을 준다."""
    import io as _io
    sid = demo["seals"]["INV-01"]
    path = demo["store"].get_snapshot(sid)["raw_path"]
    with _io.open(path, "a", encoding="utf-8") as fh:
        fh.write("x\n")
    with pytest.raises(loader.SealedDatasetError, match="체크섬이 다릅니다"):
        loader.load_sealed(demo["store"], sealed_snapshots={"INV-01": sid},
                           tenant_id=demo["tenant"], entity_mode="REAL",
                           scope_node_id=demo["scope"])


def test_없는_판을_가리키면_빈_목록이_아니라_오류다(demo):
    """★★★ 빈 목록으로 접으면 실행기가 「자료가 아직 없다」로 답한다 — 실제로는
    **읽지 못한 것**인데 「아직 준비 안 됨」으로 보인다."""
    with pytest.raises(loader.SealedDatasetError, match="찾을 수 없습니다"):
        loader.load_sealed(demo["store"], sealed_snapshots={"INV-01": "ds_없음"},
                           tenant_id=demo["tenant"], entity_mode="REAL",
                           scope_node_id=demo["scope"])


def test_최신_인증판_목록을_만들_수_있다(demo):
    got = loader.active_seals(demo["store"], instance_id=demo["instance_id"],
                              contract_keys=dv.SLICE_KEYS)
    assert got == demo["seals"]
