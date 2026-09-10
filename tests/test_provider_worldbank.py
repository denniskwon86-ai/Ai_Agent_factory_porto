"""[DAO-14] World Bank Pink Sheet — **처음으로 API 가 아닌 원천이다.**

이 파일이 지키는 것 일곱.

  ① 자격증명이 **없어도** 되는 경로가 실제로 열린다(앞의 넷은 전부 키가 필요했다).
  ② 응답이 **바이너리**(xlsx)여도 원문 보관·체크섬·계보가 끝까지 간다.
  ③ ★★★ 품목 열을 **위치로 넘겨짚지 않는다** — 못 찾으면 «다른 열을 읽는 대신» 실패한다.
  ④ ★★★ `Lead` 가 `Leaded gasoline` 을 잡지 않는다(부분 일치 금지).
  ⑤ 행 번호를 박지 않는다 — 머리 구역이 밀려도 자료 시작을 찾는다.
  ⑥ `..` 는 **0 이 아니라 제외**다. 그리고 구간 밖은 제외가 «아니다».
  ⑦ 업무 키에 **가격기준**이 들어간다 — 없으면 값과 지수가 서로 덮어쓴다.

## ⚠️⚠️ 이 fixture 는 실제 Pink Sheet 파일이 아니다

아래 `PRICES_LAYOUT` 이 **이 저장소가 가정한 모양 전부**다. 실제 워크북과 대조하지
못했으므로(`LAYOUT_VERIFIED=False`), 가정을 숨기지 않고 **읽을 수 있게 상수로 펼쳐 둔다** —
실제 파일을 손에 넣은 사람이 이 표와 눈으로 비교할 수 있도록.
"""
import io

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence import provenance as PV
from core.external_intelligence.acquisition_store import AcquisitionStore
from core.external_intelligence.orchestrator import AcquisitionOrchestrator
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import worldbank as W
from core.external_intelligence.raw_store import RawStore

REQUESTER = "t_member_a@test.invalid"
APPROVER = "t_dataadmin@test.invalid"

# ── 가정한 레이아웃 — 여기가 이 파일의 «계약» 이다 ────────────────────────────
#: ⚠️ `Lead` 바로 옆에 `Leaded gasoline` 을 일부러 뒀다 — 부분 일치를 허용하는 파서는
#:   여기서 틀린 열을 읽는다.
PRICES_LAYOUT = [
    ["World Bank Commodity Price Data (The Pink Sheet)"],
    ["Monthly prices in nominal US dollars, 1960 to present"],
    [],
    ["", "Crude oil, Brent", "Copper", "Aluminum", "Lead", "Leaded gasoline", "Zinc"],
    ["", "($/bbl)", "($/mt)", "($/mt)", "($/mt)", "($/gal)", "($/mt)"],
    ["", "CRUDE_BRENT", "COPPER", "ALUMINUM", "LEAD", "GASOLINE_LEAD", "ZINC"],
    ["2024M12", 74.2, 8900.0, 2500.0, 1950.0, 2.00, 2800.0],   # ← 구간 «밖»
    ["2025M01", 78.5, 9100.2, 2550.0, 1980.5, 2.10, 2850.0],
    ["2025M02", 76.0, "..", 2540.0, 1975.0, 2.05, 2830.0],     # ← 값 없음
    ["2025M03", 79.1, 9250.0, 2600.0, 1990.0, 2.15, 2900.0],
    ["2025M04", 80.3, 9310.5, 2610.0, 2005.0, 2.20, 2915.0],
    ["2025M05", 77.8, 9180.0, 2585.0, 1998.0, 2.12, 2880.0],
    ["2025M06", 81.0, 9400.0, 2640.0, 2020.0, 2.25, 2950.0],
    [],
    ["Source: World Bank"],                                     # ← 각주 — 세지 않는다
]

INDICES_LAYOUT = [
    ["World Bank Commodity Price Data (The Pink Sheet)"],
    [],
    ["", "Copper"],
    ["", "(2010=100)"],
    ["2025M01", 118.4],
    ["2025M02", 117.9],
    ["2025M03", 120.3],
]

#: 구간(2025-01~2025-12) 안의 줄 수 = 6. 그중 하나가 `..` 다.
IN_WINDOW = 6
LOADED = 5
REJECTED = 1


def _xlsx(sheets):
    """레이아웃 표를 진짜 xlsx 바이트로 굽는다."""
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _book(prices=None, indices=None):
    return _xlsx({"Monthly Prices": prices if prices is not None else PRICES_LAYOUT,
                  "Monthly Indices": indices if indices is not None else INDICES_LAYOUT})


