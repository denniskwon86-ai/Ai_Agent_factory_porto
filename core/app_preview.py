"""[I-4 6 / Wave F-1] Preview 경계 — **미리보기가 운영 데이터에 닿을 수 없게 한다.**

## 왜 «논리적 분리» 로는 부족한가

Preview 는 아직 승인되지 않은 판을 사람이 눌러 보는 자리다. 그 코드는 LLM 이 방금
썼고, 아무도 실행해 본 적이 없다.

⚠️⚠️ 그런 코드에 「운영 DB 를 쓰되 `is_preview` 플래그를 보고 걸러라」로 대응하면,
  **그 플래그를 안 보는 경로 하나가 곧 운영 데이터 오염**이다. 그리고 그 경로는
  대개 나중에 추가된다 — 처음 만든 사람은 플래그를 알지만 다음 사람은 모른다.

그래서 **파일을 나눈다.** Preview 는 다른 DB 파일을 쓰고, 그 사실은 코드가 아니라
경로가 보증한다. 플래그를 빠뜨려도 운영 데이터에 닿지 않는다.

## 청중(audience) — 증명은 어느 쪽 것인가

증명에 **청중**을 봉인한다. Preview 증명으로 운영 데이터를 만질 수 없고, 운영
증명으로 Preview 데이터를 만질 수도 없다 — **양방향**이다.

⚠️ 한 방향만 막으면 반대쪽이 곧 우회로가 된다. 「Preview 는 약한 권한이니 운영
  증명으로 봐도 되겠지」가 정확히 그 실수다: 그러면 운영 증명을 가진 사람이
  검토되지 않은 코드에 자기 권한을 빌려 주게 된다.

## SYNTHETIC_TEST — Preview 는 실제 회사 문맥이 아니다

Preview 실행의 조직 문맥은 `SYNTHETIC_TEST` 하나뿐이다. `REAL` 문맥으로 Preview 를
돌리면 그 화면의 숫자가 실적으로 읽히고, 승인 전 판이 만든 숫자가 회의에 올라간다.

★ 부수 효과로 **파일 Snapshot 도 자연히 막힌다** — 인증판은 `REAL` 범위에 매여
  있고, Dispatch 가 매 요청 범위를 대조하기 때문이다(BDR-6). 즉 Preview 에서 본
  것은 **운영 기준선으로 승격되지 않는다**: 애초에 운영 판을 읽지 못한다.
"""
from typing import Any, Optional, Tuple

#: ★★★ 청중 — **닫힌 목록**. 여기 없는 값은 결함이지 새 청중이 아니다.
AUDIENCE_OPERATIONAL = "operational"
AUDIENCE_PREVIEW = "preview"
AUDIENCES: Tuple[str, ...] = (AUDIENCE_OPERATIONAL, AUDIENCE_PREVIEW)

#: ★★★ Preview 실행의 조직 문맥. **이것 하나뿐이다.**
#: ⚠️ `REAL` 로 Preview 를 돌리면 승인 전 판이 만든 숫자가 실적으로 읽힌다.
ENTITY_MODE_SYNTHETIC = "SYNTHETIC_TEST"

#: 릴리스가 아직 «후보» 인 상태. 운영 ACTIVE 와 다른 값이어야 한다 —
#: ⚠️ 같은 값으로 두면 「후보만 Preview」와 「ACTIVE 만 운영」을 구분할 수 없다.
STATE_CANDIDATE = "candidate"

# ⚠️⚠️ **[F-1 알려진 미완] 아직 아무도 이 상태를 «만들지» 않는다.**
#
#   `program_lifecycle` 의 상태는 `active`·`deprecated`·`disabled` 셋뿐이고,
#   게시(`create_release`)는 상태를 아예 적지 않는다. 그래서 지금 운영에서는
#   `audience_for_state(STATE_CANDIDATE)` 가 **한 번도 불리지 않고**, Preview 증명은
#   발급되지 않는다. 이 모듈은 «경계를 세워 둔 것» 이지 «Preview 가 도는 것» 이 아니다.
#
#   ★ 기본값을 지금 켜지 않는 이유: ACTIVE 로 승격시키는 경로(I-4 7 / Wave F-2)가 아직
#     없다. 지금 게시를 후보로 바꾸면 **모든 새 릴리스가 후보로 갇히고**, 그 상태에서
#     사용자는 앱이 고장 났다고 본다.
#
#   ⚠️ 그러므로 F-2 에서 **승격 경로와 기본값 전환을 같은 커밋에** 넣는다. 나누면 그
#     사이에 만들어진 릴리스가 전부 갇힌다.


