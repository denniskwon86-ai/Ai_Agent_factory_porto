"""★★★ [I-4 4c-5·4c-6] 계약 노드 배선과 **비소급** 보장.

이 시험이 전제하는 것: **조직도를 쓰지 않는다.** 라우터는 순수 함수이고 노드는
`tmp_path` 안의 파일과 격리된 원장만 만진다.

⚠️ 이 파일이 막으려는 사고는 하나다 — **진행 중 프로젝트에 계약 노드가 소급
  삽입되는 것.** 그 어긋남은 «재개할 때에야» 드러나고, 그때는 원인을 찾기 어렵다.
  그래서 「연결됐다」보다 **「레거시는 닿지 않는다」를 먼저** 못 박는다.
"""
import asyncio
import json
import os

import pytest

from core import agent_graph as ag
from state_models import ProjectState

FP_A = "a" * 64
FP_B = "b" * 64


def _st(**kw):
    base = {"project_name": "p", "current_required_agents": ["Tech_Lead", "Backend"]}
    base.update(kw)
    return ProjectState(**base)


# ── 4c-5 비소급 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("profile", ["", "v2", "V1.0", "  "])
def test_a_legacy_project_never_reaches_the_contract_nodes(profile):
    """★★★ 프로필이 `v1` 이 아니면 **예전 목적지 그대로**다.

    ⚠️ 여기가 깨지면 이미 돌고 있는 모든 프로젝트가 새 노드에 진입하고, 그
      어긋남은 재개할 때에야 드러난다."""
    assert ag.route_from_tech_lead(_st(runtime_contract_profile=profile)) == "Backend"


@pytest.mark.parametrize("agents,expected", [
    (["Tech_Lead", "Backend"], "Backend"),
    (["Tech_Lead", "Frontend"], "Frontend"),
    (["Tech_Lead"], "CodeBuilder"),
    (["Tech_Lead", "백엔드 개발자"], "Backend"),
    #: ★ 둘 다 배정된 태스크에서 **Backend 가 먼저**다. 순서를 안 고정하면 배선을
    #:   옮기며 뒤바뀌어도 아무 시험이 깨지지 않는다.
    (["Tech_Lead", "Frontend", "Backend"], "Backend"),
])
def test_legacy_routing_is_the_old_behaviour_unchanged(agents, expected):
    """★ 예전 `route_from_tech_lead` 본문을 그대로 옮겼음을 고정한다 — 옮기며 한
    줄이라도 달라지면 레거시 프로젝트가 다른 곳으로 간다."""
    st = _st(runtime_contract_profile="", current_required_agents=agents)
    assert ag.route_from_tech_lead(st) == expected
    assert ag._after_contract(st) == expected


def test_only_v1_enters_the_compiler():
    assert ag.route_from_tech_lead(
        _st(runtime_contract_profile="v1")) == "HostContractCompiler"


def test_new_nodes_do_not_change_the_hotl_interrupts():
    """★★★ 노드는 늘어도 **HOTL 중단점은 그대로**여야 한다.

    ⚠️ `interrupt_after` 가 바뀌면 **기존 체크포인트의 재개 지점이 달라진다** —
      멈춰 있던 프로젝트가 다른 곳에서 깨어나거나, 멈춰야 할 곳을 지나친다."""
    wf, interrupts = ag.build_graph_from_registry()
    assert interrupts == ["Requirement_Interviewer", "RFP_Analyst", "Master_PM",
                          "VisionQA", "Master_PMO", "Supervisor"]
    assert wf.compile() is not None
    nodes = set(getattr(wf, "nodes", {}) or {})
    assert {"HostContractCompiler", "ContractReviewGate",
            "ContractReviewPending"} <= nodes


def test_every_old_node_is_still_there():
    """⚠️ 배선을 고치며 기존 노드를 잃으면 레거시 체크포인트가 없는 노드를 가리킨다."""
    wf, _ = ag.build_graph_from_registry()
    nodes = set(getattr(wf, "nodes", {}) or {})
    for old in ("Tech_Lead", "Backend", "Frontend", "CodeBuilder", "Reviewer", "QA",
                "Supervisor", "ManualWriter", "WBS_Approved", "TerminalHandler",
                "Master_PMO", "Architect", "UIDesigner", "VisionQA",
                "Requirement_Interviewer", "RFP_Analyst", "Master_PM"):
        assert old in nodes, f"{old} 노드가 사라졌다"