def _transport(payload=None, record=None, content_type=W.XLSX_CONTENT_TYPE):
    body = payload if payload is not None else _book()

    def call(url, *, allowed_hosts, timeout=20.0):
        if record is not None:
            record.append({"url": url, "allowed_hosts": allowed_hosts})
        return {"body": body, "content_type": content_type, "status": 200,
                "final_url": url, "fetched_at": "2026-09-08T00:00:00+00:00"}
    return call


def _provider(transport=None, env=None):
    return W.WorldBankPinkSheetProvider(env=env if env is not None else {},
                                        transport=transport or _transport())


def _candidate(ref="COPPER:nominal_price:2025-01:2025-12"):
    return B.DiscoveryCandidate(provider_id="WB_PINK_SHEET", dataset_ref=ref,
                                title="구리", target_contract_key="EXT-02")


def _batch(ref="COPPER:nominal_price:2025-01:2025-12", payload=None):
    p = _provider(transport=_transport(payload))
    return p.normalize(p.fetch(_candidate(ref)))


# ── ① 순수 파서 — 기간·값 ────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("1960M01", "1960-01"), ("2025M12", "2025-12"), ("2025M1", "2025-01"),
    ("1960", "1960"), ("2025M13", ""), ("2025M00", ""), ("Source: World Bank", ""),
    ("", ""), ("annual", ""),
])
def test_period_shapes(raw, expected):
    assert W.normalise_period(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (9100.2, 9100.2), ("9100.2", 9100.2), ("1,234.5", 1234.5), (-3, -3.0),
    ("..", None), ("...", None), ("", None), ("n/a", None), ("N/A", None),
    ("—", None), ("보류", None), (True, None), (False, None),
])
def test_missing_markers_never_become_zero(raw, expected):
    """★ `..` 를 0 으로 읽으면 «구리가 공짜였던 달»이 생긴다."""
    assert W.parse_value(raw) == expected


# ── ② 위치를 박지 않는다 ─────────────────────────────────────────────────────
def test_data_start_is_found_by_content_not_by_row_number():
    """머리 구역이 밀려도 찾는다 — 행 번호를 박았다면 여기서 깨진다."""
    shifted = [[], ["공지"], [], []] + PRICES_LAYOUT
    grid = W.load_grid(_book(prices=shifted), "Monthly Prices")
    base = W.load_grid(_book(), "Monthly Prices")
    assert W.find_data_start(grid) == W.find_data_start(base) + 4


def test_layout_without_a_period_column_is_rejected_not_guessed():
    grid = W.load_grid(_book(prices=[["가", "나"], ["다", "라"]]), "Monthly Prices")
    with pytest.raises(W.LayoutNotRecognised):
        W.find_data_start(grid)


def test_series_column_is_found_by_name():
    grid = W.load_grid(_book(), "Monthly Prices")
    start = W.find_data_start(grid)
    _, col = W.find_series_column(grid, start, ("copper",))
    assert float(grid[start][col]) == 8900.0        # 첫 자료 행은 2024M12 다


def test_a_name_with_a_comma_still_matches():
    """`Crude oil, Brent` 처럼 쉼표가 붙는 이름이 있다."""
    grid = W.load_grid(_book(), "Monthly Prices")
    start = W.find_data_start(grid)
    _, col = W.find_series_column(grid, start, ("crude oil, brent",))
    assert float(grid[start][col]) == 74.2         # 2024M12


def test_lead_does_not_match_leaded_gasoline():
    """★★★ 부분 일치를 허용하면 납 자리에서 «가솔린» 가격을 읽는다."""
    grid = W.load_grid(_book(), "Monthly Prices")
    start = W.find_data_start(grid)
    _, col = W.find_series_column(grid, start, ("lead",))
    assert float(grid[start][col]) == 1950.0          # 납이지 2.00(가솔린)이 아니다


def test_lead_is_not_found_when_only_leaded_gasoline_exists():
    """앞 시험은 «순서» 덕분일 수 있다 — 납 열을 아예 빼고 다시 본다."""
    without_lead = [list(r) for r in PRICES_LAYOUT]
    for row in without_lead:
        if len(row) > 4:
            del row[4]                                 # "Lead" 열을 통째로 뺀다
    grid = W.load_grid(_book(prices=without_lead), "Monthly Prices")
    start = W.find_data_start(grid)
    with pytest.raises(W.SeriesNotFound):
        W.find_series_column(grid, start, ("lead",))


