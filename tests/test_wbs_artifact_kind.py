"""★★★ [I-4 4단계 · 설계 §15] WBS 산출물 종류와 계약 대상 판정.

이 시험이 전제하는 것: **조직도·DB·LLM 을 쓰지 않는다.** `core.wbs_artifact_kind` 는
아무것도 import 하지 않는 순수 판정 모듈이고, `WBSManager` 는 `tmp_path` 안의 파일
하나만 만진다. 그래서 `seeded_org` 도 `enforced_org` 도 붙이지 않는다.

⚠️ 이 파일이 지키려는 것은 「분류가 맞는가」가 아니라 **「분류할 수 없을 때 어느 쪽으로
  떨어지는가」**다. rev.2 의 순환 논리(데이터를 쓴다고 판정된 태스크만 계약 대상)가
  바로 그 자리에서 무너졌다 — 놓친 태스크가 곧 계약을 우회하는 태스크가 된다.
"""
import json

import pytest

from core import wbs_artifact_kind as ak
from nodes.utils.wbs_manager import WBSManager


# ── 닫힌 목록 ────────────────────────────────────────────────────────────
def test_kind_table_is_pinned_literally():
    """★★★ 표를 **글자 그대로** 고정한다.

    ⚠️ [I-4 2.2a 실측] 「모든 값을 훑어 계약 필요 여부를 확인한다」식 시험은
      **표를 넓혀도 초록으로 남는다** — 시험이 표를 읽어 자기 기대를 만들기
      때문이다(동어반복). 그래서 값을 손으로 적는다. 여기가 깨지면 표가 바뀐
      것이고, 표가 바뀌는 것은 사람이 판단할 일이다."""
    assert ak.ARTIFACT_KINDS == ("APP", "SIMULATOR", "REPORT", "DOCUMENT", "LIBRARY")
    assert ak.CONTRACT_REQUIRED_KINDS == ("APP", "SIMULATOR")
    assert ak.UNREADABLE_FALLBACK == "APP"
    assert ak.UNREADABLE_FALLBACK in ak.CONTRACT_REQUIRED_KINDS, (
        "판독 실패는 **계약 대상**으로 떨어져야 한다 — 「모르면 면제」는 우회로다")


@pytest.mark.parametrize("kind,need", [
    ("APP", True), ("SIMULATOR", True),
    ("REPORT", False), ("DOCUMENT", False), ("LIBRARY", False),
])
def test_declared_kinds_decide_contract(kind, need):
    assert ak.requires_contract(kind) is need


# ── fail-closed: 세 가지 판독 실패를 모두 눌러 본다 ─────────────────────
@pytest.mark.parametrize("raw", [
    None,                    # 값 없음 — LLM 이 필드를 빼먹은 경우
    "",                      # 빈 문자열
    "   ",                   # 공백만
    "application",           # 목록 밖 — 「비슷하니 읽어 주겠지」
    "app_in_app",
    "Report ",               # ← 이건 읽힌다(공백·대소문자). 아래에서 따로 확인
    123,                     # 타입 오류
    ["APP"],                 # 배열로 왔다
    {"kind": "APP"},         # 객체로 왔다
])
def test_unreadable_kind_falls_closed(raw):
    kind, source = ak.normalize_kind(raw)
    if raw == "Report ":
        # ★ 대소문자·앞뒤 공백까지만 흡수한다. 그 이상은 추측하지 않는다.
        assert (kind, source) == ("REPORT", ak.SOURCE_DECLARED)
        return
    assert kind == ak.APP, f"{raw!r} 는 판독 불가 → APP 이어야 한다"
    assert source == ak.SOURCE_FALLBACK
    assert ak.requires_contract(raw) is True


def test_fallback_is_distinguishable_from_a_declared_app():
    """★ 「기획이 APP 이라고 말했다」와 「읽을 수 없어 APP 이 됐다」는 다른 사실이다.

    둘 다 계약 대상이라 **동작은 같다.** 그래서 구분이 사라져도 시험이 안 깨지기
    쉽다 — 그런데 구분이 없으면 판독 실패 건수를 셀 수 없고, 그 숫자가 곧 기획
    프롬프트의 결함을 가리키는 유일한 신호다."""
    declared = ak.normalize_task({"task_id": "T1", "artifact_kind": "APP"})
    fallen = ak.normalize_task({"task_id": "T2"})
    assert declared[ak.KIND_KEY] == fallen[ak.KIND_KEY] == "APP"
    assert declared[ak.SOURCE_KEY] == ak.SOURCE_DECLARED
    assert fallen[ak.SOURCE_KEY] == ak.SOURCE_FALLBACK