class PreviewBoundaryError(Exception):
    """Preview 경계 위반. **판정 실패가 아니라 경계 위반**이다 — 호출부가 접지 않는다."""


def normalize_audience(value: Any) -> str:
    """청중 이름을 정규화한다. **모르면 빈 문자열** 이고 호출부는 그것을 거부해야 한다.

    ⚠️ 기본값을 돌려주지 않는다. 「모르면 운영」이면 오타 하나가 운영 데이터를 열고,
      「모르면 Preview」면 운영 요청이 조용히 빈 DB 를 읽는다. 둘 다 조용하다."""
    v = str(value or "").strip().lower()
    return v if v in AUDIENCES else ""


def assert_audience(value: Any) -> str:
    """청중을 확정한다. 모르면 던진다 — **기본값 없음**이 이 함수의 요점이다."""
    out = normalize_audience(value)
    if not out:
        raise PreviewBoundaryError(
            f"알 수 없는 증명 청중입니다: {value or '(없음)'} — "
            f"가능한 것은 {list(AUDIENCES)} 입니다.")
    return out


def assert_audience_match(*, sealed: Any, requested: Any) -> None:
    """증명에 봉인된 청중과 지금 경로의 청중이 같은가. **양방향으로 막는다.**

    ★★★ 한 방향만 막으면 반대쪽이 곧 우회로다. 「Preview 는 약한 권한이니 운영
      증명으로 봐도 되겠지」가 그 실수다 — 그러면 운영 권한을 가진 사람이 **검토되지
      않은 코드에 자기 권한을 빌려 준다.**

    ⚠️ 봉인 값이 **없는** 증명도 거부한다. 청중 이전에 발급된 증명은 어느 쪽인지
      알 수 없고, 「모르니까 통과」가 곧 경계 없음이다."""
    want = assert_audience(requested)
    got = normalize_audience(sealed)
    if not got:
        raise PreviewBoundaryError(
            "이 증명에는 청중이 봉인돼 있지 않습니다 — 어느 쪽 것인지 알 수 없는 "
            "증명으로는 열지 않습니다. 앱을 다시 열어 새 증명을 받으십시오.")
    if got != want:
        #: ⚠️ 어느 쪽으로 어긋났는지는 **앱에 말하지 않는다**(호출부가 접는다).
        #:   여기서는 감사에 남길 사실만 만든다.
        raise PreviewBoundaryError(
            f"증명 청중이 다릅니다(봉인 {got} · 요청 {want}) — Preview 와 운영은 "
            f"서로의 증명을 쓰지 않습니다.")


def is_preview(audience: Any) -> bool:
    """**모르면 Preview 가 아니다**(fail-closed 방향이 여기서는 «운영 아님»).

    ⚠️ 이 함수로 운영 여부를 판단하지 않는다 — 운영은 `assert_audience_match` 로
      **명시 대조**해야 한다. 여기서 `not is_preview(x)` 를 운영으로 읽으면 오타가
      운영이 된다."""
    return normalize_audience(audience) == AUDIENCE_PREVIEW


def audience_for_state(state: Any) -> str:
    """릴리스 상태 → 그 판이 발급할 수 있는 **유일한** 청중.

    ★★★ 후보는 Preview 만, 운영은 운영만. 둘 다 되는 상태는 없다.
    ⚠️ 모르는 상태는 빈 문자열이다 — 호출부가 거부한다. 「모르면 운영」이면 아직
      승인되지 않은 판이 운영 데이터를 만진다."""
    from core.program_lifecycle import ACTIVE, DEPRECATED

    s = str(state or "").strip().lower()
    if s == STATE_CANDIDATE:
        return AUDIENCE_PREVIEW
    if s in (ACTIVE, DEPRECATED):
        #: 폐기 예정(`deprecated`)도 «이미 도는 앱» 이다 — 열되 운영 청중이다.
        return AUDIENCE_OPERATIONAL
    return ""


