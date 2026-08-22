"""★★★ [G2 B2 / M0-2] **경로 단위 계산 실행기** 회귀 — 관문 7개·지문 2개.

계약: `docs/handoff/G2_A_PATH_CALCULATION_CONTRACT_2026-08-21.md`

## 이 파일이 지키는 것

1. **승인 없이는 계산하지 않는다** — 지금은 관문 3에서 전부 멈춘다(구간 3종이 승인 전).
2. **부분 결과 없음** — 한 구간이라도 막히면 경로 전체가 `BLOCKED` 이고 `metrics` 는 비어 있다.
3. **차단 사유도 누설이다** — 대외 사유에 구간 이름·건수·식별자를 넣지 않는다.
4. **지문 둘** — 질문 지문은 언제나, 결과 지문은 `COMPLETE` 일 때만.
5. **BLOCKED 와 무결성 장애를 가른다** — 「아직 못 한다」와 「자료가 어긋났다」는 다르다.

⚠️ 산식 자체는 `tests/test_calc_models.py` 가 시험한다. 여기서 다시 시험하면 산식을
  고칠 때 두 파일이 함께 빨개지고, 사람들은 산식이 아니라 시험을 고친다.
"""
import pytest

from core import calc_capability as cc
from core import calc_models as cm
from core import path_calculation as pc

AS_OF = "2026-08-21T00:00:00+00:00"
SNAP = {k: f"ds_{k}" for k in pc.REQUIRED_DATASETS}


def _req(**kw):
    args = dict(
        query_id="q1", path_fingerprint="pf1", tenant_id="tenant_default",
        entity_mode="REAL", scope_node_id="NODE_A", as_of=AS_OF,
        baseline_id="bl1", baseline_fingerprint="blfp1",
        sealed_snapshots=dict(SNAP),
        required_relation_ids=("rel_1",),
        relation_approvals={"rel_1": "evt_1"},
        assumptions={"reserved_quantity_zero": True,
                     "baseline_recognition": {"SL-1": "2026-09-30T00:00:00+00:00"},
                     #: ★ 정본에 없다 — **승인된 생산-판매 배분**에서 온다(§관계표
                     #:   `FULFILLS_SALES` 의 근거가 «승인된 allocation» 이다).
                     "sales_allocation": {"SL-1": "PL-1"},
                     "recognition_span_days": {"SL-1": "30"}})
    args.update(kw)
    return pc.PathCalculationRequest(**args)


def _rows(key, rows):
    """★ 관문 6 — 읽은 판이 봉인된 판과 같아야 한다. 그래서 행에 판 id 를 싣는다."""
    return [{**r, "__snapshot_id__": SNAP[key]} for r in rows]


def _datasets(**over):
    """★★★ **정본 계약키의 실제 열 이름**으로 쓴다.

    ⚠️⚠️ 앞 판은 계산 모델의 말(`material_code`·`milestone_code`…)로 fixture 를 썼다.
      그래서 실제 CSV 를 넣으면 즉시 실패하는데도 회귀는 전부 초록이었다 — fixture 가
      계약을 대신 정의한 셈이고, 그 상태에서 「계산 모델 완료」라고 보고했다.
    ★ 정본 열 이름은 `docs/architecture/g2_first_vertical_ontology_contract_v1.json` 과
      상세설계 §관계표에서 온다."""
    base = {
        #: PRC-02 — **선적의 자재를 찾는 유일한 근거**(LOG-02 에는 자재 ID 가 없다).
        "PRC-02": _rows("PRC-02", [
            {"po_line_id": "PO-1", "material_id": "LIOH"},
            {"po_line_id": "PO-2", "material_id": "NIOH"}]),
        "LOG-02": _rows("LOG-02", [
            {"shipment_id": "SHP-1", "po_line_id": "PO-1",
             "shipment_quantity": "1000", "eta": "2026-08-15T00:00:00+00:00"}]),
        "LOG-03": _rows("LOG-03", [
            {"shipment_id": "SHP-1", "event_type": "ATD",
             "actual_at": "2026-08-01T00:00:00+00:00"}]),
        "INV-01": _rows("INV-01", [
            {"material_id": "LIOH", "location_id": "WH1",
             "snapshot_date": "2026-08-20T00:00:00+00:00",
             "unrestricted_quantity": "32.4325"},
            {"material_id": "NIOH", "location_id": "WH1",
             "snapshot_date": "2026-08-20T00:00:00+00:00",
             "unrestricted_quantity": "400"}]),
        "MFG-01": _rows("MFG-01", [
            {"plan_line_id": "PL-1", "product_id": "FG-CATHODE",
             "plan_quantity": "100", "plan_date": "2026-09-01T00:00:00+00:00"}]),
        "MDM-05": _rows("MDM-05", [
            {"output_material_id": "FG-CATHODE", "input_material_id": "LIOH",
             "quantity_per_output": "0.6", "standard_yield": "0.925"},
            {"output_material_id": "FG-CATHODE", "input_material_id": "NIOH",
             "quantity_per_output": "0.5", "standard_yield": "0.925"}]),
        "SLS-01": _rows("SLS-01", [
            {"sales_line_id": "SL-1", "product_id": "FG-CATHODE",
             "due_date": "2026-09-10T00:00:00+00:00"}]),
    }
    base.update({k: _rows(k, v) for k, v in over.items()})
    return base


