"""[DAO-14] World Bank Pink Sheet Provider — 월별 국제 원자재 가격 → `EXT-02`.

## 앞의 넷과 «범주»가 다르다 — 처음으로 API 가 아니다

앞의 넷(DART·ECOS·KOSIS·공공데이터포털)은 전부 JSON API 였다. 이것은 **공식 파일**이다.
설계서 §4.2 가 `SRC_WB_PINK_SHEET` 를 「공식 XLS 다운로드」로 등록해 뒀고, 지시 3 의
우선순위(공식 API > **공식 파일** > 계약 Provider > RSS·공시 > 웹)에서 아무도 밟지 않은
두 번째 층이다.

★★★ 그래서 이 Provider 가 처음으로 하는 것 셋
  ① 자격증명이 **필요 없다** (`requires_credential=False`) — 비밀 없는 경로가 처음이다
  ② 응답이 **바이너리**다 (xlsx = zip) — 원문 보관소가 `"wb"` 로 쓰므로 그대로 들어간다
  ③ 응답에 **요청한 구간이 없다** — 파일은 늘 1960년부터 «전부» 온다

③ 때문에 구간 선택이 URL 이 아니라 `dataset_ref` 에 실린다(KOSIS 의 관례를 따른다).

## ⚠️⚠️⚠️ 레이아웃을 실제 파일로 확인하지 못했다

`LAYOUT_VERIFIED = False`. 이 파서는 공표된 Pink Sheet 의 **문서상 모양**을 따라 썼고
실제 워크북과 대조하지 않았다. 그래서 **행·열 번호를 하나도 박아 넣지 않았다** —
전부 내용으로 찾는다:

    자료 시작 행   A열이 `1960M01` 모양인 «첫 행»
    품목 열       머리 구역에서 품목 이름이 적힌 칸을 찾아 그 열
    단위          그 열의, 품목 이름 아래·자료 시작 위의 `(...)` 칸

★★★ **위치로 넘겨짚지 않는다.** 품목 이름을 못 찾으면 «다른 열을 읽는 대신» 실패한다.
  넘겨짚으면 구리 자리에서 알루미늄 가격을 읽고도 아무도 모른다 — 이 저장소에서
  「엉뚱한 회사의 DART 응답을 조용히 적재」한 사고가 실제로 있었다(§5).

## ⚠️ 문서 URL 에 회전하는 해시가 들어 있다

World Bank 는 파일 경로에 문서 해시를 넣고 그것을 갱신한다. 박아 두면 언젠가 404 가 된다.
그래서 `AFS_WORLDBANK_PINK_SHEET_URL` 로 덮어쓸 수 있게 뒀다.
★ 그래도 **임의 URL 이 되지 않는다** — `_get()` 이 `allowed_hosts` 로 막는다(지시 12).
  이것은 비밀이 아니라 경로다. 키가 아니므로 원문 보관소의 비밀 지우기 대상이 아니다.

## 등급이 `silver` 인 이유 — 내 취향이 아니라 설계서에서 나온다

설계서 §4.2 는 이 원천을 「Gold 또는 Silver」로 **정하지 않고** 뒀지만, 같은 줄에
「실구매 단가를 대체하지 않는다. 국제 기준 가격·**시나리오 동인**으로 쓴다」고 적었다.
기존 `PURPOSE_MIN_GRADE` 가 정확히 그 경계다:

    baseline_plan · official_report  →  gold   (기준 계획·공식 보고)   ← 막힌다
    scenario · review                →  silver (전망·검토)            ← 열린다

즉 설계서가 쓴 용도 제약이 `silver` 로 **이미 표현돼 있다.** gold 로 두면 그 문장이
코드에서 사라진다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import provider_registry

CONTRACT_KEY = "EXT-02"
HOST = "thedocs.worldbank.org"

#: 문서 경로. ⚠️ 해시가 회전한다 — 환경변수로 덮어쓸 수 있다(호스트는 못 바꾼다).
DEFAULT_PATH = ("/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/"
                "CMO-Historical-Data-Monthly.xlsx")
URL_ENV = "AFS_WORLDBANK_PINK_SHEET_URL"

#: ★★★ 실제 워크북과 대조하면 True 로 바꾸고, 어긋난 곳을 이 파일에 적는다.
LAYOUT_VERIFIED = False

XLSX_CONTENT_TYPE = ("application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet")

#: 가격판과 지수판. **업무 키에 들어간다** — 빼면 둘이 같은 키가 되어 하나가 다른
#: 하나를 덮어쓴다(KOSIS 의 분류축과 같은 교훈).
SHEET_BY_BASIS: Dict[str, str] = {
    "nominal_price": "Monthly Prices",
    "index": "Monthly Indices",
}
DEFAULT_BASIS = "nominal_price"

#: 이 저장소가 다루는 품목. ⚠️ 여기 없는 품목은 **추측하지 않고 후보에서 뺀다.**
#:   Pink Sheet 는 70여 개 계열을 담는데, 이름을 넘겨짚어 고르면 엉뚱한 열을 읽는다.
COMMODITIES: Dict[str, Dict[str, Any]] = {
    "COPPER": {"label": "구리", "indicator_code": "WB_COPPER",
               "names": ("copper",), "keywords": ("구리", "동", "copper")},
    "ZINC": {"label": "아연", "indicator_code": "WB_ZINC",
             "names": ("zinc",), "keywords": ("아연", "zinc")},
    "LEAD": {"label": "납", "indicator_code": "WB_LEAD",
             "names": ("lead",), "keywords": ("납", "연", "lead")},
    "NICKEL": {"label": "니켈", "indicator_code": "WB_NICKEL",
               "names": ("nickel",), "keywords": ("니켈", "nickel")},
    "ALUMINUM": {"label": "알루미늄", "indicator_code": "WB_ALUMINUM",
                 "names": ("aluminum", "aluminium"),
                 "keywords": ("알루미늄", "aluminum", "aluminium")},
    "GOLD": {"label": "금", "indicator_code": "WB_GOLD",
             "names": ("gold",), "keywords": ("금", "gold")},
    "SILVER": {"label": "은", "indicator_code": "WB_SILVER",
               "names": ("silver",), "keywords": ("은", "silver")},
    "CRUDE_BRENT": {"label": "원유(브렌트)", "indicator_code": "WB_CRUDE_BRENT",
                    "names": ("crude oil, brent",),
                    "keywords": ("원유", "유가", "brent", "crude")},
}

#: 「값 없음」 표시. ★ 0 으로 채우지 않는다 — 사유와 함께 «뺀다».
MISSING_MARKERS = ("..", "...", "n/a", "na", "-", "—", "")

_MONTHLY = re.compile(r"^\s*(\d{4})\s*M\s*(\d{1,2})\s*$", re.IGNORECASE)
_ANNUAL = re.compile(r"^\s*(\d{4})\s*$")
_UNIT = re.compile(r"^\s*[\(\[](?P<u>.+?)[\)\]]\s*$")
_NUM = re.compile(r"^-?\d+(\.\d+)?$")

#: 머리 구역이 이보다 길면 자료 시작을 못 찾은 것이다 — 통째로 훑지 않는다.
MAX_HEADER_ROWS = 40
MAX_SCAN_ROWS = 5000


class NotASpreadsheet(B.ProviderError):
    """받은 것이 xlsx 가 아니다 — 점검 페이지·오류 HTML 을 표로 읽지 않는다."""


class SheetNotFound(B.ProviderError):
    """워크북에 그 판이 없다 — 레이아웃이 바뀐 것이다."""


class SeriesNotFound(B.ProviderError):
    """★★★ 품목 열을 못 찾았다. **위치로 넘겨짚지 않고 여기서 멈춘다.**"""


class LayoutNotRecognised(B.ProviderError):
    """자료 시작 행을 못 찾았다."""


# ── 순수 파서 ────────────────────────────────────────────────────────────────
def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm(value: Any) -> str:
    """비교용 정규화 — 소문자·공백 축약. 이름 비교는 **이것으로만** 한다."""
    return re.sub(r"\s+", " ", _text(value)).strip().lower()


def normalise_period(raw: Any) -> str:
    """`1960M01` → `1960-01`, `1960` → `1960`. 모르면 빈 문자열."""
    text = _text(raw)
    m = _MONTHLY.match(text)
    if m:
        month = int(m.group(2))
        if not 1 <= month <= 12:
            return ""
        return f"{m.group(1)}-{month:02d}"
    m = _ANNUAL.match(text)
    return m.group(1) if m else ""


def parse_value(raw: Any) -> Optional[float]:
    """수치만 통과. `..` 같은 결측 표시와 글자는 **버린다**(0 으로 채우지 않는다)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = _text(raw).replace(",", "")
    if _norm(text) in MISSING_MARKERS:
        return None
    return float(text) if _NUM.match(text) else None


