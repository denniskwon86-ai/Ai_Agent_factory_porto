"""★★★ [I-4 4c-1] 프로젝트 단위 계약 합산.

이 시험이 전제하는 것: **조직도·DB·LLM 을 쓰지 않는다.** 합산기는 순수 함수이고
컴파일러도 그렇다. 권한 경계를 보는 시험이 아니므로 `seeded_org` 를 붙이지 않는다.

⚠️ 이 파일이 막으려는 사고는 하나다 — **APP 태스크 B 의 계약이 A 의 계약을 덮어
  A 의 데이터셋이 소실되는 것.** 그 상태는 오류를 내지 않는다. B 를 만든 사람은
  A 를 모르기 때문이다.
"""
import pytest

from core import project_contract_aggregator as agg
from core import app_runtime_contract as arc


def _ds(name, actions=("read",), fields=(("qty", "number"),), **kw):
    d = {
        "name": name, "label": name, "purpose": "설명",
        "allowed_actions": list(actions),
        "data_role": "NATIVE_SUPPLEMENT",
        "source_intent": "AFS_NATIVE",
        "duplicate_entry_policy": "NO_DUPLICATE_CHECK_REQUIRED",
        "fields": [{"name": n, "type": t, "required": True,
                    "classification": "INTERNAL"} for n, t in fields],
    }
    d.update(kw)
    return d


def _draft(*datasets, app_class="departmental"):
    return {"app_class": app_class, "datasets": list(datasets),
            "capability_intents": []}


APP_A = {"task_id": "A", "artifact_kind": "APP"}
APP_B = {"task_id": "B", "artifact_kind": "APP"}
REPORT_C = {"task_id": "C", "artifact_kind": "REPORT"}


# ── 두 앱이 서로를 덮지 않는다 ───────────────────────────────────────────
def test_two_apps_keep_both_datasets():
    """★★★ 이것이 4c-1 의 전부다. 하나라도 빠지면 그 앱은 계약에 없는 데이터셋을
    쓰는 앱이 된다."""
    r = agg.aggregate([APP_A, APP_B],
                      {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))})
    assert not r.blocked, (r.errors, r.conflicts)
    assert [d["name"] for d in r.draft["datasets"]] == ["production", "quality"]
    assert r.included_task_ids == ["A", "B"]


def test_non_contract_tasks_are_excluded_with_their_drafts():
    """⚠️ 계약 대상이 아닌 태스크의 초안은 **무시한다.** 실수로 딸려 오면 보고서가
    데이터셋 권한을 얻는다."""
    r = agg.aggregate([APP_A, REPORT_C],
                      {"A": _draft(_ds("production")), "C": _draft(_ds("몰래"))})
    assert [d["name"] for d in r.draft["datasets"]] == ["production"]
    assert r.excluded_task_ids == ["C"]


def test_task_order_does_not_change_the_fingerprint():
    """★ WBS 순서를 바꾼 것은 업무의 변경이 아니다 — 재승인을 요구하면 사람이
    게이트를 습관으로 통과시킨다."""
    drafts = {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))}
    r1, _ = agg.compile_project_contract([APP_A, APP_B], drafts, project_id="p1")
    r2, _ = agg.compile_project_contract([APP_B, APP_A], drafts, project_id="p1")
    assert not r1.errors and not r2.errors, (r1.errors, r2.errors)
    assert r1.contract["semantic_fingerprint"] == r2.contract["semantic_fingerprint"]
    assert r1.contract["semantic_fingerprint"] != ""


def test_same_dataset_declared_twice_identically_appears_once():
    r = agg.aggregate([APP_A, APP_B],
                      {"A": _draft(_ds("production")), "B": _draft(_ds("production"))})
    assert not r.blocked, (r.errors, r.conflicts)
    assert len(r.draft["datasets"]) == 1


def test_wording_differences_are_not_conflicts():
    """⚠️ `label`·`purpose` 는 지문에도 안 들어간다. 문구가 다르다고 막으면 사람이
    문구를 맞추느라 의미를 안 본다."""
    a = _ds("production", label="생산실적", purpose="A 관점")
    b = _ds("production", label="생산 실적", purpose="B 관점")
    r = agg.aggregate([APP_A, APP_B], {"A": _draft(a), "B": _draft(b)})
    assert not r.blocked, (r.errors, r.conflicts)


