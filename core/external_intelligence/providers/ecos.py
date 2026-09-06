"""[DAO-10] 한국은행 ECOS Provider — 환율·금리·물가.

## OpenDART 와 다른 점 셋 — 그래서 명시적 변환기가 따로 있다

★★★ ① **인증키가 경로에 있다.**
  `https://ecos.bok.or.kr/api/StatisticSearch/<KEY>/json/kr/1/100/731Y001/...`
  질의 문자열만 지우는 검사기는 이것을 통과시킨다. `raw_store.redact_url` 이 값 기반으로
  지우고 `assert_no_secret` 이 디코드한 형태로도 확인한다 — 그 통제가 **실제로 필요한
  첫 원천**이다.

★★★ ② **오류가 200 으로 온다.** 본문의 `RESULT.CODE` 를 봐야 한다.
  `INFO-200`(해당하는 데이터가 없습니다)은 **정상 응답**이고 「자료 없음」이다. 이것을
  장애로 접으면 스케줄러가 없는 자료를 영원히 재시도한다. OpenDART 의 `013` 과 같은 자리다.

★★★ ③ **항목 코드를 추측하지 않는다.**
  통계표(`STAT_CODE`)는 널리 알려져 있지만 세부항목(`ITEM_CODE`)은 통계표마다 다르고 바뀐다.
  그래서 `discover()` 가 `StatisticItemList` 를 **물어본 뒤** 후보를 만든다.
  ⚠️ 코드를 상수로 박아 두면 원천이 바꾼 날 조용히 다른 계열을 받아 온다.

## 목적지 — 이미 있는 계약이다

`EXT-01 환율·금리·물가` 는 업무키트에 이미 있고 열 모양도 관측값 그대로다
(`observation_id · indicator_code · observed_at · published_at · vintage_date · value ·
unit · source_id · trust_grade`). 새 계약을 만들지 않는다.

⚠️⚠️ 다만 키트의 `EXT-01` 은 `data_class: SYNTHETIC` 으로 선언돼 있다(시연용). 공개 통계를
  그 선언 아래 넣으면 계약이 말하는 것과 행이 실제인 것이 갈린다 — 오케스트레이터의
  원천-성격 적합성 검사가 이것을 막고, 사람이 계약을 고쳐야 통과한다.

## ⚠️ 이 값으로 하면 안 되는 것

  · 매매기준율은 **회사의 실제 체결 환율이 아니다.** 헤지·수수료·결제일 차이를 담지 않는다.
  · 기준금리는 **회사의 조달금리가 아니다.**
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import provider_registry

CONTRACT_KEY = "EXT-01"
BASE = "https://ecos.bok.or.kr/api"

#: ★★★ ECOS 상태코드. **`INFO-200` 만 「자료 없음」이고 나머지는 장애다.**
#:   이 표가 곧 「장애와 자료 없음의 분리」다 — 호출부가 문자열을 다시 해석하지 않는다.
RESULT_OK = "INFO-000"
RESULT_NO_DATA = "INFO-200"
RESULT_FAILURE_KIND = {
    "INFO-100": am.FAILURE_AUTH,           # 인증키가 유효하지 않습니다
    "INFO-300": am.FAILURE_AUTH,           # 등록되지 않은 인증키
    "ERROR-100": am.FAILURE_SCHEMA_DRIFT,  # 필수 값 누락
    "ERROR-101": am.FAILURE_SCHEMA_DRIFT,  # 주기가 적절하지 않음
    "ERROR-200": am.FAILURE_SCHEMA_DRIFT,  # 파일타입 누락·무효
    "ERROR-300": am.FAILURE_SCHEMA_DRIFT,  # 조회 건수 누락
    "ERROR-301": am.FAILURE_SCHEMA_DRIFT,  # 조회 시작일자 누락
    "ERROR-500": am.FAILURE_TRANSPORT,     # 서버 오류
    "ERROR-600": am.FAILURE_TRANSPORT,     # DB 연결 오류
    "ERROR-601": am.FAILURE_TRANSPORT,     # SQL 오류
    "ERROR-602": am.FAILURE_TRANSPORT,     # 과도한 트래픽
}

#: 다룰 통계표. **닫힌 목록**이다 — 여기 없는 통계는 요청해도 후보가 되지 않는다.
#:   ⚠️ `item_hint` 는 «어느 세부항목을 고를 것인가» 의 힌트일 뿐이고, 실제 코드는
#:     `StatisticItemList` 에서 받아 온다(추측하지 않는다).
SERIES: Dict[str, Dict[str, Any]] = {
    "731Y001": {
        "label": "원/미국달러 환율(매매기준율)", "kind": "fx_rate",
        "item_hint": "원/미국달러", "cycle": "M", "indicator_code": "FX_USDKRW",
        "aliases": ("환율", "원달러", "달러환율", "원/달러", "usdkrw", "exchange rate", "fx"),
        "limits": ("매매기준율은 회사의 실제 체결 환율이 아닙니다 — "
                   "헤지·수수료·결제일 차이를 담지 않습니다.",),
    },
    "722Y001": {
        "label": "한국은행 기준금리", "kind": "interest_rate",
        "item_hint": "한국은행 기준금리", "cycle": "M", "indicator_code": "BOK_BASE_RATE",
        "aliases": ("기준금리", "정책금리", "금리", "base rate", "policy rate"),
        "limits": ("기준금리는 회사의 조달금리가 아닙니다.",),
    },
    "901Y009": {
        "label": "소비자물가지수", "kind": "price_index",
        "item_hint": "총지수", "cycle": "M", "indicator_code": "CPI_TOTAL",
        "aliases": ("소비자물가", "물가", "cpi", "물가지수", "consumer price"),
        "limits": ("소비자물가지수는 회사의 구매단가 상승률이 아닙니다.",),
    },
}

_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_TIME_SHAPES = (
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "{0}-{1}-{2}"),   # 일별
    (re.compile(r"^(\d{4})(\d{2})$"), "{0}-{1}"),              # 월별
    (re.compile(r"^(\d{4})Q(\d)$"), "{0}-Q{1}"),               # 분기
    (re.compile(r"^(\d{4})$"), "{0}"),                          # 연별
)


class NoDataFromSource(B.ProviderError):
    """★★★ ECOS 가 **정상 응답**했고 해당 자료가 없다(`INFO-200`). 재시도해도 같다."""


class EcosResultError(B.ProviderError):
    """ECOS 가 오류 코드를 돌려줬다. `failure_kind` 로 어느 상태로 갈지 정한다."""

    def __init__(self, code: str, message: str, failure_kind: str):
        super().__init__(f"ECOS {code}: {message}")
        self.code = code
        self.failure_kind = failure_kind


def normalise_time(raw: str) -> str:
    """ECOS 의 `TIME` 을 읽을 수 있는 날짜로. **모르는 모양이면 빈 문자열** — 지어내지 않는다."""
    text = str(raw or "").strip()
    for pattern, template in _TIME_SHAPES:
        m = pattern.match(text)
        if m:
            return template.format(*m.groups())
    return ""


def parse_value(raw: Any) -> Optional[float]:
    """숫자로 읽는다. **읽지 못하면 `None`** — 0 으로 만들지 않는다.

    ⚠️ 0 으로 채우면 「환율이 0」이 되고, 그것은 결손보다 나쁘다."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if not text or not _NUM.match(text):
        return None
    return float(text)