def test_malformed_task_is_kept_not_dropped():
    """⚠️ 읽을 수 없는 태스크를 **버리지 않는다.** 버리면 WBS 개수가 조용히 줄고,
    그 손실은 실행이 끝난 뒤에야 드러난다."""
    out = ak.normalize_tasks(["문자열이 태스크로 왔다", None, {"task_id": "T3"}])
    assert len(out) == 3
    assert all(t[ak.KIND_KEY] == "APP" for t in out)
    assert out[0]["malformed_task"].startswith("'문자열")
    assert ak.task_requires_contract("문자열") is True


@pytest.mark.parametrize("broken", [None, "", "WBS", 42, {"tasks": []}, ("a",)])
def test_whole_wbs_unreadable_is_not_an_empty_list(broken):
    """★★★ 목록이 아니면 **빈 목록이 아니라 판독 불가 태스크 한 건**이다.

    ⚠️ 빈 목록이면 계약 대상이 0건이 되어 프로젝트 판정이 `NOT_APPLICABLE` 로
      떨어진다. 태스크 하나를 못 읽는 것보다 WBS 전체를 못 읽는 것이 더 나쁜데
      더 관대해지는 방향이었다 — 그 방향이 뒤집혀 있으면 **WBS 를 깨뜨리는 것**이
      가장 쉬운 우회로가 된다."""
    out = ak.normalize_tasks(broken)
    assert len(out) == 1
    assert out[0][ak.KIND_KEY] == "APP"
    assert ak.contract_required_task_ids(broken) != []


def test_empty_list_is_readable_and_stays_empty():
    """⚠️ 위와 구분한다. 빈 **목록**은 「읽었는데 태스크가 없다」이고, 비-목록은
    「읽지 못했다」다. 둘을 같게 다루면 판독 실패가 정상 상태로 위장된다."""
    assert ak.normalize_tasks([]) == []
    assert ak.contract_required_task_ids([]) == []


# ── Tech Lead 필수화 ─────────────────────────────────────────────────────
def test_tech_lead_is_injected_for_contract_tasks():
    out = ak.normalize_task({"task_id": "T1", "artifact_kind": "APP",
                             "required_agents": ["Backend", "Frontend"]})
    assert out["required_agents"] == ["Tech_Lead", "Backend", "Frontend"], (
        "계약이 나오기 전에는 Backend·Frontend 가 만들 것이 없다 — 맨 앞이어야 한다")


def test_tech_lead_is_not_duplicated_and_order_is_kept():
    out = ak.normalize_task({"task_id": "T1", "artifact_kind": "SIMULATOR",
                             "required_agents": ["Backend", "Tech_Lead", "Frontend"]})
    assert out["required_agents"] == ["Backend", "Tech_Lead", "Frontend"]


def test_non_contract_task_is_not_given_a_tech_lead():
    """⚠️ 계약이 필요 없는 태스크에까지 Tech_Lead 를 넣으면 명단이 의미를 잃는다 —
    「전부 들어 있으면 아무것도 뜻하지 않는다」."""
    out = ak.normalize_task({"task_id": "T1", "artifact_kind": "REPORT",
                             "required_agents": ["Master_PM"]})
    assert out["required_agents"] == ["Master_PM"]


def test_broken_required_agents_do_not_lose_the_tech_lead():
    """명단이 배열이 아니거나 원소가 문자열이 아니어도 Tech_Lead 는 남아야 한다."""
    assert ak.normalize_task({"artifact_kind": "APP",
                              "required_agents": "Backend"})["required_agents"] == ["Tech_Lead"]
    assert ak.normalize_task({"artifact_kind": "APP",
                              "required_agents": [None, 7, "Backend"]})["required_agents"] == \
        ["Tech_Lead", "Backend"]


def test_normalize_does_not_mutate_the_caller_object():
    """⚠️ 원본을 조용히 바꾸면 같은 리스트를 들고 있는 다른 호출부가 함께 바뀐다."""
    original = {"task_id": "T1", "required_agents": ["Backend"]}
    ak.normalize_task(original)
    assert original == {"task_id": "T1", "required_agents": ["Backend"]}


# ── 적용 범위(opt-in) ────────────────────────────────────────────────────
def test_profile_default_is_off():
    """★★★ 기본값이 켜져 있으면 **이미 돌고 있는 모든 프로젝트**가 소급 적용된다."""
    assert ak.PROFILE_NONE == ""
    assert ak.profile_enforces_contract("") is False
    assert ak.profile_enforces_contract(None) is False


@pytest.mark.parametrize("raw,on", [
    ("v1", True), ("V1", True), (" v1 ", True),
    ("", False), (None, False), ("v2", False), ("V1.0", False), (1, False), (True, False),
])
def test_only_an_explicit_v1_turns_the_contract_on(raw, on):
    """⚠️ 여기만 fail-**open** 이다(다른 판정과 반대). 모르는 프로필을 강제 쪽으로
    떨어뜨리면 진행 중 프로젝트가 재개하는 순간 체크포인터가 어긋난다."""
    assert ak.profile_enforces_contract(raw) is on