# ── 충돌은 합치지 않는다 ────────────────────────────────────────────────
@pytest.mark.parametrize("other,changed", [
    (_ds("production", actions=("read", "write")), "allowed_actions"),
    (_ds("production", fields=(("qty", "text"),)), "fields"),
    (_ds("production", fields=(("qty", "number"), ("lot", "text"))), "fields"),
    (_ds("production", data_role="SCENARIO_INPUT"), "data_role"),
    (_ds("production", source_intent="ENTERPRISE_READ"), "source_intent"),
    (_ds("production", duplicate_entry_policy="ALLOW_SUPPLEMENT_ONLY"), "duplicate_entry_policy"),
])
def test_conflicting_dataset_blocks_instead_of_merging(other, changed):
    """★★★ 권한에서 합집합은 곧 **조용한 권한 확대**다. 스키마에서 합집합은 아무도
    의도하지 않은 세 번째 것이다. 둘 다 사람이 정해야 한다."""
    r = agg.aggregate([APP_A, APP_B],
                      {"A": _draft(_ds("production")), "B": _draft(other)})
    assert r.blocked
    c = next(c for c in r.conflicts if c["kind"] == agg.CONFLICT_DATASET)
    assert c["dataset_key"] == "production"
    assert sorted(c["tasks"]) == ["A", "B"]
    assert changed in c["differences"]


def test_conflict_does_not_produce_a_compiled_contract():
    """⚠️ 막힌 채로 컴파일하면 「일부만 담긴 계약」이 `COMPILED` 로 나오고, 그것은
    승인 가능한 대상이 된다 — 사람은 그게 전부라고 믿는다."""
    res, a = agg.compile_project_contract(
        [APP_A, APP_B],
        {"A": _draft(_ds("production")), "B": _draft(_ds("production", actions=("read", "write")))},
        project_id="p1")
    assert a.blocked and res.errors
    assert res.contract["status"] == "DRAFT"
    assert res.contract["semantic_fingerprint"] == ""


def test_different_app_class_is_not_promoted_to_the_wider_one():
    r = agg.aggregate([APP_A, APP_B],
                      {"A": _draft(_ds("a"), app_class="personal"),
                       "B": _draft(_ds("b"), app_class="enterprise")})
    assert r.blocked
    assert any(c["kind"] == agg.CONFLICT_APP_CLASS for c in r.conflicts)


def test_same_key_with_a_different_name_is_a_conflict():
    """`dataset_key` 가 정체다 — 같은 정체에 다른 이름이면 둘 중 하나가 틀렸다."""
    a = _ds("production", dataset_key="prod")
    b = _ds("생산", dataset_key="prod")
    r = agg.aggregate([APP_A, APP_B], {"A": _draft(a), "B": _draft(b)})
    assert r.blocked
    assert any(c["kind"] == agg.CONFLICT_DATASET for c in r.conflicts)


# ── 개정과 삭제 ─────────────────────────────────────────────────────────
def test_revising_one_task_preserves_the_other():
    """★★★ A 를 고쳤다고 B 의 데이터셋이 사라지면 안 된다 — 태스크 단위 컴파일러를
    그대로 이었을 때 생기는 바로 그 사고다."""
    before, _ = agg.compile_project_contract(
        [APP_A, APP_B], {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))},
        project_id="p1")
    after, _ = agg.compile_project_contract(
        [APP_A, APP_B],
        {"A": _draft(_ds("production", fields=(("qty", "number"), ("lot", "text")))),
         "B": _draft(_ds("quality"))},
        project_id="p1", previous=before.contract)

    names = [d["name"] for d in after.contract["datasets"]]
    assert "quality" in names, "B 의 데이터셋이 사라졌다"
    assert "production" in names
    assert after.contract["semantic_fingerprint"] != before.contract["semantic_fingerprint"]
    assert after.fingerprint_changed is True


def test_deleting_a_task_drops_it_from_the_new_contract():
    """확정된 정책: 삭제된 태스크의 데이터셋은 **새 합산에서 즉시 제외**한다.
    지문이 바뀌므로 재승인을 지난다."""
    before, _ = agg.compile_project_contract(
        [APP_A, APP_B], {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))},
        project_id="p1")
    after, _ = agg.compile_project_contract(
        [APP_A], {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))},
        project_id="p1", previous=before.contract)

    assert [d["name"] for d in after.contract["datasets"]] == ["production"]
    assert after.fingerprint_changed is True, "재승인을 지나야 한다"