def test_missing_series_fails_instead_of_reading_a_neighbour():
    """★★★ 이 저장소는 «엉뚱한 회사의 DART 응답을 조용히 적재»한 적이 있다."""
    grid = W.load_grid(_book(), "Monthly Prices")
    start = W.find_data_start(grid)
    with pytest.raises(W.SeriesNotFound) as exc:
        W.find_series_column(grid, start, ("tungsten",))
    assert "넘겨짚" in str(exc.value)


def test_unit_is_read_from_the_header_block():
    grid = W.load_grid(_book(), "Monthly Prices")
    start = W.find_data_start(grid)
    row, col = W.find_series_column(grid, start, ("copper",))
    assert W.find_unit(grid, row, start, col) == "$/mt"


def test_unit_is_empty_when_the_header_has_none():
    layout = [["", "Copper"], ["2025M01", 9100.2]]
    grid = W.load_grid(_book(prices=layout), "Monthly Prices")
    start = W.find_data_start(grid)
    row, col = W.find_series_column(grid, start, ("copper",))
    assert W.find_unit(grid, row, start, col) == ""


# ── ③ 정규화 ────────────────────────────────────────────────────────────────
def test_rows_carry_the_price_basis():
    batch = _batch()
    assert {r["price_basis"] for r in batch.rows} == {"nominal_price"}
    assert {r["commodity_code"] for r in batch.rows} == {"COPPER"}
    assert {r["unit"] for r in batch.rows} == {"$/mt"}


def test_a_missing_value_is_rejected_with_a_reason_not_stored_as_zero():
    batch = _batch()
    assert len(batch.rows) == LOADED
    assert [r.reason for r in batch.rejected] == ["값 없음"]
    assert "2025-02" in batch.rejected[0].detail
    assert 0.0 not in [r["value"] for r in batch.rows]


def test_rows_and_rejects_account_for_the_window():
    """★ 정산의 분모는 «파일 전체»가 아니라 구간 안의 줄이다."""
    batch = _batch()
    assert batch.source_row_count == IN_WINDOW
    assert batch.accounted
    assert len(batch.rows) + len(batch.rejected) == IN_WINDOW


def test_out_of_window_rows_are_not_counted_as_rejected():
    """2024M12 는 «버린» 것이 아니라 애초에 요청 대상이 아니다."""
    batch = _batch()
    assert "2024-12" not in [r["observed_at"] for r in batch.rows]
    assert all("2024-12" not in r.detail for r in batch.rejected)


def test_a_footnote_row_is_not_counted():
    assert _batch().source_row_count == IN_WINDOW      # "Source: World Bank" 는 제외


def test_the_index_sheet_is_a_different_series():
    batch = _batch("COPPER:index:2025-01:2025-12")
    assert {r["unit"] for r in batch.rows} == {"2010=100"}
    assert {r["price_basis"] for r in batch.rows} == {"index"}


def test_source_fields_carry_the_column_header():
    """★ 원천 스키마 변경을 볼 수 있어야 한다 — 정규화 결과만 보면 안 보인다."""
    assert "Copper" in _batch().source_fields


def test_an_unregistered_commodity_is_refused_not_guessed():
    with pytest.raises(B.ProviderError):
        _batch("TUNGSTEN:nominal_price:2025-01:2025-12")


def test_an_unregistered_basis_is_refused_not_defaulted():
    """기준을 모르면 «가격판으로 대신»하지 않는다 — 그러면 지수 요청이 값을 받는다."""
    with pytest.raises(B.ProviderError):
        _batch("COPPER:real_price:2025-01:2025-12")


def test_a_malformed_dataset_ref_is_refused():
    with pytest.raises(B.ProviderError):
        _batch("COPPER")


# ── ④ 검증 — 던지지 않는다 ───────────────────────────────────────────────────
def test_a_clean_batch_passes_every_check():
    report = _provider().validate(_batch())
    assert report.ok, [c.name for c in report.failures]


def test_the_layout_check_is_not_an_always_failing_gate():
    """★★★ KOSIS 에서 저지른 실수 — 미확인 사실을 `ok=False` 로 두면 정상 자료가 늘 격리된다."""
    assert W.LAYOUT_VERIFIED is False
    check = [c for c in _provider().validate(_batch()).checks
             if c.name == "레이아웃 실측 여부"][0]
    assert check.ok is True
    assert "LAYOUT_VERIFIED" in check.detail


