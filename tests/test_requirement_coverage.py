"""★★★ 만들 수 없는 요구가 **말없이 사라지면 안 된다.** (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

`CRM002` 의 RFP 에 `FR-008`(사용자 권한 제어)이 **Must** 로 있었고 WBS 에 그 태스크
(`E2E-06`)도 생겼다. 그런데 승인된 계약에는 —

    FR-009 (파일 첨부)  → `unsupported_requirements` 에 기록
                          (「데이터 평면에 바이너리가 없다」 · user_decision=WAIT)
    FR-008 (권한 제어)  → **능력에도 없고 미지원 목록에도 없다**

아무도 「이 요구는 만들 수 없습니다」라고 말하지 않았다. **요구가 증발했다.**
만들 수 없는 것을 말없이 지우는 것은 만들었다고 말하는 것 다음으로 나쁘다 —
사용자는 그것이 만들어지는 줄 알고 인수한다.

## 이 검사가 강제하는 것은 «만들라» 가 아니라 «말하라» 다

능력으로 다루든 미지원으로 적든 **둘 다 통과**한다. 못 만들면 못 만든다고 적으면 된다.

## ⚠️⚠️ [2026-08-27 정정] 「오탐이 없다」고 썼는데 **틀렸다**

처음 이 파일에는 「집합 비교라 오탐이 없다」고 적혀 있었다. 그리고 `CRM003` 의 `E2E-04`
가 바로 그 오탐에 걸렸다 —

    태스크    FR-003(상세 조회)·FR-004(수정)·FR-005(삭제)
    초안 선언  FR-002 → app_data.read   ← 상세 조회가 쓸 능력이 **이미 여기**
              FR-004 → app_data.update
              FR-005 → app_data.delete

**한 능력이 여러 요구를 덮는 것은 정상**이다. 요구마다 행을 만들라고 강요하면 마찰이다.
`CRM002` 의 `FR-008` 과는 다르다 — 그건 `auth.local_roles` 가 필요한데 **선언될 수도
없는** 것이었다. 이 검사는 문자열만 보므로 둘을 가르지 못한다.

★ 그래서 **차단이 아니라 경고**로 내렸다. 해악은 「사라지는 것」이 아니라 「**말없이**」다.
⚠️ 만들 수 없는 요구를 애초에 막는 것은 **입구**(`requirement_normalizer`)의 일이다.
"""
import pytest

from core.project_contract_aggregator import _coverage_errors, _task_requirements


def _task(tid="T1", **kw):
    return {"task_id": tid, **kw}


def _intent(ref, cap="app_data.read"):
    return {"requirement_ref": ref, "capability": cap}


# ── 잡아야 하는 것 ───────────────────────────────────────────────────────

def test_계약이_안_다룬_요구를_잡는다():
    """★★★ **이 파일의 요지.** `CRM002` 의 FR-008 이 정확히 이 모양이었다."""
    errs = _coverage_errors(
        [_task("E2E-06", title="사용자 권한 기반 기능 제어 구현",
               goal="FR-008(사용자 권한 기반 기능 제어) 기능을 구현하여…")],
        [_intent("FR-001"), _intent("FR-002")])
    assert errs and "FR-008" in errs[0], errs


def test_여러_개면_모두_말한다():
    errs = _coverage_errors(
        [_task("T1", goal="FR-010 과 FR-011 을 구현한다")], [_intent("FR-010")])
    assert errs and "FR-011" in errs[0] and "FR-010" not in errs[0], errs


# ── 통과해야 하는 것 — 오탐이 나면 이 검사는 꺼진다 ─────────────────────

def test_능력으로_다루면_통과한다():
    assert _coverage_errors([_task("T1", goal="FR-001 을 구현한다")],
                            [_intent("FR-001")]) == []


def test_미지원으로_적어도_통과한다():
    """★★★ 강제하는 것은 「만들라」가 아니라 **「말하라」** 다.

    ⚠️ 못 만드는 요구까지 능력으로 적으라고 하면, 에이전트는 **못 만드는 것을 만들 수
      있다고 적는다** — 그것이 훨씬 나쁘다."""
    assert _coverage_errors(
        [_task("T1", goal="FR-009 파일 첨부")],
        [{"requirement_ref": "FR-009", "capability": "file.upload",
          "user_decision": "WAIT"}]) == []


