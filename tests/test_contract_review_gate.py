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
#: ⚠️ 이 절은 **스파이 객체를 쓰지 않는다.** [4c-2] 에서 검사와 기록이 한
#:   트랜잭션이 되면서, 가짜 원장으로는 「이미 결정된 요청인가」를 볼 수 없게 됐다.
#:   진짜 원장(conftest 가 tmp 로 격리)을 쓴다 — 아래 `ledger` fixture.
@pytest.mark.parametrize("verdict_kw", [
    {},                                 # AUTO_PASS
    {"compiled_fingerprint": ""},       # BLOCKED
    {"requires_contract": False},       # NOT_APPLICABLE
])
def test_only_a_review_can_be_recorded(verdict_kw):
    """⚠️ 사람이 판단하지 않은 일을 승인으로 쌓으면 원장에서 승인 건수를 세는 순간
    실제보다 많아지고, 그 숫자는 「우리는 계약을 N번 검토했다」로 읽힌다.

    ★ 예전에는 「조용히 `None` 을 돌려준다」였다. 지금은 **거부한다** — 부를 일이
      없는 자리에서 불렸다는 것 자체가 호출부의 결함이고, 조용히 넘기면 그 결함이
      남는다."""
    class _NoLedger:
        def transaction(self):          # 여기까지 오면 안 된다
            raise AssertionError("원장을 건드렸다")

    with pytest.raises(gate.ReviewRequestError):
        gate.record_decision(_NoLedger(), gate.evaluate(
            **{"requires_contract": True, "compiled_fingerprint": FP_A,
               "approved_fingerprint": FP_A, "contract_status": gate.APPROVED,
               **verdict_kw}),
            project_id="p1", request_event_id="dle_x", approved=True)


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


# ── [4c-2] 검토 요청 이벤트 ─────────────────────────────────────────────
#: 이 절이 전제하는 것: conftest 가 `decision_ledger.db` 를 `tmp_path` 로 격리한다.
#: 원장이 정본이므로 **스파이 객체로는 이 절을 시험할 수 없다** — 진짜 원장을 쓴다.
import pytest as _pytest


@_pytest.fixture
def ledger():
    from core.decision_ledger import DecisionLedger
    return DecisionLedger()


def _review(fp=FP_B, prev=FP_A):
    return _ev(compiled_fingerprint=fp, approved_fingerprint=prev)


def test_review_request_is_created_once(ledger):
    ev1, made1 = gate.ensure_review_request(ledger, _review(), project_id="p1",
                                            task_ids=["A", "B"])
    ev2, made2 = gate.ensure_review_request(ledger, _review(), project_id="p1",
                                            task_ids=["A", "B"])
    assert made1 is True and made2 is False
    assert ev1["event_id"] == ev2["event_id"]
    assert ev1["subject_id"] == FP_B
    assert ev1["evidence_refs"][0]["task_ids"] == ["A", "B"]


def test_open_request_is_found_from_the_ledger_not_the_state(ledger):
    """★★★ 상태를 **한 번도 저장하지 않았어도** 두 번째 호출이 같은 요청을 찾는다.

    ⚠️ 체크포인트 저장이 실패하면 상태의 `contract_review_request_event_id` 는 비어
      있다. 그때 상태만 보고 판정하면 요청이 두 건 생기고, 승인이 어느 쪽에 붙었는지
      아무도 답할 수 없다."""
    ev1, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    #: 상태는 잃어버렸다고 치자 — 원장에는 남아 있다.
    ev2, made = gate.ensure_review_request(ledger, _review(), project_id="p1")
    assert made is False and ev2["event_id"] == ev1["event_id"]


def test_a_different_fingerprint_gets_its_own_request(ledger):
    """⚠️ 지문이 다르면 **다른 계약**이다. 옛 요청을 재사용하면 사람이 A 를 보고
    승인한 기록이 B 의 승인이 된다."""
    a, _ = gate.ensure_review_request(ledger, _review(fp=FP_A, prev=""), project_id="p1")
    b, made = gate.ensure_review_request(ledger, _review(fp=FP_B, prev=FP_A), project_id="p1")
    assert made is True and a["event_id"] != b["event_id"]


def test_another_project_gets_its_own_request(ledger):
    a, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    b, made = gate.ensure_review_request(ledger, _review(), project_id="p2")
    assert made is True and a["event_id"] != b["event_id"]


