"""★★★ [BDR-3] L0 파일 Snapshot — 파일 하나가 **믿을 수 있는 표**가 되기까지.

이 시험이 전제하는 것: **저장소는 `tmp_path` 로 격리한다.** 조직도·LLM 을 쓰지 않는다.

## 이 파일이 막으려는 세 가지

★★★ ① **실패를 0행으로 저장하지 않는다.** 파싱이 깨졌는데 「0행 Snapshot」이 남으면
  그것은 「데이터가 없다」로 읽히고, 그 위에서 계산이 돌아 **합계가 0인 보고서**가
  나온다. 아무도 그것이 고장이라고 생각하지 않는다.
★★★ ② **잘린 파일을 전체로 저장하지 않는다.** 읽다 끊긴 파일은 「일부」이지 「작은
  파일」이 아니다.
★★★ ③ **파일명으로 원천을 믿지 않는다.** 이름은 아무것도 보증하지 않는다 — 믿는
  것은 내용의 SHA-256 이다.
"""
import os

import pytest

from core.data_preparation import models as m
from core.data_preparation import snapshot_service as ss
from core.data_preparation.store import DataPreparationStore

GOOD_CSV = (
    "ordered_at,material_code,quantity,unit_price\n"
    "2026-01-05,M1,10,1000\n"
    "2026-01-06,M2,5,2000\n"
).encode("utf-8")

GOOD_ROWS = [
    {"ordered_at": "2026-01-05", "material_code": "M1", "quantity": "10",
     "unit_price": "1000"},
    {"ordered_at": "2026-01-06", "material_code": "M2", "quantity": "5",
     "unit_price": "2000"},
]
GOOD_COLS = ["ordered_at", "material_code", "quantity", "unit_price"]
CONTROL = {"row_count": 2, "sums": {"quantity": 15, "unit_price": 3000}}


def _reg_kit(store, kit_id="k", version="1.0.0"):
    """시험용 키트를 **등록부에 올리고** 지문을 돌려준다.

    ★★★ [M0-3.1 ④] `create_instance` 는 등록된 판본만 받는다 — 임의 지문으로 인증판을
      쌓으면 「어느 계약의 판인가」에 답할 수 없다. 지문은 손으로 적지 않고 등록 결과에서
      읽는다."""
    store.upsert_kit_version(
        kit_id=kit_id, version=version, name=f"{kit_id} 시험용", mode="DEMO/SYNTHETIC",
        source_path=f"{kit_id}.test.json", fingerprint_value=f"fp-test-{kit_id}",
        profile={"datasets": []})
    return store.get_kit_version(kit_id, version)["fingerprint"]


@pytest.fixture
def store(tmp_path):
    return DataPreparationStore(db_path=str(tmp_path / "dp.db"))


@pytest.fixture
def binding(store):
    inst = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint=_reg_kit(store),
                                 tenant_id="t1", scope_node_id="n1", entity_mode="REAL")
    return store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key="purchase_orders",
        provider=m.PROVIDER_FILE_SNAPSHOT,
        config={"file_name": "po.csv", "column_map": {"a": "A"}},
        tenant_id="t1", scope_node_id="n1", entity_mode="REAL")


def _ingest(store, binding, tmp_path, payload=GOOD_CSV, name="po.csv", data_kind=None):
    kw = {} if data_kind is None else {"data_kind": data_kind}
    return ss.ingest(store, binding=binding, payload=payload, file_name=name,
                     workspace_root=str(tmp_path), created_by="t_admin@test.invalid", **kw)


# ── ① 실패는 0행이 아니다 ───────────────────────────────────────────────
@pytest.mark.parametrize("payload,why", [
    (b"", "비어"),
    (b"ordered_at,quantity\n", "데이터 행이 없습니다"),
    ("주문일,수량\n".encode("cp949"), "UTF-8"),
    #: ⚠️ 이 바이트열은 **UTF-8 로는 디코드된다**(제어문자). NUL 검사가 없으면
    #:   「데이터 행이 없습니다」로 빠져 막히긴 하지만 **사유가 틀린다** — 사용자는
    #:   파일이 잘못된 줄 모르고 내용을 의심한다.
    (b"\x00\x01\x02\x03", "이진 파일"),
])
def test_a_broken_file_creates_no_snapshot_at_all(store, binding, tmp_path, payload, why):
    """★★★ **파싱 실패는 Snapshot 을 남기지 않는다.**

    ⚠️ 「0행 Snapshot」이 남으면 그것은 「데이터가 없다」로 읽히고, 그 위에서 돌아간
      계산은 **합계 0** 을 낸다 — 그리고 아무도 그것을 고장으로 보지 않는다."""
    with pytest.raises(ss.IngestError) as e:
        _ingest(store, binding, tmp_path, payload=payload)
    assert why in str(e.value)
    assert store.list_snapshots(binding["instance_id"]) == [], "실패가 Snapshot 을 남겼다"


