"""[DAO-14] 공공데이터포털(data.go.kr) — **포털은 원천이 아니다. 서비스가 원천이다.**

## ★★★ 왜 「공공데이터포털 Provider」 하나로 만들지 않았나

앞의 셋(DART·ECOS·KOSIS)은 **하나의 기관이 하나의 신뢰도로** 자료를 준다. 공공데이터포털은
수천 개 서비스를 호스팅하는 **창구**이고, 그 안의 자료는 기관도 신뢰도도 제각각이다.

`ProviderDescriptor.default_trust_grade` 는 Provider 당 **하나**다. 포털을 한 Provider 로
두면 그 하나가 전부를 대표하게 되고, 설계서가 `KPX = Silver` · `KOSIS = Gold` 로 나눠 둔
것이 **뭉개진다.** 그래서 이 파일은 다음 모양이다:

    DataGoKrService   포털의 **공통 봉투**만 읽는 기반 클래스 (등록되지 않는다)
      └ KpxSmpProvider   서비스 하나 = Provider 하나 = 등급 하나

★ 이렇게 하면 기존 계약을 **바꾸지 않고** 서비스마다 등급·한계·계약을 정확히 말할 수 있다.

## 봉투는 공통, 필드는 서비스별 — 그 경계가 지시 4 의 답이다

공공데이터포털은 **문서화된 표준 봉투**를 쓴다:

    {"response": {"header": {"resultCode": "00", ...},
                  "body": {"items": {"item": [...]}, "pageNo": .., "totalCount": ..}}}

봉투를 공통으로 읽는 것은 「느슨한 범용 파서」가 아니다 — **그 포털의 규격**이다. 그러나
`item` 안의 **필드는 서비스마다 다르므로** 기반 클래스가 기본 구현을 주지 않는다.
하위 클래스가 `FIELDS` 를 선언하지 않으면 인스턴스화조차 되지 않는다.

## 이 원천이 처음 요구한 것 셋

★★★ ① **페이징.** 앞의 셋은 한 번에 다 받았다. 여기는 `pageNo`/`totalCount` 로 나뉜다.
  `FetchResult.has_more`·`next_cursor` 는 `base.py` 에 **선언만 돼 있고 아무도 읽지
  않았다** — 이 Provider 가 처음 쓴다.
  ⚠️ 쪽을 합쳐 하나의 「원문」으로 만들지 않는다. 그러면 보관된 원문이 **원천이 보낸 것이
    아니게** 되고, 「원천이 이렇게 말했다」가 거짓이 된다. 쪽마다 따로 보관한다.

★★★ ② **오류가 두 가지 봉투로 온다.**
    봉투 안:   `response.header.resultCode != "00"`
    다른 봉투: `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": ...}}}`
  둘째를 모르면 인증 오류가 **스키마 표류**로 잘못 분류되고, 사람은 엉뚱한 곳을 고친다.

★★★ ③ **1건이면 `item` 이 배열이 아니라 객체다.** XML→JSON 변환의 고전적 함정이다.
  배열만 기대하면 **마지막 1건이 조용히 사라진다.**

## ⚠️ 실측 미확인

`ENDPOINT` 와 `FIELDS` 는 공개 문서를 근거로 적었으나 이 저장소가 실제 응답으로 확인하지
못했다. `SERVICE_VERIFIED = False` 를 카드·검증 보고서에 남긴다 — KOSIS 오류표와 같은 규율.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import provider_registry

BASE = "https://apis.data.go.kr"

#: ★★★ 표준 봉투의 상태코드. **`03` 만 「자료 없음」이고 나머지는 장애다.**
RESULT_OK = "00"
RESULT_NO_DATA = "03"
RESULT_FAILURE_KIND: Dict[str, str] = {
    "01": am.FAILURE_TRANSPORT,     # APPLICATION_ERROR
    "02": am.FAILURE_TRANSPORT,     # DB_ERROR
    "04": am.FAILURE_TRANSPORT,     # HTTP_ERROR
    "05": am.FAILURE_TRANSPORT,     # SERVICETIME_OUT
    "10": am.FAILURE_SCHEMA_DRIFT,  # INVALID_REQUEST_PARAMETER
    "11": am.FAILURE_SCHEMA_DRIFT,  # NO_MANDATORY_REQUEST_PARAMETERS
    "12": am.FAILURE_POLICY,        # NO_OPENAPI_SERVICE
    "20": am.FAILURE_POLICY,        # SERVICE_ACCESS_DENIED
    "22": am.FAILURE_TRANSPORT,     # LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS
    "30": am.FAILURE_AUTH,          # SERVICE_KEY_IS_NOT_REGISTERED
    "31": am.FAILURE_AUTH,          # DEADLINE_HAS_EXPIRED
    "32": am.FAILURE_POLICY,        # UNREGISTERED_IP
    "99": am.FAILURE_TRANSPORT,     # UNKNOWN_ERROR
}

DEFAULT_ROWS_PER_PAGE = 100
#: 한 수집이 받을 수 있는 최대 쪽수. **끝없는 페이징을 막는다** — 원천이 `totalCount` 를
#: 잘못 주면 영원히 돈다.
MAX_PAGES = 50

_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_SHAPES = (
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "{0}-{1}-{2}"),
    (re.compile(r"^(\d{4})(\d{2})$"), "{0}-{1}"),
    (re.compile(r"^(\d{4})$"), "{0}"),
)


class NoDataFromSource(B.ProviderError):
    """★★★ `resultCode=03` — 정상 응답이고 해당 자료가 없다. 재시도해도 같다."""


class DataGoKrError(B.ProviderError):
    """포털이 오류를 돌려줬다. **두 봉투 어느 쪽이든** 여기로 온다."""

    def __init__(self, code: str, message: str, failure_kind: str, envelope: str = "standard"):
        super().__init__(f"data.go.kr {envelope} resultCode={code}: {message}")
        self.code = code
        self.failure_kind = failure_kind
        self.envelope = envelope


def normalise_date(raw: Any) -> str:
    text = str(raw or "").strip()
    for pattern, template in _DATE_SHAPES:
        m = pattern.match(text)
        if m:
            return template.format(*m.groups())
    return ""


def parse_value(raw: Any) -> Optional[float]:
    """읽지 못하면 `None` — 0 으로 만들지 않는다."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if not text or not _NUM.match(text):
        return None
    return float(text)