def load_grid(payload: bytes, sheet_name: str) -> List[List[str]]:
    """xlsx 한 판을 글자 격자로 읽는다. **순수** — 네트워크를 만지지 않는다."""
    from io import BytesIO
    try:
        import openpyxl
    except ImportError as exc:                                  # pragma: no cover
        raise B.ProviderError("openpyxl 이 없어 Pink Sheet 를 읽을 수 없습니다.") from exc
    if not payload:
        raise NotASpreadsheet("빈 응답입니다.")
    #: ★ zip 서명 확인 — 오류 HTML 을 openpyxl 에 넘기면 알아보기 힘든 예외가 난다.
    if payload[:2] != b"PK":
        raise NotASpreadsheet(
            "받은 것이 xlsx(zip) 가 아닙니다 — 점검 페이지나 오류 응답일 수 있습니다. "
            f"앞부분: {payload[:40]!r}")
    try:
        wb = openpyxl.load_workbook(BytesIO(payload), read_only=True, data_only=True)
    except Exception as exc:                                    # noqa: BLE001
        raise NotASpreadsheet(f"xlsx 를 열지 못했습니다: {type(exc).__name__}: {exc}") from exc
    try:
        if sheet_name not in wb.sheetnames:
            raise SheetNotFound(
                f"워크북에 «{sheet_name}» 판이 없습니다. 있는 판: {wb.sheetnames}")
        ws = wb[sheet_name]
        grid: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            grid.append([_text(c) for c in row])
            if len(grid) >= MAX_SCAN_ROWS:
                break
        return grid
    finally:
        wb.close()