def test_a_header_only_file_is_not_a_zero_row_table(store, binding, tmp_path):
    """⚠️ 「머리글만 있는 파일」은 **데이터가 없는 것**이지 0행 표가 아니다 — 사람이
    잘못된 파일을 올린 것에 가깝다."""
    with pytest.raises(ss.IngestError):
        _ingest(store, binding, tmp_path, payload=b"a,b,c\n")


def test_a_file_without_a_header_is_refused(store, binding, tmp_path):
    with pytest.raises(ss.IngestError):
        _ingest(store, binding, tmp_path, payload=b"")


# ── ③ 이름이 아니라 내용을 믿는다 ───────────────────────────────────────
def test_the_checksum_comes_from_the_content_not_the_name(store, binding, tmp_path):
    """★★★ `purchase_orders_2026.csv` 라는 이름은 아무것도 보증하지 않는다."""
    a = _ingest(store, binding, tmp_path, name="purchase_orders_2026.csv")
    b = _ingest(store, binding, tmp_path, name="아무이름.csv")
    assert a["checksum"] == b["checksum"], "같은 내용인데 지문이 다르다"

    other = _ingest(store, binding, tmp_path,
                    payload=GOOD_CSV + b"2026-01-07,M3,1,50\n", name="purchase_orders_2026.csv")
    assert other["checksum"] != a["checksum"], "내용이 다른데 지문이 같다"


@pytest.mark.parametrize("name", ["a.xlsx", "b.json", "c.txt", "d.parquet"])
def test_an_unsupported_format_is_refused(store, binding, tmp_path, name):
    """⚠️ 파서가 확실하지 않은 형식을 «되는 만큼» 읽으면 잘린 표가 전체로 들어온다."""
    with pytest.raises(ss.IngestError) as e:
        _ingest(store, binding, tmp_path, name=name)
    assert "만 읽습니다" in str(e.value)


# ── RAW 보관 ─────────────────────────────────────────────────────────────
def test_the_raw_file_is_stored_and_reproduces_its_checksum(store, binding, tmp_path):
    """★ Gate D 의 「RAW checksum 재현」."""
    snap = _ingest(store, binding, tmp_path)
    assert os.path.exists(snap["raw_path"])
    assert ss.verify_raw(snap["raw_path"], snap["checksum"]) is True
    assert snap["byte_size"] == len(GOOD_CSV)


def test_a_tampered_raw_file_fails_verification(store, binding, tmp_path):
    """⚠️ 보관본이 바뀌면 「그때 그 파일」이라는 전제가 깨진다 — 그 사실이 보여야 한다."""
    snap = _ingest(store, binding, tmp_path)
    with open(snap["raw_path"], "ab") as f:
        f.write("2026-01-09,M9,1,1\n".encode("utf-8"))
    assert ss.verify_raw(snap["raw_path"], snap["checksum"]) is False


def test_the_raw_area_is_not_overwritten(store, binding, tmp_path):
    """⚠️ 덮어쓰기를 허용하면 checksum 은 그대로인데 파일이 달라질 수 있다."""
    snap = _ingest(store, binding, tmp_path)
    with pytest.raises(ss.IngestError):
        ss.store_raw(str(tmp_path), snap["snapshot_id"], GOOD_CSV, "po.csv")


def test_a_snapshot_always_starts_at_raw(store, binding, tmp_path):
    """⚠️ 호출부가 상태를 정하게 두면 「파싱도 안 했는데 인증됨」이 만들어진다."""
    snap = _ingest(store, binding, tmp_path)
    assert snap["state"] == m.RAW
    assert snap["certified_at"] == ""


# ── 스키마 추정 ──────────────────────────────────────────────────────────
def test_the_schema_is_inferred_from_the_values(store, binding, tmp_path):
    snap = _ingest(store, binding, tmp_path)
    types = {c["name"]: c["type"] for c in snap["schema"]}
    assert types == {"ordered_at": "datetime", "material_code": "string",
                     "quantity": "number", "unit_price": "number"}


def test_an_empty_column_is_unknown_not_string():
    """⚠️ `string` 으로 두면 「빈 열」과 「글자 열」이 같아지고, 나중에 숫자를 넣으려다
    형이 안 맞는 이유를 못 찾는다."""
    assert ss.infer_type([]) == "unknown"
    assert ss.infer_type(["", "  "]) == "unknown"
    assert ss.infer_type(["1", ""]) == "number"