def test_legacy_project_is_not_touched(tmp_path):
    """★★★ 프로필이 꺼져 있으면 **아무것도 바뀌지 않는다.** `artifact_kind` 도
    `Tech_Lead` 도 들어가지 않는다 — 소급 적용의 경계가 여기다."""
    mgr = WBSManager(str(tmp_path / "legacy"))
    written = mgr.initialize_wbs("p", [{"title": "앱", "required_agents": ["Frontend"]}])
    assert written[0].get("artifact_kind") is None
    assert written[0]["required_agents"] == ["Frontend"]

    stored = mgr.get_wbs()
    assert stored[ak.PROFILE_KEY] == ""
    assert stored["tasks"][0]["required_agents"] == ["Frontend"]

    # append 경로도 프로필을 따른다 — 피드백 한 번으로 절차가 켜지면 안 된다
    mgr.add_revision_task("고쳐 주세요")
    rev = next(t for t in mgr.get_wbs()["tasks"] if t["task_id"].startswith("TASK_REV_"))
    assert "artifact_kind" not in rev


# ── 두 번째 진입 경로: WBSManager 파일 ──────────────────────────────────
def test_initialize_wbs_returns_what_it_wrote(tmp_path):
    """★★★ [P0-1] **반환값과 파일이 같아야 한다.**

    ⚠️ 정규화는 새 dict 를 만들므로 호출부가 넘긴 원본에는 반영되지 않는다. 반환을
      버리고 원본을 다시 읽으면 **파일에는 `Tech_Lead` 가 있는데 실행 상태에는 없는**
      상태가 되고, 최초 실행이 계약을 건너뛴다. 정규화를 넣어 놓고 그 결과를 안 쓰는
      것이 가장 알아채기 어려운 형태의 무력화다."""
    mgr = WBSManager(str(tmp_path / "ws"))
    original = [{"title": "앱", "required_agents": ["Frontend"]}]
    written = mgr.initialize_wbs("p", original, runtime_contract_profile="v1")

    assert written[0]["required_agents"] == ["Tech_Lead", "Frontend"]
    assert written == mgr.get_wbs()["tasks"], "반환값이 곧 기록된 내용이어야 한다"
    # 원본은 건드리지 않는다 — 호출부가 반환을 «써야» 한다는 계약이 여기서 드러난다
    assert original[0]["required_agents"] == ["Frontend"]


def test_initialize_wbs_normalizes_on_the_way_to_disk(tmp_path):
    """★★★ **두 진입 경로를 각각 뚫는다.** 판정 함수만 시험하면, 호출부가 그것을
    부르지 않게 되는 날 조용히 통과한다 — [I-4] 에서 반복해 겪은 유형이다."""
    mgr = WBSManager(str(tmp_path / "ws"))
    mgr.initialize_wbs("p", runtime_contract_profile="v1", tasks=[
        {"title": "앱 화면", "required_agents": ["Frontend"]},          # 종류 없음
        {"title": "보고서", "artifact_kind": "report",
         "required_agents": ["Master_PM"]},                              # 소문자
        {"title": "시뮬레이터", "artifact_kind": "SIMULATOR",
         "required_agents": ["Backend"]},
    ])
    tasks = json.loads((tmp_path / "ws" / "00_wbs_master_plan.json")
                       .read_text(encoding="utf-8"))["tasks"]
    assert [t["artifact_kind"] for t in tasks] == ["APP", "REPORT", "SIMULATOR"]
    assert [t["artifact_kind_source"] for t in tasks] == ["fallback", "declared", "declared"]
    assert tasks[0]["required_agents"] == ["Tech_Lead", "Frontend"]
    assert tasks[1]["required_agents"] == ["Master_PM"]      # 보고서에는 넣지 않는다
    assert tasks[2]["required_agents"] == ["Tech_Lead", "Backend"]
    assert [t["task_id"] for t in tasks] == ["WBS-001", "WBS-002", "WBS-003"]


