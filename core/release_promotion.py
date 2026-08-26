"""[I-4 7 / Wave F-2] ACTIVE 원자 승격 — **후보를 운영으로 올리는 단 하나의 문.**

## 이 파일이 지키는 것 넷

★★★ ① **승격 시점에 다시 본다.** 계약이 승인됐다는 것은 «그때» 의 사실이다. 그 뒤에
  계약이 개정되거나, 물질화가 어긋나거나, 원천 인증이 회수될 수 있다. 승격은 그
  변화들의 **뒤에** 오므로, 승격하는 순간의 사실로 판단해야 한다.

★★★ ② **하나라도 어긋나면 아무것도 바꾸지 않는다.** 「대체로 괜찮으니 올리자」는
  없다. 부분 승격은 «운영이라고 적혀 있는데 계약과 다른 판» 을 만들고, 그 상태는
  오류를 내지 않는다.

★★★ ③ **실패해도 이전 ACTIVE 는 그대로다.** 새 판을 올리려다 실패했다고 이미 도는
  앱이 멈추면, 승격을 시도하는 것 자체가 위험한 일이 된다 — 그러면 아무도 안 한다.

★★★ ④ **승격은 옛 Preview 증명을 무효로 만든다.** 상태가 바뀌면 청중이 바뀌고,
  런타임이 요청마다 대조하므로(F-1) 그 증명은 곧바로 «다시 열어야 하는» 것이 된다.
  ⚠️ 여기서 토큰을 지우지 않는다 — 지우는 방식은 «지우기를 빠뜨린 경로» 를 남긴다.
    상태에서 유도되는 대조가 **빠뜨릴 수 없는 방식**이다.

## 왜 «게시 = 후보» 를 이 파일과 같은 커밋에서 켜는가

⚠️⚠️ 게시 기본값 전환과 승격 경로를 나누면, 그 사이에 만들어진 릴리스가 **전부 후보로
  갇힌다.** 올릴 방법이 없기 때문이다. 사용자는 그것을 「앱이 고장 났다」로 본다.
"""
from typing import Any, Dict, List, NamedTuple, Optional


class PromotionError(Exception):
    """승격할 수 없다. **아무것도 바꾸지 않은 상태**로 던진다."""


class Check(NamedTuple):
    """검사 하나의 결과. `ok=False` 면 `reason` 이 사람에게 보일 문장이다."""
    name: str
    ok: bool
    reason: str = ""


class Verdict(NamedTuple):
    ok: bool
    checks: List[Check]

    @property
    def blocking(self) -> List[Check]:
        return [c for c in self.checks if not c.ok]

    def summary(self) -> str:
        return " / ".join(f"{c.name}: {c.reason}" for c in self.blocking)


#: ★ 검사 이름은 **닫힌 목록**이다. 늘어나면 여기에 적고, 적지 않으면 시험이 잡는다.
#: ⚠️ 이름만 늘리고 구현을 안 하면 「검사했다」는 거짓 기록이 된다 — 그래서 목록과
#:   구현을 같은 곳에서 만든다(`run_checks` 가 이 순서로 돌린다).
CHECK_STATE = "릴리스 상태"
CHECK_CONTRACT = "계약↔물질화"
CHECK_STATIC = "정적 인증 검사"
CHECK_REVIEW = "계약 승인"
CHECK_READINESS = "데이터 준비도"
CHECK_NAMES = (CHECK_STATE, CHECK_CONTRACT, CHECK_STATIC, CHECK_REVIEW, CHECK_READINESS)


def _check_state(release_id: str, lifecycle: Any) -> Check:
    """후보만 승격한다.

    ⚠️ 이미 운영인 판을 다시 승격하면 이력에 «두 번 올렸다» 가 남고, 어느 쪽이 지금
      도는 판인지 흐려진다. 폐기된 판을 되살리는 것도 여기서 하지 않는다 — 그것은
      `reactivate` 의 일이고 사유·이력이 다르다."""
    from core.program_lifecycle import CANDIDATE

    try:
        st = str(lifecycle.get_status(release_id).get("status", ""))
    except Exception as e:
        #: ⚠️ 「못 읽었으니 통과」가 곧 통제 없음이다.
        return Check(CHECK_STATE, False, f"상태를 읽을 수 없습니다: {str(e)[:100]}")
    if st != CANDIDATE:
        return Check(CHECK_STATE, False,
                     f"후보 판만 승격할 수 있습니다(현재 {st or '(기록 없음)'}).")
    return Check(CHECK_STATE, True)