def find_data_start(grid: Sequence[Sequence[str]]) -> int:
    """A열이 기간 모양인 **첫 행**. 행 번호를 박지 않는 이유가 이것이다."""
    for i, row in enumerate(grid):
        if row and normalise_period(row[0]):
            return i
        if i > MAX_HEADER_ROWS:
            break
    raise LayoutNotRecognised(
        f"머리 {MAX_HEADER_ROWS}행 안에서 기간 열(`1960M01` 모양)을 찾지 못했습니다 — "
        "레이아웃이 바뀌었거나 다른 파일입니다.")


def find_series_column(grid: Sequence[Sequence[str]], data_start: int,
                       names: Sequence[str]) -> Tuple[int, int]:
    """품목 이름이 적힌 (행, 열). 못 찾으면 **예외** — 다른 열로 대신하지 않는다.

    Pink Sheet 의 이름은 `Copper` 처럼 짧기도, `Crude oil, Brent` 처럼 쉼표가 붙기도
    한다. 그래서 «정확히 같거나» «이름 뒤에 쉼표가 오는» 경우만 맞는 것으로 본다 —
    부분 일치를 허용하면 `Lead` 가 `Leaded gasoline` 을 잡는다."""
    wanted = [_norm(n) for n in names if _norm(n)]
    if not wanted:
        raise SeriesNotFound("찾을 품목 이름이 비어 있습니다.")
    header = grid[:data_start]
    for r, row in enumerate(header):
        for c, cell in enumerate(row):
            text = _norm(cell)
            if not text:
                continue
            for w in wanted:
                if text == w or text.startswith(w + ","):
                    return r, c
    raise SeriesNotFound(
        f"머리 구역 {len(header)}행에서 품목 «{names[0]}» 열을 찾지 못했습니다. "
        "★ 위치로 넘겨짚지 않고 멈춥니다 — 넘겨짚으면 다른 품목 가격을 읽습니다.")


def find_unit(grid: Sequence[Sequence[str]], name_row: int, data_start: int,
              col: int) -> str:
    """품목 이름 아래·자료 시작 위에서 `($/mt)` 모양 칸을 찾는다. 없으면 빈 값."""
    for r in range(name_row + 1, data_start):
        if col >= len(grid[r]):
            continue
        m = _UNIT.match(_text(grid[r][col]))
        if m:
            return m.group("u").strip()
    return ""