def _approved(monkeypatch):
    """세 구간을 **승인된 상태로** 세운다.

    ⚠️ 등록부를 직접 고치지 않는다 — 제품 상태를 시험이 바꿔 놓으면 다음 시험이 그
      상태를 물려받는다. `monkeypatch` 로만 바꾼다."""
    approved = {}
    for ref in pc.SEGMENTS:
        base = cc.get(ref)
        kw = {**base.__dict__, "state": cc.APPROVED, "blocked_reason": "",
              "ledger_event_id": f"evt_{ref}", "model_version": base.model_version}
        approved[ref] = cc.Capability(**kw)
    monkeypatch.setattr(cc, "get", lambda ref: approved.get(ref) or cc._REGISTRY[ref])
    return approved


def _ok_ledger(cap):
    return True


def _ok_relation(rel_id, event_id):
    return True


# ── ① 승인 전에는 계산하지 않는다 ────────────────────────────────────────

def test_승인_전에는_경로_전체가_BLOCKED_다():
    """★★★ 계약 §6 — 「지금은 3번에서 전부 멈춘다」. 그 사실을 못 박는다.

    ⚠️ 이 시험이 초록에서 빨강으로 바뀌는 날은 **승인이 생긴 날**이어야 한다. 산식을
      구현했다고 저절로 열리면, 검증 없는 숫자가 화면에 오른다."""
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}, "차단인데 수치가 있다"
    assert "result_fingerprint" not in got, "차단에 결과 지문을 만들었다(§3.7)"


def test_차단에도_질문_지문은_있다():
    """★ 「이 질문은 무엇이었나」는 차단이어도 답할 수 있어야 한다 — 그러지 않으면 같은
    질문을 다시 물었는지 대조할 수 없다."""
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["request_fingerprint"]


def test_대외_차단_사유에_구간_이름과_건수가_없다():
    """★★★ §2.1 — **차단 사유도 누설이다.**

    ⚠️ 「승인되지 않은 관계 3건」은 그 조직에 관계가 3건 있다는 뜻이다. 내부 사유는
      남기고, 대외 사유는 그것을 말하지 않는다."""
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    public = got["blocked"]["public_reason"]
    for leak in ("CALC.", "LOG-02", "INV-01", "rel_1", "evt_"):
        assert leak not in public, f"대외 사유에 내부 값이 들어갔다: {leak}"
    #: ★ 그러나 내부 사유에는 **있어야** 한다 — 운영자가 고칠 수 있어야 한다.
    assert any("CALC." in r for r in got["blocked"]["internal_reasons"])


# ── ② 승인 관문 ──────────────────────────────────────────────────────────

def test_관계_승인이_없으면_BLOCKED_다(monkeypatch):
    _approved(monkeypatch)
    got = pc.calculate(_req(relation_approvals={}), datasets=_datasets(),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "relation_approvals" in str(got["blocked"]["internal_reasons"])


def test_승인_검증기가_없으면_통과시키지_않는다(monkeypatch):
    """★★★ 「검증기를 안 넘겼으니 그냥 통과」는 **철회된 승인으로 계산이 지나가는 문**이다.
    등록부의 `assert_executable` 과 같은 규칙이다."""
    _approved(monkeypatch)
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=None)
    assert got["status"] == pc.BLOCKED
    assert "relation_verifier" in str(got["blocked"]["internal_reasons"])