def _check_contract(release: Any, release_id: str, plane: Any = None) -> Check:
    """계약 원문과 물질화가 **지금도** 맞는가.

    ★ 승인 시점이 아니라 **승격 시점**에 본다 — 그 사이에 계약이 개정되거나 결속이
      바뀌었을 수 있고, 그때 올리면 「승인받은 것과 다른 판」이 운영이 된다.

    ★★★ [F-3] `plane` 은 **그 판이 지금 사는 평면**이다. 후보는 Preview 평면에
      물질화돼 있으므로(F-1·F-2), 운영 평면으로 대조하면 「계약에 있는 데이터셋이
      물질화되지 않았습니다」로 **모든 승격이 막힌다** — 종단 카나리가 그 자리에서
      멈춰 드러났다."""
    from core import app_contract_gate

    try:
        v = app_contract_gate.evaluate(release, release_id, plane=plane)
    except Exception as e:
        return Check(CHECK_CONTRACT, False, f"판정할 수 없습니다: {str(e)[:100]}")
    if not v.ok:
        return Check(CHECK_CONTRACT, False, " / ".join(v.reasons)[:300])
    return Check(CHECK_CONTRACT, True)


def _check_review(release: Any) -> Check:
    """실행 가능한 App-in-App 이면 **승인된 계약이 있어야 한다.**

    ⚠️ `app_contract_gate` 가 이미 같은 것을 보지만, 그쪽은 «레거시는 통과» 경로를
      갖고 있다. 승격은 **새 판을 운영으로 올리는 일**이므로 레거시 면제를 쓰지 않는다 —
      면제는 이미 도는 것을 지키기 위한 것이지 새로 올리기 위한 것이 아니다."""
    from core import app_contract_gate

    if not app_contract_gate.is_executable_app_in_app(release):
        return Check(CHECK_REVIEW, True)
    contract = app_contract_gate.release_contract(release)
    if not contract:
        return Check(CHECK_REVIEW, False,
                     "실행 가능한 앱인데 릴리스에 승인된 계약이 없습니다 — 레거시 면제는 "
                     "이미 도는 판을 지키기 위한 것이지 새로 올리기 위한 것이 아닙니다.")
    if str((contract.get("approval") or {}).get("status", "")) != "APPROVED":
        return Check(CHECK_REVIEW, False, "계약이 승인되지 않았습니다.")
    return Check(CHECK_REVIEW, True)


def _check_static(code_paths: Optional[List[str]]) -> Check:
    """생성 코드가 플랫폼 인증을 **직접** 만지지 않는가.

    ⚠️ 검사할 경로가 **없으면 통과가 아니다.** 「볼 것이 없었다」와 「봤는데 깨끗했다」는
      다른 사실이고, 전자를 통과로 읽으면 이 게이트는 장식이 된다."""
    from nodes.utils import platform_auth_checker as checker

    if not code_paths:
        return Check(CHECK_STATIC, False,
                     "검사할 코드 경로가 없습니다 — 보지 못한 것을 통과로 세지 않습니다.")
    try:
        out = checker.scan_paths(list(code_paths))
    except Exception as e:
        return Check(CHECK_STATIC, False, f"검사할 수 없습니다: {str(e)[:100]}")
    if out.get("unreadable"):
        return Check(CHECK_STATIC, False,
                     f"읽지 못한 파일이 {len(out['unreadable'])}개 있습니다 — "
                     f"검사하지 못한 것을 통과로 세지 않습니다.")
    #: ★★★ [2026-08-27 실측] **한 건도 안 봤으면 통과가 아니다.**
    #:
    #: ⚠️⚠️ 바로 위 주석은 「검사할 경로가 없으면 통과가 아니다」라고 말하는데, 실제로
    #:   막힌 자리는 그게 아니었다 — 경로는 **있었고**(라이브러리 릴리스 디렉터리),
    #:   그 안에 코드가 한 줄도 없었다. `scanned == 0` 이라 findings 가 비었고,
    #:   `ok = not blocking` 이 그대로 `True` 가 됐다.
    #:   결과: 자체 로그인 폼과 비밀번호 비교가 든 앱이 **운영으로 승격됐다.**
    #:   게시 때 같은 검사기가 워크스페이스를 훑어 차단 3건을 이미 찾아 둔 상태였다.
    #: ★ 「빈 결과」와 「깨끗한 결과」를 가른다 — 통제가 자기가 볼 것이 있었는지를
    #:   먼저 확인해야 통제다.
    if not out.get("scanned"):
        return Check(CHECK_STATIC, False,
                     "검사한 파일이 0개입니다 — 생성 코드를 찾지 못했습니다. "
                     "보지 못한 것을 통과로 세지 않습니다.")
    if not out.get("ok"):
        first = (out.get("blocking") or [{}])[0]
        return Check(CHECK_STATIC, False,
                     f"차단 신호 {len(out.get('blocking') or [])}건"
                     f"({first.get('signal', '')} @ {first.get('path', '')}).")
    return Check(CHECK_STATIC, True)


