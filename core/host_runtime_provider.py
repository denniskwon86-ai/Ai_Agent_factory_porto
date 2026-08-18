"""[BDR-6] Host Runtime Provider Dispatch — **앱은 출처를 모른다.**

## 앱 표면은 하나다

생성 앱은 `window.afs.data.*` 만 쓴다. 그 뒤에 무엇이 있는지 — 우리 DB인지, 올라온
파일 판인지, 사내 시스템인지 — 앱은 알지 못하고 알 필요도 없다.

⚠️⚠️ **앱에게 Provider 종류를 돌려주지 않는다.** 「이건 FILE_SNAPSHOT 이야」를 알려
  주는 순간 LLM 이 쓴 앱 코드가 출처별로 분기하기 시작하고, 그러면 출처를 바꾸는
  일이 앱을 고치는 일이 된다 — 우리가 이 층을 만든 이유가 사라진다.
  자격증명·내부 ID·SQL·URL 도 같은 이유로 표면 밖이다.

## 이 파일이 지키는 것 셋

★★★ ① **모르는 Provider 는 «못 읽음» 이지 «기본값» 이 아니다.** `AFS_NATIVE` 로
  폴백하면 사내 시스템에서 와야 할 숫자를 우리 DB의 빈 표에서 읽고, 앱은 그것을
  「0건」으로 그린다. 그 화면은 오류를 내지 않는다.

★★★ ② **Native 밖에는 쓰지 않는다.** 파일 판·사내 시스템·계산 결과에 앱이 쓰면
  그것은 원천과 갈라진 사본이 되고, 갈라진 사실은 아무도 모른다. L3 write-back 은
  별도 Command Contract·승인·멱등·보상이 필요하며 이 설계 범위 밖이다.

★★★ ③ **원천 장애를 0건으로 그리지 않는다.** 「응답이 없었다」와 「없다」는 다르다.
  0건으로 접으면 화면에서 데이터가 사라지고, 사용자는 그것을 «삭제됨» 으로 읽는다.

## 준비도와의 관계

준비도(`data_preparation.readiness`)는 **사람에게 무엇을 하라고 말하는** 판정이고,
여기는 **앱 요청 하나를 지금 처리할 수 있는가**를 본다. 둘은 같은 사실을 보지만
답하는 상대가 다르다 — 그래서 준비도 문장을 앱에 그대로 흘리지 않는다.
"""
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from core import host_runtime_sdk as sdk
from core.business_data_semantics import (AFS_NATIVE, DERIVED_READ, ENTERPRISE_READ,
                                          EXTERNAL_REFERENCE)
from core.data_preparation import models as dpm, readiness

#: ★ Provider — **닫힌 목록**. 여기 없는 값은 결함이지 새 출처가 아니다.
NATIVE = dpm.PROVIDER_AFS_NATIVE               # 우리 DB(app_data)
FILE_SNAPSHOT = dpm.PROVIDER_FILE_SNAPSHOT     # 승인된 data_preparation 판
CONNECTOR_QUERY = dpm.PROVIDER_CONNECTOR_QUERY  # 사내 시스템 — 아직 지원 대기
DERIVED = "DERIVED"                            # 승인된 계산 결과 — 후속 연결

PROVIDERS: Tuple[str, ...] = (NATIVE, FILE_SNAPSHOT, CONNECTOR_QUERY, DERIVED)

#: ★★★ **지금 실제로 데이터를 돌려줄 수 있는 것.** 나머지는 «지원 대기» 다.
#: ⚠️ 「곧 될 것」을 여기 넣지 않는다 — 넣는 순간 빈 응답이 정상 응답이 된다.
SERVING_PROVIDERS: Tuple[str, ...] = (NATIVE, FILE_SNAPSHOT)

#: ★★★ **쓸 수 있는 곳은 하나뿐이다.**
WRITABLE_PROVIDERS: Tuple[str, ...] = (NATIVE,)

#: 앱 계약의 `source_intent` → Provider. **모르는 의도는 표에 없고, 없으면 못 읽음이다.**
#: ⚠️ `dict.get(x, NATIVE)` 를 쓰지 않는다 — 기본값이 있는 순간 오타가 우리 DB를 가리킨다.
_INTENT_TO_PROVIDER: Dict[str, str] = {
    AFS_NATIVE: NATIVE,
    ENTERPRISE_READ: FILE_SNAPSHOT,      # 사내 실적은 승인된 판으로만 읽는다
    EXTERNAL_REFERENCE: CONNECTOR_QUERY,  # 외부 공표 지표 — Host 서비스가 가져온다
    DERIVED_READ: DERIVED,
}

#: 지원 대기 Provider 에 붙는 사유. **앱에게는 코드만, 사람에게는 문장.**
NOT_YET_SUPPORTED = "NOT_YET_SUPPORTED"


class ProviderError(Exception):
    """Dispatch 가 요청을 처리할 수 없다. `app_code` 가 앱에게 갈 코드다."""

    def __init__(self, app_code: str, *, reason: str = "", provider: str = ""):
        super().__init__(reason or app_code)
        self.app_code = app_code
        self.reason = reason
        self.provider = provider


class Resolution(NamedTuple):
    """이 요청이 어디로 가는가. ⚠️ **이 객체는 앱에 나가지 않는다** — 서버 안에서만 산다."""
    provider: str
    dataset_contract_key: str
    binding: Optional[Dict[str, Any]]
    snapshot: Optional[Dict[str, Any]]
    stale: bool
    as_of: str


