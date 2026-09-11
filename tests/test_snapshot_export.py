"""[F-3] 승격된 관측값 → 업무키트 Snapshot. 선택지 **B**(스냅샷 경유)의 시험.

이 파일이 지키는 것 여섯.

  ① 계약 열은 **정본에서 왔다** — 내 말로 쓴 20열이 아니다
  ② 조용한 빈 값을 만들지 않는다 — 값·업무키가 없으면 **거부**한다(건너뛰지 않는다)
  ③ 같은 관측값은 **같은 행**이 된다(record_id·lineage_id 가 결정론적)
  ④ ★★★ 실물은 `RECONCILED` 가 종점이다 — 시연 인증이 실물을 **거부**한다
  ⑤ ★★★ 시연 자료의 `SYNTHETIC` 성격을 쓰지 않는다 — T-2 가 막는 그 혼합이다
  ⑥ 남의 계약·남의 provider 로는 안 나간다

## ⚠️ 운영 저장소를 쓰지 않는다

전부 `tmp_path` 격리 인스턴스다. 실제 적재는 별도 1회 실행으로 하고 그 결과는
인계 문서에 남긴다 — 시험이 운영 DB 에 쓰면 정산이 매번 어긋난다(실제로 그랬다).
"""
import pytest

from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from core.external_intelligence import snapshot_export as SX

OBS = [
    {"observation_id": "WB_COPPER:2016-01", "indicator_code": "WB_COPPER",
     "observed_at": "2016-01", "vintage": "2016-01", "value": 4471.79,
     "unit": "$/mt", "currency": "USD", "source_id": "WB_PINK_SHEET", "grade": "silver"},
    {"observation_id": "WB_ZINC:2016-01", "indicator_code": "WB_ZINC",
     "observed_at": "2016-01", "vintage": "2016-01", "value": 1520.36,
     "unit": "$/mt", "currency": "USD", "source_id": "WB_PINK_SHEET", "grade": "silver"},
]

#: ★★★ 운영 스냅샷 `ds_f0ee93365f3747` 의 `schema_json` 에서 «읽어 온» 열 이름과 순서.
#:   손으로 지어내지 않았다 — 이 목록이 틀리면 계약과 파일이 갈린다.
CANON_COLUMNS = [
    "record_id", "tenant_id", "scope_node_id", "data_class", "business_data_kind",
    "data_origin", "quality_status", "certification_status", "as_of_date", "lineage_id",
    "observation_id", "commodity_code", "observed_at", "published_at", "vintage_date",
    "value", "unit", "currency", "source_id", "trust_grade",
]


@pytest.fixture()
def store(tmp_path):
    s = DataPreparationStore(db_path=str(tmp_path / "dp.db"))
    assert "WorkSpace" not in s.db_path, "운영 저장소를 열었다"
    return s


@pytest.fixture()
def binding(store):
    store.upsert_kit_version(kit_id="k", version="1.0.0", name="시험", mode="DEMO/SYNTHETIC",
                             source_path="k.json", fingerprint_value="fp-test",
                             profile={"datasets": []})
    fp = store.get_kit_version("k", "1.0.0")["fingerprint"]
    inst = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint=fp,
                                 tenant_id="T", scope_node_id="S", entity_mode="REAL")
    return store.create_binding(instance_id=inst["instance_id"],
                                dataset_contract_key="EXT-02",
                                provider=m.PROVIDER_FILE_SNAPSHOT, config={},
                                tenant_id="T", scope_node_id="S", entity_mode="REAL")


#: ★ 기본값 표시. `observations or OBS` 로 쓰면 **빈 목록이 기본값으로 되돌아가**
#:   「0건 거부」 시험이 조용히 통과한다 — 실제로 그랬다(2026-09-11).
_UNSET = object()


def _export(store, binding, tmp_path, observations=_UNSET, as_of="2026-09-11"):
    return SX.export(store, binding=binding,
                     observations=OBS if observations is _UNSET else observations,
                     workspace_root=str(tmp_path), created_by="t@test.invalid",
                     as_of_date=as_of)


