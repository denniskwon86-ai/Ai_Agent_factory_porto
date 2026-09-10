"""[DAO-2] Provider 계약 — 「이 원천에서 값을 어떻게 가져오는가」의 공통 모양.

## 여덟 메서드를 왜 이렇게 갈랐나

    describe()    무엇을 주는 원천인가          순수 · 네트워크 0 · 자격증명 0
    discover()    이 요청에 맞는 자료가 있는가    네트워크 읽기
    preview()     실제로 몇 줄만 받아 보자       네트워크 읽기
    fetch()       받아온다                     네트워크 읽기  ← **여기서만 나간다**
    normalize()   우리 계약 모양으로 옮긴다      순수
    validate()    쓸 수 있는 값인가             순수
    checkpoint()  어디까지 받았나               순수
    refresh()     다음에 무엇을 받아야 하나      순수

★★★ **`normalize`·`validate`·`checkpoint`·`refresh` 는 순수해야 한다.** 네트워크도 DB 도
  시계도 만지지 않는다. 그래야 실제 API 키 없이 **공식 응답 fixture 만으로 종단 검증**이
  된다. 하나라도 네트워크를 만지면 그 순간 「실제로 받아 봐야만 확인되는」 코드가 되고,
  그것은 실행할 때마다 남의 서버를 두드려야 확인할 수 있다는 뜻이다.

## ⚠️ 느슨한 범용 파서를 만들지 않는다

지시 4 가 명시했다. OpenDART 응답을 받으려고 「어떤 JSON 이든 대충 읽는」 파서를 만들면
그 파서는 **KOSIS 응답도 통과시킨다.** 통과시키되 뜻은 다르게 읽는다. 그래서 `normalize()`
는 Provider 마다 **명시적으로** 구현하고, 이 기반 클래스는 구현을 제공하지 않는다.

## ⚠️ robots.txt 를 여기서 보지 않는다 — 그 대신 무엇을 보는가

`core/external_research._SafeHttpFetcher` 는 robots.txt 를 확인한다. 그것은 **HTML·RSS 를
크롤링**하는 도구이고 거기서는 옳다. 그러나 공식 Open API 는 크롤링 대상이 아니라 **프로그램
호출용으로 공개된 창구**이고, 사이트의 robots.txt 는 대개 그 창구를 다루지 않는다(오히려
`Disallow: /` 로 API 호출을 막는 것처럼 읽힌다).

여기서 이용 조건을 보는 자리는 **원천 등록·승인**이다. `describe()` 가 `license_url`·
`allowed_usage`·`redistribution_allowed` 를 선언하고, 승인 없이는(`enabled=0`) 한 줄도
적재되지 않는다(`external_intelligence.record_observation()` 이 거부한다).

## 자격증명

Provider 는 키를 **들고 있지 않는다.** `credential_env` 이름만 선언하고, 값은 호출 시점에
환경에서 읽는다. `secret_values()` 가 「이번 호출에서 새어 나갈 수 있는 값」을 돌려주고
오케스트레이터가 그것을 원문 보관소에 넘겨 지운다.

★★★ `FetchResult.requested_url` 은 **이미 지워진 값**이다. 지우지 않은 URL 을 결과에 담으면
  그 결과가 로그·원장·화면 어디로든 흘러가고, 그때는 이미 늦다.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.raw_store import assert_no_secret, redact_url

#: 한 번에 받아올 수 있는 최대 크기. 원천이 예상 밖으로 큰 응답을 주면 **끊는다** —
#: 메모리에 다 올리고 나서 판단하면 이미 늦다.
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
DEFAULT_TIMEOUT_SEC = 20.0


class ProviderError(ValueError):
    """Provider 사용 오류 — 4xx 로 전달한다."""


class ProviderTransportError(ProviderError):
    """원천에 닿지 못했다. **`FAILED`(재시도 가능)로 분류된다** — 자료 없음이 아니다."""


class ProviderCredentialError(ProviderError):
    """자격증명이 없거나 거부됐다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 서술 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ProviderDescriptor:
    """원천 카드. 지시 3 이 요구한 「추천 결과에 반드시 표시」 항목이 전부 여기 있다.

    ⚠️ 사람이 원천을 고르는 화면은 **이 값만** 보여 준다. 화면이 따로 문구를 만들면
      그 문구와 실제 수집 대상이 갈린다."""
    provider_id: str
    name: str
    publisher: str
    source_type: str                      # external_intelligence.SOURCE_TYPES
    allowed_hosts: Tuple[str, ...]        # ★ 이 밖으로는 한 번도 나가지 않는다
    license_url: str
    allowed_usage: str
    redistribution_allowed: bool
    requires_credential: bool
    credential_env: str
    cost: str                             # "무료" · "유료(계약 필요)"
    default_trust_grade: str              # gold · silver · bronze
    refresh_frequency: str
    coverage_note: str
    target_contract_keys: Tuple[str, ...]  # 어느 데이터 계약으로 흐르는가
    data_origin: str                      # acquisition_models.DATA_ORIGINS
    known_limits: Tuple[str, ...] = ()    # 「이 값으로 하면 안 되는 것」

    def __post_init__(self):
        am.assert_origin(self.data_origin)
        from core import external_intelligence as ei
        if self.source_type not in ei.SOURCE_TYPES:
            raise ProviderError(f"source_type 은 {ei.SOURCE_TYPES} 중 하나여야 합니다: "
                                f"{self.source_type!r}")
        if self.default_trust_grade not in ei.GRADES:
            raise ProviderError(f"등급은 {ei.GRADES} 중 하나여야 합니다: "
                                f"{self.default_trust_grade!r}")
        if not self.allowed_hosts:
            raise ProviderError("허용 호스트가 비어 있으면 어디로든 나갈 수 있습니다.")
        if self.requires_credential and not self.credential_env:
            raise ProviderError("자격증명이 필요한데 환경변수 이름이 없습니다.")