def provider_for_intent(source_intent: Any) -> str:
    """`source_intent` → Provider. **모르면 빈 문자열** 이고 호출부는 그것을 거부해야 한다.

    ⚠️ 여기서 기본값을 돌려주지 않는다. 「모르면 우리 DB」가 곧 조용한 오답이다."""
    return _INTENT_TO_PROVIDER.get(str(source_intent or "").strip(), "")


def is_writable(provider: Any) -> bool:
    """이 Provider 에 쓸 수 있는가. **목록에 없으면 못 쓴다**(fail-closed)."""
    return str(provider or "") in WRITABLE_PROVIDERS


def assert_writable(provider: Any) -> None:
    """쓰기 시도를 막는다. ★ 거부는 **그 앱 자신의 계약**에 대한 사실이므로 알려 준다 —
    숨기면 개발자가 무엇을 고쳐야 하는지 모른 채 이름을 의심한다."""
    if not is_writable(provider):
        raise ProviderError(
            sdk.ERR_FORBIDDEN,
            reason=f"WRITE_NOT_ALLOWED_FOR_PROVIDER:{provider or 'UNKNOWN'}",
            provider=str(provider or ""))


def resolve(*, source_intent: Any, dataset_contract_key: Any,
            binding: Optional[Dict[str, Any]],
            snapshots: Optional[List[Dict[str, Any]]],
            now: str, max_age_days: Optional[float] = None,
            scope: Optional[Dict[str, Any]] = None,
            allow_stale: bool = False) -> Resolution:
    """이 데이터셋 요청을 어디로 보낼지 정한다.

    ★★★ **매 요청 대조한다.** 계약(`source_intent`)·결속 상태·판 상태·범위를 전부
      본다. 한 번 통과한 것을 기억해 두고 다음 요청에서 건너뛰면, 그 사이에 종료된
      결속이 계속 살아 있게 된다.

    ⚠️ `allow_stale` 은 **호출부가 명시적으로 켤 때만** 만료된 판을 내보낸다. 기본이
      켜져 있으면 만료가 조용히 정상 응답이 되고, 「언제 것인지 모르는 숫자」가
      공식 화면에 오른다."""
    provider = provider_for_intent(source_intent)
    if not provider:
        raise ProviderError(sdk.ERR_UNAVAILABLE,
                            reason=f"UNKNOWN_SOURCE_INTENT:{source_intent or ''}")

    key = str(dataset_contract_key or "").strip()

    if provider == NATIVE:
        #: 우리 DB — 결속·판이 필요 없다. 계약이 그렇게 말했다.
        return Resolution(NATIVE, key, None, None, False, "")

    if provider not in SERVING_PROVIDERS:
        #: ⚠️ **빈 목록이 아니다.** 「아직 안 된다」를 「없다」로 답하면 앱이 화면에서
        #:   그 표를 지우고, 사용자는 데이터가 사라졌다고 읽는다.
        raise ProviderError(sdk.ERR_UNAVAILABLE, reason=NOT_YET_SUPPORTED,
                            provider=provider)

    if not key:
        raise ProviderError(sdk.ERR_UNAVAILABLE, reason="NO_CONTRACT_KEY", provider=provider)

    verdict = readiness.evaluate_dataset(key, binding=binding, snapshots=snapshots or [],
                                         now=now, max_age_days=max_age_days, scope=scope)
    state = verdict["state"]

    if state == readiness.READY:
        snap = readiness.latest_certified(snapshots or [])
        return Resolution(provider, key, binding, snap, False,
                          str((snap or {}).get("certified_at") or ""))

    if state == readiness.STALE:
        if not allow_stale:
            #: ⚠️ 만료를 `NOT_FOUND` 로 접지 않는다 — 앱이 「없어졌다」로 그린다.
            raise ProviderError(sdk.ERR_UNAVAILABLE, reason=readiness.STALE,
                                provider=provider)
        snap = readiness.latest_certified(snapshots or [])
        return Resolution(provider, key, binding, snap, True,
                          str((snap or {}).get("certified_at") or ""))

    #: ★★★ 준비되지 않은 나머지 — **전부 `UNAVAILABLE`.**
    #: ⚠️ 사유(승인 전·격리·대사 실패)는 **앱에 흘리지 않는다.** 그것은 사람이 화면에서
    #:   준비도 보드로 볼 사실이고, 앱에 주면 그 앱을 쓰는 사람이 볼 수 없는 조직의
    #:   내부 상태가 앱 코드를 통해 새어나간다.
    raise ProviderError(sdk.ERR_UNAVAILABLE, reason=state, provider=provider)


def snapshot_rows(rows: List[Dict[str, Any]], *, limit: int, offset: int
                  ) -> Tuple[List[Dict[str, Any]], int]:
    """판의 행을 잘라서 돌려준다 — **총계를 함께** 준다.

    ⚠️ 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린 순간 사용자는 「우리 데이터는
      N건」으로 믿는다. Native 경로가 이미 같은 이유로 총계를 준다."""
    total = len(rows)
    start = max(0, int(offset or 0))
    return rows[start:start + max(1, int(limit or 1))], total


def public_meta(res: Resolution) -> Dict[str, Any]:
    """앱에게 **줘도 되는 것만** 남긴다.

    ★★★ Provider 종류·결속 id·내부 경로는 나가지 않는다. 나가는 것은 둘뿐:
      · `as_of` — 이 숫자가 «언제 것인가». 없으면 사용자는 지금 것으로 읽는다.
      · `stale` — 오래됐다는 사실. 숨기면 그 숫자가 최신으로 읽힌다."""
    return {"as_of": res.as_of, "stale": bool(res.stale)}