# ── 전이표 ───────────────────────────────────────────────────────────────
def test_the_snapshot_transition_table_is_pinned_literally():
    """★ 표를 통째로 박아 둔다 — 종점을 늘리는 사람이 «반드시» 여기를 보게 한다.

    ⚠️ [2026-09-11] 실제로 걸렸다. `SOURCE_CERTIFIED` 를 더하면서 이 시험이 깨졌고,
      그래서 「인증 종점이 하나 더 생긴다」는 사실을 지나칠 수 없었다. 이런 시험이
      «귀찮은 시험» 처럼 보이지만, 그 귀찮음이 목적이다."""
    assert m.SNAPSHOT_TRANSITIONS == {
        "RAW": ("PROFILED", "QUARANTINED"),
        "PROFILED": ("STANDARDIZED", "QUARANTINED"),
        "STANDARDIZED": ("RECONCILED", "QUARANTINED"),
        #: 대사를 마친 판은 «성격에 맞는» 종점으로 간다 — 어느 쪽인지는 data_kind 가 정한다.
        "RECONCILED": ("DEMO_CERTIFIED", "SOURCE_CERTIFIED", "OWNER_CERTIFIED", "QUARANTINED"),
        "DEMO_CERTIFIED": ("REVOKED",),
        "SOURCE_CERTIFIED": ("REVOKED",),
        "OWNER_CERTIFIED": ("REVOKED",),
        "QUARANTINED": (),
        "REVOKED": (),
    }


# ── 인증 종점 셋 — 시연/공표 원천/회사 실적의 책임을 구분한다 (2026-09-12) ──────
def test_the_three_certification_endpoints_preserve_data_kind():
    """★★★ 종점마다 허용 성격이 다르다. 섞이면 어느 것이 시연이었는지 가릴 수 없다."""
    assert m.CERTIFIED_STATES == (m.DEMO_CERTIFIED, m.SOURCE_CERTIFIED, m.OWNER_CERTIFIED)
    assert m.CERTIFICATION_DATA_KIND[m.DEMO_CERTIFIED] == m.DATA_KIND_DEMO
    assert m.CERTIFICATION_DATA_KIND[m.SOURCE_CERTIFIED] == m.DATA_KIND_REAL
    assert m.CERTIFICATION_DATA_KIND[m.OWNER_CERTIFIED] == m.DATA_KIND_REAL


def test_is_certified_covers_all_three_endpoints():
    """★ 「인증되었는가」를 묻는 자리는 이 함수를 쓴다 — 상수를 직접 비교하면
    종점이 늘어난 날 한 곳만 고쳐지고 실물이 조용히 안 보인다."""
    assert m.is_certified(m.DEMO_CERTIFIED) is True
    assert m.is_certified(m.SOURCE_CERTIFIED) is True
    assert m.is_certified(m.OWNER_CERTIFIED) is True
    for state in (m.RAW, m.PROFILED, m.STANDARDIZED, m.RECONCILED,
                  m.QUARANTINED, m.REVOKED, "", None):
        assert m.is_certified(state) is False


def test_real_data_cannot_take_the_demo_endpoint(store, binding, tmp_path):
    snap = _ingest(store, binding, tmp_path, data_kind=m.DATA_KIND_REAL)
    sid = snap["snapshot_id"]
    ss.profile(store, sid, GOOD_ROWS, GOOD_COLS)
    ss.standardize(store, sid, GOOD_ROWS)
    ss.reconcile(store, sid, GOOD_ROWS, {"row_count": len(GOOD_ROWS)})
    with pytest.raises(m.StateConflict) as e:
        store.advance_snapshot(sid, m.DEMO_CERTIFIED)
    assert "DEMO/SYNTHETIC» 전용" in str(e.value)


def test_demo_data_cannot_take_the_source_endpoint(store, binding, tmp_path):
    """★ 반대편 — 시연 자료가 «원천 인증» 을 받으면 시연이 실물로 읽힌다."""
    snap = _ingest(store, binding, tmp_path)
    sid = snap["snapshot_id"]
    ss.profile(store, sid, GOOD_ROWS, GOOD_COLS)
    ss.standardize(store, sid, GOOD_ROWS)
    ss.reconcile(store, sid, GOOD_ROWS, {"row_count": len(GOOD_ROWS)})
    with pytest.raises(m.StateConflict) as e:
        store.advance_snapshot(sid, m.SOURCE_CERTIFIED)
    assert "REAL» 전용" in str(e.value)