# ── 탐색·미리보기 ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AcquisitionRequest:
    """구조화된 수집 요청. **내부 ID 를 사용자에게 입력시키지 않는다**(지시 1).

    사람은 회사명·기간·목적을 고르고, `legal_entity_id` 같은 내부 값은 시스템이 채운다."""
    subject_name: str = ""                # "LS MnM" — 사람이 쓴 이름
    purpose: str = ""                     # "원료구매·손익 시뮬레이션"
    period_from: str = ""                 # "2016"
    period_to: str = ""                   # "2025"
    indicators: Tuple[str, ...] = ()      # "매출", "영업이익", "환율", "구리가격"
    target_contract_keys: Tuple[str, ...] = ()
    frequency: str = ""                   # "annual" · "monthly" · "daily"
    required_grade: str = ""              # 없으면 Provider 기본값
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryCandidate:
    """원천 안에서 찾아낸 자료 한 건. **아직 받지 않았다.**"""
    provider_id: str
    dataset_ref: str                      # Provider 내부 식별자(corp_code·통계표코드 등)
    title: str
    target_contract_key: str
    period_from: str = ""
    period_to: str = ""
    frequency: str = ""
    unit: str = ""
    match_reason: str = ""                # ★ 「왜 이것이 요청에 맞는가」 — 비면 화면이 지어낸다
    params: Mapping[str, Any] = field(default_factory=dict)
    ambiguous_with: Tuple[str, ...] = ()  # 같은 이름의 다른 후보(모호한 회사명 처리)


@dataclass(frozen=True)
class ExcludedSource:
    """고르지 않은 원천과 **제외 사유**(지시 3). 사유 없는 제외는 기록하지 않는다."""
    provider_id: str
    reason: str


# ── 수집 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FetchResult:
    """받아온 원문 한 덩이. `requested_url` 은 **이미 비밀이 지워진 값**이다."""
    provider_id: str
    dataset_ref: str
    payload: bytes
    content_type: str
    requested_url: str
    fetched_at: str
    http_status: int = 200
    page: int = 1
    has_more: bool = False
    next_cursor: str = ""


# ── 정규화 ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RejectedRow:
    """★★★ 버린 줄은 **반드시 사유와 함께** 남는다.

    ⚠️ 조용히 버리면 「받은 건수」와 「적재 건수」가 달라지는데 아무도 이유를 모른다.
      이 저장소가 `readiness.py` 에서 「없음·못 읽음」을 가른 것과 같은 규칙이다."""
    index: int
    reason: str
    detail: str = ""
    raw_excerpt: str = ""                 # 진단용 — 100자 이내로 자른다