def test_appended_tasks_declare_their_kind_instead_of_falling_back(tmp_path):
    """⚠️ append 경로(`add_revision_task`·`add_data_task`)가 `initialize_wbs` 를
    거치지 않는다. 그래서 여기가 우회로가 되기 쉽다 — 각자 종류를 **명시**한다."""
    mgr = WBSManager(str(tmp_path / "ws"))
    mgr.initialize_wbs("p", [{"title": "앱", "artifact_kind": "APP"}],
                       runtime_contract_profile="v1")

    mgr.add_revision_task("버튼이 안 눌립니다")
    mgr.add_data_task("생산실적 정의", "MES 실적 표 정의")

    tasks = mgr.get_wbs()["tasks"]
    rev = next(t for t in tasks if t["task_id"].startswith("TASK_REV_"))
    data = next(t for t in tasks if t["task_id"].startswith("TASK_DATA_"))

    # 수정 태스크는 앱을 고친다 → 계약 대상
    assert rev["artifact_kind"] == "APP"
    assert rev["artifact_kind_source"] == "declared"
    assert "Tech_Lead" in rev["required_agents"]

    # 데이터 준비는 실행 가능한 릴리스를 만들지 않는다 → 계약 불필요
    assert data["artifact_kind"] == "DOCUMENT"
    assert data["artifact_kind_source"] == "declared"
    assert data["required_agents"] == ["Master_PM"]
    assert ak.task_requires_contract(data) is False


def test_contract_required_ids_count_what_is_left(tmp_path):
    mgr = WBSManager(str(tmp_path / "ws"))
    mgr.initialize_wbs("p", [
        {"task_id": "A", "artifact_kind": "APP"},
        {"task_id": "B", "artifact_kind": "LIBRARY"},
        {"task_id": "C"},                                # 판독 불가 → 계약 대상
    ], runtime_contract_profile="v1")
    assert ak.contract_required_task_ids(mgr.get_wbs()["tasks"]) == ["A", "C"]


# ── 세 번째 진입 경로: PMO 노드가 상태에 무엇을 싣는가 ───────────────────
def test_pmo_node_puts_the_normalized_agents_into_the_state(tmp_path, monkeypatch):
    """★★★ [P0-1] 파일이 아니라 **실행 상태**를 본다.

    ⚠️ 이것이 이번에 보고된 우회로다: WBS 파일에는 `Tech_Lead` 가 들어갔는데
      `current_required_agents` 에는 정규화 **전** 명단이 실렸다. 저장본만 시험하면
      영원히 초록이다 — 그래서 노드를 직접 돌려 상태를 본다.
    ⚠️ LLM 은 부르지 않는다. 게이트웨이와 채점을 모두 대역으로 바꾼다.
    """
    import asyncio as _asyncio
    import json as _json

    import nodes.planning as planning

    async def _fake_exec(_state, _prompt, **kw):
        return _json.dumps({"tasks": [
            {"title": "앱 화면", "goal": "g", "required_agents": ["Frontend"]},
            {"title": "보고서", "goal": "g", "artifact_kind": "REPORT",
             "required_agents": ["Master_PM"]},
        ]})

    async def _fake_score(_state, _stage):
        return {"score": 1.0, "verdict": "PASS", "blocking_fails": []}

    monkeypatch.setattr(planning.gateway, "aexecute", _fake_exec, raising=False)
    monkeypatch.setattr(planning, "_load_skill", lambda *_a, **_k: "prompt", raising=False)
    monkeypatch.setattr("nodes.utils.scoring.score_stage", _fake_score, raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    #: ⚠️ 이 저장소에는 pytest-asyncio 가 없다 — 코루틴을 직접 돌린다.
    out = _asyncio.run(planning.run_master_pmo({
        "project_name": "p", "workspace_root": str(ws),
        "runtime_contract_profile": "v1",
    }))

    assert out["current_required_agents"] == ["Tech_Lead", "Frontend"], (
        "정규화 전 명단이 상태로 갔다 — 최초 실행이 계약을 건너뛴다")

    stored = _json.loads((ws / "00_wbs_master_plan.json").read_text(encoding="utf-8"))
    assert stored["tasks"][0]["required_agents"] == out["current_required_agents"], \
        "저장본과 실행본이 갈리면 안 된다"


def test_pmo_node_leaves_legacy_projects_alone(tmp_path, monkeypatch):
    """프로필이 꺼진 프로젝트는 상태도 파일도 예전 그대로여야 한다."""
    import asyncio as _asyncio
    import json as _json

    import nodes.planning as planning

    async def _fake_exec(_state, _prompt, **kw):
        return _json.dumps({"tasks": [{"title": "앱", "goal": "g",
                                       "required_agents": ["Frontend"]}]})

    async def _fake_score(_state, _stage):
        return {"score": 1.0, "verdict": "PASS", "blocking_fails": []}

    monkeypatch.setattr(planning.gateway, "aexecute", _fake_exec, raising=False)
    monkeypatch.setattr(planning, "_load_skill", lambda *_a, **_k: "prompt", raising=False)
    monkeypatch.setattr("nodes.utils.scoring.score_stage", _fake_score, raising=False)

    ws = tmp_path / "legacy"
    ws.mkdir()
    out = _asyncio.run(planning.run_master_pmo({"project_name": "p",
                                                "workspace_root": str(ws)}))
    assert out["current_required_agents"] == ["Frontend"]