# ── ② 잘림 ≠ 전체 ───────────────────────────────────────────────────────
def test_a_truncated_file_is_quarantined_by_the_row_count(store, binding, tmp_path):
    """★★★ 읽다 끊긴 파일은 **행 수가 모자라다** — 원천이 말한 수와 대사해 잡는다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control={"row_count": 12})
    assert out["state"] == m.QUARANTINED
    kinds = {mm["kind"] for mm in out["control_total"]["mismatches"]}
    assert "row_count" in kinds
    assert "잘렸" in out["quarantine"]["mismatches"][0]["note"]


def test_a_truncated_file_is_quarantined_by_the_sum(store, binding, tmp_path):
    """⚠️ 행 수가 맞아도 값이 변형됐을 수 있다 — 합계가 두 번째 그물이다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control={"row_count": 2, "sums": {"quantity": 99}})
    assert out["state"] == m.QUARANTINED


def test_the_sum_tolerance_is_absolute_not_relative():
    """★★★ 상대 오차로 두면 **금액이 커질수록 허용 폭이 커진다** — 큰 숫자일수록
    틀려도 통과한다. 반대로 가야 한다."""
    rows = [{"amount": "1000000000"}]
    off_by_one = ss.reconcile_totals(rows, {"sums": {"amount": 1000000001}})
    assert off_by_one["ok"] is False, "10억에서 1 차이를 놓쳤다"


def test_an_unreadable_number_is_a_mismatch_not_a_zero():
    """⚠️ 읽을 수 없는 값을 0 으로 세면 합계는 그럴듯해지고 차이는 사라진다."""
    rows = [{"amount": "1000"}, {"amount": "천원"}]
    out = ss.reconcile_totals(rows, {"sums": {"amount": 1000}})
    assert out["ok"] is False
    assert out["checked"][0]["unreadable"] == 1


def test_a_matching_file_reconciles(store, binding, tmp_path):
    snap = _ingest(store, binding, tmp_path)
    out = ss.reconcile(store, snap["snapshot_id"], GOOD_ROWS, CONTROL) \
        if False else None
    row = ss.profile(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS)
    row = ss.standardize(store, snap["snapshot_id"], GOOD_ROWS)
    row = ss.reconcile(store, snap["snapshot_id"], GOOD_ROWS, CONTROL)
    assert row["state"] == m.RECONCILED
    assert row["control_total"]["ok"] is True


# ── 미매핑·단위 격리 ─────────────────────────────────────────────────────
def test_unmapped_codes_are_quarantined(store, binding, tmp_path):
    """⚠️ 매핑되지 않은 코드를 통과시키면 집계에서 조용히 다른 것과 묶이거나 빠진다 —
    어느 쪽이든 합계는 그럴듯해 보인다."""
    snap = _ingest(store, binding, tmp_path)
    ss.profile(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS)
    out = ss.standardize(store, snap["snapshot_id"], GOOD_ROWS,
                         code_columns={"material_code": ["M1"]})
    assert out["state"] == m.QUARANTINED
    assert out["quarantine"]["unmapped_count"] == 1
    assert out["quarantine"]["unmapped"][0]["value"] == "M2"


def test_a_unit_mismatch_is_quarantined(store, binding, tmp_path):
    """⚠️ 단위가 다른 값을 그대로 더하면 «톤 + 킬로그램» 이 된다 — 그 숫자는 틀린
    줄도 모르고 보고서에 실린다."""
    snap = _ingest(store, binding, tmp_path)
    ss.profile(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS)
    out = ss.standardize(store, snap["snapshot_id"], GOOD_ROWS,
                         unit_columns={"quantity": "kg"},
                         expected_units={"quantity": "ton"})
    assert out["state"] == m.QUARANTINED
    assert out["quarantine"]["unit_error_count"] >= 1


