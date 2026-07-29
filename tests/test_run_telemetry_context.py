"""카나리 계측 ①③ — **컨텍스트 구성**과 **실행 주체·폴백 사유**가 실제로 남는가.

## 왜 이 파일이 있나 (2026-07-29 카나리 실측)

사용자가 고정한 필수 계측 5종 중 두 개가 비어 있었다.

  ① 단계·에이전트별 모델과 **폴백 사유** — 36콜 중 **13콜(36%)이 stage 빈 값**이었고,
     폴백 4건 중 3건이 그 안에 있어 "어디서 왜 넘어갔는지"를 답할 수 없었다.
  ③ **컨텍스트 길이와 참조된 지식팩** — 코드 자체가 없었다. 그래서 D-010(전수 주입,
     ≈2,200자 → ≈5,300자)의 타당성을 카나리로 판정할 방법이 없었다.

계측은 "만들었다"가 아니라 **호출 기록에 실제로 실린다**가 증명이다. 그래서 모듈 단위가 아니라
**게이트웨이가 쓰는 레코드**까지 확인한다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import context_report, run_context


# ── ③ 컨텍스트 구성 ──────────────────────────────────────────────────────────
def test_context_blocks_are_measured_separately(tmp_path, monkeypatch):
    """블록별 길이가 따로 남아야 **무엇이 무엇을 밀어냈는지** 알 수 있다."""
    import core.context_engine as ce
    from state_models import ProjectState

    class _Master:
        def get_master_context(self, state, max_chars=-1):
            return "[기준정보] " + "M" * 500

    class _Knowledge:
        def get_relevant_context(self, state):
            return ""

        def get_grounding_context(self, state):
            return "[지식] " + "K" * 300

    class _Profile:
        def get_company_profile(self):
            return {}

    monkeypatch.setattr(ce, "master_data", _Master())
    monkeypatch.setattr(ce, "knowledge_base", _Knowledge())
    monkeypatch.setattr(ce, "persona_learner", _Profile())

    state = ProjectState.model_validate({
        "project_name": "T", "workspace_root": str(tmp_path),
        "current_stage": "BUILD", "tech_spec_summary": "# API\nGET /x",
    })
    ce.ContextEngine.build_core_context(state, light=True)

    rep = context_report.current()
    blocks = rep["blocks"]
    assert blocks["master_data"] > 500          # 기준정보 블록이 따로 세어진다
    assert blocks["knowledge_grounding"] > 300
    assert blocks["tech_spec"] > 0              # ★ 밀려나면 안 되는 블록
    assert rep["total_chars"] > 0 and rep["budget_chars"] > 0


def test_clipping_is_recorded_as_an_event(tmp_path, monkeypatch):
    """★ 절단은 사건이다 — 예산을 넘겼다는 것은 뒤쪽 블록이 잘렸다는 뜻이고,
    2026-07-29 회귀(기준정보가 기술 명세를 밀어냄)가 정확히 그 형태였다."""
    import core.context_engine as ce
    import config
    from state_models import ProjectState

    class _Fat:
        def get_master_context(self, state, max_chars=-1):
            return "X" * 100_000

    monkeypatch.setattr(ce, "master_data", _Fat())
    monkeypatch.setattr(ce, "knowledge_base", type("K", (), {
        "get_relevant_context": lambda s, x: "", "get_grounding_context": lambda s, x: ""})())
    monkeypatch.setattr(ce, "persona_learner", type("P", (), {
        "get_company_profile": lambda s: {}})())

    state = ProjectState.model_validate({"project_name": "T", "workspace_root": str(tmp_path)})
    ce.ContextEngine.build_core_context(state, light=True)
    assert context_report.current()["clipped"] is True


def test_injected_knowledge_sources_are_recorded():
    """'팩을 연결했다'와 '그 지식이 프롬프트에 들어갔다'는 다르다 — 후자를 남긴다."""
    context_report.start()
    context_report.note_knowledge([
        {"metadata": {"pack_id": "core-m3", "filename": "std.pdf", "page": 12}, "distance": 0.31},
        {"metadata": {"pack_id": "core-m3", "filename": "std.pdf"}, "distance": 0.44},
    ])
    rep = context_report.current()
    assert rep["knowledge_packs"] == ["core-m3"]          # 중복 없이
    assert len(rep["knowledge_hits"]) == 2
    assert rep["knowledge_hits"][0]["page"] == 12 and rep["knowledge_hits"][0]["distance"] == 0.31


def test_report_is_isolated_per_task():
    """★ 스웜은 에이전트 3개를 병렬로 돌린다 — 보고서가 섞이면 엉뚱한 호출에 붙는다."""
    import asyncio

    async def worker(tag, n):
        context_report.start()
        context_report.add_block("master_data", "M" * n)
        await asyncio.sleep(0)
        return context_report.current()["blocks"]["master_data"]

    async def main():
        return await asyncio.gather(worker("a", 100), worker("b", 700))

    assert asyncio.run(main()) == [100, 700]


# ── ① 실행 주체 · 폴백 사유 ─────────────────────────────────────────────────
def test_agent_identity_survives_empty_stage():
    """stage 가 비어도 **누가 불렀는지**는 남아야 한다(카나리 36% 미상 문제)."""
    run_context.set_agent("Backend")
    assert run_context.current_agent() == "Backend"


def test_fallback_errors_are_collected_not_swallowed():
    """LangChain `with_fallbacks` 가 삼키는 개별 실패를 콜백이 잡는다."""
    run_context.reset_fallback_errors()
    cb = run_context.FallbackErrorCollector()
    cb.on_llm_error(RuntimeError("429 quota exceeded"),
                    serialized={"name": "gemini-2.5-pro"})
    cb.on_llm_error(RuntimeError("timeout"), metadata={"ls_model_name": "llama-3.3-70b"})

    errs = run_context.get_fallback_errors()
    assert [e["model"] for e in errs] == ["gemini-2.5-pro", "llama-3.3-70b"]
    assert "429" in errs[0]["error"]


def test_collector_never_breaks_the_call():
    """계측 콜백에서 예외가 나면 **LLM 호출 자체가 죽는다** — 무슨 일이 있어도 삼킨다."""
    cb = run_context.FallbackErrorCollector()
    cb.on_llm_error(RuntimeError("x"), serialized="not-a-dict")   # 예외 없이 통과해야 한다
    assert cb.raise_error is False


def test_reset_prevents_bleed_between_calls():
    run_context.reset_fallback_errors()
    run_context.record_fallback_error("m1", "e1")
    run_context.reset_fallback_errors()
    assert run_context.get_fallback_errors() == []


# ── 배선: 게이트웨이 레코드에 실제로 실리는가 ────────────────────────────────
def test_log_record_carries_context_and_agent(tmp_path, monkeypatch):
    """★★ 만들어만 두고 로그에 안 실으면 카나리에서 또 비어 있다(이번에 겪은 그대로)."""
    import json

    import core.llm_gateway as gw

    context_report.start()
    context_report.add_block("master_data", "M" * 1234)
    context_report.note_knowledge([{"metadata": {"pack_id": "p1", "filename": "a.pdf"},
                                    "distance": 0.2}])
    context_report.finish("X" * 5000, 20000)
    run_context.set_agent("Frontend")
    run_context.reset_fallback_errors()
    run_context.record_fallback_error("gemini-2.5-pro", "429")

    log_path = tmp_path / "llm_call_log.jsonl"
    monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH", str(log_path))

    class _S:
        project_name = "T"
        workspace_root = "./projects/p1"
        owner_dept_id = "D-BAT"
        current_stage = ""          # ★ stage 가 비어도

    gw._log_llm_call(_S(), "pro_router", "code", 0, ["gemini-2.5-pro", "gemini-2.5-flash"],
                     True, 1.5, input_tokens=100, output_tokens=50,
                     _fallback_errors=run_context.get_fallback_errors())

    rec = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert rec["agent"] == "Frontend"                       # 단계 미상이어도 주체는 남는다
    assert rec["context_blocks"]["master_data"] == 1234
    assert rec["context_chars"] == 5000 and rec["context_budget"] == 20000
    assert rec["knowledge_packs"] == ["p1"]
    assert rec["fallback_errors"][0]["model"] == "gemini-2.5-pro"


def test_graph_nodes_are_wrapped_with_identity():
    """노드 등록이 래퍼를 거치지 않으면 agent 축이 영원히 빈다."""
    import inspect

    import core.agent_graph as ag

    # 실제 노드 등록은 `build_graph_from_registry` 가 한다(`_build_workflow` 는 위임 껍데기).
    src = inspect.getsource(ag.build_graph_from_registry)
    assert src.count("_with_agent_identity") >= 2, "SW·범용 두 경로 모두 래핑돼야 한다"


# ── 사고 재발 방지: 계측 콜백이 파이프라인을 죽이지 않는가 ──────────────────
def test_collector_satisfies_langchain_handler_interface():
    """★★ 이 콜백의 초판이 **A-1 재카나리를 두 번 죽였다**(`run_inline` AttributeError).

    상류가 무엇을 읽을지 우리가 열거할 수 있다고 가정한 것이 원인이었다. 이제 상속으로
    충족하고, 그래도 없는 속성은 터지는 대신 무해한 기본값을 준다."""
    cb = run_context.FallbackErrorCollector()

    # 상류(LangChain)가 실제로 읽는 것들 — 하나라도 터지면 호출 전체가 죽는다.
    for attr in ("run_inline", "raise_error", "ignore_llm", "ignore_chain", "ignore_agent",
                 "ignore_retriever", "ignore_chat_model", "ignore_retry", "ignore_custom_event"):
        getattr(cb, attr)          # 예외가 나지 않아야 한다

    # 앞으로 상류가 추가할지 모르는 미지의 속성·훅도 터지지 않는다.
    assert getattr(cb, "some_future_flag_we_never_heard_of") is False
    assert cb.on_some_future_hook("x") is None


def test_collector_is_accepted_by_langchain_callback_manager():
    """★★ '속성이 있다'가 아니라 **상류가 실제로 받아들이는가**를 본다.

    초판도 속성 테스트는 통과했을 것이다 — 정작 LangChain 내부에 넘겼을 때 터졌다."""
    from langchain_core.callbacks import CallbackManager

    cb = run_context.FallbackErrorCollector()
    mgr = CallbackManager(handlers=[cb])        # 여기서 상류가 핸들러를 검사한다
    assert cb in mgr.handlers


def test_dunder_lookups_still_raise():
    """`__getattr__` 이 dunder 까지 삼키면 copy·pickle 등이 조용히 오작동한다."""
    cb = run_context.FallbackErrorCollector()
    with pytest.raises(AttributeError):
        cb.__deepcopy__