def test_a_batch_without_units_is_a_quality_failure():
    layout = [["", "Copper"], ["2025M01", 9100.2], ["2025M02", 9250.0]]
    report = _provider().validate(_batch(payload=_book(prices=layout)))
    failed = {c.name: c for c in report.failures}
    assert "단위 있음" in failed
    assert failed["단위 있음"].failure_kind == am.FAILURE_QUALITY


def test_mixed_commodities_are_a_quality_failure():
    mixed = B.NormalizedBatch(
        provider_id="WB_PINK_SHEET", contract_key="EXT-02", source_row_count=2,
        rows=({"commodity_code": "COPPER", "price_basis": "nominal_price",
               "observed_at": "2025-01", "unit": "$/mt"},
              {"commodity_code": "ZINC", "price_basis": "nominal_price",
               "observed_at": "2025-01", "unit": "$/mt"}))
    failed = {c.name for c in _provider().validate(mixed).failures}
    assert "품목 단일" in failed


def test_mixed_bases_are_a_quality_failure():
    """$/mt 와 2010=100 이 한 계열이 되면 평균이 뜻을 잃는다."""
    mixed = B.NormalizedBatch(
        provider_id="WB_PINK_SHEET", contract_key="EXT-02", source_row_count=2,
        rows=({"commodity_code": "COPPER", "price_basis": "nominal_price",
               "observed_at": "2025-01", "unit": "$/mt"},
              {"commodity_code": "COPPER", "price_basis": "index",
               "observed_at": "2025-02", "unit": "2010=100"}))
    failed = {c.name for c in _provider().validate(mixed).failures}
    assert "가격기준 단일" in failed


def test_validate_never_raises_even_on_an_empty_batch():
    empty = B.NormalizedBatch(provider_id="WB_PINK_SHEET", contract_key="EXT-02")
    report = _provider().validate(empty)
    assert not report.ok and "자료 있음" in {c.name for c in report.failures}


# ── ⑤ 자격증명이 «없는» 경로 — 이 원천이 처음이다 ────────────────────────────
def test_no_credential_is_required():
    """★ 앞의 넷은 전부 키가 필요했다. 키 없는 경로가 실제로 열리는지 여기서 처음 확인한다."""
    p = _provider(env={})
    assert p.describe().requires_credential is False
    assert p.has_credential() is True
    assert p.credential() == ""
    assert p.secret_values() == ()


def test_discover_does_not_fail_without_a_key():
    request = B.AcquisitionRequest(indicators=("구리",), period_from="2025", period_to="2025")
    assert _provider(env={}).discover(request)


# ── ⑥ 탐색 ──────────────────────────────────────────────────────────────────
def test_discover_builds_the_dataset_ref():
    request = B.AcquisitionRequest(indicators=("구리",), period_from="2016", period_to="2025")
    found = _provider().discover(request)
    assert [c.dataset_ref for c in found] == ["COPPER:nominal_price:2016-01:2025-12"]
    assert "실구매 단가가 아닙니다" in found[0].match_reason


def test_discover_returns_nothing_for_an_unknown_indicator():
    request = B.AcquisitionRequest(indicators=("텅스텐",), period_from="2025", period_to="2025")
    assert _provider().discover(request) == []


def test_discover_honours_the_requested_basis():
    request = B.AcquisitionRequest(indicators=("구리",), period_from="2025", period_to="2025",
                                   extras={"price_basis": "index"})
    assert _provider().discover(request)[0].dataset_ref.split(":")[1] == "index"


def test_an_unknown_basis_falls_back_to_the_price_sheet_at_discovery():
    request = B.AcquisitionRequest(indicators=("구리",), period_from="2025", period_to="2025",
                                   extras={"price_basis": "made_up"})
    assert _provider().discover(request)[0].dataset_ref.split(":")[1] == "nominal_price"


def test_discover_is_pure_and_does_not_call_the_network():
    calls = []
    request = B.AcquisitionRequest(indicators=("구리",), period_from="2025", period_to="2025")
    _provider(transport=_transport(record=calls)).discover(request)
    assert calls == []


# ── ⑦ 전송·형식 ─────────────────────────────────────────────────────────────
def test_the_request_is_pinned_to_the_allowed_host():
    calls = []
    _provider(transport=_transport(record=calls)).fetch(_candidate())
    assert calls[0]["allowed_hosts"] == (W.HOST,)
    assert calls[0]["url"].startswith(f"https://{W.HOST}/")


