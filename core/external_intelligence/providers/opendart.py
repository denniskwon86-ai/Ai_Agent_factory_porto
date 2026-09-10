"""[DAO-3] OpenDART Provider — 금융감독원 전자공시의 정기보고서 재무제표.

## 이 Provider 가 특히 조심하는 것 넷

★★★ ① **「자료 없음」은 장애가 아니다.** OpenDART 는 `status=013` 으로 «조회된 데이터 없음»
  을 **정상 응답**으로 준다. 이것을 예외로 던지면 스케줄러가 없는 자료를 영원히 재시도하고,
  성공으로 접으면 0건이 적재 완료로 보인다. `NoDataFromSource` 를 따로 두고 오케스트레이터가
  `NO_DATA` 상태로 옮긴다.

★★★ ② **연결(CFS)과 별도(OFS)를 섞지 않는다.** 한 회사의 같은 해 매출이 두 개 있고 뜻이
  다르다. 섞이면 합계가 조용히 부풀거나 줄고, 어느 쪽인지 나중에 알 수 없다. 후보마다
  `fs_div` 를 못 박고, 정규화가 요청한 것과 다른 `fs_div` 행을 만나면 **버린다**(사유와 함께).

★★★ ③ **정정공시는 덮어쓰지 않는다.** 같은 (회사·연도·보고서·구분)에 접수번호가 여럿이면
  나중 것이 앞의 것을 **대체(supersedes)** 한다. 앞의 판을 지우면 「그 계획이 당시 어떤
  발표값을 썼는가」에 답할 수 없다(§12.5 vintage). 그래서 지우지 않고 대체 관계만 남긴다.

★★★ ④ **미래 발표값이 과거 계획에 섞이지 않게 한다.** 접수번호 앞 8자리가 접수일자다
  (`20260315...` → 2026-03-15). 그것이 곧 `published_at` 이고, as-of 보다 나중에 발표된
  값은 그 시점 계획의 근거가 될 수 없다.

## 왜 새 데이터 계약(`PUB-01`)인가

지시 5 — 「기존 계약과 의미가 다르면 억지로 연결하지 말고 새 데이터 계약 제안으로 분리한다」.
업무키트의 `FIN-03 예산·회계실적·현금흐름` 은 **내부 회계 실적**이다. 공시 재무제표는 사실
이지만 내부 실적이 아니고, 상세 매입·고객·BOM 을 담지 않는다. 같은 그릇에 넣으면 상세 계산이
공개 총계를 내부 실적으로 읽는다.

## ⚠️ 알려진 한계 — 카드에 적어 화면까지 간다

  · 공개 재무제표는 내부 매입·고객·BOM 실적을 **대체하지 않는다.** 총계 대사에만 쓴다.
  · 계정과목(`account_id`)은 회사 계정과목이 아니다 — 매핑은 사람이 승인한다.
  · 무료 계정은 일 호출 한도가 있다. 10개년 × 분기까지 한 번에 받지 않는다.
"""
from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import provider_registry

#: 이 Provider 가 채우는 데이터 계약. 업무키트의 내부 회계 계약과 **다른 그릇**이다.
CONTRACT_KEY = "PUB-01"

BASE = "https://opendart.fss.or.kr/api"

#: 정기보고서 종류. 지금은 사업보고서(연간)만 쓴다 — 분기를 섞으면 기간이 겹친다.
REPRT_ANNUAL = "11011"
REPRT_CODES = {
    "11011": "사업보고서(연간)",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}

#: 재무제표 구분. **하나의 수집 작업은 하나만 쓴다.**
FS_CONSOLIDATED = "CFS"   # 연결
FS_SEPARATE = "OFS"       # 별도
FS_DIVS = (FS_CONSOLIDATED, FS_SEPARATE)

#: 재무제표 종류(`sj_div`).
SJ_NAMES = {"BS": "재무상태표", "IS": "손익계산서", "CIS": "포괄손익계산서",
            "CF": "현금흐름표", "SCE": "자본변동표"}