@dataclass(frozen=True)
class NormalizedBatch:
    """계약 모양으로 옮긴 결과. `rows` 와 `rejected` 의 합이 원문 줄 수여야 한다."""
    provider_id: str
    contract_key: str
    rows: Tuple[Mapping[str, Any], ...] = ()
    rejected: Tuple[RejectedRow, ...] = ()
    source_row_count: int = 0
    #: ★★★ **원천이 실제로 준 필드 이름들.** 정규화된 행이 아니라 원문의 것이다.
    #:   ⚠️ 이것이 없으면 원천 스키마 변경을 볼 수 없다 — 명시적 변환기가 새 열을
    #:     조용히 버리기 때문에, 정규화 결과만 보면 원천이 바뀌어도 아무 차이가 없다.
    #:     (실측: 그래서 「새 필드 차단」 관문이 장식이었다.)
    source_fields: Tuple[str, ...] = ()

    @property
    def accounted(self) -> bool:
        """받은 줄이 전부 «들어갔거나 사유와 함께 빠졌는가»."""
        return self.source_row_count == len(self.rows) + len(self.rejected)


# ── 검증 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    count: int = 0
    failure_kind: str = ""                # acquisition_models.FAILURE_KINDS


@dataclass(frozen=True)
class ValidationReport:
    """★ **던지지 않는다.** dry-run 화면이 「무엇이 왜 걸렸는지」를 통째로 보여줘야 한다."""
    checks: Tuple[CheckResult, ...] = ()

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> Tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def worst_failure_kind(self) -> str:
        """어느 상태로 보낼지 정할 때 쓴다. 격리 사유가 있으면 그것이 우선이다."""
        kinds = [c.failure_kind for c in self.failures if c.failure_kind]
        for k in kinds:
            if k in am.QUARANTINE_FAILURES:
                return k
        return kinds[0] if kinds else ""


# ── 이어받기 ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Checkpoint:
    """어디까지 받았나. 정기 갱신이 **처음부터 다시 받지 않게** 한다."""
    provider_id: str
    dataset_ref: str
    cursor: str = ""
    covered_from: str = ""
    covered_to: str = ""
    last_success_at: str = ""
    last_checksum: str = ""