def read_series(payload: bytes, *, sheet_name: str, names: Sequence[str]) -> Dict[str, Any]:
    """한 품목 계열을 뽑는다. **순수.** 걸러내기는 하지 않는다(정규화의 일)."""
    grid = load_grid(payload, sheet_name)
    data_start = find_data_start(grid)
    name_row, col = find_series_column(grid, data_start, names)
    unit = find_unit(grid, name_row, data_start, col)
    points: List[Tuple[int, str, str]] = []
    for i in range(data_start, len(grid)):
        row = grid[i]
        if not row:
            continue
        period = _text(row[0])
        if not period:
            continue
        raw = _text(row[col]) if col < len(row) else ""
        points.append((i, period, raw))
    return {"sheet": sheet_name, "column": col, "name_row": name_row,
            "header_name": _text(grid[name_row][col]), "unit": unit,
            "points": points, "header_rows": data_start}


def _parts(dataset_ref: str) -> Dict[str, str]:
    """`COPPER:nominal_price:2016-01:2025-12` — KOSIS 의 관례를 따른다."""
    bits = str(dataset_ref or "").split(":")
    if len(bits) != 4:
        return {}
    return {"commodity": bits[0], "basis": bits[1], "start": bits[2], "end": bits[3]}


def match_commodities(indicators: Sequence[str]) -> List[Tuple[str, Dict[str, Any]]]:
    """요청 지표 이름을 품목으로 맞춘다. **모르면 비운다** — 지어내지 않는다."""
    wants = [_norm(i) for i in indicators if _norm(i)]
    hits: List[Tuple[str, Dict[str, Any]]] = []
    for code, meta in COMMODITIES.items():
        keys = [_norm(k) for k in meta["keywords"]] + [_norm(code)]
        if any(any(k in w or w in k for k in keys) for w in wants):
            hits.append((code, meta))
    return hits


