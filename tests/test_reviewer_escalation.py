"""★★★ 리뷰어가 **수렴하지 않으면 PM 으로 올린다.** (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

`CRM003` 의 `E2E-05` 가 리뷰 왕복 8회를 소진하고 `FAILED_REVIEW` 로 죽었다. 마지막
리뷰 의견은 이랬다:

    성능 항목(응답 시간 2초 이내)은 **개발팀의 통제 범위를 벗어나는** 근본적인
    제약사항으로 인해 충족이 어렵습니다. 개발팀은 측정 로직(`fetchTimeMs`)까지
    구현했으나, 호스트…

★ 리뷰어가 **옳다.** 앱이 통제할 수 없는 비기능 요구를 증명하라는 태스크다.
  그런데 「통제 밖이다」를 기록할 자리가 없어 재작업만 반복했다.

## 통제는 **이미 있었다** — 매칭이 너무 빡빡했다

`ESCALATE_PM` 경로도, 자동 상신도, 프롬프트 안내도 전부 있었다. 자동 상신의 반복 판정이
**앞 200자 완전 일치**였던 것이 문제다. 리뷰어는 매 회차 표현을 조금씩 바꾼다:

    1회차  「…일부 항목이 미흡합니다. 1. **성능 - … 3초 이내 응답 시간 검증**: …」
    3회차  「…**여전히** 일부 항목이 미흡합니다. 1. **성능 - … 3초 이내 …**: …」

「여전히」 한 낱말 때문에 다른 지적으로 셌고, 상신이 **한 번도 발동하지 않았다.**

## 두 겹으로 고친다

  ① **유사도**(`difflib`) — 실측으로 문턱을 잡았다. 같은 지적 0.49 · 다른 지적 0.14.
     짐작으로 0.75 를 넣었더니 실제 반복을 못 잡았다 — 상수는 재 봐야 한다.
  ② **홉 바닥** — 유사도가 놓쳐도 상한 전에 올린다. 상한에서 죽는 것보다 상신이
     **언제나** 낫다: 죽으면 아무도 못 고치고, 상신하면 PM 이 요구를 조정할 수 있다.
"""
import json
import re

import pytest

from nodes.execution import _repeat_count

#: `CRM003` E2E-05 의 **실제** 재작업 이력에서 그대로 가져왔다. 바꾸지 않는다.
_R1 = ("태스크 E2E-05의 비기능 요구사항 검증 결과, 일부 항목이 미흡합니다.\n\n"
       "1.  **성능 - 거래처 목록 조회 및 검색 시 3초 이내 응답 시간 검증**: "
       "`useCustomers` 훅에서 `customers.list` 호출 시 `isLoading` 상태를 관리하고 있으나")
_R2 = ("1. **FR-006 (거래처 검색) 및 FR-007 (거래처 필터링) 기능 미흡:**\n"
       "   - `CustomerList.tsx`에서 검색 및 필터링 로직이 `useCustomers` 훅의 "
       "`searchCustomers` 및 `filterCustomers` 함수를 호출하여")
_R3 = ("E2E-05 태스크의 비기능 요구사항 검증 결과, 여전히 일부 항목이 미흡합니다.\n\n"
       "1.  **성능 - 거래처 목록 조회 및 검색 시 3초 이내 응답 시간 검증**: "
       "`useCustomers` 훅에서 `responseTime`을 측정하고 UI에 표시하고 있으나")


# ── ① 유사도가 실제 반복을 잡는가 ───────────────────────────────────────

def test_실제_반복_지적을_잡는다():
    """★★★ **이 파일의 요지.** 종전 규칙(앞 200자 완전 일치)은 이것을 못 잡았다."""
    n, why = _repeat_count(_R3, [_R1, _R2])
    assert n >= 1, f"같은 지적을 반복으로 세지 못한다 ({why})"