def _check_readiness(readiness_state: Any) -> Check:
    """이 앱이 읽는 업무 데이터가 **지금 준비돼 있는가.**

    ⚠️ 준비되지 않은 데이터 위에 운영 앱을 올리면, 그 앱은 첫날부터 「읽을 수 없음」을
      그린다. 그리고 사용자는 앱이 고장 났다고 본다 — 원인은 데이터인데.
    ★ 판정하지 않는다(그것은 `data_preparation.readiness` 의 일이다). 여기서는
      **넘겨받은 판정을 읽을 뿐**이고, 넘어오지 않으면 승격하지 않는다."""
    from core.data_preparation import readiness as rd

    if readiness_state is None:
        #: 이 릴리스가 업무 데이터를 안 쓰는 경우는 호출부가 «해당 없음» 을 명시한다.
        return Check(CHECK_READINESS, False,
                     "데이터 준비도를 확인하지 못했습니다 — 확인하지 못한 것을 "
                     "«준비됨» 으로 세지 않습니다.")
    if readiness_state is NOT_APPLICABLE:
        #: ⚠️ [변이 검사 실측] 여기에 `or readiness_state is None` 을 더해도 시험이
        #:   잡지 못한다 — **바로 위 분기가 `None` 을 먼저 돌려보내기 때문**이다.
        #:   구조상 관측 불가라 가짜 시험을 짓지 않았다. 다만 위 분기를 지우면
        #:   이 자리가 곧 「확인 못함이 조용히 면제되는」 구멍이 되므로, 둘의 **순서**가
        #:   계약이라는 사실을 여기 적어 둔다.
        return Check(CHECK_READINESS, True)
    status = str((readiness_state or {}).get("status", ""))
    if status != rd.INSTANCE_READY:
        blocked = (readiness_state or {}).get("blocked_outputs") or []
        first = blocked[0].get("user_message", "") if blocked else ""
        return Check(CHECK_READINESS, False,
                     f"업무 데이터가 아직 준비되지 않았습니다({status or '(모름)'})."
                     + (f" {first}" if first else ""))
    return Check(CHECK_READINESS, True)


#: ★ 「이 앱은 업무 데이터를 쓰지 않는다」를 **명시**하는 표식.
#: ⚠️ `None` 과 구분한다 — `None` 은 「확인하지 못했다」이고 그것은 통과가 아니다.
class _NotApplicable:
    def __repr__(self) -> str:                 # pragma: no cover - 표시용
        return "NOT_APPLICABLE"


NOT_APPLICABLE = _NotApplicable()


#: ★ 「이 앱은 업무 데이터를 쓰지 않는다」를 **봉인값에도** 그대로 적는다.
#: ⚠️ 빈 문자열로 적으면 「봉인하지 않았다」와 구분되지 않는다.
DATA_NOT_APPLICABLE = "NOT_APPLICABLE"


def data_fingerprint(readiness_state: Any) -> str:
    """이 승격이 **어느 데이터 판 위에서** 일어났는가.

    ★★★ 승격 검사는 「지금 준비됐는가」에 답한다. 그런데 승격 뒤에 원천이 바뀌면
      도는 앱은 «승인받은 것과 다른 숫자» 를 그리기 시작하고, **아무 오류도 나지
      않는다.** 그래서 승인 시점의 판 집합을 여기서 못박는다 — 나중에 「그때 그
      데이터가 맞나」에 답할 수 있어야 하기 때문이다.

    ⚠️ 지문은 `baseline_build.fingerprint_for` 를 그대로 쓴다. 여기서 따로 계산하면
      같은 판 집합이 두 곳에서 다른 값을 내고, 대조가 곧 거짓말이 된다.
    ⚠️ 준비되지 않은 데이터셋의 판은 **넣지 않는다** — 승격이 선 근거는 준비된 것뿐이다.
    """
    from core.baseline_build import fingerprint_for
    from core.data_preparation import readiness as rd

    if readiness_state is NOT_APPLICABLE:
        return DATA_NOT_APPLICABLE
    if not readiness_state:
        #: 「확인하지 못했다」는 봉인할 것이 없다. 검사(`_check_readiness`)가 이미
        #: 막지만, 여기서도 빈 값을 지어내지 않는다.
        return ""
    ids = [str(d.get("snapshot_id") or "")
           for d in (readiness_state.get("datasets") or [])
           if str(d.get("state") or "") in rd.OFFICIAL_STATES
           and str(d.get("snapshot_id") or "")]
    return fingerprint_for(ids) if ids else ""