def test_the_url_override_cannot_leave_the_allowed_host():
    """★ 경로는 덮어쓸 수 있어도 호스트 검사는 전송층이 한다(임의 URL 이 되지 않는다)."""
    calls = []
    p = _provider(transport=_transport(record=calls),
                  env={W.URL_ENV: "https://evil.example.com/x.xlsx"})
    p.fetch(_candidate())
    assert calls[0]["allowed_hosts"] == (W.HOST,)     # 검사 대상은 그대로 worldbank


def test_an_error_page_is_not_read_as_a_spreadsheet():
    html = "<html><body>점검 중입니다</body></html>".encode("utf-8")
    with pytest.raises(W.NotASpreadsheet):
        _batch(payload=html)


def test_an_empty_response_is_not_read_as_a_spreadsheet():
    with pytest.raises(W.NotASpreadsheet):
        _batch(payload=b"")


def test_a_missing_sheet_is_named_not_swallowed():
    book = _xlsx({"Annual Prices": PRICES_LAYOUT})
    with pytest.raises(W.SheetNotFound) as exc:
        _batch(payload=book)
    assert "Annual Prices" in str(exc.value)


# ── ⑧ 이어받기 · 갱신 — 순수 ────────────────────────────────────────────────
def test_checkpoint_covers_what_was_loaded():
    p = _provider()
    cp = p.checkpoint(_batch())
    assert cp.dataset_ref == "COPPER:nominal_price"
    assert (cp.covered_from, cp.covered_to, cp.cursor) == ("2025-01", "2025-06", "2025-06")


def test_refresh_asks_for_the_next_month_only():
    p = _provider()
    nxt = p.refresh(p.checkpoint(_batch()))
    assert [c.dataset_ref for c in nxt] == ["COPPER:nominal_price:2025-07:2025-12"]


def test_refresh_rolls_over_the_year():
    cp = B.Checkpoint(provider_id="WB_PINK_SHEET", dataset_ref="COPPER:nominal_price",
                      cursor="2025-12", covered_to="2025-12")
    assert _provider().refresh(cp)[0].dataset_ref == "COPPER:nominal_price:2026-01:2026-12"


def test_refresh_without_a_cursor_asks_for_nothing():
    cp = B.Checkpoint(provider_id="WB_PINK_SHEET", dataset_ref="COPPER:nominal_price")
    assert _provider().refresh(cp) == []


def test_refresh_does_not_touch_the_network():
    calls = []
    p = _provider(transport=_transport(record=calls))
    batch = p.normalize(p.fetch(_candidate()))
    calls.clear()
    p.refresh(p.checkpoint(batch))
    assert calls == []


# ── ⑨ 업무 키 — 가격기준이 빠지면 서로 덮어쓴다 ──────────────────────────────
def test_the_business_key_separates_price_from_index():
    """★★★ 이 축이 없으면 «구리 $/mt» 와 «구리 지수» 가 같은 행이 된다."""
    price = {"commodity_code": "COPPER", "price_basis": "nominal_price",
             "observed_at": "2025-01"}
    index = dict(price, price_basis="index")
    assert M.commodity_row_id(price) != M.commodity_row_id(index)


def test_the_business_key_refuses_to_guess_a_missing_basis():
    with pytest.raises(M.MappingError):
        M.commodity_row_id({"commodity_code": "COPPER", "observed_at": "2025-01"})


def test_the_orchestrator_actually_uses_that_rule():
    """★ 규칙을 «선언»만 하고 표에 안 넣으면 내용 해시로 떨어진다 — 조용히."""
    from core.external_intelligence import orchestrator as O
    assert O.AcquisitionOrchestrator._BUSINESS_KEY_RULES["EXT-02"] is M.commodity_row_id


# ── ⑩ 등록·배선 ─────────────────────────────────────────────────────────────
def test_the_provider_is_registered_and_ranked_as_an_official_file():
    assert "WB_PINK_SHEET" in {d.provider_id for d in P.descriptors()}
    assert P.source_priority(W.WorldBankPinkSheetProvider.descriptor.source_type) == 2


def test_the_grade_matches_the_usage_constraint_in_the_design_doc():
    """설계서가 「시나리오 동인으로 쓴다」고 적은 것이 `silver` 로 표현돼 있다."""
    from core.external_intelligence import PURPOSE_MIN_GRADE
    assert W.WorldBankPinkSheetProvider.descriptor.default_trust_grade == "silver"
    assert PURPOSE_MIN_GRADE["baseline_plan"] == "gold"      # 기준 계획에는 못 쓴다
    assert PURPOSE_MIN_GRADE["scenario"] == "silver"         # 시나리오에는 쓴다