def test_a_52_checkpoint_reads_clean_and_routes_the_old_way():
    """★ 5.2 로 저장된 체크포인트가 그대로 읽히고 계약 필드는 **빈 값**이다."""
    st = ProjectState(**{"schema_version": "5.2.0", "project_name": "구",
                         "current_required_agents": ["Tech_Lead", "Backend"]})
    assert st.schema_version == "5.3.0"
    assert st.runtime_contract_profile == ""
    assert st.contract_review_request_event_id == ""
    assert ag.route_from_tech_lead(st) == "Backend"


# ── 4c-6 판정별 목적지 ──────────────────────────────────────────────────
def test_compiler_failure_goes_to_the_terminal_handler():
    """⚠️ 볼 계약이 없는데 게이트로 보내면, 사용자는 「승인하라」는 화면과 「계약이
    없다」는 문장을 동시에 본다.

    ## ⚠️⚠️ [2026-08-26 실측] 판정 기준을 지문 → **종결 자취**로 바꿨다

    종전에는 「지문이 비면 무조건 종결」이었다. 그런데 지문이 비는 경우는 **둘**이다:

        ① 계약을 만들다 실패했다        → 종결 (`terminal_status` 가 찍혀 있다)
        ② 이번 범위에 계약 대상이 없다  → 그냥 다음 단계로 (LIBRARY·REPORT 태스크)

    ②를 종결로 보내면 **계약이 필요 없는 태스크가 전부 실패로 끝난다.** 실제 가동에서
    WBS 5개 중 그 갈래에 걸려 완주가 막혔다.

    ★ 이 시험이 지키려던 것(「승인하라」와 「계약이 없다」를 동시에 보이지 않기)은
      **그대로 지킨다** — 아래 마지막 단언이 그것이다. 계약이 필요한데 지문이 없으면
      게이트가 `BLOCKED` 로 잡는다. 층마다 가정이 다르므로 층이다."""
    #: ① 실패는 종결로 — 자취를 보고 판단한다.
    assert ag.route_from_contract_compiler(
        _st(app_runtime_contract_fingerprint="",
            terminal_status="CONTRACT_BLOCKED")) == "TerminalHandler"
    #: ② 계약이 있으면 게이트로.
    assert ag.route_from_contract_compiler(
        _st(app_runtime_contract_fingerprint=FP_B)) == "ContractReviewGate"
    #: ③ 계약 대상이 없어 지문이 빈 것은 실패가 아니다 — 지나간다.
    assert ag.route_from_contract_compiler(
        _st(app_runtime_contract_fingerprint="")) == "ContractReviewGate"


def test_the_gate_still_blocks_a_contract_less_walkthrough(tmp_path):
    """★★★ 위 완화가 **구멍을 만들지 않는지**가 진짜 질문이다.

    계약이 필요한 태스크가 지문 없이 게이트에 닿으면, 게이트가 막아야 한다.
    막지 못하면 계약 대상 앱이 **계약 없이** 빌드된다."""
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    out = asyncio.run(cn.run_contract_review_gate(
        {"project_name": "p", "workspace_root": ws, "current_sprint_task_id": "A",
         "runtime_contract_profile": "v1"}))
    assert out["terminal_status"] == "CONTRACT_BLOCKED"


def test_gate_routes_by_what_the_node_left_behind():
    """★ 라우터가 판정을 **다시 계산하지 않는다** — 두 번 계산하면 그 사이에 상태가
    바뀌었을 때 노드가 연 요청과 라우터가 본 판정이 갈린다."""
    assert ag.route_from_contract_gate(
        _st(contract_review_request_event_id="dle_1")) == "ContractReviewPending"
    assert ag.route_from_contract_gate(
        _st(contract_review_request_event_id="")) == "Backend"
    assert ag.route_from_contract_gate(
        _st(terminal_status="CONTRACT_BLOCKED")) == "TerminalHandler"


