"""[DAO-13] 국가통계포털 KOSIS Provider — 제조업 생산·출하·재고·가동률.

## 앞의 둘과 또 다른 점 셋 — 그래서 세 번째 명시적 변환기다

★★★ ① **성공 응답이 객체가 아니라 «배열»이다.** 오류일 때만 객체(`{"err": ...}`)로 온다.
  DART 는 `{"status": ...}`, ECOS 는 `{"StatisticSearch": {...}}` 였다. 셋 다 다르다 —
  「어떤 JSON 이든 대충 읽는」 파서를 만들면 이 셋을 구분하지 못한다(지시 4).

★★★ ② **「자료 없음」이 코드가 아니라 «모양»으로 온다.** 빈 배열 `[]` 이다.
  DART 는 `status=013`, ECOS 는 `INFO-200` 이었다. 코드 표만 보는 판정기는 이것을 놓치고
  **0건을 적재 성공으로 읽는다.**

★★★ ③ **분류 축이 있다.** 한 통계표의 행이 `C1`(산업분류) 같은 축으로 갈린다 —
  「제조업 생산지수」와 「광업 생산지수」가 같은 표에 있다. 축을 무시하고 합치면
  **서로 다른 계열이 한 지표로 뭉친다.** `EXT-03.target_ref` 가 그 축을 담는다.

## ⚠️ 오류 코드 표는 «실측으로 확인해야» 한다

DART·ECOS 와 달리 KOSIS 오류 코드는 이 저장소에서 아직 실제 응답으로 확인하지 못했다.
그래서 **표에 없는 코드는 `TRANSPORT`(재시도 가능)로 떨어뜨리고**, 그 사실을 여기 적는다.
⚠️ 모르는 코드를 성공으로 접지 않는 것이 중요하다 — 그러면 오류 본문이 계약 모양으로
  옮겨진다. 시험이 「모르는 코드가 성공이 되지 않는지」를 센다.

★ 다행히 **「자료 없음」 판정은 코드에 기대지 않는다**(빈 배열). 코드 표가 틀려도 그
  가장 중요한 갈래는 정확하다.

## 목적지 — `EXT-03`, 다만 한 곳이 비어 있다

라우팅표가 `industry_indicator → EXT-03` 이다. 그런데 키트의 `EXT-03` 에는 형제 계약
(`EXT-01`)에 있는 **`vintage_date` 가 없다.** 그것이 없으면 「그 계획이 당시 어떤 발표값을
썼는가」에 답할 수 없다(§12.5). 그래서 `ext03_public_proposal()` 이 그 열을 **더한다.**
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import provider_registry

CONTRACT_KEY = "EXT-03"
BASE = "https://kosis.kr/openapi"

#: ⚠️⚠️ **실측 미확인 표.** 아래는 공개 문서를 근거로 적었으나 이 저장소가 실제 응답으로
#:   확인하지 못했다. 표에 없는 코드는 `TRANSPORT` 로 떨어진다 — 모르는 코드를 성공으로
#:   접으면 오류 본문이 계약 모양으로 옮겨진다.
#:   ★ 실제 키로 한 번 돌린 뒤 이 표를 갱신할 것.
ERROR_FAILURE_KIND: Dict[str, str] = {
    "20": am.FAILURE_AUTH,        # 서비스 인증 실패
    "21": am.FAILURE_AUTH,        # 일시적으로 사용할 수 없는 키
    "22": am.FAILURE_TRANSPORT,   # 요청 제한 횟수 초과
    "30": am.FAILURE_AUTH,        # 등록되지 않은 서비스키
    "31": am.FAILURE_AUTH,        # 기한만료 서비스키
    "32": am.FAILURE_POLICY,      # 등록되지 않은 IP
    "100": am.FAILURE_SCHEMA_DRIFT,   # 필수 요청변수 누락
    "101": am.FAILURE_SCHEMA_DRIFT,   # 부적절한 요청변수
    "500": am.FAILURE_TRANSPORT,      # 서버 오류
}
ERROR_TABLE_VERIFIED = False      # ★ 실측 후 True 로 바꾸고 표를 갱신한다

#: 다룰 통계표. **닫힌 목록**이다.
#:   ⚠️ 분류 축(`C1`)의 코드는 상수로 박지 않는다 — 표마다 다르고 바뀐다. 이름(`C1_NM`)
#:     으로 고르되 **고르지 못하면 모호함을 알린다.**
TABLES: Dict[str, Dict[str, Any]] = {
    "101:DT_1F31502": {
        "label": "광업제조업동향조사 — 생산지수", "kind": "industry_indicator",
        "indicator_code": "MFG_PRODUCTION_INDEX", "cycle": "M",
        "category_hint": "제조업",
        "aliases": ("생산지수", "제조업 생산", "광공업 생산", "production index",
                    "산업생산", "가동률"),
        "limits": ("산업 전체 지수는 **우리 공장의 가동률이 아닙니다** — "
                   "업종 경기의 기준선으로만 씁니다.",),
    },
    "101:DT_1F31503": {
        "label": "광업제조업동향조사 — 재고지수", "kind": "industry_indicator",
        "indicator_code": "MFG_INVENTORY_INDEX", "cycle": "M",
        "category_hint": "제조업",
        "aliases": ("재고지수", "재고", "inventory index"),
        "limits": ("산업 재고지수는 **우리 재고가 아닙니다** — 시장 수급의 보조 지표입니다.",),
    },
}

_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_PRD_SHAPES = (
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "{0}-{1}-{2}"),
    (re.compile(r"^(\d{4})(\d{2})$"), "{0}-{1}"),
    (re.compile(r"^(\d{4})$"), "{0}"),
)


class NoDataFromSource(B.ProviderError):
    """★★★ KOSIS 가 **빈 배열**을 줬다 — 정상 응답이고 해당 자료가 없다."""


class KosisErrorResponse(B.ProviderError):
    """KOSIS 가 오류 객체를 돌려줬다. `failure_kind` 로 어느 상태로 갈지 정한다."""

    def __init__(self, code: str, message: str, failure_kind: str):
        super().__init__(f"KOSIS err={code}: {message}")
        self.code = code
        self.failure_kind = failure_kind


def normalise_period(raw: str) -> str:
    """`PRD_DE` 를 읽을 수 있는 날짜로. **모르는 모양이면 빈 문자열** — 지어내지 않는다."""
    text = str(raw or "").strip()
    for pattern, template in _PRD_SHAPES:
        m = pattern.match(text)
        if m:
            return template.format(*m.groups())
    return ""


def parse_value(raw: Any) -> Optional[float]:
    """숫자로 읽는다. **읽지 못하면 `None`** — 0 으로 만들지 않는다.

    ⚠️ 지수를 0 으로 채우면 「생산이 멈췄다」로 읽힌다."""
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if not text or not _NUM.match(text):
        return None
    return float(text)


def load_rows(payload: bytes) -> List[Dict[str, Any]]:
    """★★★ KOSIS 의 응답 모양을 **명시적으로** 가른다.

        배열       → 자료(빈 배열이면 「자료 없음」)
        객체+err   → 오류
        그 밖      → 스키마 표류

    ⚠️ 「배열이면 성공」만 보면 빈 배열이 **0건 적재 성공**이 된다."""
    try:
        data = json.loads(bytes(payload or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KosisErrorResponse("100", f"응답을 JSON 으로 읽지 못했습니다: {exc}",
                                 am.FAILURE_SCHEMA_DRIFT) from exc

    if isinstance(data, Mapping):
        code = str(data.get("err") or "").strip()
        message = str(data.get("errMsg") or "").strip()
        if code:
            raise KosisErrorResponse(code, message or "(메시지 없음)",
                                     ERROR_FAILURE_KIND.get(code, am.FAILURE_TRANSPORT))
        raise KosisErrorResponse("100", "응답이 배열도 오류 객체도 아닙니다.",
                                 am.FAILURE_SCHEMA_DRIFT)

    if not isinstance(data, list):
        raise KosisErrorResponse("100", f"응답 최상위가 배열이 아닙니다: {type(data).__name__}",
                                 am.FAILURE_SCHEMA_DRIFT)
    if not data:
        #: ★★★ 코드가 아니라 **모양**으로 오는 「자료 없음」.
        raise NoDataFromSource("KOSIS 에 해당 조건의 자료가 없습니다(빈 배열).")
    return [r for r in data if isinstance(r, dict)]


def match_tables(indicators: Sequence[str]) -> List[Tuple[str, Dict[str, Any]]]:
    """요청한 지표 이름을 통계표로. **닫힌 목록 안에서만** 고른다."""
    wanted = [str(x or "").strip().lower() for x in indicators if str(x or "").strip()]
    out: List[Tuple[str, Dict[str, Any]]] = []
    for ref, meta in TABLES.items():
        keys = tuple(a.lower() for a in meta["aliases"]) + (meta["label"].lower(),)
        if any(any(k in w or w in k for k in keys) for w in wanted):
            out.append((ref, meta))
    return out


@provider_registry.register
class KosisProvider(B.Provider):
    """국가통계포털 KOSIS."""

    descriptor = B.ProviderDescriptor(
        provider_id="KOSIS",
        name="국가통계포털 KOSIS",
        publisher="통계청",
        source_type="API",
        allowed_hosts=("kosis.kr",),
        license_url="https://kosis.kr/openapi/",
        allowed_usage="공표 통계의 내부 분석·저장. 출처 표시가 필요합니다.",
        redistribution_allowed=False,
        requires_credential=True,
        credential_env="AFS_KOSIS_API_KEY",
        cost="무료(인증키 신청 · 일 호출 한도 있음)",
        default_trust_grade="gold",
        refresh_frequency="통계표별 공표 주기(광업제조업동향조사는 월별)",
        coverage_note="제조업 생산·출하·재고 지수. 기관·통계표·분류축으로 조회합니다.",
        target_contract_keys=(CONTRACT_KEY,),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        known_limits=(
            "산업 전체 지수는 우리 공장의 가동률·재고가 아닙니다 — 업종 경기의 기준선입니다.",
            "한 통계표에 분류축(산업분류 등)이 여럿입니다 — 축을 섞으면 다른 계열이 뭉칩니다.",
            "오류 코드 표가 아직 실측으로 확인되지 않았습니다 — 모르는 코드는 재시도 대상으로 둡니다.",
        ),
    )

    # ── ② 탐색 ─────────────────────────────────────────────────────────
    def discover(self, request: B.AcquisitionRequest) -> List[B.DiscoveryCandidate]:
        matches = match_tables(request.indicators)
        if not matches:
            return []
        years = _years(request)
        if not years:
            raise B.ProviderError("기간(연도)이 필요합니다 — KOSIS 는 기간 없이 조회하지 않습니다.")

        out: List[B.DiscoveryCandidate] = []
        for ref, meta in matches:
            org_id, tbl_id = ref.split(":", 1)
            cycle = str(meta["cycle"]).upper()
            start, end = _period(years, cycle)
            #: ★ 분류축은 **첫 응답에서 확인**한다 — 코드를 상수로 박지 않는다.
            #:   탐색 단계에서 한 달치만 받아 어떤 축이 있는지 본다.
            categories = self._categories(org_id, tbl_id, cycle, start)
            hint = str(meta["category_hint"])
            chosen = next((c for c in categories if hint in c["name"]),
                          categories[0] if categories else None)
            if chosen is None:
                continue
            others = tuple(f"{c['name']}({c['code']})" for c in categories
                           if c["code"] != chosen["code"])[:6]
            out.append(B.DiscoveryCandidate(
                provider_id=self.descriptor.provider_id,
                dataset_ref=f"{org_id}:{tbl_id}:{chosen['code']}:{cycle}:{start}:{end}",
                title=f"{meta['label']} — {chosen['name']}",
                target_contract_key=CONTRACT_KEY,
                period_from=start, period_to=end, frequency=_frequency(cycle),
                unit=str(chosen.get("unit") or ""),
                match_reason=(f"요청 지표가 통계표 {tbl_id}({meta['label']}) 와 맞고, "
                              f"분류축은 첫 응답에서 '{chosen['name']}' 을 골랐습니다"
                              f"(코드는 조회 시점에 확인했습니다)."),
                params={"org_id": org_id, "tbl_id": tbl_id, "category": chosen["code"],
                        "category_name": chosen["name"], "cycle": cycle,
                        "start": start, "end": end,
                        "indicator_code": meta["indicator_code"],
                        "unit": str(chosen.get("unit") or "")},
                ambiguous_with=others))
        return out

    def _categories(self, org_id: str, tbl_id: str, cycle: str,
                    probe_period: str) -> List[Dict[str, str]]:
        """분류축을 **물어본다.** ⚠️ 상수로 박으면 통계청이 분류를 개편한 날 다른 계열을 받는다."""
        url = self._url(org_id=org_id, tbl_id=tbl_id, cycle=cycle,
                        start=probe_period, end=probe_period, category="ALL")
        try:
            rows = load_rows(bytes(self._get(url).get("body") or b""))
        except NoDataFromSource:
            return []
        seen: Dict[str, Dict[str, str]] = {}
        for r in rows:
            code = str(r.get("C1") or "").strip()
            if code and code not in seen:
                seen[code] = {"code": code, "name": str(r.get("C1_NM") or "").strip(),
                              "unit": str(r.get("UNIT_NM") or "").strip()}
        return list(seen.values())

    def _url(self, *, org_id: str, tbl_id: str, cycle: str, start: str, end: str,
             category: str) -> str:
        return (f"{BASE}/Param/statisticsParameterData.do?method=getList"
                f"&apiKey={self.credential()}&format=json&jsonVD=Y"
                f"&orgId={org_id}&tblId={tbl_id}&objL1={category}&itmId=ALL"
                f"&prdSe={cycle}&startPrdDe={start}&endPrdDe={end}")

    # ── ③ 미리보기 · ④ 수집 ────────────────────────────────────────────
    def preview(self, candidate: B.DiscoveryCandidate) -> B.FetchResult:
        return self.fetch(candidate)

    def fetch(self, candidate: B.DiscoveryCandidate, *,
              checkpoint: Optional[B.Checkpoint] = None) -> B.FetchResult:
        p = dict(candidate.params or {})
        for field in ("org_id", "tbl_id", "category", "cycle", "start", "end"):
            if not str(p.get(field, "")).strip():
                raise B.ProviderError(f"후보에 {field} 가 없습니다 — discover 를 먼저 부르십시오.")
        start = str(p["start"])
        if checkpoint and checkpoint.cursor:
            start = _next_period(str(checkpoint.cursor), str(p["cycle"]))
        url = self._url(org_id=p["org_id"], tbl_id=p["tbl_id"], cycle=p["cycle"],
                        start=start, end=str(p["end"]), category=str(p["category"]))
        response = self._get(url)
        load_rows(bytes(response.get("body") or b""))     # 상태를 여기서 한 번 본다
        return self._fetch_result(dataset_ref=candidate.dataset_ref, response=response,
                                  requested_url=url)

    # ── ⑤ 정규화 — 순수 ────────────────────────────────────────────────
    def normalize(self, result: B.FetchResult) -> B.NormalizedBatch:
        """KOSIS 배열을 `EXT-03` 모양으로. **세 번째 명시적 변환기다.**"""
        rows_in = load_rows(result.payload)
        parts = _dataset_parts(result.dataset_ref)
        meta = TABLES.get(f"{parts.get('org_id')}:{parts.get('tbl_id')}", {})
        indicator = str(meta.get("indicator_code") or parts.get("tbl_id") or "")
        want_category = str(parts.get("category") or "")

        rows: List[Dict[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        for i, item in enumerate(rows_in):
            excerpt = json.dumps(item, ensure_ascii=False)[:100]
            category = str(item.get("C1") or "").strip()
            if want_category and category and category != want_category:
                #: ★★★ 축이 다르면 **버린다.** 섞으면 서로 다른 계열이 한 지표로 뭉친다.
                rejected.append(B.RejectedRow(
                    i, "분류축 불일치", f"요청 {want_category} · 행 {category}",
                    raw_excerpt=excerpt))
                continue
            observed = normalise_period(item.get("PRD_DE"))
            if not observed:
                rejected.append(B.RejectedRow(i, "시점을 읽지 못함",
                                              f"PRD_DE={item.get('PRD_DE')!r}",
                                              raw_excerpt=excerpt))
                continue
            value = parse_value(item.get("DT"))
            if value is None:
                rejected.append(B.RejectedRow(i, "값을 숫자로 읽지 못함",
                                              f"DT={item.get('DT')!r}", raw_excerpt=excerpt))
                continue
            rows.append({
                "observation_id": f"{parts.get('org_id')}:{parts.get('tbl_id')}:"
                                  f"{category}:{str(item.get('ITM_ID') or '')}:{observed}",
                "indicator_code": indicator,
                "org_id": str(parts.get("org_id") or ""),
                "tbl_id": str(parts.get("tbl_id") or ""),
                #: ★ 분류축을 계약의 `target_ref` 에 담는다 — 「무엇에 대한 지표인가」.
                "target_ref": str(item.get("C1_NM") or parts.get("category") or ""),
                "category_code": category,
                "item_code": str(item.get("ITM_ID") or ""),
                "item_name": str(item.get("ITM_NM") or ""),
                "observed_at": observed,
                #: ⚠️ KOSIS 도 발표일을 주지 않는다 — **지어내지 않고 비운다.**
                "published_at": "",
                "vintage_date": observed,
                "value": value,
                "unit": str(item.get("UNIT_NM") or parts.get("unit") or ""),
                "cycle": str(parts.get("cycle") or ""),
            })
        seen = sorted({k for it in rows_in for k in it})
        return B.NormalizedBatch(provider_id=self.descriptor.provider_id,
                                 contract_key=CONTRACT_KEY, rows=tuple(rows),
                                 rejected=tuple(rejected), source_row_count=len(rows_in),
                                 source_fields=tuple(seen))

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

        #: ★★★ 분류축이 섞이면 서로 다른 계열이 한 지표로 뭉친다.
        targets = {r.get("target_ref") for r in rows if r.get("target_ref")}
        checks.append(B.CheckResult(
            "분류축 단일", len(targets) <= 1, f"발견된 축: {sorted(targets)}",
            count=len(targets),
            failure_kind="" if len(targets) <= 1 else am.FAILURE_QUALITY))

        units = {r.get("unit") for r in rows if r.get("unit")}
        checks.append(B.CheckResult(
            "단위 단일", len(units) <= 1, f"발견된 단위: {sorted(units)}", count=len(units),
            failure_kind="" if len(units) <= 1 else am.FAILURE_QUALITY))

        times = [r.get("observed_at") for r in rows]
        duplicates = len(times) - len(set(times))
        checks.append(B.CheckResult(
            "시점 중복 없음", duplicates == 0, f"같은 시점이 {duplicates}건 겹칩니다.",
            count=duplicates,
            failure_kind="" if duplicates == 0 else am.FAILURE_QUALITY))

        checks.append(B.CheckResult(
            "발표일 없음(정상)", True,
            "KOSIS 는 발표일을 제공하지 않습니다 — 지어내지 않고 비웠습니다. "
            "vintage 는 관측 시점을 씁니다.", count=len(rows)))

        #: ⚠️ 오류 코드 표가 실측 미확인이라는 사실을 **보고서에 싣되 막지는 않는다.**
        #:
        #: ⚠️⚠️ 처음에 이것을 `ok=ERROR_TABLE_VERIFIED` 로 만들어 **매번 실패**하게 했다.
        #:   그러면 정상 자료가 늘 격리되고, 자동 적용은 영원히 막힌다. **항상 걸리는 검사는
        #:   아무도 안 보게 되거나 영구 차단기가 된다** — 둘 다 나쁘다.
        #:   코드표가 미확인이라는 것은 **자료 품질 문제가 아니라 주의사항**이고, 실제 위험
        #:   (모르는 코드를 성공으로 읽는 것)은 `load_rows` 가 이미 막는다.
        checks.append(B.CheckResult(
            "오류코드표 실측 여부", True,
            ("실측으로 확인됨" if ERROR_TABLE_VERIFIED else
             "⚠️ 아직 실제 응답으로 확인하지 못했습니다 — 모르는 코드는 재시도 대상(TRANSPORT)으로 "
             "떨어집니다. 실제 키로 한 번 돌린 뒤 ERROR_FAILURE_KIND 를 갱신하십시오."),
            count=len(ERROR_FAILURE_KIND)))

        return B.ValidationReport(checks=tuple(checks))

    # ── ⑦ 이어받기 · ⑧ 갱신 — 순수 ────────────────────────────────────
    def checkpoint(self, batch: B.NormalizedBatch, *,
                   previous: Optional[B.Checkpoint] = None) -> B.Checkpoint:
        times = sorted({str(r.get("observed_at") or "") for r in batch.rows} - {""})
        ref = ""
        if batch.rows:
            r = batch.rows[0]
            ref = f"{r.get('org_id')}:{r.get('tbl_id')}:{r.get('category_code')}:{r.get('cycle')}"
        return B.Checkpoint(
            provider_id=self.descriptor.provider_id,
            dataset_ref=ref or (previous.dataset_ref if previous else ""),
            cursor=(times[-1].replace("-", "") if times
                    else (previous.cursor if previous else "")),
            covered_from=times[0] if times else "",
            covered_to=times[-1] if times else "",
            last_success_at=times[-1] if times else "")

    def refresh(self, checkpoint: B.Checkpoint, *, until: str = "") -> List[B.DiscoveryCandidate]:
        """다음 구간. **순수** — 시계를 읽지 않는다."""
        bits = str(checkpoint.dataset_ref or "").split(":")
        if len(bits) != 4 or not bits[0]:
            return []
        org_id, tbl_id, category, cycle = bits
        cursor = str(checkpoint.cursor or "")
        if not cursor:
            return []
        start = _next_period(cursor, cycle)
        if start == cursor:
            return []
        meta = TABLES.get(f"{org_id}:{tbl_id}", {})
        end = str(until or "").strip() or _period_end(start, cycle)
        return [B.DiscoveryCandidate(
            provider_id=self.descriptor.provider_id,
            dataset_ref=f"{org_id}:{tbl_id}:{category}:{cycle}:{start}:{end}",
            title=f"{meta.get('label', tbl_id)} — {start} 이후",
            target_contract_key=CONTRACT_KEY,
            period_from=start, period_to=end, frequency=_frequency(cycle),
            match_reason=f"직전 수집이 {checkpoint.covered_to} 까지였습니다.",
            params={"org_id": org_id, "tbl_id": tbl_id, "category": category,
                    "cycle": cycle, "start": start, "end": end,
                    "indicator_code": meta.get("indicator_code", tbl_id)})]


# ── 보조 ─────────────────────────────────────────────────────────────────────
_PERIOD_SHAPE = {"D": ("{0}0101", "{0}1231"), "M": ("{0}01", "{0}12"),
                 "Q": ("{0}Q1", "{0}Q4"), "H": ("{0}01", "{0}02"),
                 "Y": ("{0}", "{0}"), "A": ("{0}", "{0}")}


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


def _period(years: Tuple[str, str], cycle: str) -> Tuple[str, str]:
    start_fmt, end_fmt = _PERIOD_SHAPE.get(str(cycle or "M").upper(), _PERIOD_SHAPE["M"])
    return start_fmt.format(years[0]), end_fmt.format(years[1])


def _frequency(cycle: str) -> str:
    return {"D": "daily", "M": "monthly", "Q": "quarterly", "H": "half-yearly",
            "Y": "annual", "A": "annual"}.get(str(cycle or "").upper(), "")


def _next_period(cursor: str, cycle: str) -> str:
    raw = str(cursor or "").replace("-", "")
    c = str(cycle or "M").upper()
    try:
        if c == "M" and len(raw) >= 6:
            year, month = int(raw[:4]), int(raw[4:6])
            return f"{year + 1}01" if month >= 12 else f"{year}{month + 1:02d}"
        if c in ("Y", "A"):
            return str(int(raw[:4]) + 1)
        if c == "D" and len(raw) >= 8:
            from datetime import date, timedelta
            return (date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
                    + timedelta(days=1)).strftime("%Y%m%d")
    except (TypeError, ValueError):
        return raw
    return raw


def _period_end(start: str, cycle: str) -> str:
    year = str(start)[:4]
    try:
        nxt = str(int(year) + 1)
    except ValueError:
        return start
    _, end_fmt = _PERIOD_SHAPE.get(str(cycle or "M").upper(), _PERIOD_SHAPE["M"])
    return end_fmt.format(nxt)


def _dataset_parts(dataset_ref: str) -> Dict[str, str]:
    bits = str(dataset_ref or "").split(":")
    if len(bits) != 6:
        return {}
    return {"org_id": bits[0], "tbl_id": bits[1], "category": bits[2],
            "cycle": bits[3], "start": bits[4], "end": bits[5]}