def run_checks(*, release: Any, release_id: str, lifecycle: Any,
               code_paths: Optional[List[str]] = None,
               readiness_state: Any = None, plane: Any = None) -> Verdict:
    """다섯 가지를 **전부** 본다. 하나라도 어긋나면 승격하지 않는다.

    ★ 첫 실패에서 멈추지 않는다 — 사용자가 같은 화면을 다섯 번 보게 하지 않으려면
      한 번에 다 알려 줘야 한다."""
    checks = [
        _check_state(release_id, lifecycle),
        _check_contract(release, release_id, plane),
        _check_static(code_paths),
        _check_review(release),
        _check_readiness(readiness_state),
    ]
    #: 목록과 구현이 갈라지지 않게 — 이름이 빠지면 시험이 잡는다.
    assert {c.name for c in checks} == set(CHECK_NAMES)
    return Verdict(ok=all(c.ok for c in checks), checks=checks)


def promote(*, release: Any, release_id: str, lifecycle: Any, actor: str,
            code_paths: Optional[List[str]] = None,
            readiness_state: Any = None, reason: str = "", plane: Any = None,
            on_promote: Any = None) -> Dict[str, Any]:
    """후보 → 운영. **검사가 전부 통과할 때만 상태를 바꾼다.**

    ★★★ 검사와 전이를 나눈 이유가 ②·③ 이다 — 검사에서 던지면 상태는 손대지 않았고,
      이전 ACTIVE 도 그대로다.

    ⚠️ 승격 뒤에는 그 판으로 발급된 Preview 증명이 전부 «다시 열어야 하는» 것이 된다.
      여기서 토큰을 지우지 않는다 — 지우는 방식은 «지우기를 빠뜨린 경로» 를 남기고,
      상태에서 유도되는 대조가 빠뜨릴 수 없는 방식이다(F-1)."""
    if not str(actor or "").strip():
        raise PromotionError(
            "승격자 식별이 필요합니다 — 누가 운영으로 올렸는지 모르는 승격은 "
            "감사 대상이 될 수 없습니다.")

    verdict = run_checks(release=release, release_id=release_id, lifecycle=lifecycle,
                         code_paths=code_paths, readiness_state=readiness_state,
                         plane=plane)
    if not verdict.ok:
        raise PromotionError(verdict.summary())

    #: ★★★ [I-4 7 / F-3] **승격과 바인딩 전환의 원자성.**
    #:
    #: 후보는 Preview 평면에 물질화돼 있다. 운영으로 올린다는 것은 「그 계약을 운영
    #: 평면에도 물질화한다」는 뜻이고, 그 일이 실패하면 **상태를 바꾸지 않는다** —
    #: 그러지 않으면 「운영이라고 적혀 있는데 읽을 데이터가 없는 판」이 생긴다.
    #:
    #: ⚠️ 상태 전이보다 **먼저** 한다. 순서를 바꾸면 물질화 실패가 이미 운영이 된 판을
    #:   남기고, 그 판은 첫 요청부터 「물질화되지 않았습니다」로 막힌다.
    if on_promote is not None:
        try:
            on_promote()
        except Exception as e:
            raise PromotionError(f"운영 평면 물질화에 실패했습니다: {str(e)[:200]}")

    from core.program_lifecycle import ACTIVE

    #: ★★★ **무엇 위에서 올렸는지를 함께 못박는다.** 검사만 하고 지나가면 「그때
    #:   준비돼 있었다」는 말은 남지만 「그때 무엇이었나」는 남지 않는다.
    sealed = data_fingerprint(readiness_state)
    row = lifecycle.set_status(release_id, ACTIVE, actor=actor,
                               reason=reason or "Preview 확인 후 운영 승격",
                               data_fingerprint=sealed)
    return {"release_id": release_id, "status": ACTIVE,
            "data_fingerprint": sealed,
            "checks": [c._asdict() for c in verdict.checks], "lifecycle": row}
