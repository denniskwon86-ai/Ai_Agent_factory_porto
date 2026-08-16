"""★★★ [I-4 4단계 · 설계 §3·§13] Contract Review Gate.

이 시험이 전제하는 것: **조직도를 쓰지 않는다.** 판정은 순수 함수이고, 원장은
conftest 가 `tmp_path` 로 격리한 `decision_ledger.db` 를 쓴다. 그래서 `seeded_org`
를 붙이지 않는다 — 권한 경계를 보는 시험이 아니다.

규칙은 두 줄이다: 최초 계약 또는 지문 변경이면 사람이 보고, 지문이 그대로면
자동 통과한다. 그래서 **이 파일의 대부분은 「같다」의 정의를 지킨다.**
"""
import pytest

from core import contract_review_gate as gate

FP_A = "a" * 64
FP_B = "b" * 64


def _ev(**kw):
    #: 기본은 «승인된 계약이 그대로 있는» 상태다 — 여기서 무엇을 하나씩 무너뜨려
    #: 게이트가 열리는지를 본다.
    base = dict(requires_contract=True, compiled_fingerprint=FP_A,
                approved_fingerprint=FP_A, contract_status=gate.APPROVED)
    base.update(kw)
    return gate.evaluate(**base)


# ── 두 줄의 규칙 ─────────────────────────────────────────────────────────
def test_unchanged_fingerprint_passes_without_a_human():
    d = _ev()
    assert d.verdict == gate.AUTO_PASS
    assert d.needs_human is False


def test_first_contract_requires_review():
    d = _ev(approved_fingerprint="")
    assert d.verdict == gate.REVIEW_REQUIRED
    assert d.needs_human is True
    assert "최초" in d.reason


def test_changed_fingerprint_requires_review():
    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A)
    assert d.verdict == gate.REVIEW_REQUIRED
    assert d.needs_human is True
    # 화면이 «무엇이 바뀌었나» 를 말할 수 있어야 한다
    assert FP_A[:12] in d.reason and FP_B[:12] in d.reason


def test_non_contract_artifact_is_not_applicable():
    d = _ev(requires_contract=False, compiled_fingerprint="", approved_fingerprint="")
    assert d.verdict == gate.NOT_APPLICABLE
    assert d.needs_human is False


# ── 가장 조용한 구멍: 「둘 다 비었으니 같다」 ────────────────────────────
def test_no_contract_at_all_is_blocked_not_auto_passed():
    """★★★ 계약도 승인도 없을 때 **자동 통과가 아니다.**

    ⚠️ 지문을 그냥 `==` 로 비교하면 `"" == ""` 이 참이 되어 「바뀐 것이 없으니 통과」
      가 된다 — 그 결과는 계약 대상 태스크가 **계약 없이 빌드되는 것**이다.
      [I-4 3단계] 에서 봉인이 「그때와 같은가」에만 답한 것과 같은 함정이다."""
    d = _ev(compiled_fingerprint="", approved_fingerprint="")
    assert d.verdict == gate.BLOCKED
    assert d.needs_human is False, "사람을 부를 것이 아니라 컴파일을 먼저 해야 한다"


def test_losing_the_contract_does_not_ride_the_old_approval():
    """⚠️ 승인 지문은 남아 있는데 계약이 사라진 상태. 옛 승인에 얹혀 통과하면,
    계약을 지우는 것이 곧 게이트를 지나는 방법이 된다."""
    assert _ev(compiled_fingerprint="", approved_fingerprint=FP_A).verdict == gate.BLOCKED