def test_종전_완전일치_규칙이었다면_못_잡았다():
    """★★★ 대조군 — 「고쳤다」가 아니라 **무엇을 고쳤는지**를 고정한다.

    ⚠️ 이 시험이 없으면 다음 사람이 유사도를 완전 일치로 되돌려도 아무도 모른다."""
    def _old(t, hist):
        n = re.sub(r"\s+", " ", t).strip().lower()[:200]
        return sum(1 for h in hist
                   if re.sub(r"\s+", " ", h).strip().lower()[:200] == n)

    assert _old(_R3, [_R1, _R2]) == 0, "종전 규칙이 이미 잡았다면 이 변경의 근거가 없다"


def test_다른_지적은_반복으로_세지_않는다():
    """★★★ 문턱을 낮추면 **고칠 수 있는 것까지 상신**된다.

    ⚠️ 실측: 서로 다른 지적끼리는 0.137·0.140 이었다. 0.45 문턱은 그 위에 있다."""
    assert _repeat_count(_R2, [_R1])[0] == 0
    assert _repeat_count("빌드 실패: 괄호가 맞지 않습니다", [_R1, _R2, _R3])[0] == 0


def test_빈_지적은_세지_않는다():
    assert _repeat_count("", [_R1])[0] == 0
    assert _repeat_count("   ", [_R1])[0] == 0


def test_문턱이_실측_구간_안에_있다():
    """★★★ 상수를 **짐작으로** 넣었다가 실제 반복을 못 잡았다.

    ⚠️ 측정값: 같은 지적 0.49 · 다른 지적 0.14. 문턱은 그 사이여야 한다.
      밖으로 나가면 둘 중 하나가 깨진다 — 이 시험이 그때 운다."""
    import config

    thr = getattr(config, "REPEAT_FEEDBACK_SIMILARITY", 0.45)
    assert 0.20 < thr < 0.49, f"문턱 {thr} 이 실측 구간(0.14~0.49) 밖이다"


# ── ② 홉 바닥이 상한 전에 올리는가 ──────────────────────────────────────

def test_홉_바닥이_상한보다_먼저다():
    """★★★ 유사도가 놓쳐도 **상한에서 죽기 전에** 올라야 한다.

    ⚠️ 상한에서 죽으면 `FAILED_REVIEW` 로 아무도 못 고친다. 상신하면 PM 이 요구를
      조정할 수 있다 — 그러므로 상신이 **언제나** 낫다."""
    import config

    cap = getattr(config, "GLOBAL_MAX_SUPERVISOR_HOPS", 8)
    floor = max(2, int(cap * 0.6))
    assert 2 <= floor < cap, f"바닥 {floor} 이 상한 {cap} 전이 아니다"


def test_리뷰어가_홉_바닥으로도_상신한다():
    """⚠️ 유사도 조건만 있으면 표현을 매번 크게 바꾸는 리뷰어에게는 안 걸린다."""
    import inspect

    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    #: ⚠️ 그냥 `ESCALATE_PM` 을 찾으면 **프롬프트 문구**(「3. ESCALATE_PM: 기획서 자체의…」)
    #:   가 먼저 걸린다. 실제 판정이 바뀌는 자리는 대입문이다.
    i = src.index('reviewer_decision = "ESCALATE_PM"')
    around = src[max(0, i - 1500):i + 300]
    assert "hops >=" in around, "홉 바닥 조건이 없다"
    assert "_repeats >=" in around, "반복 조건이 없다"


def test_결정적_게이트는_상신하지_않는다():
    """★★★ 렌더·인증·서버·합성데이터 게이트는 **개발자가 고칠 수 있는** 것이고,
    고칠 방법까지 함께 준다. 그것을 PM 에게 올리면 사람이 대신 코드를 고쳐야 한다.

    ⚠️ 상신은 **LLM 리뷰어의 REWORK_DEV** 에만 건다 — 그 위 결정적 게이트들은
      `return` 으로 먼저 빠져나가므로 이 자리에 도달하지 않는다."""
    import inspect

    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    esc = src.index('reviewer_decision = "ESCALATE_PM"')
    for gate in ("app_local_auth", "app_builds_server", "synthetic_data_as_real"):
        assert src.index(gate) < esc, (
            f"{gate} 게이트가 상신 로직 뒤에 있다 — 고칠 수 있는 결함이 PM 으로 간다")