def test_철회된_관계_승인은_BLOCKED_다(monkeypatch):
    _approved(monkeypatch)
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=lambda r, e: False)
    assert got["status"] == pc.BLOCKED
    assert "유효하지 않습니다" in str(got["blocked"]["internal_reasons"])


def test_승인_조회_장애는_BLOCKED_가_아니라_장애다(monkeypatch):
    """★★★ 「못 읽었다」는 「승인 없음」도 「있음」도 아니다.

    ⚠️ 이것을 `BLOCKED` 로 접으면 원장 장애 중에 모든 경로가 「아직 준비되지 않았다」로
      보이고, 아무도 저장소를 보러 가지 않는다."""
    _approved(monkeypatch)

    def _boom(rel_id, event_id):
        raise RuntimeError("원장 장애")

    with pytest.raises(pc.PathCalculationError, match="확인하지 못했습니다"):
        pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_boom)


# ── ③ 정체성·봉인 관문 ───────────────────────────────────────────────────

@pytest.mark.parametrize("missing", ["query_id", "path_fingerprint", "tenant_id",
                                     "entity_mode", "scope_node_id", "baseline_id",
                                     "baseline_fingerprint"])
def test_정체성이_비면_무결성_장애다(missing):
    """★★★ §3.3 — `scope_node_id` 가 빠지면 **같은 tenant 안의 다른 조직 계산을 구분할
    수 없다.** 정본 다섯 종은 이미 두 조직 노드에 걸쳐 있다.

    ⚠️ 이것을 `BLOCKED` 로 두면 「승인이 없다」와 「요청이 깨졌다」가 같은 답이 되고,
      운영자는 승인을 찾으러 간다."""
    with pytest.raises(pc.PathCalculationError, match="정체성"):
        pc.calculate(_req(**{missing: ""}), datasets=_datasets(),
                     ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)