# ── Provider ────────────────────────────────────────────────────────────────
@provider_registry.register
class WorldBankPinkSheetProvider(B.Provider):
    """World Bank Commodity Markets(Pink Sheet) — 월별 국제 원자재 가격."""

    descriptor = B.ProviderDescriptor(
        provider_id="WB_PINK_SHEET",
        name="World Bank Pink Sheet (월별 국제 원자재 가격)",
        publisher="World Bank",
        #: ⚠️ 실제 형식은 **xlsx** 인데 닫힌 목록 `SOURCE_TYPES` 에 「공식 파일」이 없다.
        #:   `CSV` 를 쓰는 이유는 코드가 이 값을 **우선순위**로만 쓰기 때문이다
        #:   (`_SOURCE_PRIORITY[CSV] = 2` = 지시 3 의 「공식 파일」 자리).
        #:   ★ 어휘를 늘리는 것은 external_intelligence 레인의 결정이라 여기서 하지 않는다.
        source_type="CSV",
        allowed_hosts=(HOST,),
        license_url="https://www.worldbank.org/en/research/commodity-markets",
        allowed_usage="출처 표시 시 재사용 가능(World Bank Terms of Use).",
        redistribution_allowed=True,
        requires_credential=False,
        credential_env="",
        cost="무료(인증키 없음)",
        #: 설계서 §4.2 의 용도 제약이 그대로 등급이 된다 — 위 docstring 참조.
        default_trust_grade="silver",
        refresh_frequency="월 1회(매월 초 갱신)",
        coverage_note=("금속·에너지·비료의 월별 국제 기준 가격(1960년~). "
                       "공식 xlsx 파일 한 개로 전 기간이 함께 옵니다."),
        target_contract_keys=(CONTRACT_KEY,),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        known_limits=(
            "국제 기준 가격입니다 — 우리 실구매 단가가 아닙니다. "
            "공급사 계약단가·헤지·프리미엄·물류비를 대체하지 않습니다(설계서 §4.2).",
            "등급이 silver 이므로 기준 계획·공식 보고(baseline_plan·official_report)에 "
            "쓸 수 없습니다. 시나리오·검토 용도입니다.",
            "월 평균값입니다 — 특정 일자의 체결가가 아닙니다.",
            "과거 값이 «소급 정정»될 수 있습니다. 같은 업무 키로 다시 오면 중복으로 거부되며, "
            "반영은 사람이 판단합니다.",
            "레이아웃을 실제 파일로 확인하지 못했습니다(LAYOUT_VERIFIED=False) — "
            "품목 열을 못 찾으면 다른 열을 읽는 대신 실패합니다.",
        ),
    )

    # ── ② 탐색 ─────────────────────────────────────────────────────────
    def discover(self, request: B.AcquisitionRequest) -> List[B.DiscoveryCandidate]:
        matches = match_commodities(request.indicators)
        if not matches:
            return []
        basis = str((request.extras or {}).get("price_basis") or DEFAULT_BASIS)
        if basis not in SHEET_BY_BASIS:
            basis = DEFAULT_BASIS
        start, end = _window(request)
        out: List[B.DiscoveryCandidate] = []
        for code, meta in matches:
            out.append(B.DiscoveryCandidate(
                provider_id=self.descriptor.provider_id,
                dataset_ref=f"{code}:{basis}:{start}:{end}",
                title=f"{meta['label']} 국제 기준 가격 — Pink Sheet {SHEET_BY_BASIS[basis]}",
                target_contract_key=CONTRACT_KEY,
                period_from=start, period_to=end, frequency="monthly",
                unit="",
                match_reason=(f"요청 지표에서 «{meta['label']}» 를 찾았습니다. "
                              f"Pink Sheet 의 «{meta['names'][0]}» 계열입니다. "
                              "⚠️ 국제 기준 가격이며 실구매 단가가 아닙니다."),
                params={"commodity": code, "basis": basis, "start": start, "end": end,
                        "indicator_code": meta["indicator_code"],
                        "sheet": SHEET_BY_BASIS[basis]}))
        return out

    # ── ③ 미리보기 · ④ 수집 ────────────────────────────────────────────
    def _url(self) -> str:
        override = str(self._env.get(URL_ENV, "") or "").strip()
        return override or f"https://{HOST}{DEFAULT_PATH}"

    def preview(self, candidate: B.DiscoveryCandidate) -> B.FetchResult:
        """파일이 하나뿐이라 미리보기도 같은 파일이다. **보관하지 않는다.**"""
        return self.fetch(candidate)

    def fetch(self, candidate: B.DiscoveryCandidate, *,
              checkpoint: Optional[B.Checkpoint] = None) -> B.FetchResult:
        url = self._url()
        response = self._get(url)
        #: ★ 파일 한 개가 전 기간을 담는다 — 쪽이 없다.
        return self._fetch_result(dataset_ref=candidate.dataset_ref, response=response,
                                  requested_url=url, has_more=False)

    # ── ⑤ 정규화 — 순수 ────────────────────────────────────────────────
    def normalize(self, result: B.FetchResult) -> B.NormalizedBatch:
        parts = _parts(result.dataset_ref)
        if not parts:
            raise B.ProviderError(
                f"dataset_ref 모양이 «품목:기준:시작:끝» 이 아닙니다: {result.dataset_ref!r}")
        code = parts["commodity"]
        meta = COMMODITIES.get(code)
        if meta is None:
            raise B.ProviderError(f"등록되지 않은 품목입니다: {code!r} — 넘겨짚지 않습니다.")
        basis = parts["basis"]
        if basis not in SHEET_BY_BASIS:
            raise B.ProviderError(
                f"등록되지 않은 가격기준입니다: {basis!r} — 넘겨짚지 않습니다.")
        series = read_series(result.payload, sheet_name=SHEET_BY_BASIS[basis],
                             names=meta["names"])

        start, end = parts["start"], parts["end"]
        rows: List[Dict[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        for index, raw_period, raw_value in series["points"]:
            period = normalise_period(raw_period)
            if not period:
                #: 각주·합계 줄이다. 세지 않는다 — 자료 구역이 아니다.
                continue
            if start and period < start:
                continue
            if end and period > end:
                continue
            value = parse_value(raw_value)
            if value is None:
                rejected.append(B.RejectedRow(
                    index, "값 없음",
                    f"{period} 의 값이 «{raw_value}» 입니다 — 0 으로 채우지 않고 뺍니다.",
                    raw_excerpt=str(raw_value)[:100]))
                continue
            rows.append({
                "indicator_code": meta["indicator_code"],
                "commodity_code": code,
                "commodity_name": series["header_name"] or meta["names"][0],
                "price_basis": basis,
                "observed_at": period,
                #: ★ 발표일을 주지 않는다 — 받은 날을 적지 않는다(지어내지 않는다).
                "published_at": "",
                "vintage_date": period,
                "value": value,
                "unit": series["unit"],
                "cycle": "M",
            })
        #: ⚠️ 구간 밖은 «제외»가 아니라 애초에 요청 대상이 아니다. 그래서 정산의 분모는
        #:   파일 전체가 아니라 **구간 안의 줄**이다.
        in_window = len(rows) + len(rejected)
        return B.NormalizedBatch(
            provider_id=self.descriptor.provider_id, contract_key=CONTRACT_KEY,
            rows=tuple(rows), rejected=tuple(rejected), source_row_count=in_window,
            #: ★★★ 원천이 실제로 준 «필드». 파일이라 열 머리가 곧 필드다.
            source_fields=("period", series["header_name"] or meta["names"][0]))

    # ── ⑥ 검증 — 순수, 던지지 않는다 ───────────────────────────────────
    def validate(self, batch: B.NormalizedBatch) -> B.ValidationReport:
        rows = list(batch.rows)
        checks: List[B.CheckResult] = []

        checks.append(B.CheckResult(
            "행 정산", batch.accounted,
            f"구간 내 {batch.source_row_count} = 적재 {len(rows)} + 제외 {len(batch.rejected)}",
            count=batch.source_row_count,
            failure_kind="" if batch.accounted else am.FAILURE_RECONCILIATION))

        checks.append(B.CheckResult("자료 있음", bool(rows), f"{len(rows)}행", count=len(rows),
                                    failure_kind="" if rows else am.FAILURE_QUALITY))

        #: ★★★ 품목이 섞이면 구리와 아연이 한 계열로 뭉친다.
        commodities = {r.get("commodity_code") for r in rows if r.get("commodity_code")}
        checks.append(B.CheckResult(
            "품목 단일", len(commodities) <= 1, f"발견된 품목: {sorted(commodities)}",
            count=len(commodities),
            failure_kind="" if len(commodities) <= 1 else am.FAILURE_QUALITY))

        #: ★ 가격판과 지수판이 섞이면 «$/mt» 와 «2010=100» 이 한 계열이 된다.
        bases = {r.get("price_basis") for r in rows if r.get("price_basis")}
        checks.append(B.CheckResult(
            "가격기준 단일", len(bases) <= 1, f"발견된 기준: {sorted(bases)}", count=len(bases),
            failure_kind="" if len(bases) <= 1 else am.FAILURE_QUALITY))

        units = {r.get("unit") for r in rows if r.get("unit")}
        checks.append(B.CheckResult(
            "단위 단일", len(units) <= 1, f"발견된 단위: {sorted(units)}", count=len(units),
            failure_kind="" if len(units) <= 1 else am.FAILURE_QUALITY))

        #: ⚠️ 단위를 못 읽으면 «숫자만» 남는다 — 계약이 단위를 required 로 요구한다.
        missing_unit = [r for r in rows if not str(r.get("unit") or "").strip()]
        checks.append(B.CheckResult(
            "단위 있음", not missing_unit,
            ("모든 행에 단위가 있습니다." if not missing_unit else
             f"{len(missing_unit)}행에 단위가 없습니다 — 머리 구역에서 «($/mt)» 모양 칸을 "
             "찾지 못했습니다. 레이아웃이 바뀌었을 수 있습니다."),
            count=len(missing_unit),
            failure_kind="" if not missing_unit else am.FAILURE_QUALITY))

        times = [r.get("observed_at") for r in rows]
        duplicates = len(times) - len(set(times))
        checks.append(B.CheckResult(
            "시점 중복 없음", duplicates == 0, f"같은 시점이 {duplicates}건 겹칩니다.",
            count=duplicates,
            failure_kind="" if duplicates == 0 else am.FAILURE_QUALITY))

        checks.append(B.CheckResult(
            "발표일 없음(정상)", True,
            "Pink Sheet 는 값별 발표일을 주지 않습니다 — 지어내지 않고 비웠습니다. "
            "vintage 는 관측 시점을 씁니다.", count=len(rows)))

        #: ⚠️ 레이아웃 미확인은 **주의사항이지 품질 결함이 아니다.** `ok=False` 로 두면
        #:   정상 자료가 늘 격리된다 — KOSIS 에서 실제로 저지른 실수다.
        checks.append(B.CheckResult(
            "레이아웃 실측 여부", True,
            ("실측으로 확인됨" if LAYOUT_VERIFIED else
             "⚠️ 실제 Pink Sheet 파일과 대조하지 못했습니다. 품목 열을 못 찾으면 "
             "다른 열을 읽는 대신 실패하므로 «조용히 틀린 값»은 나오지 않습니다. "
             "실제 파일로 한 번 돌린 뒤 LAYOUT_VERIFIED 를 True 로 바꾸십시오."),
            count=len(COMMODITIES)))

        return B.ValidationReport(checks=tuple(checks))

    # ── ⑦ 이어받기 · ⑧ 갱신 — 순수 ────────────────────────────────────
    def checkpoint(self, batch: B.NormalizedBatch, *,
                   previous: Optional[B.Checkpoint] = None) -> B.Checkpoint:
        times = sorted({str(r.get("observed_at") or "") for r in batch.rows} - {""})
        ref = ""
        if batch.rows:
            r = batch.rows[0]
            ref = f"{r.get('commodity_code')}:{r.get('price_basis')}"
        return B.Checkpoint(
            provider_id=self.descriptor.provider_id,
            dataset_ref=ref or (previous.dataset_ref if previous else ""),
            cursor=times[-1] if times else (previous.cursor if previous else ""),
            covered_from=times[0] if times else "",
            covered_to=times[-1] if times else "",
            last_success_at=times[-1] if times else "")

    def refresh(self, checkpoint: B.Checkpoint, *, until: str = "") -> List[B.DiscoveryCandidate]:
        """다음 구간. **순수** — 시계를 읽지 않는다.

        ⚠️ 파일은 늘 전 기간을 준다. 그래도 구간을 좁히는 이유는 **이미 적재한 값을
          다시 넣지 않기 위해서**다 — 중복은 거부되지만 매달 700행을 거부시키면
          「거부 목록」이 쓸모없어진다."""
        bits = str(checkpoint.dataset_ref or "").split(":")
        if len(bits) != 2 or not bits[0]:
            return []
        code, basis = bits
        meta = COMMODITIES.get(code)
        cursor = str(checkpoint.cursor or "")
        if meta is None or not cursor:
            return []
        start = _next_month(cursor)
        if start == cursor:
            return []
        end = str(until or "").strip() or f"{start[:4]}-12"
        if end < start:
            end = start
        return [B.DiscoveryCandidate(
            provider_id=self.descriptor.provider_id,
            dataset_ref=f"{code}:{basis}:{start}:{end}",
            title=f"{meta['label']} 국제 기준 가격 — {start} 이후",
            target_contract_key=CONTRACT_KEY,
            period_from=start, period_to=end, frequency="monthly",
            match_reason=f"직전 수집이 {checkpoint.covered_to} 까지였습니다.",
            params={"commodity": code, "basis": basis, "start": start, "end": end,
                    "indicator_code": meta["indicator_code"],
                    "sheet": SHEET_BY_BASIS.get(basis, SHEET_BY_BASIS[DEFAULT_BASIS])})]


# ── 보조 ─────────────────────────────────────────────────────────────────────
def _window(request: B.AcquisitionRequest) -> Tuple[str, str]:
    """요청의 연도를 월 구간으로. 비면 빈 값 — **오늘로 채우지 않는다**(순수)."""
    def _month(raw: str, tail: str) -> str:
        text = _text(raw)
        if re.match(r"^\d{4}-\d{2}$", text):
            return text
        return f"{text}-{tail}" if _ANNUAL.match(text) else ""
    return _month(request.period_from, "01"), _month(request.period_to, "12")


def _next_month(period: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})$", _text(period))
    if not m:
        return _text(period)
    year, month = int(m.group(1)), int(m.group(2))
    return f"{year + 1}-01" if month >= 12 else f"{year}-{month + 1:02d}"