def read_envelope(payload: bytes) -> Dict[str, Any]:
    """★★★ 포털의 **두 봉투**를 모두 읽고, 쪽 정보를 함께 돌려준다.

    돌려주는 것: `{"items": [...], "page": n, "rows": n, "total": n}`

    ⚠️ 오류 봉투가 둘이라는 것을 모르면 인증 오류가 **스키마 표류**로 잘못 분류되고,
      사람은 파서를 고치러 간다 — 실제로는 키를 등록해야 한다."""
    try:
        data = json.loads(bytes(payload or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataGoKrError("10", f"응답을 JSON 으로 읽지 못했습니다: {exc}",
                            am.FAILURE_SCHEMA_DRIFT) from exc
    if not isinstance(data, Mapping):
        raise DataGoKrError("10", "응답 최상위가 객체가 아닙니다.", am.FAILURE_SCHEMA_DRIFT)

    #: ① 다른 봉투 — 인증·서비스 오류가 여기로 온다.
    other = data.get("OpenAPI_ServiceResponse")
    if isinstance(other, Mapping):
        head = other.get("cmmMsgHeader")
        head = head if isinstance(head, Mapping) else {}
        code = str(head.get("returnReasonCode") or "").strip()
        message = str(head.get("returnAuthMsg") or head.get("errMsg") or "").strip()
        raise DataGoKrError(code or "(코드 없음)", message or "(메시지 없음)",
                            RESULT_FAILURE_KIND.get(code, am.FAILURE_TRANSPORT),
                            envelope="OpenAPI_ServiceResponse")

    #: ② 표준 봉투
    response = data.get("response")
    if not isinstance(response, Mapping):
        raise DataGoKrError("10", "응답에 response 도 OpenAPI_ServiceResponse 도 없습니다.",
                            am.FAILURE_SCHEMA_DRIFT)
    header = response.get("header")
    header = header if isinstance(header, Mapping) else {}
    code = str(header.get("resultCode") or "").strip()
    message = str(header.get("resultMsg") or "").strip()
    if code == RESULT_NO_DATA:
        raise NoDataFromSource(f"공공데이터포털에 해당 조건의 자료가 없습니다: {message or code}")
    if code and code != RESULT_OK:
        raise DataGoKrError(code, message or "(메시지 없음)",
                            RESULT_FAILURE_KIND.get(code, am.FAILURE_TRANSPORT))

    body = response.get("body")
    body = body if isinstance(body, Mapping) else {}
    raw_items = body.get("items")
    #: ★★★ 1건이면 `item` 이 **배열이 아니라 객체**다(XML→JSON 변환의 고전적 함정).
    #:   배열만 기대하면 마지막 1건이 조용히 사라진다.
    if isinstance(raw_items, Mapping):
        inner = raw_items.get("item")
    elif isinstance(raw_items, list):
        inner = raw_items
    else:
        inner = []                      # `items` 가 빈 문자열로 오는 경우가 있다
    if isinstance(inner, Mapping):
        inner = [inner]
    if not isinstance(inner, list):
        inner = []

    def _int(key: str, default: int = 0) -> int:
        try:
            return int(body.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    return {"items": [x for x in inner if isinstance(x, Mapping)],
            "page": _int("pageNo", 1), "rows": _int("numOfRows", DEFAULT_ROWS_PER_PAGE),
            "total": _int("totalCount", 0)}


class DataGoKrService(B.Provider):
    """공공데이터포털 서비스 하나의 기반. **등록되지 않는다** — 하위 클래스가 등록된다.

    ⚠️ `FIELDS` 를 선언하지 않은 하위 클래스는 만들 수 없다. 기본 구현을 주면 새 서비스가
      그것을 물려받아 「대충 돌아가는」 상태가 되고, 그것이 지시 4 가 금지한 느슨한 파서다."""

    #: 하위 클래스가 반드시 채운다.
    ENDPOINT: str = ""
    #: 원천 필드 → 우리 이름. **서비스마다 다르다.**
    FIELDS: Dict[str, str] = {}
    #: 이 서비스의 지표 코드와 축.
    INDICATOR_CODE: str = ""
    TARGET_REF_FIELD: str = ""
    UNIT_LITERAL: str = ""
    #: ⚠️ 엔드포인트·필드가 실측으로 확인됐는가.
    SERVICE_VERIFIED: bool = False
    #: 이 서비스가 다루는 지표 이름들(닫힌 목록).
    ALIASES: Tuple[str, ...] = ()

    def __init__(self, **kwargs):
        if not self.ENDPOINT or not self.FIELDS:
            raise B.ProviderError(
                f"{type(self).__name__} 이 ENDPOINT·FIELDS 를 선언하지 않았습니다 — "
                f"서비스마다 응답 필드가 다르므로 기본 구현을 주지 않습니다.")
        super().__init__(**kwargs)

    # ── 공통 URL ───────────────────────────────────────────────────────
    def _page_url(self, *, start: str, end: str, page: int, rows: int) -> str:
        #: ⚠️ `serviceKey` 는 이미 인코딩된 값으로 발급된다 — 다시 인코딩하면 인증이
        #:   깨진다(공공데이터포털의 흔한 실수). 그대로 넣는다.
        return (f"{BASE}{self.ENDPOINT}?serviceKey={self.credential()}"
                f"&_type=json&pageNo={int(page)}&numOfRows={int(rows)}"
                f"&startDt={start}&endDt={end}")

    # ── ② 탐색 ─────────────────────────────────────────────────────────
    def discover(self, request: B.AcquisitionRequest) -> List[B.DiscoveryCandidate]:
        wanted = [str(x or "").strip().lower() for x in request.indicators if str(x or "").strip()]
        keys = tuple(a.lower() for a in self.ALIASES)
        if not any(any(k in w or w in k for k in keys) for w in wanted):
            return []
        start, end = _period(request)
        if not start:
            raise B.ProviderError("기간(연도)이 필요합니다 — 이 서비스는 기간 없이 조회하지 않습니다.")
        #: ★ 자격증명을 **여기서** 확인한다. 앞의 셋은 탐색이 네트워크를 타서 저절로 일찍
        #:   실패했지만, 이 서비스의 탐색은 순수해서 후보를 만들어 놓고 dry-run 에서야
        #:   실패한다 — 사람은 「찾았는데 왜 안 되지」를 두 단계 뒤에 본다(실측).
        self.credential()
        desc = self.describe()
        return [B.DiscoveryCandidate(
            provider_id=desc.provider_id,
            dataset_ref=f"{desc.provider_id}:{start}:{end}",
            title=desc.name, target_contract_key=desc.target_contract_keys[0],
            period_from=start, period_to=end, frequency="daily",
            unit=self.UNIT_LITERAL,
            match_reason=(f"요청 지표가 이 서비스의 지표({', '.join(self.ALIASES[:3])})와 "
                          f"맞습니다."
                          + ("" if self.SERVICE_VERIFIED else
                             " ⚠️ 엔드포인트·필드가 아직 실측으로 확인되지 않았습니다.")),
            params={"start": start, "end": end, "page": 1,
                    "rows": DEFAULT_ROWS_PER_PAGE,
                    "indicator_code": self.INDICATOR_CODE})]

    # ── ③ 미리보기 · ④ 수집 ────────────────────────────────────────────
    def preview(self, candidate: B.DiscoveryCandidate) -> B.FetchResult:
        return self._fetch_page(candidate, page=1, rows=10)

    def fetch(self, candidate: B.DiscoveryCandidate, *,
              checkpoint: Optional[B.Checkpoint] = None,
              page: int = 0) -> B.FetchResult:
        """★★★ **한 쪽만** 받는다. 다음 쪽이 있으면 `has_more` 로 알린다.

        ⚠️ 쪽을 합쳐 하나의 「원문」으로 만들지 않는다 — 그러면 보관된 원문이 원천이
          보낸 것이 아니게 되고 「원천이 이렇게 말했다」가 거짓이 된다."""
        p = dict(candidate.params or {})
        for field in ("start", "end"):
            if not str(p.get(field, "")).strip():
                raise B.ProviderError(f"후보에 {field} 가 없습니다 — discover 를 먼저 부르십시오.")
        want = int(page or p.get("page") or 1)
        rows = int(p.get("rows") or DEFAULT_ROWS_PER_PAGE)
        url = self._page_url(start=str(p["start"]), end=str(p["end"]), page=want, rows=rows)
        response = self._get(url)
        env = read_envelope(bytes(response.get("body") or b""))
        #: 쪽 정보는 **응답이 말한 값**을 쓴다 — 우리가 보낸 값이 아니다.
        got_page, got_rows, total = env["page"], env["rows"], env["total"]
        seen = got_page * got_rows
        has_more = bool(total and seen < total and got_page < MAX_PAGES)
        return self._fetch_result(
            dataset_ref=candidate.dataset_ref, response=response, requested_url=url,
            page=got_page, has_more=has_more,
            next_cursor=str(got_page + 1) if has_more else "")

    def _fetch_page(self, candidate: B.DiscoveryCandidate, *, page: int,
                    rows: int) -> B.FetchResult:
        p = dict(candidate.params or {})
        url = self._page_url(start=str(p.get("start") or ""), end=str(p.get("end") or ""),
                             page=page, rows=rows)
        response = self._get(url)
        read_envelope(bytes(response.get("body") or b""))
        return self._fetch_result(dataset_ref=candidate.dataset_ref, response=response,
                                  requested_url=url, page=page)

    # ── ⑤ 정규화 — 순수 ────────────────────────────────────────────────
    def normalize(self, result: B.FetchResult) -> B.NormalizedBatch:
        """서비스가 선언한 `FIELDS` 로만 옮긴다. **기본 구현이 없다.**"""
        env = read_envelope(result.payload)
        items = env["items"]
        desc = self.describe()
        contract_key = desc.target_contract_keys[0]

        date_field = self.FIELDS["period"]
        value_field = self.FIELDS["value"]
        rows: List[Dict[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        for i, item in enumerate(items):
            excerpt = json.dumps(item, ensure_ascii=False)[:100]
            observed = normalise_date(item.get(date_field))
            if not observed:
                rejected.append(B.RejectedRow(i, "시점을 읽지 못함",
                                              f"{date_field}={item.get(date_field)!r}",
                                              raw_excerpt=excerpt))
                continue
            value = parse_value(item.get(value_field))
            if value is None:
                rejected.append(B.RejectedRow(i, "값을 숫자로 읽지 못함",
                                              f"{value_field}={item.get(value_field)!r}",
                                              raw_excerpt=excerpt))
                continue
            target_ref = (str(item.get(self.TARGET_REF_FIELD) or "")
                          if self.TARGET_REF_FIELD else desc.name)
            rows.append({
                "observation_id": f"{desc.provider_id}:{target_ref}:{observed}",
                "indicator_code": self.INDICATOR_CODE,
                "org_id": desc.provider_id,
                "tbl_id": self.ENDPOINT.rsplit("/", 1)[-1],
                "target_ref": target_ref,
                "category_code": target_ref,
                "observed_at": observed,
                #: 이 포털도 발표일을 주지 않는다 — **지어내지 않고 비운다.**
                "published_at": "",
                "vintage_date": observed,
                "value": value,
                "unit": self.UNIT_LITERAL,
                "cycle": "D",
            })
        seen = sorted({k for it in items for k in it})
        return B.NormalizedBatch(provider_id=desc.provider_id, contract_key=contract_key,
                                 rows=tuple(rows), rejected=tuple(rejected),
                                 source_row_count=len(items), source_fields=tuple(seen))

    # ── ⑥ 검증 — 순수 ──────────────────────────────────────────────────
    def validate(self, batch: B.NormalizedBatch) -> B.ValidationReport:
        rows = list(batch.rows)
        checks: List[B.CheckResult] = [
            B.CheckResult("행 정산", batch.accounted,
                          f"원문 {batch.source_row_count} = 적재 {len(rows)} + "
                          f"제외 {len(batch.rejected)}", count=batch.source_row_count,
                          failure_kind="" if batch.accounted else am.FAILURE_RECONCILIATION),
            B.CheckResult("자료 있음", bool(rows), f"{len(rows)}행", count=len(rows),
                          failure_kind="" if rows else am.FAILURE_QUALITY),
        ]
        targets = {r.get("target_ref") for r in rows if r.get("target_ref")}
        checks.append(B.CheckResult(
            "대상 단일", len(targets) <= 1, f"발견된 대상: {sorted(targets)}",
            count=len(targets),
            failure_kind="" if len(targets) <= 1 else am.FAILURE_QUALITY))

        times = [r.get("observed_at") for r in rows]
        duplicates = len(times) - len(set(times))
        checks.append(B.CheckResult(
            "시점 중복 없음", duplicates == 0, f"같은 시점이 {duplicates}건 겹칩니다.",
            count=duplicates,
            failure_kind="" if duplicates == 0 else am.FAILURE_QUALITY))

        checks.append(B.CheckResult(
            "발표일 없음(정상)", True,
            "이 포털은 발표일을 제공하지 않습니다 — 지어내지 않고 비웠습니다.", count=len(rows)))

        #: ⚠️ 실측 미확인을 **보고서에 싣되 막지 않는다**(KOSIS 에서 배운 것).
        checks.append(B.CheckResult(
            "엔드포인트·필드 실측 여부", True,
            ("실측으로 확인됨" if self.SERVICE_VERIFIED else
             "⚠️ 아직 실제 응답으로 확인하지 못했습니다 — 실제 키로 한 번 돌린 뒤 "
             "ENDPOINT·FIELDS 를 갱신하고 SERVICE_VERIFIED 를 켜십시오."),
            count=len(self.FIELDS)))
        return B.ValidationReport(checks=tuple(checks))

    # ── ⑦ 이어받기 · ⑧ 갱신 — 순수 ────────────────────────────────────
    def checkpoint(self, batch: B.NormalizedBatch, *,
                   previous: Optional[B.Checkpoint] = None) -> B.Checkpoint:
        times = sorted({str(r.get("observed_at") or "") for r in batch.rows} - {""})
        return B.Checkpoint(
            provider_id=self.describe().provider_id,
            dataset_ref=self.describe().provider_id,
            cursor=(times[-1].replace("-", "") if times
                    else (previous.cursor if previous else "")),
            covered_from=times[0] if times else "",
            covered_to=times[-1] if times else "",
            last_success_at=times[-1] if times else "")

    def refresh(self, checkpoint: B.Checkpoint, *, until: str = "") -> List[B.DiscoveryCandidate]:
        cursor = str(checkpoint.cursor or "")
        if not cursor or len(cursor) < 8:
            return []
        from datetime import date, timedelta
        try:
            nxt = (date(int(cursor[:4]), int(cursor[4:6]), int(cursor[6:8]))
                   + timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            return []
        if nxt == cursor:
            return []
        desc = self.describe()
        end = str(until or "").strip() or f"{int(nxt[:4]) + 1}1231"
        return [B.DiscoveryCandidate(
            provider_id=desc.provider_id, dataset_ref=f"{desc.provider_id}:{nxt}:{end}",
            title=f"{desc.name} — {nxt} 이후",
            target_contract_key=desc.target_contract_keys[0],
            period_from=nxt, period_to=end, frequency="daily",
            match_reason=f"직전 수집이 {checkpoint.covered_to} 까지였습니다.",
            params={"start": nxt, "end": end, "page": 1, "rows": DEFAULT_ROWS_PER_PAGE,
                    "indicator_code": self.INDICATOR_CODE})]


# ── 서비스 하나 = Provider 하나 = 등급 하나 ─────────────────────────────────
@provider_registry.register
class KpxSmpProvider(DataGoKrService):
    """전력거래소 계통한계가격(SMP).

    ⚠️ 설계서 §4.3 — **SMP 는 전기요금 청구서·계약요금의 대체값이 아니다.** 전력시장
      변동성의 보조 동인이고, 그래서 등급이 `silver` 다(ECOS·KOSIS 는 `gold`)."""

    ENDPOINT = "/B552115/Smp/getSmp"
    FIELDS = {"period": "baseDt", "value": "smp"}
    INDICATOR_CODE = "KPX_SMP"
    TARGET_REF_FIELD = "areaNm"
    UNIT_LITERAL = "KRW/kWh"
    SERVICE_VERIFIED = False
    ALIASES = ("smp", "계통한계가격", "전력가격", "전력단가", "전력")

    descriptor = B.ProviderDescriptor(
        provider_id="KPX_SMP",
        name="전력거래소 계통한계가격(SMP)",
        publisher="한국전력거래소 (공공데이터포털)",
        source_type="API",
        allowed_hosts=("apis.data.go.kr",),
        license_url="https://www.data.go.kr/",
        allowed_usage="공표 자료의 내부 분석·저장. 출처 표시가 필요합니다.",
        redistribution_allowed=False,
        requires_credential=True,
        credential_env="AFS_DATA_GO_KR_SERVICE_KEY",
        cost="무료(활용신청 · 일 호출 한도 있음)",
        #: ★★★ 설계서 §4.2 가 지정한 등급. 포털을 한 Provider 로 뭉쳤으면 이 구분이 사라진다.
        default_trust_grade="silver",
        refresh_frequency="일별",
        coverage_note="계통한계가격(SMP) 일별 시계열. 지역(육지·제주)별로 갈립니다.",
        target_contract_keys=("EXT-03",),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        known_limits=(
            "SMP 는 전기요금 청구서·계약요금의 대체값이 아닙니다 — 실제 공장 전력비가 아닙니다.",
            "전력시장 변동성의 **보조 동인**이며 기준 계획의 근거가 아닙니다(등급 silver).",
            "지역(육지·제주)이 갈립니다 — 섞으면 다른 시장이 한 지표로 뭉칩니다.",
            "엔드포인트·응답 필드가 아직 실측으로 확인되지 않았습니다.",
        ),
    )


# ── 보조 ─────────────────────────────────────────────────────────────────────
def _period(request: B.AcquisitionRequest) -> Tuple[str, str]:
    def _y(v: str) -> str:
        m = re.search(r"(\d{4})", str(v or ""))
        return m.group(1) if m else ""

    a, b = _y(request.period_from), _y(request.period_to)
    if not a and not b:
        return "", ""
    a = a or b
    b = b or a
    if b < a:
        a, b = b, a
    return f"{a}0101", f"{b}1231"