def assert_issuable(*, state: Any, audience: Any) -> None:
    """이 상태의 릴리스에 이 청중의 증명을 낼 수 있는가.

    ⚠️ **후보에 운영 증명을 내지 않는다.** 그러면 검토되지 않은 코드가 운영 데이터를
      만지고, 아무 오류도 나지 않는다.
    ⚠️ **운영 판에 Preview 증명을 내지 않는다.** 그러면 이미 승인된 앱이 조용히 빈
      DB 를 읽고, 사용자는 「데이터가 사라졌다」로 본다."""
    want = assert_audience(audience)
    allowed = audience_for_state(state)
    if not allowed:
        raise PreviewBoundaryError(
            f"이 릴리스 상태로는 증명을 낼 수 없습니다: {state or '(없음)'}")
    if allowed != want:
        raise PreviewBoundaryError(
            f"이 릴리스는 {allowed} 증명만 낼 수 있습니다(요청 {want}) — "
            f"후보 판은 Preview 에서만, 운영 판은 운영에서만 돕니다.")


def db_path(audience: Any) -> str:
    """이 청중이 쓸 **앱 데이터 파일 경로**.

    ★★★ 여기가 물리 분리의 실체다. Preview 는 **다른 파일**을 쓰고, 그 사실은 코드의
      플래그가 아니라 **경로**가 보증한다 — 플래그를 빠뜨려도 운영 데이터에 닿지 않는다.
    ⚠️ 모르는 청중에 운영 경로를 주지 않는다."""
    from core.paths import data_path

    if is_preview(audience):
        return data_path("app_data_preview.db")
    if normalize_audience(audience) == AUDIENCE_OPERATIONAL:
        return data_path("app_data.db")
    raise PreviewBoundaryError(
        f"알 수 없는 청중에 데이터 경로를 줄 수 없습니다: {audience or '(없음)'}")


def assert_preview_context(entity_mode: Any) -> None:
    """Preview 실행의 조직 문맥은 `SYNTHETIC_TEST` 하나뿐이다.

    ⚠️ `REAL` 로 Preview 를 돌리면 승인 전 판이 만든 숫자가 실적으로 읽힌다. 그리고
      그 화면은 오류를 내지 않는다."""
    mode = str(entity_mode or "").strip()
    if mode != ENTITY_MODE_SYNTHETIC:
        raise PreviewBoundaryError(
            f"Preview 는 {ENTITY_MODE_SYNTHETIC} 문맥에서만 돕니다(현재 "
            f"{mode or '(없음)'}) — 실제 조직 문맥으로 미리보기를 돌리면 승인 전 판이 "
            f"만든 숫자가 실적으로 읽힙니다.")


_preview_service: Optional[Any] = None


def preview_app_data():
    """Preview 전용 `AppDataService`. **운영과 다른 파일**을 연다.

    ★ 지연 생성한다 — import 만으로 파일을 만들지 않는다(운영 저장소와 같은 규칙).
    ⚠️ 운영 싱글턴을 재사용하지 않는다. 재사용하면 「경로만 바꾼 같은 객체」가 되고,
      한쪽에서 경로를 되돌리면 다른 쪽이 조용히 따라간다."""
    global _preview_service
    if _preview_service is None:
        from core.app_data import AppDataService
        from core.app_data_store import AppDataStore

        _preview_service = AppDataService(AppDataStore(db_path=db_path(AUDIENCE_PREVIEW)))
    return _preview_service


def app_data_for(audience: Any):
    """이 청중이 만질 수 있는 데이터 평면 하나.

    ★★★ 호출부가 «어느 DB 인가» 를 스스로 고르지 않게 한다 — 고르게 두면 언젠가
      한 곳이 잘못 고르고, 그 한 곳이 곧 경계 위반이다."""
    if is_preview(audience):
        return preview_app_data()
    if normalize_audience(audience) == AUDIENCE_OPERATIONAL:
        from core.app_data import app_data_service

        return app_data_service
    raise PreviewBoundaryError(
        f"알 수 없는 청중입니다: {audience or '(없음)'}")