@pytest.mark.parametrize("junk", [
    None, "", "   ", "UNAPPROVED", "no-contract", 12345, ["a" * 64],
    "A" * 63,           # 한 글자 짧다
    "z" * 64,           # 16진수가 아니다
    "a" * 65,
])
def test_junk_is_not_a_fingerprint(junk):
    """★ 쓰레기 값 **두 개가 같아도** 「같다」가 아니다.

    ⚠️ 이것이 실제 위험한 이유: 지문 계산이 실패하면 두 자리 모두 같은 실패
      문자열(`""`·`"UNAPPROVED"`)이 들어가기 쉽다. 그대로 비교하면 계산이 깨진
      바로 그때 게이트가 **자동 통과**한다."""
    d = gate.evaluate(requires_contract=True,
                      compiled_fingerprint=junk, approved_fingerprint=junk)
    assert d.verdict == gate.BLOCKED
    assert d.compiled_fingerprint == "" and d.approved_fingerprint == ""


def test_case_and_whitespace_are_absorbed_but_nothing_else():
    d = gate.evaluate(requires_contract=True,
                      compiled_fingerprint="  " + FP_A.upper() + " ",
                      approved_fingerprint=FP_A, contract_status=gate.APPROVED)
    assert d.verdict == gate.AUTO_PASS


def test_status_string_cannot_open_the_gate():
    """⚠️ `app_runtime_contract_status="APPROVED"` 라고 적어 두는 것만으로 지나면,
    상태 문자열을 쓰는 모든 자리가 우회로가 된다. **지문을 믿는다.**"""
    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A,
            contract_status=gate.APPROVED)
    assert d.verdict == gate.REVIEW_REQUIRED


# ── 승인이 «지금도» 유효한가 ─────────────────────────────────────────────
@pytest.mark.parametrize("status", ["", "DRAFT", "COMPILED", "REJECTED", "REVOKED",
                                    "approved ", None, 0, "알 수 없는 값"])
def test_matching_fingerprints_do_not_pass_a_revoked_approval(status):
    """★★★ 지문이 같아도 **승인 상태가 유효하지 않으면** 통과하지 않는다.

    ⚠️ 지문은 「그때와 같은가」에만 답한다 — 그 승인이 **취소·반려됐는지**에는
      답하지 않는다([I-4 3단계] 에서 닫은 것과 같은 종류의 구멍). 상태를 안 보면
      반려된 계약이 반려된 채로 빌드된다."""
    d = _ev(contract_status=status)
    if isinstance(status, str) and status.strip().upper() == "APPROVED":
        # `"approved "` — 공백·대소문자는 흡수한다
        assert d.verdict == gate.AUTO_PASS
        return
    assert d.verdict == gate.REVIEW_REQUIRED
    assert d.needs_human is True


def test_revocation_reopens_the_gate_end_to_end():
    """승인 → 취소 → 다시 검토. 상태 하나만 바꿔도 게이트가 다시 열려야 한다."""
    assert _ev().verdict == gate.AUTO_PASS
    assert _ev(contract_status=gate.COMPILED).verdict == gate.REVIEW_REQUIRED


# ── 상태에서 읽는 경로 ───────────────────────────────────────────────────
class _State:
    app_runtime_contract_fingerprint = FP_A
    approved_contract_fingerprint = FP_A
    app_runtime_contract_status = "APPROVED"


def test_state_object_and_dict_agree():
    """★ 두 진입 경로(객체·dict)가 **같은 답**을 내야 한다. 하나만 시험하면 다른
    하나가 조용히 어긋난다."""
    as_obj = gate.evaluate_state(_State(), requires_contract=True)
    as_dict = gate.evaluate_state(
        {"app_runtime_contract_fingerprint": FP_A,
         "approved_contract_fingerprint": FP_A,
         "app_runtime_contract_status": "APPROVED"}, requires_contract=True)
    assert as_obj == as_dict == gate.evaluate(
        requires_contract=True, compiled_fingerprint=FP_A, approved_fingerprint=FP_A,
        contract_status="APPROVED")