#: ★★★ OpenDART 상태코드. **`013` 만 「자료 없음」이고 나머지는 장애다.**
#:   이 표가 곧 「장애와 자료 없음의 분리」다 — 호출부가 문자열을 다시 해석하지 않는다.
STATUS_OK = "000"
STATUS_NO_DATA = "013"
STATUS_FAILURE_KIND = {
    "010": am.FAILURE_AUTH,          # 등록되지 않은 키
    "011": am.FAILURE_AUTH,          # 사용할 수 없는 키
    "012": am.FAILURE_POLICY,        # 접근할 수 없는 IP
    "014": am.FAILURE_AUTH,          # 파일이 존재하지 않음 / 권한
    "020": am.FAILURE_TRANSPORT,     # 요청 제한 초과
    "021": am.FAILURE_TRANSPORT,     # 조회 가능한 회사 개수 초과
    "100": am.FAILURE_SCHEMA_DRIFT,  # 부적절한 필드
    "101": am.FAILURE_POLICY,        # 부적절한 접근
    "800": am.FAILURE_TRANSPORT,     # 서비스 점검
    "900": am.FAILURE_TRANSPORT,     # 정의되지 않은 오류
    "901": am.FAILURE_AUTH,          # 개인정보 보유기간 만료
}

_AMOUNT_JUNK = re.compile(r"[,\s]")
_RCEPT_NO = re.compile(r"^(\d{4})(\d{2})(\d{2})\d+$")


class NoDataFromSource(B.ProviderError):
    """★★★ 원천이 **정상 응답**했고 해당 자료가 없다. 장애가 아니다 — 재시도해도 같다."""


class OpenDartStatusError(B.ProviderError):
    """OpenDART 가 오류 상태코드를 돌려줬다. `failure_kind` 로 어느 상태로 갈지 정한다."""

    def __init__(self, status: str, message: str, failure_kind: str):
        super().__init__(f"OpenDART status={status}: {message}")
        self.status = status
        self.failure_kind = failure_kind


def published_at_from_rcept_no(rcept_no: str) -> str:
    """접수번호 앞 8자리가 접수일자다. **이것이 발표일이고 vintage 의 근거다.**

    ⚠️ 발표일을 「받은 날」로 채우면 §12.5 의 재현성이 조용히 깨진다 — 같은 값을 언제
      받았는지는 우리 사정이고, 원천이 언제 발표했는지가 근거다."""
    m = _RCEPT_NO.match(str(rcept_no or "").strip())
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def parse_amount(text: Any) -> Optional[float]:
    """금액 문자열을 수로. **읽지 못하면 `None`** — 0 으로 만들지 않는다.

    ⚠️ 0 으로 채우면 지표가 「값이 0」으로 보이고, 그것은 결손보다 나쁘다(결손은 보이지만
      0 은 계산에 섞인다). `external_collector` 가 지켜 온 규칙과 같다."""
    raw = str(text if text is not None else "").strip()
    if not raw or raw in ("-", "--"):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    raw = _AMOUNT_JUNK.sub("", raw)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _check_status(payload: Mapping[str, Any]) -> None:
    """★ 상태 판정을 **한 곳에서만** 한다. 호출부가 각자 문자열을 보면 반드시 갈린다."""
    status = str(payload.get("status", "")).strip()
    message = str(payload.get("message", "")).strip()
    if status == STATUS_OK:
        return
    if status == STATUS_NO_DATA:
        raise NoDataFromSource(f"OpenDART 에 해당 조건의 자료가 없습니다: {message or status}")
    kind = STATUS_FAILURE_KIND.get(status, am.FAILURE_TRANSPORT)
    raise OpenDartStatusError(status, message or "(메시지 없음)", kind)