def test_a_decided_request_does_not_block_a_new_one(ledger):
    """★ 반려된 뒤 같은 계약을 다시 올릴 수 있어야 한다 — 「열린」 요청만 막는다."""
    ev, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    gate.record_decision(ledger, _review(), project_id="p1", approved=False,
                         actor_id=ADMIN, request_event_id=ev["event_id"])
    again, made = gate.ensure_review_request(ledger, _review(), project_id="p1")
    assert made is True and again["event_id"] != ev["event_id"]


@_pytest.mark.parametrize("verdict_kw", [
    {"compiled_fingerprint": ""},              # BLOCKED
    {},                                        # AUTO_PASS
    {"requires_contract": False},              # NOT_APPLICABLE
])
def test_only_a_review_creates_a_request(ledger, verdict_kw):
    with _pytest.raises(gate.ReviewRequestError):
        gate.ensure_review_request(ledger, _ev(**verdict_kw), project_id="p1")


def test_concurrent_requests_do_not_duplicate(ledger):
    """★★★ 조회와 기록 사이에 틈이 있으면 재시작이 겹칠 때 요청이 두 건 생긴다."""
    import threading

    made = []
    barrier = threading.Barrier(4)

    def _go():
        barrier.wait()
        try:
            made.append(gate.ensure_review_request(ledger, _review(), project_id="p1"))
        except Exception as e:      # 실패도 기록해 조용히 사라지지 않게 한다
            made.append(e)

    threads = [threading.Thread(target=_go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(not isinstance(m, Exception) for m in made), made
    ids = {m[0]["event_id"] for m in made}
    assert len(ids) == 1, f"동시 요청이 {len(ids)} 건의 요청을 만들었다"
    assert sum(1 for m in made if m[1]) == 1, "새로 만든 것은 한 번뿐이어야 한다"


# ── [4c-2] 결정 가능성 검사 ─────────────────────────────────────────────
ADMIN = "t_admin@test.invalid"


def test_decidable_requires_all_four_conditions(ledger):
    ev, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")

    # ① 정상
    assert gate.assert_decidable(ledger, ev["event_id"], project_id="p1",
                                 compiled_fingerprint=FP_B)["event_id"] == ev["event_id"]

    # ② 없는 요청
    with _pytest.raises(gate.ReviewRequestError):
        gate.assert_decidable(ledger, "dle_없음", project_id="p1",
                              compiled_fingerprint=FP_B)

    # ③ 다른 프로젝트
    with _pytest.raises(gate.ReviewRequestError):
        gate.assert_decidable(ledger, ev["event_id"], project_id="p2",
                              compiled_fingerprint=FP_B)

    # ④ 요청 이후 계약이 바뀌었다 — 그 승인은 지금 계약을 본 승인이 아니다
    with _pytest.raises(gate.ReviewRequestError) as e:
        gate.assert_decidable(ledger, ev["event_id"], project_id="p1",
                              compiled_fingerprint=FP_A)
    assert "다릅니다" in str(e.value)


def test_a_non_request_event_cannot_be_a_parent(ledger):
    """⚠️ 아무 이벤트나 부모로 삼으면 승인이 엉뚱한 것에 붙는다.

    ⚠️⚠️ 이 시험은 원래 **엉뚱한 이유로 초록**이었다(변이 검사에서 드러났다).
      `subject_type` 이 다른 이벤트는 조회 자체에 안 걸려 「존재하지 않는 요청」으로
      막혔고, 정작 **이벤트 종류 검사는 한 번도 실행되지 않았다.** 그래서 같은
      `app_contract` 주체를 가진 «승인» 이벤트를 부모로 삼아 본다 — 그것이 종류
      검사가 유일하게 발동하는 자리다."""
    # ① 주체가 아예 다른 이벤트 — 조회에 안 걸린다
    other = ledger.append(event_type="WBS_APPROVED", subject_type="wbs_task",
                          subject_id="T1", project_id="p1")
    with _pytest.raises(gate.ReviewRequestError) as e1:
        gate.assert_decidable(ledger, other["event_id"], project_id="p1",
                              compiled_fingerprint=FP_B)
    assert "존재하지 않는" in str(e1.value)

    # ② ★ 같은 주체(app_contract)의 «승인» 이벤트를 부모로 — 종류 검사가 막아야 한다
    req, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    approved = gate.record_decision(ledger, _review(), project_id="p1",
                                    request_event_id=req["event_id"], approved=True,
                                    actor_id=ADMIN)
    with _pytest.raises(gate.ReviewRequestError) as e2:
        gate.assert_decidable(ledger, approved["event_id"], project_id="p1",
                              compiled_fingerprint=FP_B)
    assert "검토 요청 이벤트가 아닙니다" in str(e2.value)


def test_an_empty_request_id_says_so(ledger):
    """⚠️ 「요청을 지정하지 않았다」와 「없는 요청이다」는 사용자가 할 일이 다르다.
    둘을 같은 문장으로 뭉개면 화면이 무엇을 고치라고 말할 수 없다."""
    gate.ensure_review_request(ledger, _review(), project_id="p1")
    with _pytest.raises(gate.ReviewRequestError) as e:
        gate.assert_decidable(ledger, "", project_id="p1", compiled_fingerprint=FP_B)
    assert "지정되지 않았습니다" in str(e.value)


def test_the_earliest_open_request_wins(ledger):
    """★★★ 열린 요청이 둘이면 **가장 처음 것**이 정본이다.

    ⚠️ 지금 코드는 중복을 막지만, 이 규칙이 없으면 «막기 전에 생긴» 중복이나 손으로
      들어간 기록 앞에서 재시작마다 다른 요청을 집는다 — 그러면 승인이 어느 쪽에
      붙었는지 아무도 답할 수 없다.
    ★ 그래서 중복 상태를 **직접 만들어** 확인한다. `ensure_review_request` 로는
      만들 수 없으므로(그것이 막는다) 원장에 그대로 넣는다."""
    made = []
    for _ in range(2):
        made.append(ledger.append(
            event_type=gate.EVENT_REVIEW_REQUESTED, subject_type=gate.SUBJECT_TYPE,
            subject_id=FP_B, actor_type="system", project_id="p1"))
    assert made[0]["event_id"] != made[1]["event_id"]

    picked, created = gate.ensure_review_request(ledger, _review(), project_id="p1")
    assert created is False
    assert picked["event_id"] == made[0]["event_id"], "가장 처음 열린 요청이어야 한다"


@_pytest.mark.parametrize("first,second", [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_a_request_cannot_be_decided_twice(ledger, first, second):
    ev, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    gate.record_decision(ledger, _review(), project_id="p1", approved=first,
                         actor_id=ADMIN, request_event_id=ev["event_id"])
    with _pytest.raises(gate.ReviewRequestError):
        gate.assert_decidable(ledger, ev["event_id"], project_id="p1",
                              compiled_fingerprint=FP_B)
    with _pytest.raises(gate.ReviewRequestError):
        gate.record_decision(ledger, _review(), project_id="p1", approved=second,
                             actor_id=ADMIN, request_event_id=ev["event_id"])


def test_decision_is_linked_to_its_request(ledger):
    """★ 원장이 SSOT 이려면 **요청과 결정이 이어져** 있어야 한다 — 그래야 그래프
    재개가 실패해도 결정을 복구할 수 있다."""
    ev, _ = gate.ensure_review_request(ledger, _review(), project_id="p1")
    row = gate.record_decision(ledger, _review(), project_id="p1", approved=True,
                               actor_id=ADMIN, request_event_id=ev["event_id"])
    assert row["parent_event_id"] == ev["event_id"]
    assert row["event_type"] == gate.EVENT_APPROVED


def test_ledger_accepts_the_new_event_and_subject_types(ledger):
    """★ 상수만 맞춰 두고 원장에 등록하지 않으면 실제 기록이 `DecisionLedgerError`
    로 죽는다 — 값 목록과 실제 기록 **두 곳**을 함께 본다."""
    from core.decision_ledger import EVENT_TYPES, SUBJECT_TYPES

    assert {gate.EVENT_REVIEW_REQUESTED, gate.EVENT_APPROVED,
            gate.EVENT_REJECTED} <= set(EVENT_TYPES)
    assert gate.SUBJECT_TYPE in SUBJECT_TYPES

    d = _review()
    req, _ = gate.ensure_review_request(ledger, d, project_id="p1", task_ids=["WBS-001"])
    row = gate.record_decision(ledger, d, project_id="p1",
                               request_event_id=req["event_id"], approved=True,
                               actor_id=ADMIN, task_id="WBS-001")
    assert row and row.get("event_id")
    assert row["event_type"] == gate.EVENT_APPROVED
    assert row["subject_type"] == "app_contract"
    assert row["subject_id"] == FP_B, "«어느 계약을 승인했는가» 가 남아야 한다"
    assert row["actor_type"] == "user"
    # 「무엇에서 무엇으로」 가 복원돼야 한다
    ev = row["evidence_refs"][0]
    assert ev["previous_approved_fingerprint"] == FP_A
    assert ev["task_id"] == "WBS-001"