def test_real_project_state_passes_through_the_gate():
    """★ 세 번째 진입 경로 — **실제 `ProjectState`**. 필드 이름이 바뀌면 dict 시험은
    그대로 통과하지만 제품은 조용히 `BLOCKED` 가 된다."""
    from state_models import ProjectState

    st = ProjectState(project_name="p",
                      app_runtime_contract_fingerprint=FP_A,
                      approved_contract_fingerprint=FP_A,
                      app_runtime_contract_status="APPROVED")
    assert gate.evaluate_state(st, requires_contract=True).verdict == gate.AUTO_PASS
    # 기본값 상태(계약 없음)는 막힌다
    assert gate.evaluate_state(ProjectState(project_name="p"),
                               requires_contract=True).verdict == gate.BLOCKED


def test_missing_state_fields_block_rather_than_pass():
    """필드 이름이 바뀌거나 오타가 나면 값이 사라진다 — 그때 열려서는 안 된다."""
    assert gate.evaluate_state({}, requires_contract=True).verdict == gate.BLOCKED


def test_approval_pins_the_fingerprint_it_saw():
    """⚠️ 「승인됨」 플래그만 세우면 다음에 계약이 바뀌어도 플래그가 남아 게이트가
    다시 열리지 않는다. 승인은 **그때 본 지문**을 박는 것이다."""
    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A)
    updates = gate.state_updates_for_approval(d)
    assert updates == {"approved_contract_fingerprint": FP_B,
                       "app_runtime_contract_status": "APPROVED"}
    # 그 값을 되먹이면 이제 자동 통과한다 — 상태까지 함께 되먹여야 한다
    assert _ev(compiled_fingerprint=FP_B,
               approved_fingerprint=updates["approved_contract_fingerprint"],
               contract_status=updates["app_runtime_contract_status"]
               ).verdict == gate.AUTO_PASS


@pytest.mark.parametrize("bad", ["blocked", "auto_pass", "n/a"])
def test_only_a_review_can_be_approved(bad):
    """★★★ 어떤 판정이든 승인으로 바꿔 주면, **계약이 없는 `BLOCKED` 상태에서**
    빈 지문이 승인된 지문으로 박힌다. 그러면 다음 판정은 「지문이 없다」가 아니라
    「승인된 것과 다르다」로 읽히고, 사람은 계약이 있다고 믿는다."""
    d = {"blocked": _ev(compiled_fingerprint=""),
         "auto_pass": _ev(),
         "n/a": _ev(requires_contract=False)}[bad]
    with pytest.raises(gate.GateTransitionError):
        gate.state_updates_for_approval(d)
    with pytest.raises(gate.GateTransitionError):
        gate.state_updates_for_rejection(d)


def test_rejection_clears_the_approved_fingerprint():
    """⚠️ 상태만 되돌리고 승인 지문을 남기면, 다음 판정에서 「지문이 같다」가 먼저
    걸려 자동 통과로 새어 나간다. 반려는 **지문을 비우는 것**이다."""
    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A)
    updates = gate.state_updates_for_rejection(d)
    assert updates == {"approved_contract_fingerprint": "",
                       "app_runtime_contract_status": "COMPILED"}
    after = gate.evaluate(requires_contract=True, compiled_fingerprint=FP_B,
                          approved_fingerprint=updates["approved_contract_fingerprint"],
                          contract_status=updates["app_runtime_contract_status"])
    assert after.verdict == gate.REVIEW_REQUIRED


# ── 원장 ─────────────────────────────────────────────────────────────────
def test_auto_pass_is_not_written_to_the_ledger():
    """⚠️ 사람이 판단하지 않은 일을 승인으로 쌓으면 승인 건수가 실제보다 많아진다."""
    calls = []

    class _Spy:
        def append(self, **kw):
            calls.append(kw)
            return {"event_id": "e1"}

    assert gate.record_decision(_Spy(), _ev(), project_id="p1") is None
    assert calls == []