def test_the_pipeline_stops_at_the_first_quarantine(store, binding, tmp_path):
    """★ 격리되면 거기서 멈춘다 — 계속 가면 「격리됐는데 인증됨」이 된다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL, code_columns={"material_code": ["M1"]})
    assert out["state"] == m.QUARANTINED
    assert out["certified_at"] == ""


def test_a_quarantined_snapshot_cannot_be_fixed_in_place(store, binding, tmp_path):
    """⚠️ 같은 Snapshot 을 고쳐 통과시키면 「무엇이 왜 격리됐는가」의 이력이 지워진다 —
    고친 파일은 **새 Snapshot** 이다."""
    snap = _ingest(store, binding, tmp_path)
    ss.profile(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS)
    ss.standardize(store, snap["snapshot_id"], GOOD_ROWS,
                   code_columns={"material_code": ["M1"]})
    for target in (m.STANDARDIZED, m.RECONCILED, m.DEMO_CERTIFIED, m.RAW):
        with pytest.raises(m.StateConflict):
            store.advance_snapshot(snap["snapshot_id"], target)


# ── 인증 ─────────────────────────────────────────────────────────────────
def test_a_clean_file_reaches_demo_certified(store, binding, tmp_path):
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    assert out["state"] == m.DEMO_CERTIFIED
    assert out["certified_at"]
    assert out["data_kind"] == m.DATA_KIND_DEMO


def test_certification_never_claims_a_real_actual(store, binding, tmp_path):
    """★★★ 실제 Data Owner 가 없으므로 `CERTIFIED ACTUAL` 을 **주장하지 않는다.**"""
    assert "ACTUAL" not in m.SNAPSHOT_STATES
    assert m.DEMO_CERTIFIED == "DEMO_CERTIFIED"
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    label = ss.display_label(out)
    assert "시연" in label and "실적 인증이 아닙니다" in label


def test_real_data_is_not_demo_certified(store, binding, tmp_path):
    """⚠️ 섞이는 순간 어느 것이 시연이었는지 가릴 수 없다."""
    snap = store.create_snapshot(
        binding_id=binding["binding_id"], instance_id=binding["instance_id"],
        dataset_contract_key="x", checksum="c" * 64, row_count=1,
        data_kind=m.DATA_KIND_REAL, tenant_id="t1", scope_node_id="n1",
        entity_mode="REAL")
    store.advance_snapshot(snap["snapshot_id"], m.PROFILED)
    store.advance_snapshot(snap["snapshot_id"], m.STANDARDIZED)
    store.advance_snapshot(snap["snapshot_id"], m.RECONCILED)
    with pytest.raises(m.StateConflict) as e:
        ss.certify_demo(store, snap["snapshot_id"])
    assert "섞이면" in str(e.value)


def test_a_certified_snapshot_cannot_be_edited(store, binding, tmp_path):
    """★★★ Gate D 의 「인증 후 수정 차단」.

    ⚠️ 인증된 것을 고칠 수 있게 두면 「우리가 인증한 그 숫자」가 무엇이었는지 아무도
      답할 수 없다 — 보고서에 실린 값과 지금 표의 값이 달라도 알아챌 방법이 없다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    assert out["state"] == m.DEMO_CERTIFIED
    for target in (m.RAW, m.PROFILED, m.STANDARDIZED, m.RECONCILED, m.QUARANTINED):
        with pytest.raises(m.StateConflict):
            store.advance_snapshot(out["snapshot_id"], target)
    #: 되돌릴 수 있는 것은 **폐기**뿐이다
    assert store.advance_snapshot(out["snapshot_id"], m.REVOKED)["state"] == m.REVOKED


def test_the_raw_body_is_untouched_by_the_pipeline(store, binding, tmp_path):
    """★ 파이프라인이 갱신하는 것은 «새로 알아낸 것»뿐이다 — 원문·지문·행 수는 아니다."""
    snap = _ingest(store, binding, tmp_path)
    before = (snap["raw_path"], snap["checksum"], snap["row_count"], snap["byte_size"])
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    assert (out["raw_path"], out["checksum"], out["row_count"], out["byte_size"]) == before
    assert ss.verify_raw(out["raw_path"], out["checksum"]) is True


def test_a_correction_is_a_new_snapshot(store, binding, tmp_path):
    """★ 정정은 **새 Snapshot** 이고, 옛 것은 그대로 남는다."""
    first = _ingest(store, binding, tmp_path)
    ss.run_pipeline(store, first["snapshot_id"], GOOD_ROWS, GOOD_COLS, control=CONTROL)
    fixed = GOOD_CSV + b"2026-01-07,M3,1,50\n"
    second = _ingest(store, binding, tmp_path, payload=fixed, name="po_v2.csv")
    assert second["snapshot_id"] != first["snapshot_id"]
    assert store.get_snapshot(first["snapshot_id"])["state"] == m.DEMO_CERTIFIED
    assert len(store.list_snapshots(binding["instance_id"])) == 2