def test_the_known_limits_say_it_is_not_our_purchase_price():
    limits = " ".join(W.WorldBankPinkSheetProvider.descriptor.known_limits)
    assert "실구매 단가" in limits


# ── ⑪ 종단 — 오케스트레이터를 통과한다 ──────────────────────────────────────
def _rig(tmp_path, transport=None, record=None):
    store = AcquisitionStore(str(tmp_path / "ei.db"),
                             ledger=DecisionLedger(str(tmp_path / "ledger.db")))
    raw = RawStore(str(tmp_path / "raw"))
    orch = AcquisitionOrchestrator(
        store=store, raw_store=raw, registry=P.provider_registry, env={},
        transport=transport or _transport(record=record))
    proposal = store.propose_contract(M.ext02_public_proposal(), proposed_by=REQUESTER)
    store.decide_contract(proposal["proposal_id"], approve=True, reviewed_by=APPROVER,
                          reason="공표 국제가격용")
    return {"store": store, "raw": raw, "orch": orch}


def _walk(rig):
    store, orch = rig["store"], rig["orch"]
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM", purpose="원료구매 시나리오",
                       request={"subject_name": "LS MnM", "purpose": "원료구매 시나리오",
                                "period_from": "2025", "period_to": "2025",
                                "indicators": ["구리"],
                                "extras": {"provider_ids": ["WB_PINK_SHEET"]}})
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, dry = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    job, applied = orch.apply(job["job_id"], actor_id=APPROVER)
    return {"job": job, "dry": dry, "applied": applied}


def test_a_binary_source_walks_all_the_way_through(tmp_path):
    """★ 앞의 넷은 전부 JSON 이었다 — 바이너리가 끝까지 가는지 여기서 처음 확인한다."""
    out = _walk(_rig(tmp_path))
    assert out["applied"].inserted == LOADED
    assert out["job"]["status"] == am.ACTIVE


def test_the_raw_xlsx_is_preserved_and_verifiable(tmp_path):
    rig = _rig(tmp_path)
    out = _walk(rig)
    refs = [o["raw_object_ref"] for o in rig["store"].raw_objects(out["job"]["job_id"])]
    assert len(refs) == 1
    assert refs[0].endswith(".xlsx")           # `.bin` 이 아니다 — 사람이 열 수 있다
    assert rig["raw"].verify(refs[0])["ok"] is True


def test_the_silver_grade_travels_into_the_stored_row(tmp_path):
    """★ 등급이 행까지 따라가야 목적별 관문이 작동한다."""
    rig = _rig(tmp_path)
    _walk(rig)
    rows = rig["store"].staged_rows(contract_key="EXT-02")
    #: ⚠️ 도메인 필드는 최상위 열이 아니라 `payload` 안에 있다(저장소가 파싱해 준다).
    assert rows and {r["payload"]["trust_grade"] for r in rows} == {"silver"}
    assert {r["data_origin"] for r in rows} == {am.ORIGIN_PUBLIC_DISCLOSED}
    #: ★ 실물 인증은 아직 아무 데도 없다 — 격리 적재본이다(§4-3).
    assert {r["certification_status"] for r in rows} == {"UNCERTIFIED"}


def test_the_value_can_be_traced_back_to_the_file(tmp_path):
    rig = _rig(tmp_path)
    _walk(rig)
    answer = PV.answer(rig["store"], contract_key="EXT-02",
                       match={"indicator_code": "WB_COPPER", "observed_at": "2025-03"},
                       value_field="value")
    assert answer.found and answer.value == 9250.0
    assert answer.trust_grade == "silver"
    assert answer.unit == "$/mt"               # 계보가 «단위까지» 되찾는다
    assert answer.raw_object_ref


def test_the_missing_month_is_visible_in_the_dry_run(tmp_path):
    """사람이 «왜 6개월인데 5행인가» 를 화면에서 알 수 있어야 한다."""
    out = _walk(_rig(tmp_path))
    assert out["dry"].rejected_rows == REJECTED
    assert out["dry"].new_rows == LOADED


def test_applying_twice_inserts_nothing_new(tmp_path):
    """소급 정정은 «덮어쓰기가 아니라 거부»로 드러난다."""
    rig = _rig(tmp_path)
    _walk(rig)
    second = _walk(rig)
    assert second["applied"].inserted == 0
    assert second["applied"].duplicate == LOADED