def test_요구를_안_적은_태스크는_통과한다():
    """⚠️ FR 을 안 적은 태스크도 정상이다(설정·통합 태스크). 없는 것을 요구하지 않는다."""
    assert _coverage_errors([_task("T1", goal="프로젝트 기본 구조를 세운다")], []) == []


def test_out_of_scope_의_요구는_요구하지_않는다():
    """★★★ `out_of_scope` 는 「이 태스크가 **안 하는** 일」이다.

    ⚠️ 섞으면 하지 않기로 한 것까지 계약에 요구하게 되고, 그러면 에이전트는 하지 않기로
      한 것을 선언한다 — 통제가 정반대로 작동한다."""
    t = _task("T1", goal="FR-001 을 구현한다",
              out_of_scope=["FR-008 사용자별 권한 생성/수정 (회사 조직 체계에 따름)"])
    assert "FR-008" not in _task_requirements(t)
    assert _coverage_errors([t], [_intent("FR-001")]) == []


def test_scope_의_요구는_함께_본다():
    """★ `goal` 에만 있는 것이 아니다 — `scope` 항목에 적힌 FR 도 그 태스크의 것이다."""
    t = _task("T1", goal="목록 화면", scope=["FR-005 조회", "FR-006 검색"])
    assert _task_requirements(t) == {"FR-005", "FR-006"}


# ── 실제로 걸려 있는가 ──────────────────────────────────────────────────

def test_합산기가_이_검사를_부른다():
    """⚠️⚠️ 검사기를 만들어 두고 부르는 곳이 없으면 없는 것과 같다 —
    이 저장소가 이번 세션에만 세 번 겪은 모양이다."""
    import inspect

    from core import project_contract_aggregator as agg

    assert "_coverage_errors" in inspect.getsource(agg.aggregate), (
        "합산기가 요구 커버리지를 보지 않는다")


def test_차단이_아니라_경고다():
    """★★★ [2026-08-27 실측 — 내 오탐] **막지 않는다.**

    ⚠️⚠️ 처음에는 `errors` 에 넣어 막았고, `CRM003` 의 `E2E-04` 가 걸렸다 —
      「계약이 FR-003 를 다루지 않습니다」. 그런데 실제로는 덮여 있었다:
      `FR-003`(상세 조회)이 쓸 `app_data.read` 가 **`FR-002` 로 이미 선언**돼 있었다.
      **한 능력이 여러 요구를 덮는 정상적인 경우**다.
    ★ 해악은 「사라지는 것」이 아니라 **「말없이」** 다 — 말은 하되 막지 않는다.
    ⚠️ 만들 수 없는 요구를 애초에 막는 것은 **입구**(`requirement_normalizer`)의 일이다.
      이 검사는 그 뒤의 관측이지 이중 차단기가 아니다.
    """
    import inspect

    from core import project_contract_aggregator as agg

    src = inspect.getsource(agg.aggregate)
    i = src.index("_coverage_errors")
    around = src[i:i + 200]
    assert "errors.extend" not in around, (
        "커버리지 미달을 오류로 올린다 — 정상적인 다중 FR 선언을 막는다")
    assert "print(" in around, "경고로도 말하지 않으면 «말없이» 가 그대로다"


def test_초안이_없는_태스크는_두_번_말하지_않는다():
    """★ 초안이 아예 없으면 `missing` 이 이미 말한다. 같은 사실을 두 번 말하면
    사람은 두 가지 문제로 읽는다."""
    import inspect

    from core import project_contract_aggregator as agg

    src = inspect.getsource(agg.aggregate)
    i = src.index("_coverage_errors")
    assert "included" in src[max(0, i - 400):i], (
        "커버리지를 «포함된 태스크» 로 좁히지 않는다 — 초안 없는 태스크까지 걸린다")