def _check_result(payload: Mapping[str, Any]) -> None:
    """★ 상태 판정을 **한 곳에서만** 한다. ECOS 는 오류도 HTTP 200 으로 준다."""
    result = payload.get("RESULT")
    if not isinstance(result, Mapping):
        return                              # 정상 응답에는 RESULT 가 없다
    code = str(result.get("CODE") or "").strip()
    message = str(result.get("MESSAGE") or "").strip()
    if code == RESULT_OK:
        return
    if code == RESULT_NO_DATA:
        raise NoDataFromSource(f"ECOS 에 해당 조건의 자료가 없습니다: {message or code}")
    raise EcosResultError(code or "(코드 없음)", message or "(메시지 없음)",
                          RESULT_FAILURE_KIND.get(code, am.FAILURE_TRANSPORT))


def _load(payload: bytes, service: str) -> List[Dict[str, Any]]:
    """서비스별 `row` 목록을 꺼낸다. **명시적 변환기** — 아무 JSON 이나 받지 않는다."""
    try:
        data = json.loads(bytes(payload or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EcosResultError("ERROR-100", f"응답을 JSON 으로 읽지 못했습니다: {exc}",
                              am.FAILURE_SCHEMA_DRIFT) from exc
    if not isinstance(data, dict):
        raise EcosResultError("ERROR-100", "응답 최상위가 객체가 아닙니다.",
                              am.FAILURE_SCHEMA_DRIFT)
    _check_result(data)
    block = data.get(service)
    if not isinstance(block, Mapping):
        raise EcosResultError("ERROR-100", f"응답에 {service} 가 없습니다.",
                              am.FAILURE_SCHEMA_DRIFT)
    rows = block.get("row")
    if not isinstance(rows, list):
        raise EcosResultError("ERROR-100", f"{service}.row 가 목록이 아닙니다.",
                              am.FAILURE_SCHEMA_DRIFT)
    return [r for r in rows if isinstance(r, dict)]


def match_series(indicators: Sequence[str]) -> List[Tuple[str, Dict[str, Any]]]:
    """요청한 지표 이름을 통계표로. **닫힌 목록 안에서만** 고른다."""
    wanted = [str(x or "").strip().lower() for x in indicators if str(x or "").strip()]
    out: List[Tuple[str, Dict[str, Any]]] = []
    for code, meta in SERIES.items():
        keys = tuple(a.lower() for a in meta["aliases"]) + (meta["label"].lower(), code.lower())
        if any(any(k in w or w in k for k in keys) for w in wanted):
            out.append((code, meta))
    return out


@provider_registry.register
class EcosProvider(B.Provider):
    """한국은행 경제통계시스템(ECOS)."""

    descriptor = B.ProviderDescriptor(
        provider_id="ECOS",
        name="한국은행 경제통계시스템(ECOS)",
        publisher="한국은행",
        source_type="API",
        allowed_hosts=("ecos.bok.or.kr",),
        license_url="https://ecos.bok.or.kr/api/#/AuthKeyApply",
        allowed_usage="공표 통계의 내부 분석·저장. 출처 표시가 필요합니다.",
        redistribution_allowed=False,
        requires_credential=True,
        credential_env="AFS_ECOS_API_KEY",
        cost="무료(인증키 신청 · 일 호출 한도 있음)",
        default_trust_grade="gold",
        refresh_frequency="통계표별 공표 주기(환율 일별 · 기준금리 변경 시 · 물가 월별)",
        coverage_note="환율·금리·물가 등 한국은행 공표 통계. 통계표와 세부항목으로 조회합니다.",
        target_contract_keys=(CONTRACT_KEY,),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        known_limits=(
            "매매기준율은 회사의 실제 체결 환율이 아닙니다 — 헤지·수수료·결제일 차이가 빠집니다.",
            "기준금리는 회사의 조달금리가 아닙니다.",
            "인증키가 URL 경로에 들어갑니다 — 요청 URL 을 그대로 기록하면 키가 샙니다.",
            "세부항목 코드는 통계표마다 다르고 바뀝니다 — 조회 시점에 확인합니다.",
        ),
    )

    # ── ② 탐색 ─────────────────────────────────────────────────────────
    def discover(self, request: B.AcquisitionRequest) -> List[B.DiscoveryCandidate]:
        """지표 이름 → 통계표 → **원천에 물어본** 세부항목."""
        matches = match_series(request.indicators)
        if not matches:
            return []
        if not _years(request):
            raise B.ProviderError("기간(연도)이 필요합니다 — ECOS 는 기간 없이 조회하지 않습니다.")

        out: List[B.DiscoveryCandidate] = []
        for stat_code, meta in matches:
            items = self._items(stat_code)
            if not items:
                continue
            hint = str(meta["item_hint"])
            exact = [i for i in items if hint in str(i.get("ITEM_NAME") or "")]
            chosen = (exact or items)[0]
            others = tuple(f"{i.get('ITEM_NAME')}({i.get('ITEM_CODE')})"
                           for i in (exact or items)[1:6])
            cycle = str(chosen.get("CYCLE") or meta["cycle"]).upper()
            #: ★★★ 기간 표기는 **주기를 알고 난 뒤에** 만든다.
            #:   ⚠️ 실측으로 어긋났다 — 주기가 `D` 인데 기간을 `YYYYMM` 으로 만들어
            #:     보내면 원천이 다른 것을 주거나 거부하고, 커서도 넘어가지 않는다.
            start, end = _period(request, cycle)
            item_code = str(chosen.get("ITEM_CODE") or "")
            out.append(B.DiscoveryCandidate(
                provider_id=self.descriptor.provider_id,
                dataset_ref=f"{stat_code}:{item_code}:{cycle}:{start}:{end}",
                title=f"{meta['label']} ({chosen.get('ITEM_NAME')})",
                target_contract_key=CONTRACT_KEY,
                period_from=start, period_to=end, frequency=_frequency(cycle),
                unit=str(chosen.get("UNIT_NAME") or ""),
                match_reason=(f"요청 지표가 통계표 {stat_code}({meta['label']}) 와 맞고, "
                              f"세부항목은 원천 목록에서 '{chosen.get('ITEM_NAME')}' 를 "
                              f"골랐습니다(코드는 조회 시점에 확인했습니다)."),
                params={"stat_code": stat_code, "item_code": item_code, "cycle": cycle,
                        "start": start, "end": end,
                        "indicator_code": meta["indicator_code"],
                        "item_name": str(chosen.get("ITEM_NAME") or ""),
                        "unit": str(chosen.get("UNIT_NAME") or "")},
                ambiguous_with=others))
        return out

    def _items(self, stat_code: str) -> List[Dict[str, Any]]:
        """세부항목을 **물어본다.** ⚠️ 상수로 박아 두면 원천이 바꾼 날 다른 계열을 받는다."""
        url = (f"{BASE}/StatisticItemList/{self.credential()}/json/kr/1/100/"
               f"{stat_code}")
        try:
            response = self._get(url)
        except B.ProviderError:
            raise
        return _load(bytes(response.get("body") or b""), "StatisticItemList")

    # ── ③ 미리보기 · ④ 수집 ────────────────────────────────────────────
    def preview(self, candidate: B.DiscoveryCandidate) -> B.FetchResult:
        return self._fetch(candidate, limit=10)

    def fetch(self, candidate: B.DiscoveryCandidate, *,
              checkpoint: Optional[B.Checkpoint] = None) -> B.FetchResult:
        start = candidate.params.get("start")
        if checkpoint and checkpoint.cursor:
            #: ★ 이어받기 — 마지막으로 받은 시점 다음부터. 처음부터 다시 받지 않는다.
            start = _next_period(str(checkpoint.cursor), str(candidate.params.get("cycle") or "M"))
        return self._fetch(candidate, limit=1000, start_override=start)

    def _fetch(self, candidate: B.DiscoveryCandidate, *, limit: int,
               start_override: Optional[str] = None) -> B.FetchResult:
        p = dict(candidate.params or {})
        for field in ("stat_code", "item_code", "cycle", "start", "end"):
            if not str(p.get(field, "")).strip():
                raise B.ProviderError(f"후보에 {field} 가 없습니다 — discover 를 먼저 부르십시오.")
        start = str(start_override or p["start"])
        #: ⚠️ 인증키가 **경로**에 들어간다. 결과의 URL 은 `_fetch_result` 가 지운다.
        url = (f"{BASE}/StatisticSearch/{self.credential()}/json/kr/1/{int(limit)}/"
               f"{p['stat_code']}/{p['cycle']}/{start}/{p['end']}/{p['item_code']}")
        response = self._get(url)
        _load(bytes(response.get("body") or b""), "StatisticSearch")   # 상태를 여기서 한 번 본다
        return self._fetch_result(dataset_ref=candidate.dataset_ref, response=response,
                                  requested_url=url)

    # ── ⑤ 정규화 — 순수 ────────────────────────────────────────────────
    def normalize(self, result: B.FetchResult) -> B.NormalizedBatch:
        """ECOS 응답을 `EXT-01` 모양으로. **OpenDART 와 다른 변환기다.**

        ⚠️ 공통 봉투(tenant_id·scope_node_id 등)는 채우지 않는다 — Provider 는 테넌트를
          모르고, 적용 시점에 오케스트레이터가 씌운다."""
        rows_in = _load(result.payload, "StatisticSearch")
        parts = _dataset_parts(result.dataset_ref)
        meta = SERIES.get(parts.get("stat_code", ""), {})
        indicator = str(meta.get("indicator_code") or parts.get("stat_code") or "")

        rows: List[Dict[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        for i, item in enumerate(rows_in):
            observed = normalise_time(item.get("TIME"))
            if not observed:
                rejected.append(B.RejectedRow(
                    i, "시점을 읽지 못함", f"TIME={item.get('TIME')!r}",
                    raw_excerpt=json.dumps(item, ensure_ascii=False)[:100]))
                continue
            value = parse_value(item.get("DATA_VALUE"))
            if value is None:
                #: ★★★ 값을 못 읽은 줄은 **0 으로 채우지 않고 사유와 함께 뺀다.**
                rejected.append(B.RejectedRow(
                    i, "값을 숫자로 읽지 못함", f"DATA_VALUE={item.get('DATA_VALUE')!r}",
                    raw_excerpt=json.dumps(item, ensure_ascii=False)[:100]))
                continue
            item_code = str(item.get("ITEM_CODE1") or parts.get("item_code") or "")
            rows.append({
                "observation_id": f"{parts.get('stat_code')}:{item_code}:{observed}",
                "indicator_code": indicator,
                "stat_code": str(parts.get("stat_code") or ""),
                "item_code": item_code,
                "item_name": str(item.get("ITEM_NAME1") or ""),
                "observed_at": observed,
                #: ⚠️ ECOS 는 «발표일» 을 따로 주지 않는다. **지어내지 않고 비워 둔다** —
                #:   「받은 날」을 발표일로 적으면 §12.5 의 재현성이 조용히 깨진다.
                "published_at": "",
                "vintage_date": observed,
                "value": value,
                "unit": str(item.get("UNIT_NAME") or parts.get("unit") or ""),
                "cycle": str(parts.get("cycle") or ""),
            })
        return B.NormalizedBatch(provider_id=self.descriptor.provider_id,
                                 contract_key=CONTRACT_KEY, rows=tuple(rows),
                                 rejected=tuple(rejected), source_row_count=len(rows_in))

    # ── ⑥ 검증 — 순수 ──────────────────────────────────────────────────
    def validate(self, batch: B.NormalizedBatch) -> B.ValidationReport:
        rows = list(batch.rows)
        checks: List[B.CheckResult] = []

        checks.append(B.CheckResult(
            "행 정산", batch.accounted,
            f"원문 {batch.source_row_count} = 적재 {len(rows)} + 제외 {len(batch.rejected)}",
            count=batch.source_row_count,
            failure_kind="" if batch.accounted else am.FAILURE_RECONCILIATION))

        checks.append(B.CheckResult("자료 있음", bool(rows), f"{len(rows)}행", count=len(rows),
                                    failure_kind="" if rows else am.FAILURE_QUALITY))

        units = {r.get("unit") for r in rows if r.get("unit")}
        checks.append(B.CheckResult(
            "단위 단일", len(units) <= 1, f"발견된 단위: {sorted(units)}", count=len(units),
            failure_kind="" if len(units) <= 1 else am.FAILURE_QUALITY))

        indicators = {r.get("indicator_code") for r in rows}
        checks.append(B.CheckResult(
            "지표 단일", len(indicators) <= 1, f"발견된 지표: {sorted(x for x in indicators if x)}",
            count=len(indicators),
            failure_kind="" if len(indicators) <= 1 else am.FAILURE_QUALITY))

        times = [r.get("observed_at") for r in rows]
        duplicates = len(times) - len(set(times))
        checks.append(B.CheckResult(
            "시점 중복 없음", duplicates == 0, f"같은 시점이 {duplicates}건 겹칩니다.",
            count=duplicates,
            failure_kind="" if duplicates == 0 else am.FAILURE_QUALITY))

        #: ★ ECOS 는 발표일을 주지 않는다 — 비어 있는 것이 정상이고, **그 사실을 적는다.**
        checks.append(B.CheckResult(
            "발표일 없음(정상)", True,
            "ECOS 는 발표일을 제공하지 않습니다 — 지어내지 않고 비웠습니다. "
            "vintage 는 관측 시점을 씁니다.", count=len(rows)))

        return B.ValidationReport(checks=tuple(checks))

    # ── ⑦ 이어받기 · ⑧ 갱신 — 순수 ────────────────────────────────────
    def checkpoint(self, batch: B.NormalizedBatch, *,
                   previous: Optional[B.Checkpoint] = None) -> B.Checkpoint:
        times = sorted({str(r.get("observed_at") or "") for r in batch.rows} - {""})
        ref = ""
        if batch.rows:
            r = batch.rows[0]
            ref = f"{r.get('stat_code')}:{r.get('item_code')}:{r.get('cycle')}"
        return B.Checkpoint(
            provider_id=self.descriptor.provider_id,
            dataset_ref=ref or (previous.dataset_ref if previous else ""),
            cursor=(times[-1].replace("-", "") if times
                    else (previous.cursor if previous else "")),
            covered_from=times[0] if times else "",
            covered_to=times[-1] if times else "",
            last_success_at=times[-1] if times else "")

    def refresh(self, checkpoint: B.Checkpoint, *, until: str = "") -> List[B.DiscoveryCandidate]:
        """다음에 받을 구간. **순수** — 마지막 시점 **다음**부터.

        ⚠️ 시계를 읽지 않는다. 읽으면 같은 체크포인트가 날마다 다른 후보를 내고, 그러면
          정기 갱신이 「돌려 봐야 아는」 것이 된다. 상한은 인자로 받고, 없으면 커서 다음
          해의 끝으로 둔다 — 원천이 그보다 최신이 없으면 알아서 자른다."""
        bits = str(checkpoint.dataset_ref or "").split(":")
        if len(bits) != 3 or not bits[0]:
            return []
        stat_code, item_code, cycle = bits
        cursor = str(checkpoint.cursor or "")
        if not cursor:
            return []
        start = _next_period(cursor, cycle)
        if start == cursor:
            #: 커서를 넘기지 못했다 — 같은 구간을 다시 받으면 중복만 쌓인다.
            return []
        meta = SERIES.get(stat_code, {})
        end = str(until or "").strip() or _period_end(start, cycle)
        return [B.DiscoveryCandidate(
            provider_id=self.descriptor.provider_id,
            dataset_ref=f"{stat_code}:{item_code}:{cycle}:{start}:{end}",
            title=f"{meta.get('label', stat_code)} — {start} 이후",
            target_contract_key=CONTRACT_KEY,
            period_from=start, period_to=end, frequency=_frequency(cycle),
            match_reason=f"직전 수집이 {checkpoint.covered_to} 까지였습니다.",
            params={"stat_code": stat_code, "item_code": item_code, "cycle": cycle,
                    "start": start, "end": end,
                    "indicator_code": meta.get("indicator_code", stat_code)})]


# ── 보조 ─────────────────────────────────────────────────────────────────────
def _years(request: B.AcquisitionRequest) -> Tuple[str, str]:
    def _y(v: str) -> str:
        m = re.search(r"(\d{4})", str(v or ""))
        return m.group(1) if m else ""

    a, b = _y(request.period_from), _y(request.period_to)
    if not a and not b:
        return ()
    a = a or b
    b = b or a
    return (b, a) if b < a else (a, b)


#: 주기별 기간 표기. **원천이 요구하는 자릿수가 다르다** — 하나로 두면 어긋난다.
_PERIOD_SHAPE = {
    "D": ("{0}0101", "{0}1231"),
    "M": ("{0}01", "{0}12"),
    "Q": ("{0}Q1", "{0}Q4"),
    "A": ("{0}", "{0}"),
    "Y": ("{0}", "{0}"),
}


def _period(request: B.AcquisitionRequest, cycle: str) -> Tuple[str, str]:
    """요청 기간을 **그 통계표의 주기에 맞는** 표기로."""
    years = _years(request)
    if not years:
        return "", ""
    a, b = years
    start_fmt, end_fmt = _PERIOD_SHAPE.get(str(cycle or "M").upper(), _PERIOD_SHAPE["M"])
    return start_fmt.format(a), end_fmt.format(b)


def _frequency(cycle: str) -> str:
    return {"D": "daily", "M": "monthly", "Q": "quarterly",
            "A": "annual", "Y": "annual"}.get(str(cycle or "").upper(), "")


def _next_period(cursor: str, cycle: str) -> str:
    """마지막으로 받은 시점의 **다음** 구간. 같은 시점을 다시 받으면 중복이 쌓인다."""
    raw = str(cursor or "").replace("-", "")
    c = str(cycle or "M").upper()
    try:
        if c == "M" and len(raw) >= 6:
            year, month = int(raw[:4]), int(raw[4:6])
            return f"{year + 1}01" if month >= 12 else f"{year}{month + 1:02d}"
        if c == "A" or c == "Y":
            return str(int(raw[:4]) + 1)
        if c == "D" and len(raw) >= 8:
            from datetime import date, timedelta
            nxt = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])) + timedelta(days=1)
            return nxt.strftime("%Y%m%d")
    except (TypeError, ValueError):
        return raw
    return raw


def _period_end(start: str, cycle: str) -> str:
    """상한. 커서 **다음 해의 끝**으로 둔다 — 시계를 읽지 않고도 앞으로 나아간다."""
    year = str(start)[:4]
    try:
        nxt = str(int(year) + 1)
    except ValueError:
        return start
    _, end_fmt = _PERIOD_SHAPE.get(str(cycle or "M").upper(), _PERIOD_SHAPE["M"])
    return end_fmt.format(nxt)


def _dataset_parts(dataset_ref: str) -> Dict[str, str]:
    bits = str(dataset_ref or "").split(":")
    if len(bits) != 5:
        return {}
    return {"stat_code": bits[0], "item_code": bits[1], "cycle": bits[2],
            "start": bits[3], "end": bits[4]}