# ── 노드 동작 ───────────────────────────────────────────────────────────
def _draft(ws, task_id, name="production"):
    d = os.path.join(ws, "contracts", "drafts")
    os.makedirs(d, exist_ok=True)
    body = {"app_class": "departmental", "capability_intents": [],
            "datasets": [{"name": name, "label": name, "purpose": "설명",
                          "allowed_actions": ["read"],
                          "data_role": "NATIVE_SUPPLEMENT",
                          "source_intent": "AFS_NATIVE",
                          "duplicate_entry_policy": "NO_DUPLICATE_CHECK_REQUIRED",
                          "fields": [{"name": "qty", "type": "number", "required": True,
                                      "classification": "INTERNAL"}]}]}
    with open(os.path.join(d, task_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)


def _wbs(ws, tasks):
    from nodes.utils.wbs_manager import WBSManager
    WBSManager(ws).initialize_wbs("p", tasks, runtime_contract_profile="v1")


def test_compiler_writes_the_canonical_contract(tmp_path):
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    _draft(ws, "A")

    out = asyncio.run(cn.run_host_contract_compiler(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1"}))
    assert out["app_runtime_contract_status"] == "COMPILED"
    assert len(out["app_runtime_contract_fingerprint"]) == 64
    saved = json.load(open(cn.contract_path(ws), encoding="utf-8"))
    assert [d["name"] for d in saved["datasets"]] == ["production"]
    assert "데이터셋 1개" in out["app_runtime_contract_summary"]


def test_compiler_does_not_overwrite_the_canon_on_failure(tmp_path):
    """⚠️ 실패로 정본을 덮으면 「무엇이 승인돼 있었는가」를 잃고, 고칠 근거까지 사라진다."""
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    _draft(ws, "A")
    asyncio.run(cn.run_host_contract_compiler(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1"}))
    before = open(cn.contract_path(ws), encoding="utf-8").read()

    #: 초안 없는 계약 태스크를 더한다 → 합산이 막힌다
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"},
              {"task_id": "B", "title": "앱2", "artifact_kind": "APP"}])
    #: ⚠️ `current_sprint_task_id` 를 빼면 제품과 다른 것을 시험한다 — 스프린트는
    #:   언제나 어떤 태스크를 돌고 있다. 없으면 그 태스크가 계약 범위에서 빠져
    #:   초안 요구 자체가 성립하지 않는다(2026-08-26 범위 정리 이후).
    out = asyncio.run(cn.run_host_contract_compiler(
        {"project_name": "p", "workspace_root": ws, "current_sprint_task_id": "B",
         "runtime_contract_profile": "v1"}))
    assert out["app_runtime_contract_status"] == "DRAFT"
    assert out["app_runtime_contract_fingerprint"] == ""
    assert open(cn.contract_path(ws), encoding="utf-8").read() == before


def test_an_unreadable_draft_is_not_treated_as_missing(tmp_path):
    """⚠️ 「초안이 없다」와 「초안이 깨졌다」를 같게 다루면, 사람은 안 쓴 줄 알고
    다시 쓴다 — 그리고 깨진 파일은 그대로 남는다."""
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(os.path.join(ws, "contracts", "drafts"))
    with open(os.path.join(ws, "contracts", "drafts", "A.json"), "w", encoding="utf-8") as f:
        f.write("{깨진 JSON")
    drafts = cn.load_drafts(ws)
    assert "A" in drafts and drafts["A"].get("__unreadable__")


def test_gate_opens_exactly_one_request_and_stops(tmp_path):
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    state = {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1",
             "current_sprint_task_id": "A",
             "app_runtime_contract_fingerprint": FP_B,
             "approved_contract_fingerprint": FP_A,
             "app_runtime_contract_status": "COMPILED"}

    first = asyncio.run(cn.run_contract_review_gate(state))
    second = asyncio.run(cn.run_contract_review_gate(state))
    assert first["contract_review_request_event_id"]
    assert (first["contract_review_request_event_id"]
            == second["contract_review_request_event_id"]), "요청이 두 건 생겼다"
    assert ag.route_from_contract_gate(_st(
        contract_review_request_event_id=first["contract_review_request_event_id"]
    )) == "ContractReviewPending"


def test_gate_auto_passes_without_touching_the_ledger(tmp_path):
    """★ 자동 통과는 원장에 남기지 않는다 — 사람이 판단하지 않은 일이다."""
    from core.decision_ledger import decision_ledger
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    before = len(decision_ledger.list_events(limit=1000))
    out = asyncio.run(cn.run_contract_review_gate(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1",
         "app_runtime_contract_fingerprint": FP_A,
         "approved_contract_fingerprint": FP_A,
         "app_runtime_contract_status": "APPROVED"}))
    assert out["contract_review_request_event_id"] == ""
    assert len(decision_ledger.list_events(limit=1000)) == before


def test_gate_blocks_when_there_is_no_contract(tmp_path):
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "앱", "artifact_kind": "APP"}])
    out = asyncio.run(cn.run_contract_review_gate(
        {"project_name": "p", "workspace_root": ws, "current_sprint_task_id": "A",
         "runtime_contract_profile": "v1"}))
    assert out["terminal_status"] == "CONTRACT_BLOCKED"
    assert out["contract_review_request_event_id"] == ""


def test_a_report_only_project_is_not_applicable(tmp_path):
    """★ 계약이 필요 없는 산출물만 있으면 게이트는 사람을 부르지 않는다."""
    from nodes import contract as cn

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _wbs(ws, [{"task_id": "A", "title": "보고서", "artifact_kind": "REPORT"}])
    out = asyncio.run(cn.run_contract_review_gate(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1"}))
    assert out == {"contract_review_request_event_id": ""}