def test_deleting_a_task_does_not_touch_the_previous_contract():
    """⚠️ 계약에서 빠지는 것과 **데이터를 지우는 것**은 다른 일이다. 이전 계약
    문서는 그대로 남아야 「무엇이 빠졌는가」를 볼 수 있다."""
    before, _ = agg.compile_project_contract(
        [APP_A, APP_B], {"A": _draft(_ds("production")), "B": _draft(_ds("quality"))},
        project_id="p1")
    snapshot = arc.canonical_json(before.contract)
    agg.compile_project_contract([APP_A], {"A": _draft(_ds("production"))},
                                 project_id="p1", previous=before.contract)
    assert arc.canonical_json(before.contract) == snapshot


# ── 판독 불가·누락 ──────────────────────────────────────────────────────
def test_unreadable_wbs_stays_a_contract_target():
    r = agg.aggregate("깨진 WBS", {})
    assert r.blocked
    assert r.missing_task_ids, "판독 불가 WBS 가 계약 대상 0건이 되면 안 된다"


def test_a_contract_task_without_a_draft_is_not_an_empty_contract():
    """⚠️ 「데이터를 안 쓰는 앱(데이터셋 0개)」과 「아직 계약을 안 쓴 태스크」는
    다르다. 앞은 유효한 계약이고 뒤는 미완성이다 — 같게 다루면 미완성이 승인된다."""
    r = agg.aggregate([APP_A, APP_B], {"A": _draft(_ds("production"))})
    assert r.blocked
    assert r.missing_task_ids == ["B"]


def test_a_dataset_without_an_identity_is_blocked():
    r = agg.aggregate([APP_A], {"A": _draft({"label": "이름 없음", "fields": []})})
    assert r.blocked


def test_zero_dataset_app_is_a_valid_contract():
    """★ 데이터가 없는 앱도 **「데이터셋 0개인 계약」**을 갖는다 — 0개라는 선언
    자체가 통제다(나중에 하나 생기면 지문이 바뀌고 게이트가 열린다)."""
    res, a = agg.compile_project_contract(
        [APP_A], {"A": {"app_class": "departmental", "datasets": [],
                        "capability_intents": []}}, project_id="p1")
    assert not a.blocked, (a.errors, a.conflicts)
    assert res.errors == []
    assert res.contract["datasets"] == []
    assert res.contract["semantic_fingerprint"] != ""


def test_contract_body_is_deterministic_not_just_the_fingerprint():
    """★ 지문은 정렬해서 만들므로 **본문이 흔들려도 지문은 같다.** 그러면 두 릴리스를
    눈으로 비교할 수 없고, 「같은 계약인데 문서가 다르다」가 된다.

    ⚠️ 의미는 같고 문구만 다른 데이터셋을 두 태스크가 선언하면, 어느 쪽 문구가
      본문에 남는지가 **입력 순서로 정해지면 안 된다.**"""
    a = _draft(_ds("production", label="A 문구"))
    b = _draft(_ds("production", label="B 문구"))
    r1, _ = agg.compile_project_contract([APP_A, APP_B], {"A": a, "B": b}, project_id="p1")
    r2, _ = agg.compile_project_contract([APP_B, APP_A], {"A": a, "B": b}, project_id="p1")
    assert arc.canonical_json(r1.contract) == arc.canonical_json(r2.contract)
    assert r1.contract["datasets"][0]["label"] == "A 문구", "정렬 기준이 태스크 id 여야 한다"


def test_datasets_are_sorted_even_within_one_task():
    """⚠️ 앞 시험은 이것을 못 잡는다 — 태스크를 정렬해 돌면 **삽입 순서가 우연히**
    정렬 순서와 같아지기 때문이다(태스크당 데이터셋이 하나뿐이면 늘 그렇다).
    한 태스크가 역순으로 선언하면 그 순서가 그대로 계약 본문에 새어 나온다."""
    r = agg.aggregate([APP_A], {"A": _draft(_ds("quality"), _ds("production"))})
    assert not r.blocked, (r.errors, r.conflicts)
    assert [d["name"] for d in r.draft["datasets"]] == ["production", "quality"]