@pytest.mark.parametrize("approved,event,actor", [
    (None, "APP_CONTRACT_REVIEW_REQUESTED", "system"),
    (True, "APP_CONTRACT_APPROVED", "user"),
    (False, "APP_CONTRACT_REJECTED", "user"),
])
def test_review_outcomes_are_recorded_against_the_fingerprint(approved, event, actor):
    calls = []

    class _Spy:
        def append(self, **kw):
            calls.append(kw)
            return {"event_id": "e1"}

    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A)
    gate.record_decision(_Spy(), d, project_id="p1", task_id="WBS-001",
                         actor_id="t_admin@test.invalid", approved=approved)
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event_type"] == event
    assert kw["subject_type"] == "app_contract"
    assert kw["subject_id"] == FP_B, "«어느 계약을 승인했는가» 가 남아야 한다"
    assert kw["actor_type"] == actor
    # 「무엇에서 무엇으로」 가 복원돼야 한다
    ev = kw["evidence_refs"][0]
    assert ev["previous_approved_fingerprint"] == FP_A
    assert ev["task_id"] == "WBS-001"


# ── WBS 와 잇는 자리 ─────────────────────────────────────────────────────
def test_project_gate_joins_wbs_and_contract_in_one_place():
    tasks = [{"task_id": "A", "artifact_kind": "APP"},
             {"task_id": "B", "artifact_kind": "REPORT"},
             {"task_id": "C"}]                    # 판독 불가 → 계약 대상
    d, required = gate.evaluate_project(tasks, {"app_runtime_contract_fingerprint": FP_A,
                                                "approved_contract_fingerprint": FP_A,
                                                "app_runtime_contract_status": "APPROVED"})
    assert required == ["A", "C"]
    assert d.verdict == gate.AUTO_PASS


@pytest.mark.parametrize("broken", [None, "", {"tasks": []}, 42, "WBS"])
def test_unreadable_wbs_is_blocked_not_exempted(broken):
    """★★★ **WBS 를 통째로 못 읽는 것이 가장 관대하게 처리되면 안 된다.**

    ⚠️ `normalize_tasks` 가 비-list 를 `[]` 로 만들면 계약 대상이 0건이 되고, 판정은
      `NOT_APPLICABLE` 로 떨어진다 — 즉 **WBS 를 깨뜨리는 것이 가장 쉬운 우회로**가
      된다. 태스크 하나를 못 읽는 것보다 전체를 못 읽는 것이 더 나쁜데 더 관대하게
      처리되고 있었다."""
    d, required = gate.evaluate_project(broken, {})
    assert required and required != [], "판독 불가 WBS 는 계약 대상 0건이 아니다"
    assert d.verdict == gate.BLOCKED


def test_project_with_no_contract_artifacts_is_not_applicable():
    d, required = gate.evaluate_project(
        [{"task_id": "B", "artifact_kind": "REPORT"}], {})
    assert required == []
    assert d.verdict == gate.NOT_APPLICABLE


def test_project_with_contract_artifacts_but_no_contract_is_blocked():
    """★ WBS 는 앱을 만들라고 하는데 계약이 없다 — 여기서 막지 않으면 계약 없이
    빌드로 넘어간다."""
    d, required = gate.evaluate_project([{"task_id": "A", "artifact_kind": "APP"}], {})
    assert required == ["A"]
    assert d.verdict == gate.BLOCKED


def test_ledger_accepts_the_new_event_and_subject_types():
    """★ 두 번째 진입 경로 — 상수만 맞춰 두고 원장에 등록하지 않으면, 실제 기록은
    `DecisionLedgerError` 로 죽는다. 스파이 객체만 시험하면 그것을 못 잡는다."""
    from core.decision_ledger import EVENT_TYPES, SUBJECT_TYPES, DecisionLedger

    assert {gate.EVENT_REVIEW_REQUESTED, gate.EVENT_APPROVED,
            gate.EVENT_REJECTED} <= set(EVENT_TYPES)
    assert gate.SUBJECT_TYPE in SUBJECT_TYPES

    d = _ev(compiled_fingerprint=FP_B, approved_fingerprint=FP_A)
    row = gate.record_decision(DecisionLedger(), d, project_id="p1",
                               actor_id="t_admin@test.invalid", approved=True)
    assert row and row.get("event_id")