def test_봉인된_판이_없으면_BLOCKED_다(monkeypatch):
    _approved(monkeypatch)
    seals = {k: v for k, v in SNAP.items() if k != "INV-01"}
    got = pc.calculate(_req(sealed_snapshots=seals), datasets=_datasets(),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "INV-01" in str(got["blocked"]["internal_reasons"])


def test_읽은_판이_봉인된_판과_다르면_무결성_장애다(monkeypatch):
    """★★★ §3.6 — 이것은 지문 문제가 아니다. **봉인한 판이 아닌 것을 읽었다**는 뜻이고,
    그 상태로 만든 숫자는 어떤 지문을 붙여도 근거가 없다."""
    _approved(monkeypatch)
    ds = _datasets()
    ds["INV-01"] = [{**r, "__snapshot_id__": "ds_다른판"} for r in ds["INV-01"]]
    with pytest.raises(pc.PathCalculationError, match="봉인한 판이 아닌"):
        pc.calculate(_req(), datasets=ds, ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)


def test_자료가_아예_없으면_BLOCKED_다(monkeypatch):
    _approved(monkeypatch)
    ds = _datasets()
    del ds["MDM-05"]
    got = pc.calculate(_req(), datasets=ds, ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "MDM-05" in str(got["blocked"]["internal_reasons"])


# ── ④ 승인되면 실제로 계산된다 ───────────────────────────────────────────

def test_승인되면_경로가_계산되고_지문_둘이_생긴다(monkeypatch):
    """★★★ **이 경로의 존재 이유.** 승인이 있으면 숫자가 나오고, 그 숫자에 두 지문이 붙는다."""
    _approved(monkeypatch)
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    assert got["request_fingerprint"] and got["result_fingerprint"]
    #: 세 구간의 지표가 모두 있다.
    assert set(got["metrics"]) == {"in_transit_quantity", "available_quantity",
                                   "shortage_quantity", "producible_quantity",
                                   "revenue_shift_days"}
    #: ★ 구간 판은 **정렬된 객체**로 봉인한다(§4 — 문자열로 이어 붙이지 않는다).
    assert got["segment_model_versions"] == {ref: "1.0.0" for ref in pc.SEGMENTS}
    assert got["path_model_version"] == pc.PATH_MODEL_VERSION


def test_같은_질문_같은_자료면_두_지문이_모두_같다(monkeypatch):
    """★★★ M0-1·M0-2 완료 증거 — 재현 가능해야 한다."""
    _approved(monkeypatch)
    runs = [pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                         relation_verifier=_ok_relation) for _ in range(3)]
    assert len({r["request_fingerprint"] for r in runs}) == 1
    assert len({r["result_fingerprint"] for r in runs}) == 1


def test_as_of_표기가_달라도_같은_질문이다(monkeypatch):
    """★ 지문은 표기에 흔들리지 않는다 — `Z` 와 `+00:00` 은 같은 순간이다."""
    _approved(monkeypatch)
    a = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    b = pc.calculate(_req(as_of="2026-08-21T00:00:00Z"), datasets=_datasets(),
                     ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert a["request_fingerprint"] == b["request_fingerprint"]


def test_가정이_바뀌면_질문_지문이_바뀐다(monkeypatch):
    """★★★ §7.1 — 가정을 지문 밖에 두면 「예약 0 으로 계산한 결과」와 「예약 데이터로
    계산한 결과」가 **같은 지문**을 갖는다."""
    _approved(monkeypatch)
    a = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    inv = [{"material_id": "LIOH", "location_id": "WH1",
            "snapshot_date": "2026-08-20T00:00:00+00:00",
            "unrestricted_quantity": "32.4325", "reserved_quantity": "0"},
           {"material_id": "NIOH", "location_id": "WH1",
            "snapshot_date": "2026-08-20T00:00:00+00:00",
            "unrestricted_quantity": "400", "reserved_quantity": "0"}]
    #: ★ `reserved_quantity_zero` 가정만 뺀다(재고 행에 실제 값이 있으므로 계산은 된다).
    #:   ⚠️ 가정 묶음을 통째로 갈아 끼우면 `sales_allocation` 까지 빠져 「기준선 부족」으로
    #:     막히고, 그러면 이 시험은 지문이 아니라 다른 것을 보게 된다.
    b = pc.calculate(
        _req(assumptions={"baseline_recognition":
                          {"SL-1": "2026-09-30T00:00:00+00:00"},
                          "sales_allocation": {"SL-1": "PL-1"},
                          "recognition_span_days": {"SL-1": "30"}}),
        datasets=_datasets(**{"INV-01": inv}), ledger_verifier=_ok_ledger,
        relation_verifier=_ok_relation)
    assert b["status"] == pc.COMPLETE, b.get("blocked")
    assert a["request_fingerprint"] != b["request_fingerprint"]


def test_관계_승인_이벤트가_바뀌면_질문_지문이_바뀐다(monkeypatch):
    """★★★ §3.4 — **철회 후 재승인은 다른 실행 근거다.** 지문이 같으면 옛 근거로 낸
    숫자가 새 승인 아래서도 유효해 보인다."""
    _approved(monkeypatch)
    a = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    b = pc.calculate(_req(relation_approvals={"rel_1": "evt_2"}), datasets=_datasets(),
                     ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert a["request_fingerprint"] != b["request_fingerprint"]


def test_산식_판이_바뀌면_결과_지문이_바뀐다(monkeypatch):
    """★★★ §3.2 — rev.1 은 질문 지문만 만들고 결과 지문의 이름을 붙였다. 그러면 **산식이
    바뀌어 값이 달라져도 지문이 같아서** 재현 검증이 통과한다."""
    _approved(monkeypatch)
    a = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    #: 값이 달라지는 변경을 준다(재고를 늘린다) — 질문은 같고 답이 다르다.
    inv = [{"material_id": "LIOH", "location_id": "WH1",
            "snapshot_date": "2026-08-20T00:00:00+00:00", "unrestricted_quantity": "999"},
           {"material_id": "NIOH", "location_id": "WH1",
            "snapshot_date": "2026-08-20T00:00:00+00:00", "unrestricted_quantity": "999"}]
    b = pc.calculate(_req(), datasets=_datasets(**{"INV-01": inv}),
                     ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert a["request_fingerprint"] == b["request_fingerprint"], "질문이 달라졌다"
    assert a["result_fingerprint"] != b["result_fingerprint"], \
        "값이 달라졌는데 결과 지문이 같다 — 재현 검증이 거짓말한다"


def test_전체_Registry_지문을_쓰지_않는다(monkeypatch):
    """★★★ §3.5 — 범위 밖 참조(`CALC.FINANCE…`)의 산식을 고치는 순간 MVP 결과가 전부
    무효가 되면, 사람은 지문 검증을 믿지 않게 되고 결국 끈다."""
    _approved(monkeypatch)
    before = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                          relation_verifier=_ok_relation)
    #: 범위 밖 참조만 바꾼다.
    fin = cc._REGISTRY["CALC.FINANCE.COST_MARGIN_CASH.v1"]
    changed = cc.Capability(**{**fin.__dict__, "model_version": "9.9.9"})
    monkeypatch.setitem(cc._REGISTRY, "CALC.FINANCE.COST_MARGIN_CASH.v1", changed)
    after = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                         relation_verifier=_ok_relation)
    assert before["request_fingerprint"] == after["request_fingerprint"]


# ── ⑤ 부분 결과와 0 접기 금지 ────────────────────────────────────────────

def test_자료가_계약과_다르면_0_이_아니라_BLOCKED_다(monkeypatch):
    """★★★ 「계산이 안 됐다」가 「영향이 없다」로 보이면 화면은 평온하다.

    ⚠️ 그리고 이것은 무결성 장애가 **아니다** — 자료를 채우면 풀린다. 장애로 올리면
      운영자가 데이터가 아니라 서버를 본다."""
    _approved(monkeypatch)
    ds = _datasets()
    #: 예약 수량도 가정도 없다 → 계산 불가.
    got = pc.calculate(_req(assumptions={"baseline_recognition":
                                         {"SL-1": "2026-09-30T00:00:00+00:00"}}),
                       datasets=ds, ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}
    assert "reserved_quantity" in str(got["blocked"]["internal_reasons"])


def test_BOM_대사_불일치는_BLOCKED_이고_수치가_없다(monkeypatch):
    """★★★ §7.2 — 하나를 임의로 고르지 않는다. 그리고 **부분 수치를 내보내지 않는다** —
    앞 구간(도착 지연)은 계산됐지만 경로 전체가 막힌다."""
    _approved(monkeypatch)
    plan = [{"plan_line_id": "PL-1", "product_id": "FG-CATHODE",
             "plan_quantity": "100", "plan_date": "2026-09-01T00:00:00+00:00",
             "material_requirement": "66.4"}]
    got = pc.calculate(_req(), datasets=_datasets(**{"MFG-01": plan}),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}, "부분 수치가 나갔다"
    assert got["segment_outputs"] == {}


def test_기준선이_없으면_BLOCKED_이고_이동_0_이_아니다(monkeypatch):
    """★★★ §7.3 — 기준선 없는 행을 조용히 빼면 「이동 없음」과 구분되지 않는다."""
    _approved(monkeypatch)
    got = pc.calculate(_req(assumptions={"reserved_quantity_zero": True}),
                       datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "기준선" in str(got["blocked"]["internal_reasons"])
    assert got["metrics"] == {}


# ── ⑥ [P0-CALC-PROOF] 봉인 완전성 ────────────────────────────────────────

def test_경로의_관계가_넷인데_승인이_하나면_BLOCKED_다(monkeypatch):
    """★★★ [감사 실측] 앞 판은 `relation_approvals` 가 **비었는지만** 봤다. 그래서
    관계 승인 하나만 제출해도 `COMPLETE` 가 나왔다 — 경로에 관계가 넷이든 상관없이.

    ⚠️ 승인은 「몇 개 냈는가」가 아니라 **「이 경로의 모든 관계가 승인됐는가」**다."""
    _approved(monkeypatch)
    got = pc.calculate(
        _req(required_relation_ids=("rel_1", "rel_2", "rel_3", "rel_4"),
             relation_approvals={"rel_1": "evt_1"}),
        datasets=_datasets(), ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "rel_2" in str(got["blocked"]["internal_reasons"])


def test_경로_밖_관계의_승인을_섞어도_BLOCKED_다(monkeypatch):
    """⚠️ 개수만 세면 **다른 관계의 승인**으로 개수를 맞출 수 있다."""
    _approved(monkeypatch)
    got = pc.calculate(
        _req(required_relation_ids=("rel_1", "rel_2"),
             relation_approvals={"rel_1": "evt_1", "rel_남의것": "evt_9"}),
        datasets=_datasets(), ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    reasons = str(got["blocked"]["internal_reasons"])
    assert "rel_2" in reasons and "rel_남의것" in reasons


def test_요구_관계_집합이_비면_계산하지_않는다(monkeypatch):
    """★ 무엇을 승인해야 하는지 모르는 채로 계산하면, 승인 검사 자체가 무의미하다."""
    _approved(monkeypatch)
    got = pc.calculate(_req(required_relation_ids=()), datasets=_datasets(),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "요구하는 관계 집합" in str(got["blocked"]["internal_reasons"])


def test_두_번째_행부터_다른_판이_섞이면_무결성_장애다(monkeypatch):
    """★★★ [감사 실측] 앞 판은 **첫 행의 판만** 검사했다. 그래서 두 번째 행부터 다른
    Snapshot 을 섞어 넣어도 `COMPLETE` 가 나왔다.

    ⚠️ 「판 하나를 봉인했다」는 말은 **그 판의 행만 읽었다**는 뜻이어야 한다. 섞인 자료로
      만든 숫자는 어느 판의 것인지 말할 수 없고, 그러면 재현도 반증도 불가능하다."""
    _approved(monkeypatch)
    ds = _datasets()
    ds["INV-01"] = [ds["INV-01"][0],
                    {**ds["INV-01"][1], "__snapshot_id__": "ds_몰래_섞은_판"}]
    with pytest.raises(pc.PathCalculationError, match="여러 판의 행이 섞였습니다"):
        pc.calculate(_req(), datasets=ds, ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)


def test_판은_봉인됐는데_행이_0건이면_BLOCKED_다(monkeypatch):
    """⚠️ 이것은 무결성 장애가 **아니다** — 자료가 아직 없는 것이다. 장애로 올리면
    「데이터를 채워야 한다」가 「시스템이 고장났다」로 보인다."""
    _approved(monkeypatch)
    ds = _datasets()
    ds["MDM-05"] = []
    got = pc.calculate(_req(), datasets=ds, ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "0건" in str(got["blocked"]["internal_reasons"])


def test_경로_판을_위조하면_거부한다(monkeypatch):
    """★★★ [감사 실측] 앞 판은 호출자가 주장한 `path_model_version` 을 그대로 지문에
    실었다. `"0.0.0-fake"` 로도 `COMPLETE` 가 나왔고, 그 지문은 재현 검증을 통과한다.

    ⚠️ 조용히 덮어쓰지 않고 **거부**한다 — 덮어쓰면 호출자는 자기가 다른 판을 요청한 줄
      모른 채 다른 규칙의 답을 받는다."""
    _approved(monkeypatch)
    with pytest.raises(pc.PathCalculationError, match="경로 판이 코드와 다릅니다"):
        pc.calculate(_req(path_model_version="0.0.0-fake"), datasets=_datasets(),
                     ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)


def test_요구_관계_집합이_다르면_질문_지문도_다르다(monkeypatch):
    """★ 같은 승인을 냈어도 **어느 경로의 질문이었나**가 다르면 다른 질문이다."""
    _approved(monkeypatch)
    a = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    b = pc.calculate(_req(required_relation_ids=("rel_1", "rel_2"),
                          relation_approvals={"rel_1": "evt_1", "rel_2": "evt_2"}),
                     datasets=_datasets(), ledger_verifier=_ok_ledger,
                     relation_verifier=_ok_relation)
    assert a["request_fingerprint"] != b["request_fingerprint"]


# ── ⑦ [P0-CALC-INPUT] 정본 필드로 계산된다 ──────────────────────────────

def test_LOG_02_의_자재는_PRC_02_를_거쳐_찾는다(monkeypatch):
    """★★★ [감사 실측] `LOG-02` 에는 **자재 ID 가 없다.** 주문행을 거치지 않으면
    「어느 자재의 선적인가」를 알 수 없다.

    ⚠️ 앞 판은 이 결합 없이 `LOG-02.material_code` 를 읽었고, 실제 CSV 를 넣자 즉시
      실패했다 — 그런데 집중 회귀는 전부 초록이었다(fixture 가 계산 모델의 말로 쓰여
      있었다). **fixture 가 계약을 대신 정의하면 시험은 아무것도 지키지 못한다.**"""
    _approved(monkeypatch)
    got = pc.calculate(_req(), datasets=_datasets(), ledger_verifier=_ok_ledger,
                       relation_verifier=_ok_relation)
    assert got["status"] == pc.COMPLETE, got.get("blocked")
    #: SHP-1 은 PO-1 → LIOH 다. 그 결합이 되어야 운송 중 수량이 자재별로 나온다.
    assert got["metrics"]["in_transit_quantity"] == {"LIOH": 1000.0}


def test_주문행을_못_찾으면_그_선적을_빼지_않고_막는다(monkeypatch):
    """★★★ 빼면 **운송 중 수량이 조용히 줄고** 그것은 「지연이 없다」로 읽힌다.

    ⚠️ 계산에서 한 줄을 빼는 것은 0 을 넣는 것과 같다 — 화면은 평온하다."""
    _approved(monkeypatch)
    prc = [{"po_line_id": "PO-9", "material_id": "OTHER"}]      # SHP-1 의 PO-1 이 없다
    got = pc.calculate(_req(), datasets=_datasets(**{"PRC-02": prc}),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert got["metrics"] == {}
    assert "PRC-02 에서 찾을 수 없어" in str(got["blocked"]["internal_reasons"])


def test_한_주문행에_자재가_둘이면_고르지_않는다(monkeypatch):
    _approved(monkeypatch)
    prc = [{"po_line_id": "PO-1", "material_id": "LIOH"},
           {"po_line_id": "PO-1", "material_id": "NIOH"}]
    got = pc.calculate(_req(), datasets=_datasets(**{"PRC-02": prc}),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "자재가 둘" in str(got["blocked"]["internal_reasons"])


def test_생산_판매_연결은_승인된_배분에서만_온다(monkeypatch):
    """★★★ 정본 근거가 «승인된 allocation» 이다(§관계표 `FULFILLS_SALES`).

    ⚠️ 제품·기간이 같다고 이어 붙이면 그것은 승인이 아니라 **추측**이고, 매출 이연이
      그 추측 위에 세워진다. 배분이 없으면 연결하지 않고, 계산기가 그것을 드러낸다."""
    _approved(monkeypatch)
    got = pc.calculate(
        _req(assumptions={"reserved_quantity_zero": True,
                          "baseline_recognition": {"SL-1": "2026-09-30T00:00:00+00:00"},
                          "recognition_span_days": {"SL-1": "30"}}),   # 배분 없음
        datasets=_datasets(), ledger_verifier=_ok_ledger,
        relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "기준선" in str(got["blocked"]["internal_reasons"])
    assert got["metrics"] == {}


def test_승인된_배분이_없는_계획행을_가리키면_막는다(monkeypatch):
    """⚠️ 없는 계획에 매출을 붙이면 그 이연은 아무 근거가 없다."""
    _approved(monkeypatch)
    got = pc.calculate(
        _req(assumptions={"reserved_quantity_zero": True,
                          "baseline_recognition": {"SL-1": "2026-09-30T00:00:00+00:00"},
                          "sales_allocation": {"SL-1": "PL-없음"},
                          "recognition_span_days": {"SL-1": "30"}}),
        datasets=_datasets(), ledger_verifier=_ok_ledger,
        relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "MFG-01 에 없습니다" in str(got["blocked"]["internal_reasons"])


def test_정본_열이_하나라도_없으면_추측하지_않고_막는다(monkeypatch):
    """★★★ 「비슷한 이름의 다른 열로 이어 붙이기」를 막는다 — 그 순간 「어느 자재인가」가
    코드 한 줄의 추측이 된다."""
    _approved(monkeypatch)
    inv = [{"material_id": "LIOH", "location_id": "WH1",
            "snapshot_date": "2026-08-20T00:00:00+00:00"}]      # 수량 열이 없다
    got = pc.calculate(_req(), datasets=_datasets(**{"INV-01": inv}),
                       ledger_verifier=_ok_ledger, relation_verifier=_ok_relation)
    assert got["status"] == pc.BLOCKED
    assert "unrestricted_quantity" in str(got["blocked"]["internal_reasons"])


def test_PRC_02_가_필수_계약키에_들어_있다():
    """★ 계산 능력 등록부에는 없지만 **투영에 필요하다.** 등록부만 믿으면 정본으로는
    한 줄도 계산되지 않는다."""
    assert "PRC-02" in pc.REQUIRED_DATASETS