# ── ① 계약 열은 정본에서 왔다 ────────────────────────────────────────────────
def test_columns_match_the_canonical_contract_exactly():
    """★ 순서까지 같아야 한다 — 열 순서가 달라지면 checksum 이 달라진다."""
    assert list(SX.EXT02_COLUMNS) == CANON_COLUMNS


def test_the_csv_header_is_the_contract():
    header = SX.to_csv(SX.build_rows(OBS, tenant_id="T", scope_node_id="S",
                                     as_of_date="2026-09-11")).decode("utf-8").splitlines()[0]
    assert header.split(",") == CANON_COLUMNS


# ── ② 조용한 빈 값을 만들지 않는다 ──────────────────────────────────────────
def test_an_observation_without_a_value_is_refused_not_skipped():
    """⚠️ 건너뛰면 행 수가 줄고, 그 판은 «원천보다 작은 판» 이 되는데 아무도 모른다."""
    bad = [dict(OBS[0]), {**OBS[1], "value": None}]
    with pytest.raises(SX.SnapshotExportError) as e:
        SX.build_rows(bad, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert "0 으로 채우지 않습니다" in str(e.value)


def test_an_observation_without_a_business_key_is_refused():
    bad = [{**OBS[0], "observation_id": ""}]
    with pytest.raises(SX.SnapshotExportError):
        SX.build_rows(bad, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")


def test_zero_observations_makes_no_empty_snapshot(store, binding, tmp_path):
    with pytest.raises(SX.SnapshotExportError) as e:
        _export(store, binding, tmp_path, observations=[])
    assert "빈 판을 만들지 않습니다" in str(e.value)


# ── ③ 결정론 ────────────────────────────────────────────────────────────────
def test_the_same_observation_becomes_the_same_row():
    """★ 두 번 내보내도 같은 행이어야 중복 적재를 막을 수 있다."""
    a = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    b = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert [r["record_id"] for r in a] == [r["record_id"] for r in b]
    assert [r["lineage_id"] for r in a] == [r["lineage_id"] for r in b]


def test_different_observations_get_different_rows():
    """★ 반대편 — 결정론적이라고 «전부 같아지면» 그것은 키가 아니다."""
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert rows[0]["record_id"] != rows[1]["record_id"]
    assert rows[0]["lineage_id"] != rows[1]["lineage_id"]


def test_the_csv_bytes_are_reproducible():
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert SX.to_csv(rows) == SX.to_csv(rows)
    assert b"\r\n" not in SX.to_csv(rows), "줄바꿈이 플랫폼에 따라 달라지면 checksum 이 흔들린다"


# ── ④ ★★★ 실물은 RECONCILED 가 종점이다 ───────────────────────────────────
def test_real_data_stops_at_reconciled(store, binding, tmp_path):
    out = _export(store, binding, tmp_path)
    assert out["state"] == m.RECONCILED
    assert out["data_kind"] == m.DATA_KIND_REAL
    assert out["quarantined"] is False
    assert not out["stopped_reason"]


def test_demo_certification_refuses_real_data(store, binding, tmp_path):
    """★★★ 관문을 «눌러 본다» — 있다는 것과 걸린다는 것은 다르다."""
    out = _export(store, binding, tmp_path)
    with pytest.raises(m.StateConflict) as e:
        svc.certify_demo(store, out["snapshot_id"])
    assert "시연 인증을 붙이지 않습니다" in str(e.value)


def test_the_result_says_why_it_stopped(store, binding, tmp_path):
    """⚠️ 막힌 이유를 결과에 싣지 않으면 화면은 「그냥 안 됐다」로 그린다."""
    note = _export(store, binding, tmp_path)["certification_note"]
    assert "RECONCILED 가 종점" in note
    assert "별도 결정" in note


# ── ⑤ ★★★ 시연 성격을 쓰지 않는다 ─────────────────────────────────────────
def test_rows_are_not_marked_synthetic():
    """T-2 가 막는 혼합 — 「시연 자료」 그릇에 실물을 넣거나 그 반대."""
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    for r in rows:
        assert r["data_class"] == "PUBLIC_DISCLOSED"
        assert r["data_origin"] == "PUBLIC_DISCLOSED"
        assert "SYNTHETIC" not in r["data_class"]
        assert r["certification_status"] == "UNCERTIFIED"
        assert r["certification_status"] != "CERTIFIED_FOR_DEMO"


def test_publication_date_is_not_invented():
    """★ Pink Sheet 는 값별 발표일을 주지 않는다 — 지어내지 않고 비운다."""
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert all(r["published_at"] == "" for r in rows)
    assert all(r["vintage_date"] for r in rows), "대신 vintage 는 채워져 있어야 한다"


# ── ⑥ 남의 계약·남의 provider 로는 안 나간다 ───────────────────────────────
def test_a_non_file_snapshot_binding_is_refused(store, binding, tmp_path):
    other = dict(binding, provider=m.PROVIDER_AFS_NATIVE)
    with pytest.raises(SX.SnapshotExportError) as e:
        _export(store, other, tmp_path)
    assert "기존 경로를 그대로 쓴다" in str(e.value)


def test_another_contract_is_refused(store, binding, tmp_path):
    other = dict(binding, dataset_contract_key="EXT-01")
    with pytest.raises(SX.SnapshotExportError) as e:
        _export(store, other, tmp_path)
    assert "계약이 거짓말을 합니다" in str(e.value)


# ── 대사 — 우리가 만든 파일이라도 «맞는지 확인» 한다 ────────────────────────
def test_control_totals_match_what_we_wrote():
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    control = SX.control_totals(rows)
    assert control["row_count"] == 2
    assert control["sums"]["value"] == pytest.approx(4471.79 + 1520.36)
    assert svc.reconcile_totals(rows, control)["ok"] is True


def test_a_wrong_control_total_quarantines(store, binding, tmp_path, monkeypatch):
    """★★★ 대사가 «실제로 걸리는지» — 차단기를 눌러 본다."""
    monkeypatch.setattr(SX, "control_totals",
                        lambda rows: {"row_count": len(rows) + 1, "sums": {}})
    out = _export(store, binding, tmp_path)
    assert out["quarantined"] is True
    assert out["state"] == m.QUARANTINED
    assert "대사" in out["stopped_reason"]


def test_a_quarantined_snapshot_says_to_make_a_new_one(store, binding, tmp_path, monkeypatch):
    monkeypatch.setattr(SX, "control_totals",
                        lambda rows: {"row_count": len(rows) + 1, "sums": {}})
    note = _export(store, binding, tmp_path)["certification_note"]
    assert "새 Snapshot" in note


# ── 계보 — 원문까지 되짚을 수 있는가 ────────────────────────────────────────
def test_the_snapshot_carries_the_contract_and_the_binding(store, binding, tmp_path):
    out = _export(store, binding, tmp_path)
    row = store.get_snapshot(out["snapshot_id"])
    assert row["dataset_contract_key"] == "EXT-02"
    assert row["binding_id"] == binding["binding_id"]
    assert row["row_count"] == len(OBS)


def test_an_observation_without_an_indicator_code_is_refused():
    """★★★ [2026-09-11 실측] 저장소의 관측값 행에는 `indicator_code` 가 «없다» —
    `indicator_id`(`ind_…`)만 있다. 막지 않으면 `commodity_code` 가 조용히 비고,
    그 판은 「품목을 모르는 원자재 가격」이 된다."""
    bad = [{k: v for k, v in OBS[0].items() if k != "indicator_code"}]
    with pytest.raises(SX.SnapshotExportError) as e:
        SX.build_rows(bad, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert "품목을 모르는 가격 행을 만들지 않습니다" in str(e.value)


def test_the_commodity_code_comes_off_the_indicator_code():
    rows = SX.build_rows(OBS, tenant_id="T", scope_node_id="S", as_of_date="2026-09-11")
    assert [r["commodity_code"] for r in rows] == ["COPPER", "ZINC"]


# ── 실물 인증 종점 `SOURCE_CERTIFIED` (2026-09-11) ──────────────────────────
#
# ⚠️⚠️ 이것은 «회사 실적» 인증이 아니다. 여는 것은 «발행 기관이 따로 있는 공표 자료» 뿐이고,
#   자사 매출·원가·생산 실적에는 **여전히 종점이 없다** — 그것은 실제 Data Owner 의 서명이다.

class _FakeIntel:
    """원천 등록부 대역. ⚠️ 진짜 등록부를 쓰면 시험이 운영 DB 를 읽는다."""

    def __init__(self, sources):
        self._sources = sources

    def get_source(self, source_id):
        return self._sources.get(source_id)


@pytest.fixture()
def approved_source(monkeypatch):
    import core.external_intelligence as EI
    monkeypatch.setattr(EI, "external_intelligence",
                        _FakeIntel({"WB_PINK_SHEET": {"source_id": "WB_PINK_SHEET",
                                                      "enabled": 1,
                                                      "approved_by": "someone@lsmnm.com"},
                                    "NOT_APPROVED": {"source_id": "NOT_APPROVED",
                                                     "enabled": 0, "approved_by": ""}}))


def test_a_real_snapshot_reaches_the_source_endpoint(store, binding, tmp_path, approved_source):
    """★★★ F-8 이 「RECONCILED 에서 멈춘다」고 기록한 지점을 «연다»."""
    out = _export(store, binding, tmp_path)
    assert out["state"] == m.RECONCILED
    done = SX.certify_source(store, out["snapshot_id"],
                             source_id="WB_PINK_SHEET", certified_by="someone@lsmnm.com")
    assert done["state"] == m.SOURCE_CERTIFIED
    assert done["data_kind"] == m.DATA_KIND_REAL
    assert done["certified_at"]
    assert "회사 실적 인증이 아닙니다" in done["note"]


def test_an_unapproved_source_cannot_certify(store, binding, tmp_path, approved_source):
    """★★★ 원천 승인은 사람의 결정이다 — 그것 없이 인증하면 근거가 «아무도 하지 않은 승인» 이다."""
    out = _export(store, binding, tmp_path)
    with pytest.raises(SX.SnapshotExportError) as e:
        SX.certify_source(store, out["snapshot_id"],
                          source_id="NOT_APPROVED", certified_by="someone@lsmnm.com")
    assert "승인되지 않은 원천" in str(e.value)


def test_an_unknown_source_cannot_certify(store, binding, tmp_path, approved_source):
    out = _export(store, binding, tmp_path)
    with pytest.raises(SX.SnapshotExportError) as e:
        SX.certify_source(store, out["snapshot_id"], source_id="NOPE",
                          certified_by="someone@lsmnm.com")
    assert "존재하지 않는 원천" in str(e.value)


@pytest.mark.parametrize("missing", ["source_id", "certified_by"])
def test_certification_needs_both_the_source_and_a_named_certifier(
        store, binding, tmp_path, approved_source, missing):
    out = _export(store, binding, tmp_path)
    kw = {"source_id": "WB_PINK_SHEET", "certified_by": "someone@lsmnm.com"}
    kw[missing] = ""
    with pytest.raises(SX.SnapshotExportError):
        SX.certify_source(store, out["snapshot_id"], **kw)


def test_a_quarantined_snapshot_cannot_be_certified(store, binding, tmp_path,
                                                    approved_source, monkeypatch):
    """격리된 판은 인증 대상이 아니다 — 전이표가 막는다(층이 둘이다)."""
    monkeypatch.setattr(SX, "control_totals",
                        lambda rows: {"row_count": len(rows) + 1, "sums": {}})
    out = _export(store, binding, tmp_path)
    assert out["quarantined"] is True
    with pytest.raises(m.StateConflict):
        SX.certify_source(store, out["snapshot_id"], source_id="WB_PINK_SHEET",
                          certified_by="someone@lsmnm.com")