# ── 기반 클래스 ──────────────────────────────────────────────────────────────
class Provider(ABC):
    """모든 원천이 구현하는 계약.

    ⚠️ 이 클래스는 `normalize` 의 기본 구현을 **주지 않는다.** 기본 구현을 주면 새 Provider
      가 그것을 물려받아 「대충 돌아가는」 상태가 되고, 그 순간 지시 4 가 금지한 느슨한
      범용 파서가 생긴다."""

    #: 하위 클래스가 채운다.
    descriptor: ProviderDescriptor

    def __init__(self, *, env: Optional[Mapping[str, str]] = None, transport=None):
        #: ⚠️ 환경을 주입 가능하게 둔다 — 시험이 실제 환경변수를 건드리지 않아야 한다.
        self._env = env if env is not None else os.environ
        self._transport = transport or https_get

    # ── ① 서술 — 순수 ──────────────────────────────────────────────────
    def describe(self) -> ProviderDescriptor:
        return self.descriptor

    # ── 자격증명 ───────────────────────────────────────────────────────
    def credential(self, *, required: bool = True) -> str:
        """환경에서 키를 읽는다. **파일·DB·코드에 두지 않는다**(지시 12)."""
        d = self.describe()
        if not d.requires_credential:
            return ""
        value = str(self._env.get(d.credential_env, "") or "").strip()
        if not value and required:
            raise ProviderCredentialError(
                f"{d.name} 자격증명이 없습니다. 환경변수 {d.credential_env} 를 설정하십시오. "
                f"(값을 코드·설정파일에 적지 마십시오)")
        return value

    def has_credential(self) -> bool:
        return bool(self.credential(required=False)) or not self.describe().requires_credential

    def secret_values(self) -> Tuple[str, ...]:
        """이번 호출에서 새어 나갈 수 있는 값. 원문 보관소가 이것으로 지운다."""
        value = self.credential(required=False)
        return (value,) if value else ()

    # ── 전송 — 이 창구로만 나간다 ───────────────────────────────────────
    def _get(self, url: str, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> Dict[str, Any]:
        """허용 호스트 검사·리디렉션 재검사·크기 제한을 거친 GET.

        ★★★ 하위 클래스는 `urllib` 을 직접 부르지 않는다. 직접 부르면 호스트 검사가 빠진
          경로가 하나 생기고, 그 경로는 임의 URL 을 호출할 수 있다."""
        return self._transport(url, allowed_hosts=self.describe().allowed_hosts, timeout=timeout)

    def _fetch_result(self, *, dataset_ref: str, response: Mapping[str, Any],
                      requested_url: str, **extra: Any) -> FetchResult:
        """전송 결과를 `FetchResult` 로 감싼다. **URL 을 여기서 지운다.**"""
        secrets = self.secret_values()
        safe = redact_url(requested_url, secrets)
        assert_no_secret(safe, secrets, where="Provider 요청 URL")
        return FetchResult(
            provider_id=self.describe().provider_id,
            dataset_ref=str(dataset_ref),
            payload=bytes(response.get("body") or b""),
            content_type=str(response.get("content_type") or "application/octet-stream"),
            requested_url=safe,
            fetched_at=str(response.get("fetched_at") or _now()),
            http_status=int(response.get("status") or 0),
            **extra,
        )

    # ── ②~⑧ 하위 클래스가 구현 ─────────────────────────────────────────
    @abstractmethod
    def discover(self, request: AcquisitionRequest) -> List[DiscoveryCandidate]:
        """요청에 맞는 자료가 이 원천에 있는가. **없으면 빈 목록** — 예외가 아니다."""

    @abstractmethod
    def preview(self, candidate: DiscoveryCandidate) -> FetchResult:
        """몇 줄만 받아 본다. 보관하지 않는다."""

    @abstractmethod
    def fetch(self, candidate: DiscoveryCandidate, *,
              checkpoint: Optional[Checkpoint] = None) -> FetchResult:
        """실제로 받아온다."""

    @abstractmethod
    def normalize(self, result: FetchResult) -> NormalizedBatch:
        """**순수.** 원문을 계약 모양으로 옮긴다. 버린 줄은 사유와 함께 남긴다."""

    @abstractmethod
    def validate(self, batch: NormalizedBatch) -> ValidationReport:
        """**순수.** 던지지 않고 보고서를 돌려준다."""

    @abstractmethod
    def checkpoint(self, batch: NormalizedBatch, *,
                   previous: Optional[Checkpoint] = None) -> Checkpoint:
        """**순수.** 어디까지 받았는지."""

    @abstractmethod
    def refresh(self, checkpoint: Checkpoint) -> List[DiscoveryCandidate]:
        """**순수.** 다음에 무엇을 받아야 하는지. 네트워크를 만지지 않는다."""


# ── 전송 구현 ────────────────────────────────────────────────────────────────
def https_get(url: str, *, allowed_hosts: Sequence[str],
              timeout: float = DEFAULT_TIMEOUT_SEC) -> Dict[str, Any]:
    """허용 호스트의 공개 HTTPS 만 호출한다. **임의 URL 을 받지 않는다.**

    ⚠️ SSRF 검사는 새로 짜지 않고 `external_research.validate_public_target` 을 쓴다 —
      https 강제·443 포트·사용자정보 금지·fragment 금지·**DNS 가 사설망을 가리키면 거부**
      까지 이미 들어 있다. 두 곳에서 각자 구현하면 한쪽만 고쳐지는 날이 온다."""
    from urllib.error import HTTPError, URLError
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    from core.external_research import ExternalResearchError, validate_public_target

    hosts = tuple(str(h).strip().lower() for h in allowed_hosts if str(h).strip())
    if not hosts:
        raise ProviderError("허용 호스트가 비어 있으면 호출하지 않습니다.")

    class CheckedRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            #: ★ 리디렉션마다 다시 검사한다. 최초 URL 만 보면 302 한 번으로 어디로든 간다.
            validate_public_target(newurl, hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        validate_public_target(url, hosts)
    except ExternalResearchError as exc:
        raise ProviderError(str(exc)) from exc

    opener = build_opener(CheckedRedirect())
    req = Request(url, headers={"User-Agent": "LAXS-DataAcquisition/1.0",
                                "Accept": "application/json, application/xml, text/csv, */*"})
    try:
        with opener.open(req, timeout=timeout) as response:  # nosec - 대상·DNS·리디렉션 선검증
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ProviderTransportError(
                    f"응답이 허용 크기({MAX_RESPONSE_BYTES}바이트)를 넘었습니다.")
            return {"body": body,
                    "content_type": response.headers.get_content_type(),
                    "status": int(response.status),
                    "final_url": response.geturl(),
                    "fetched_at": _now()}
    except HTTPError as exc:
        raise ProviderTransportError(f"원천이 HTTP {exc.code} 로 응답했습니다.") from exc
    except ExternalResearchError as exc:
        raise ProviderError(str(exc)) from exc
    except URLError as exc:
        raise ProviderTransportError(f"원천에 닿지 못했습니다: {exc.reason}") from exc
    except OSError as exc:
        raise ProviderTransportError(f"원천 호출이 실패했습니다: {exc}") from exc
