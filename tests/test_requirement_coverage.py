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
★ 집합 비교라 오탐이 없다 — 「태스크가 자기 것이라 말한 FR」과 「계약이 다룬 FR」의
  차집합이다. 문구를 해석하지 않는다.
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


def test_초안이_없는_태스크는_두_번_말하지_않는다():
    """★ 초안이 아예 없으면 `missing` 이 이미 말한다. 같은 사실을 두 번 말하면
    사람은 두 가지 문제로 읽는다."""
    import inspect

    from core import project_contract_aggregator as agg

    src = inspect.getsource(agg.aggregate)
    i = src.index("_coverage_errors")
    assert "included" in src[max(0, i - 400):i], (
        "커버리지를 «포함된 태스크» 로 좁히지 않는다 — 초안 없는 태스크까지 걸린다")