@provider_registry.register
class OpenDartProvider(B.Provider):
    """금융감독원 전자공시 OpenDART."""

    descriptor = B.ProviderDescriptor(
        provider_id="OPENDART",
        name="금융감독원 전자공시 OpenDART",
        publisher="금융감독원",
        source_type="API",
        allowed_hosts=("opendart.fss.or.kr",),
        license_url="https://opendart.fss.or.kr/intro/main.do",
        allowed_usage="공시 재무정보의 내부 분석·저장. 재배포·재판매는 별도 확인이 필요합니다.",
        redistribution_allowed=False,
        requires_credential=True,
        credential_env="AFS_OPENDART_API_KEY",
        cost="무료(개발자 계정 · 일 호출 한도 있음)",
        default_trust_grade="gold",
        refresh_frequency="정기보고서 공시 시점(연 1회 사업보고서 · 분기별 보고서)",
        coverage_note="공시대상법인의 정기보고서 재무제표. 연도·보고서·연결여부로 조회합니다.",
        target_contract_keys=(CONTRACT_KEY,),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        known_limits=(
            "공개 재무제표는 내부 매입·고객·BOM 실적을 대체하지 않습니다 — 총계 대사에 씁니다.",
            "연결(CFS)과 별도(OFS)를 한 수집 작업에 섞지 않습니다.",
            "계정과목(account_id)은 회사 계정과목이 아닙니다 — 매핑은 사람이 승인합니다.",
            "정정공시가 있으면 앞의 판을 지우지 않고 대체 관계로 남깁니다.",
        ),
    )

    # ── ② 탐색 ─────────────────────────────────────────────────────────
    def discover(self, request: B.AcquisitionRequest) -> List[B.DiscoveryCandidate]:
        """회사명으로 `corp_code` 를 찾고, 연도마다 후보 하나를 만든다.

        ⚠️ 사용자에게 `corp_code` 를 입력시키지 않는다(지시 1). 사람은 회사명을 쓰고
          내부 식별자는 시스템이 찾는다. **여러 회사가 걸리면 고르지 않고 모호함을 알린다.**"""
        name = str(request.subject_name or "").strip()
        if not name:
            return []
        matches = self._corp_matches(name)
        if not matches:
            return []
        primary = matches[0]
        others = tuple(f"{m['corp_name']}({m['corp_code']})" for m in matches[1:6])

        fs_div = str(request.extras.get("fs_div") or FS_CONSOLIDATED).upper()
        if fs_div not in FS_DIVS:
            raise B.ProviderError(f"fs_div 는 {FS_DIVS} 중 하나여야 합니다: {fs_div!r}")
        reprt = str(request.extras.get("reprt_code") or REPRT_ANNUAL)
        if reprt not in REPRT_CODES:
            raise B.ProviderError(f"모르는 보고서 코드입니다: {reprt!r}")

        out: List[B.DiscoveryCandidate] = []
        for year in _years(request.period_from, request.period_to):
            out.append(B.DiscoveryCandidate(
                provider_id=self.descriptor.provider_id,
                dataset_ref=f"{primary['corp_code']}:{year}:{reprt}:{fs_div}",
                title=f"{primary['corp_name']} {year}년 {REPRT_CODES[reprt]} "
                      f"{'연결' if fs_div == FS_CONSOLIDATED else '별도'} 재무제표",
                target_contract_key=CONTRACT_KEY,
                period_from=f"{year}-01-01",
                period_to=f"{year}-12-31",
                frequency="annual" if reprt == REPRT_ANNUAL else "quarterly",
                unit="KRW",
                match_reason=(f"회사명 '{name}' → {primary['corp_name']} "
                              f"(corp_code {primary['corp_code']}, 공시 등록명 일치)"),
                params={"corp_code": primary["corp_code"], "corp_name": primary["corp_name"],
                        "bsns_year": str(year), "reprt_code": reprt, "fs_div": fs_div},
                ambiguous_with=others,
            ))
        return out

    def _corp_matches(self, name: str) -> List[Dict[str, str]]:
        """`corpCode.xml`(ZIP) 에서 회사명을 찾는다. 정확 일치를 앞에 둔다."""
        url = f"{BASE}/corpCode.xml?crtfc_key={self.credential()}"
        response = self._get(url)
        rows = parse_corp_code_zip(bytes(response.get("body") or b""))
        needle = _fold(name)
        exact = [r for r in rows if _fold(r["corp_name"]) == needle]
        partial = [r for r in rows if needle and needle in _fold(r["corp_name"])
                   and r not in exact]
        #: ★ 상장사(stock_code 있음)를 앞에 둔다 — 같은 이름의 비상장 계열사가 흔하다.
        exact.sort(key=lambda r: (not r["stock_code"], r["corp_name"]))
        partial.sort(key=lambda r: (not r["stock_code"], len(r["corp_name"])))
        return exact + partial

    # ── ③ 미리보기 · ④ 수집 ────────────────────────────────────────────
    def preview(self, candidate: B.DiscoveryCandidate) -> B.FetchResult:
        """미리보기도 같은 창구로 받는다 — **다른 경로를 두면 그 경로만 검사가 빠진다.**

        받아온 것을 보관하지 않는 것은 오케스트레이터의 몫이다."""
        return self.fetch(candidate)

    def fetch(self, candidate: B.DiscoveryCandidate, *,
              checkpoint: Optional[B.Checkpoint] = None) -> B.FetchResult:
        p = dict(candidate.params or {})
        for field in ("corp_code", "bsns_year", "reprt_code", "fs_div"):
            if not str(p.get(field, "")).strip():
                raise B.ProviderError(f"후보에 {field} 가 없습니다 — discover 를 먼저 부르십시오.")
        url = (f"{BASE}/fnlttSinglAcntAll.json?crtfc_key={self.credential()}"
               f"&corp_code={p['corp_code']}&bsns_year={p['bsns_year']}"
               f"&reprt_code={p['reprt_code']}&fs_div={p['fs_div']}")
        response = self._get(url)
        #: ★ 상태를 **여기서 한 번** 본다. 정규화까지 들고 가면 오류 본문을 계약 모양으로
        #:   옮기려다 빈 행을 만든다.
        _check_status(_load_json(bytes(response.get("body") or b"")))
        return self._fetch_result(dataset_ref=candidate.dataset_ref, response=response,
                                  requested_url=url)

    # ── ⑤ 정규화 — 순수 ────────────────────────────────────────────────
    def normalize(self, result: B.FetchResult) -> B.NormalizedBatch:
        """OpenDART 응답을 `PUB-01` 모양으로 옮긴다. **명시적 변환기다** — 범용 파서가 아니다.

        ⚠️ 공통 봉투(tenant_id·scope_node_id·lineage_id 등)는 여기서 채우지 않는다.
          Provider 는 테넌트를 모른다 — 적용 시점에 오케스트레이터가 씌운다."""
        payload = _load_json(result.payload)
        _check_status(payload)
        wanted = _dataset_parts(result.dataset_ref)
        items = payload.get("list")
        if not isinstance(items, list):
            raise OpenDartStatusError("100", "응답에 list 가 없습니다.", am.FAILURE_SCHEMA_DRIFT)

        rows: List[Dict[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                rejected.append(B.RejectedRow(i, "행이 객체가 아님", raw_excerpt=str(item)[:100]))
                continue
            row, reason, detail = _to_pub01_row(item, wanted)
            if row is None:
                rejected.append(B.RejectedRow(i, reason, detail,
                                              raw_excerpt=json.dumps(
                                                  item, ensure_ascii=False)[:100]))
                continue
            rows.append(row)
        seen = sorted({k for it in items if isinstance(it, dict) for k in it})
        return B.NormalizedBatch(provider_id=self.descriptor.provider_id,
                                 contract_key=CONTRACT_KEY, rows=tuple(rows),
                                 rejected=tuple(rejected), source_row_count=len(items),
                                 source_fields=tuple(seen))

    # ── ⑥ 검증 — 순수 ──────────────────────────────────────────────────
    def validate(self, batch: B.NormalizedBatch) -> B.ValidationReport:
        """**던지지 않는다.** dry-run 화면이 무엇이 왜 걸렸는지 통째로 보여줘야 한다."""
        rows = list(batch.rows)
        checks: List[B.CheckResult] = []

        checks.append(B.CheckResult(
            "행 정산", batch.accounted,
            f"원문 {batch.source_row_count}행 = 적재 {len(rows)} + 제외 {len(batch.rejected)}",
            count=batch.source_row_count,
            failure_kind="" if batch.accounted else am.FAILURE_RECONCILIATION))

        checks.append(B.CheckResult("자료 있음", bool(rows), f"{len(rows)}행", count=len(rows),
                                    failure_kind="" if rows else am.FAILURE_QUALITY))

        corps = {r.get("corp_code") for r in rows if r.get("corp_code")}
        checks.append(B.CheckResult(
            "회사 단일", len(corps) <= 1, f"발견된 corp_code: {sorted(corps)}",
            count=len(corps),
            failure_kind="" if len(corps) <= 1 else am.FAILURE_QUALITY))

        fs_divs = {r.get("fs_div") for r in rows}
        checks.append(B.CheckResult(
            "연결/별도 단일", len(fs_divs) <= 1, f"발견된 구분: {sorted(x for x in fs_divs if x)}",
            count=len(fs_divs),
            failure_kind="" if len(fs_divs) <= 1 else am.FAILURE_QUALITY))

        currencies = {r.get("currency") for r in rows if r.get("currency")}
        checks.append(B.CheckResult(
            "통화 단일", len(currencies) <= 1, f"발견된 통화: {sorted(currencies)}",
            count=len(currencies),
            failure_kind="" if len(currencies) <= 1 else am.FAILURE_QUALITY))

        no_vintage = [r for r in rows if not r.get("vintage_date")]
        checks.append(B.CheckResult(
            "vintage 존재", not no_vintage,
            f"발표일을 못 읽은 행 {len(no_vintage)}건 — 접수번호 형식을 확인하십시오.",
            count=len(no_vintage),
            failure_kind="" if not no_vintage else am.FAILURE_QUALITY))

        #: ★★★ 결손을 0 으로 바꾸지 않았는지. `parse_amount` 가 `None` 을 돌려준 자리다.
        null_amounts = [r for r in rows if r.get("amount") is None]
        checks.append(B.CheckResult(
            "금액 결손 표시", True,
            f"금액을 읽지 못한 행 {len(null_amounts)}건 — 0 이 아니라 결손으로 남았습니다.",
            count=len(null_amounts)))

        years = {r.get("bsns_year") for r in rows}
        checks.append(B.CheckResult(
            "사업연도 단일", len(years) <= 1, f"발견된 연도: {sorted(x for x in years if x)}",
            count=len(years),
            failure_kind="" if len(years) <= 1 else am.FAILURE_QUALITY))

        return B.ValidationReport(checks=tuple(checks))

    # ── ⑦ 이어받기 · ⑧ 갱신 — 순수 ────────────────────────────────────
    def checkpoint(self, batch: B.NormalizedBatch, *,
                   previous: Optional[B.Checkpoint] = None) -> B.Checkpoint:
        rows = list(batch.rows)
        rcepts = sorted({str(r.get("rcept_no") or "") for r in rows if r.get("rcept_no")})
        years = sorted({str(r.get("bsns_year") or "") for r in rows if r.get("bsns_year")})
        ref = str(rows[0].get("_dataset_ref") or "") if rows else (
            previous.dataset_ref if previous else "")
        return B.Checkpoint(
            provider_id=self.descriptor.provider_id,
            dataset_ref=ref,
            cursor=rcepts[-1] if rcepts else (previous.cursor if previous else ""),
            covered_from=years[0] if years else "",
            covered_to=years[-1] if years else "",
            last_success_at=str(rows[0].get("published_at") or "") if rows else "",
        )

    def refresh(self, checkpoint: B.Checkpoint) -> List[B.DiscoveryCandidate]:
        """다음에 받을 것. **순수** — 다음 연도 하나를 만든다.

        ⚠️ 여기서 네트워크를 쓰면 정기 갱신이 「돌려 봐야 아는」 것이 된다."""
        parts = _dataset_parts(checkpoint.dataset_ref)
        if not parts.get("corp_code"):
            return []
        try:
            next_year = int(parts["bsns_year"]) + 1
        except (TypeError, ValueError):
            return []
        ref = f"{parts['corp_code']}:{next_year}:{parts['reprt_code']}:{parts['fs_div']}"
        return [B.DiscoveryCandidate(
            provider_id=self.descriptor.provider_id, dataset_ref=ref,
            title=f"{next_year}년 {REPRT_CODES.get(parts['reprt_code'], parts['reprt_code'])}",
            target_contract_key=CONTRACT_KEY,
            period_from=f"{next_year}-01-01", period_to=f"{next_year}-12-31",
            frequency="annual", unit="KRW",
            match_reason=f"직전 수집({parts['bsns_year']}년) 다음 회차",
            params={"corp_code": parts["corp_code"], "bsns_year": str(next_year),
                    "reprt_code": parts["reprt_code"], "fs_div": parts["fs_div"]})]


# ── 정정공시 ─────────────────────────────────────────────────────────────────
def resolve_supersessions(rows: Sequence[Mapping[str, Any]]) -> Tuple[Tuple[Dict[str, Any], ...],
                                                                     Tuple[Dict[str, Any], ...]]:
    """정정공시를 가른다 — **지우지 않고 대체 관계만 남긴다.**

    같은 (회사·연도·보고서·구분·계정)에 접수번호가 여럿이면 **가장 큰 접수번호가 현행**이고
    나머지는 `SUPERSEDED` 다. 옛 판을 지우면 「그 계획이 당시 어떤 발표값을 썼는가」에
    답할 수 없다.

    돌려주는 것: (현행 행들, 대체된 행들). 둘의 합은 입력과 같다."""
    by_key: Dict[Tuple[str, ...], List[Mapping[str, Any]]] = {}
    for r in rows:
        key = (str(r.get("corp_code") or ""), str(r.get("bsns_year") or ""),
               str(r.get("reprt_code") or ""), str(r.get("fs_div") or ""),
               str(r.get("sj_div") or ""), str(r.get("account_id") or ""))
        by_key.setdefault(key, []).append(r)

    current: List[Dict[str, Any]] = []
    superseded: List[Dict[str, Any]] = []
    for key, group in by_key.items():
        ordered = sorted(group, key=lambda r: str(r.get("rcept_no") or ""))
        latest = ordered[-1]
        for r in ordered[:-1]:
            superseded.append(dict(r, quality_status="SUPERSEDED",
                                   superseded_by_rcept_no=str(latest.get("rcept_no") or "")))
        current.append(dict(latest, quality_status="VALIDATED", superseded_by_rcept_no=""))
    current.sort(key=lambda r: (str(r.get("sj_div") or ""), str(r.get("ord") or "")))
    return tuple(current), tuple(superseded)


def drop_future_disclosures(rows: Sequence[Mapping[str, Any]], as_of: str
                            ) -> Tuple[Tuple[Dict[str, Any], ...], Tuple[Dict[str, Any], ...]]:
    """as-of 보다 **나중에 발표된** 값을 뺀다(지시 13 「미래 발표값 누출 방지」).

    ⚠️ 2026년 3월에 발표된 값을 2025년 12월 계획의 근거로 쓰면, 그 계획을 재현할 때 당시
      아무도 몰랐던 숫자가 들어간다. 그것은 재현이 아니라 사후 보정이다."""
    cutoff = str(as_of or "").strip()
    if not cutoff:
        return tuple(dict(r) for r in rows), ()
    kept, leaked = [], []
    for r in rows:
        published = str(r.get("published_at") or "")
        (leaked if (published and published > cutoff) else kept).append(dict(r))
    return tuple(kept), tuple(leaked)


# ── 보조 ─────────────────────────────────────────────────────────────────────
def _fold(text: str) -> str:
    """회사명 비교용 정규화 — 공백·괄호·주식회사 표기를 지운다."""
    raw = str(text or "").strip().lower()
    raw = re.sub(r"\(주\)|주식회사|㈜", "", raw)
    return re.sub(r"[\s\-_.]", "", raw)


def _years(period_from: str, period_to: str) -> List[int]:
    def _y(v: str) -> Optional[int]:
        m = re.search(r"(\d{4})", str(v or ""))
        return int(m.group(1)) if m else None

    a, b = _y(period_from), _y(period_to)
    if a is None and b is None:
        return []
    if a is None:
        a = b
    if b is None:
        b = a
    if b < a:
        a, b = b, a
    if b - a > 30:
        raise B.ProviderError(f"기간이 너무 넓습니다({a}~{b}) — 30년 이내로 나누십시오.")
    return list(range(a, b + 1))


def _dataset_parts(dataset_ref: str) -> Dict[str, str]:
    bits = str(dataset_ref or "").split(":")
    if len(bits) != 4:
        return {}
    return {"corp_code": bits[0], "bsns_year": bits[1],
            "reprt_code": bits[2], "fs_div": bits[3]}


def _load_json(payload: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(bytes(payload or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenDartStatusError("100", f"응답을 JSON 으로 읽지 못했습니다: {exc}",
                                  am.FAILURE_SCHEMA_DRIFT) from exc
    if not isinstance(data, dict):
        raise OpenDartStatusError("100", "응답 최상위가 객체가 아닙니다.",
                                  am.FAILURE_SCHEMA_DRIFT)
    return data


def parse_corp_code_zip(payload: bytes) -> List[Dict[str, str]]:
    """`corpCode.xml` ZIP 을 읽는다. **명시적 변환기** — 아무 ZIP 이나 받지 않는다."""
    try:
        with zipfile.ZipFile(io.BytesIO(bytes(payload or b""))) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise OpenDartStatusError("100", "ZIP 안에 XML 이 없습니다.",
                                          am.FAILURE_SCHEMA_DRIFT)
            raw = zf.read(names[0])
    except zipfile.BadZipFile as exc:
        raise OpenDartStatusError("100", f"corpCode 응답이 ZIP 이 아닙니다: {exc}",
                                  am.FAILURE_SCHEMA_DRIFT) from exc
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise OpenDartStatusError("100", f"corpCode XML 을 읽지 못했습니다: {exc}",
                                  am.FAILURE_SCHEMA_DRIFT) from exc
    out: List[Dict[str, str]] = []
    for node in root.findall(".//list"):
        code = (node.findtext("corp_code") or "").strip()
        name = (node.findtext("corp_name") or "").strip()
        if not code or not name:
            continue
        out.append({"corp_code": code, "corp_name": name,
                    "stock_code": (node.findtext("stock_code") or "").strip(),
                    "modify_date": (node.findtext("modify_date") or "").strip()})
    return out


def _to_pub01_row(item: Mapping[str, Any], wanted: Mapping[str, str]
                  ) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """한 줄을 `PUB-01` 모양으로. 못 옮기면 `(None, 사유, 상세)`."""
    #: ★★★ **요청한 회사가 맞는지 먼저 본다.** 이 검사가 없으면 응답이 다른 회사의 것이어도
    #:   조용히 적재되고, 그 뒤 어느 회사 숫자인지 되짚을 근거가 사라진다.
    #:   ⚠️ 실측으로 뚫렸다 — 요청 `00999001` 에 응답 `00126380` 이 그대로 통과했다.
    corp_code = str(item.get("corp_code") or "").strip()
    want_corp = str(wanted.get("corp_code") or "").strip()
    if want_corp and corp_code and corp_code != want_corp:
        return None, "회사 불일치", f"요청 {want_corp} · 행 {corp_code}"

    fs_div = str(item.get("fs_div") or "").strip().upper()
    want_fs = str(wanted.get("fs_div") or "").upper()
    if want_fs and fs_div and fs_div != want_fs:
        #: ★★★ 요청한 것과 다른 구분은 **버린다.** 섞이면 합계가 조용히 틀린다.
        return None, "연결/별도 구분 불일치", f"요청 {want_fs} · 행 {fs_div}"

    want_year = str(wanted.get("bsns_year") or "")
    year = str(item.get("bsns_year") or "").strip()
    if want_year and year and year != want_year:
        return None, "사업연도 불일치", f"요청 {want_year} · 행 {year}"

    account_id = str(item.get("account_id") or "").strip()
    account_nm = str(item.get("account_nm") or "").strip()
    if not account_id and not account_nm:
        return None, "계정 식별 불가", "account_id · account_nm 이 모두 비었습니다."

    rcept_no = str(item.get("rcept_no") or "").strip()
    published = published_at_from_rcept_no(rcept_no)
    return {
        "corp_code": str(item.get("corp_code") or "").strip(),
        "bsns_year": year,
        "reprt_code": str(item.get("reprt_code") or "").strip(),
        "fs_div": fs_div or want_fs,
        "fs_nm": str(item.get("fs_nm") or "").strip(),
        "sj_div": str(item.get("sj_div") or "").strip(),
        "sj_nm": str(item.get("sj_nm") or "").strip(),
        "account_id": account_id,
        "account_nm": account_nm,
        "account_detail": str(item.get("account_detail") or "").strip(),
        "ord": str(item.get("ord") or "").strip(),
        "term_name": str(item.get("thstrm_nm") or "").strip(),
        #: ★ 읽지 못하면 `None` — 0 이 아니다.
        "amount": parse_amount(item.get("thstrm_amount")),
        "prior_amount": parse_amount(item.get("frmtrm_amount")),
        "currency": str(item.get("currency") or "").strip().upper(),
        "rcept_no": rcept_no,
        "published_at": published,
        #: vintage 는 **발표일**이다 — 받은 날이 아니다(§12.5).
        "vintage_date": published,
        "_dataset_ref": f"{str(item.get('corp_code') or '').strip()}:{year}:"
                        f"{str(item.get('reprt_code') or '').strip()}:{fs_div or want_fs}",
    }, "", ""