def _reconciled_correction(store, binding, tmp_path):
    payload = GOOD_CSV + b"2026-01-07,M3,1,50\n"
    rows = GOOD_ROWS + [{"ordered_at": "2026-01-07", "material_code": "M3",
                         "quantity": "1", "unit_price": "50"}]
    snap = _ingest(store, binding, tmp_path, payload=payload, name="po_v2.csv")
    ss.profile(store, snap["snapshot_id"], rows, GOOD_COLS)
    ss.standardize(store, snap["snapshot_id"], rows)
    ss.reconcile(store, snap["snapshot_id"], rows, {"row_count": 3})
    return store.get_snapshot(snap["snapshot_id"])


def test_demo_correction_atomically_replaces_the_certified_snapshot(store, binding,
                                                                     tmp_path):
    old = _ingest(store, binding, tmp_path)
    old = ss.run_pipeline(store, old["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    new = _reconciled_correction(store, binding, tmp_path)

    out = ss.certify_demo_replacement(store, old["snapshot_id"], new["snapshot_id"])

    assert out["state"] == m.DEMO_CERTIFIED
    assert store.get_snapshot(old["snapshot_id"])["state"] == m.REVOKED
    assert ss.verify_raw(old["raw_path"], old["checksum"]), "옛 원문은 그대로 보존한다"


def test_demo_replacement_rolls_back_both_states_if_indexing_fails(store, binding,
                                                                   tmp_path):
    old = _ingest(store, binding, tmp_path)
    old = ss.run_pipeline(store, old["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    new = _reconciled_correction(store, binding, tmp_path)

    def broken_index(_conn, _fresh):
        raise RuntimeError("index failed")

    with pytest.raises(RuntimeError, match="index failed"):
        store.replace_demo_snapshot(old["snapshot_id"], new["snapshot_id"],
                                    on_commit=broken_index)
    assert store.get_snapshot(old["snapshot_id"])["state"] == m.DEMO_CERTIFIED
    assert store.get_snapshot(new["snapshot_id"])["state"] == m.RECONCILED


# ── 프로파일 ─────────────────────────────────────────────────────────────
def test_profiling_counts_missing_and_duplicates():
    rows = [{"a": "1", "b": ""}, {"a": "1", "b": ""}, {"a": "2", "b": "x"}]
    out = ss.profile_rows(rows, ["a", "b"])
    assert out["row_count"] == 3
    assert out["missing"] == {"a": 0, "b": 2}
    assert out["duplicate_rows"] == 1
    assert out["distinct"]["a"] == 2


# ── 최소 종단 3종 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("key,csv_text,control", [
    ("PRC-02",
     "ordered_at,material_code,quantity,unit_price\n"
     + "".join(f"2026-01-{d:02d},M{d % 3 + 1},{d},{d * 100}\n" for d in range(1, 13)),
     {"row_count": 12, "sums": {"quantity": 78, "unit_price": 7800}}),
    ("INV-01",
     "item_code,plant_code,quantity\nA1,P1,100\nA2,P1,50\nA1,P2,25\n",
     {"row_count": 3, "sums": {"quantity": 175}}),
    ("FIN-03",
     "month,revenue,cost,cash_open,cash_close\n"
     + "".join(f"2026-0{i},1000,600,{i * 100},{i * 100 + 400}\n" for i in range(1, 7)),
     {"row_count": 6, "sums": {"revenue": 6000, "cost": 3600}}),
])
def test_the_three_minimum_contracts_certify(store, binding, tmp_path, key, csv_text,
                                             control):
    """★ 시연 최소 종단 3종(PRC-02 · INV-01 · FIN-03)이 각각 인증까지 간다."""
    import csv as _csv
    import io as _io

    payload = csv_text.encode("utf-8")
    snap = _ingest(store, binding, tmp_path, payload=payload, name=f"{key}.csv")
    rows = list(_csv.DictReader(_io.StringIO(csv_text)))
    out = ss.run_pipeline(store, snap["snapshot_id"], rows, list(rows[0]),
                          control=control)
    assert out["state"] == m.DEMO_CERTIFIED, out.get("quarantine")
    assert out["row_count"] == control["row_count"]


def test_the_label_names_the_data_kind_not_just_the_state(store, binding, tmp_path):
    """★★★ 표시가 **성격**을 말해야 한다.

    ⚠️ 앞 시험은 이것을 못 잡는다 — 상태 꼬리표(「시연 인증됨」)에도 「시연」이 들어
      있어서, 성격 표시를 통째로 지워도 통과했다(변이 검사 실측).
    ★ 화면이 「샘플입니다」를 말하지 않으면 그 숫자는 실적으로 읽힌다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.run_pipeline(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS,
                          control=CONTROL)
    label = ss.display_label(out)
    assert m.DATA_KIND_DEMO in label, f"성격 표시가 사라졌다: {label}"

    #: 아직 인증 전이어도 성격은 늘 붙는다
    other = _ingest(store, binding, tmp_path, payload=GOOD_CSV + b"2026-01-08,M4,2,20\n",
                    name="b.csv")
    assert m.DATA_KIND_DEMO in ss.display_label(other)


def test_a_caller_cannot_choose_the_initial_state(store, binding):
    """★★★ 상태를 호출부가 정하게 두면 「파싱도 안 했는데 인증됨」이 만들어진다."""
    snap = store.create_snapshot(
        binding_id=binding["binding_id"], instance_id=binding["instance_id"],
        dataset_contract_key="x", checksum="c" * 64, row_count=1,
        state=m.DEMO_CERTIFIED,                       # ← 무시돼야 한다
        tenant_id="t1", scope_node_id="n1", entity_mode="REAL")
    assert snap["state"] == m.RAW, "호출부가 정한 상태가 그대로 들어갔다"
    assert store.get_snapshot(snap["snapshot_id"])["state"] == m.RAW


# ── [BDR-3] API 경계 ─────────────────────────────────────────────────────
#
# 이 절이 전제하는 것: **`enforced_org`**(합성 조직 + 강제 ON). 여기서 보는 것이
# 「누가 어느 Snapshot 을 볼 수 있는가」이므로 조직 경계가 필요하다.
import api.routes.data_preparation_control as dp                     # noqa: E402
from fastapi import FastAPI                                          # noqa: E402
from fastapi.testclient import TestClient                            # noqa: E402

from tests import org_seed                                           # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    #: ⚠️ RAW 보관 뿌리를 반드시 옮긴다 — 옮기지 않으면 시험이 **운영 데이터 영역에
    #:   파일을 쓴다.**
    monkeypatch.setattr(dp, "_raw_root", lambda: str(tmp_path / "raw"))
    monkeypatch.setattr(dp, "_ctx", lambda p: {"tenant_id": "tenant_default",
                                               "entity_mode": "REAL"})
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_mine"])
    app = FastAPI()
    app.include_router(dp.router)
    return TestClient(app)


def _as(user):
    return {"X-Factory-User": user}


def _api_binding(scope_node_id="n_mine"):
    inst = dp.store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint=_reg_kit(dp.store),
                                    tenant_id="tenant_default",
                                    scope_node_id=scope_node_id, entity_mode="REAL")
    return dp.store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key="arrivals",
        provider=m.PROVIDER_FILE_SNAPSHOT,
        config={"file_name": "a.csv", "column_map": {"a": "A"}},
        tenant_id="tenant_default", scope_node_id=scope_node_id, entity_mode="REAL")


def _upload(client, binding_id, payload=GOOD_CSV, name="po.csv", user=org_seed.ADMIN):
    return client.post(f"/api/v1/data-preparation/bindings/{binding_id}/snapshots",
                       files={"file": (name, payload, "text/csv")}, headers=_as(user))


def test_uploading_a_file_creates_a_raw_snapshot(client):
    r = _upload(client, _api_binding()["binding_id"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["state"] == m.RAW and data["row_count"] == 2
    assert m.DATA_KIND_DEMO in data["display_label"], "화면 표시를 서버가 주지 않았다"


@pytest.mark.parametrize("payload,name", [
    (b"", "po.csv"), (b"a,b,c\n", "po.csv"), (GOOD_CSV, "po.xlsx"),
])
def test_a_broken_upload_is_422_and_leaves_nothing(client, payload, name):
    """★★★ 실패는 **422** 이지 「0행 Snapshot 이 담긴 200」이 아니다."""
    binding = _api_binding()
    r = _upload(client, binding["binding_id"], payload=payload, name=name)
    assert r.status_code == 422, r.text
    assert dp.store.list_snapshots(binding["instance_id"]) == []


def test_a_snapshot_outside_my_scope_is_404_exactly_like_a_missing_one(client):
    """★★★ Gate D — **없는 것과 못 보는 것을 같은 404 로** 돌려준다.

    ⚠️ 다르게 답하면 그 차이가 「그 조직에 그런 데이터가 있다」는 신호가 된다."""
    theirs = _api_binding(scope_node_id="n_theirs")
    snap = ss.ingest(dp.store, binding=theirs, payload=GOOD_CSV, file_name="po.csv",
                     workspace_root=str(dp._raw_root()))

    missing = client.get("/api/v1/data-preparation/snapshots/ds_없는것",
                         headers=_as(org_seed.MEMBER_A))
    out_of_scope = client.get(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}",
        headers=_as(org_seed.MEMBER_A))
    assert missing.status_code == out_of_scope.status_code == 404
    assert missing.json()["detail"] == out_of_scope.json()["detail"], \
        "두 답이 다르면 그 차이가 신호다"


def test_a_snapshot_in_my_scope_is_readable(client):
    """⚠️ 대조군 — 위 시험이 「전부 404」로도 통과하지 않게 한다."""
    mine = _api_binding()
    r = _upload(client, mine["binding_id"])
    got = client.get(f"/api/v1/data-preparation/snapshots/{r.json()['data']['snapshot_id']}",
                     headers=_as(org_seed.ADMIN))
    assert got.status_code == 200, got.text


def test_uploading_into_another_scope_is_404(client):
    theirs = _api_binding(scope_node_id="n_theirs")
    r = _upload(client, theirs["binding_id"], user=org_seed.MEMBER_A)
    assert r.status_code == 404, r.text


def test_listing_snapshots_of_another_scope_is_404(client):
    theirs = _api_binding(scope_node_id="n_theirs")
    r = client.get(f"/api/v1/data-preparation/instances/{theirs['instance_id']}/snapshots",
                   headers=_as(org_seed.MEMBER_A))
    assert r.status_code == 404, r.text


def test_the_upload_route_is_in_the_authority_table():
    """★ 새 쓰기 라우트는 **표에 있어야** 한다 — 없으면 아무도 알려 주지 않는다."""
    from core.route_authority import ROUTE_CAPS

    assert ("POST /api/v1/data-preparation/bindings/{binding_id}/snapshots"
            in ROUTE_CAPS)


def test_an_oversized_upload_is_refused_before_parsing(client, monkeypatch):
    """⚠️ 상한이 없으면 파일 하나가 프로세스 메모리를 먹는다."""
    monkeypatch.setattr(dp, "MAX_UPLOAD_BYTES", 10)
    r = _upload(client, _api_binding()["binding_id"])
    assert r.status_code == 413, r.text


# ── 「누가 인증했나」 — certified_at 은 있는데 certified_by 가 없었다 (2026-09-11) ──
def _to_reconciled(store, binding, tmp_path, data_kind=None):
    snap = _ingest(store, binding, tmp_path, data_kind=data_kind)
    sid = snap["snapshot_id"]
    ss.profile(store, sid, GOOD_ROWS, GOOD_COLS)
    ss.standardize(store, sid, GOOD_ROWS)
    ss.reconcile(store, sid, GOOD_ROWS, {"row_count": len(GOOD_ROWS)})
    return sid


def test_certification_without_a_named_certifier_is_refused(store, binding, tmp_path):
    """★★★ 인증은 「이 판을 써도 된다」는 **사람의 판단**이다.

    ⚠️ 종전에는 `certified_at`(언제)만 남고 «누가» 가 아무 데도 없었다 —
      `approve_source` 와 같은 종류의 구멍이고, T-1 의 「다섯 가지」 중 소유자가
      비는 것과 같은 모양이다."""
    sid = _to_reconciled(store, binding, tmp_path)
    with pytest.raises(m.DataPreparationError) as e:
        store.advance_snapshot(sid, m.DEMO_CERTIFIED)
    assert "certified_by 가 필요합니다" in str(e.value)


def test_the_certifier_is_actually_stored(store, binding, tmp_path):
    """★ 「받았다」와 「저장했다」는 다르다 — 실제로 조회해 본다."""
    sid = _to_reconciled(store, binding, tmp_path)
    store.advance_snapshot(sid, m.DEMO_CERTIFIED, certified_by="someone@test.invalid")
    row = store.get_snapshot(sid)
    assert row["certified_by"] == "someone@test.invalid"
    assert row["certified_at"], "언제도 함께 남아야 한다"


def test_a_non_certifying_transition_needs_no_certifier(store, binding, tmp_path):
    """⚠️ 인증이 아닌 전이에까지 이름을 요구하면 파이프라인이 멈춘다."""
    snap = _ingest(store, binding, tmp_path)
    out = ss.profile(store, snap["snapshot_id"], GOOD_ROWS, GOOD_COLS)
    assert out["state"] == m.PROFILED
    assert out["certified_by"] == ""


def test_certify_demo_records_the_setup_actor(store, binding, tmp_path):
    """시연 인증의 기본 행위자는 «.invalid 합성 계정» 이다 — 대상이 가상회사 자료다."""
    sid = _to_reconciled(store, binding, tmp_path)
    out = ss.certify_demo(store, sid)
    assert out["certified_by"].endswith(".invalid")
    assert "@" in out["certified_by"]
