# ==========================================
# WBS 노드가 «공급자 실패» 를 «빈 산출물» 로 읽지 않는다 (2026-08-07)
#
# ## 이 테스트가 존재하는 이유 — 실측
#
# 게이트웨이는 최종 실패 시 `{"files": [], "error": "LLM UNKNOWN ERROR: ..."}` 를 돌려준다.
# 이것은 **유효한 JSON 이라서** WBS 파서를 그대로 통과하고 `.get("tasks")` 가 `[]` 를 낸다.
# 즉 「LLM 이 죽었다」와 「모델이 빈 WBS 를 냈다」가 구분되지 않았다.
#
# 2026-07-29 `test_a1_unitconv_canary2` 에서 그 대가가 나왔다. 공급자가 죽은 상태에서
#   빈 WBS → 지시 강화 재호출(2배) → 기준 미달 채점 → HOTL 거부 → 재분할이 **7회** 돌았다.
#   LLM 호출 28줄이 그렇게 쌓였다. 프롬프트에도 모델에도 문제가 없었다.
#
# ⚠️ 이때 「재시도 횟수를 늘리자」는 처방은 이 루프를 **더 길게** 만들었을 뿐이다.
#   실패율을 숨기고 비용만 늘리는 대증 처방이 어떻게 생기는지의 실물 사례다.
#
# `core.llm_gateway.is_llm_error_text` 의 독스트링은 이미 "소비자는 반드시 이 함수로 걸러
# fail-loud 처리해야 한다"고 규정하고 있었다. 이 노드만 지키지 않았다.
# ==========================================
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nodes.planning as planning
from state_models import ProjectState

_SENTINEL = json.dumps({"files": [], "error": "LLM UNKNOWN ERROR: boom"})
# ⚠️ PRD 의 FR 을 실제로 담당해야 한다 — 그러지 않으면 `wbs_fr_coverage` 가 정상적으로 걸려
#   재분할 분기로 빠지고, 이 테스트가 보려던 «재시도 성공» 경로에 도달하지 못한다.
_GOOD_WBS = json.dumps({"tasks": [
    {"title": f"T{i}", "goal": "FR-001 단위 변환 구현", "scope": "변환 로직",
     "required_agents": ["Backend"]}
    for i in range(4)]})


class _Spy:
    """게이트웨이 대역. **몇 번 불렸는지**가 이 테스트의 핵심 관측값이다."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def aexecute(self, *a, **kw):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def _run(state, spy, monkeypatch, tmp_path):
    monkeypatch.setattr(planning, "gateway", spy)
    # 스킬 파일 로딩은 이 테스트의 관심사가 아니다 — 분기만 본다.
    monkeypatch.setattr(planning, "agent_skill", lambda *a, **kw: "skill")
    monkeypatch.setattr(planning, "_load_skill", lambda *a, **kw: "프롬프트")
    return asyncio.run(planning.run_master_pmo(state))


def _state(tmp_path):
    return ProjectState(prd_summary="FR-001 단위 변환", workspace_root=str(tmp_path))


# ── ① 공급자 실패에 두 번째 호출을 태우지 않는다 ────────────────────────────
def test_provider_failure_does_not_burn_a_second_call(monkeypatch, tmp_path):
    """★★★ 「지시를 강화해 1회 재시도」는 **모델이 형식을 틀렸을 때** 듣는 처방이다.

    공급자가 죽어 있으면 같은 이유로 또 죽는다 — 비용만 정확히 두 배가 된다."""
    spy = _Spy(_SENTINEL)
    _run(_state(tmp_path), spy, monkeypatch, tmp_path)
    assert spy.calls == 1, f"공급자 실패인데 {spy.calls}회 호출했다(재시도가 무의미하게 돌았다)"


# ── ② 자동 재분할 루프에 넣지 않는다 ────────────────────────────────────────
def test_provider_failure_does_not_trigger_the_resplit_loop(monkeypatch, tmp_path):
    """★★★ `needs_revision=True` 가 자동 재분할 루프를 도는 스위치다.

    ⚠️ 실측에서 이 스위치가 켜진 채로 7회 돌았다. 모델을 시험해 본 적조차 없는데
      재분할 예산을 깎는 것은 «실패의 원인을 잘못 기록하는» 일이기도 하다."""
    out = _run(_state(tmp_path), _Spy(_SENTINEL), monkeypatch, tmp_path)
    assert out["needs_revision"] is False, "공급자 실패가 자동 재분할 루프를 돌린다"
    assert "stage_attempt_counts" not in out, "시험해 본 적 없는데 재분할 예산을 깎았다"


# ── ③ 사람에게 «다른 원인» 임이 보여야 한다 ─────────────────────────────────
def test_feedback_names_the_provider_not_the_output_quality(monkeypatch, tmp_path):
    """★★ 「WBS 기준 미달」로 보이면 사람은 프롬프트를 고치러 간다 — 엉뚱한 곳이다.

    실제로 이 화면을 보고 «Master_PMO 프롬프트가 잘못됐나» 를 먼저 의심했다."""
    out = _run(_state(tmp_path), _Spy(_SENTINEL), monkeypatch, tmp_path)
    fb = out["supervisor_feedback"]
    assert "공급자" in fb, "원인이 공급자 실패임을 말하지 않는다"
    assert "기준 미달" not in fb, "산출물 품질 문제로 오인시킨다"


def test_existing_wbs_is_not_overwritten_on_provider_failure(monkeypatch, tmp_path):
    """⚠️ 빈 WBS 로 기존 파일을 덮으면 복구할 것이 사라진다."""
    wbs = tmp_path / "00_wbs_master_plan.json"
    wbs.write_text(json.dumps({"tasks": [{"title": "기존"}]}), encoding="utf-8")
    _run(_state(tmp_path), _Spy(_SENTINEL), monkeypatch, tmp_path)
    assert json.loads(wbs.read_text(encoding="utf-8"))["tasks"][0]["title"] == "기존"


# ── ④ 공급자가 «살아 있을 때» 의 기존 동작은 그대로다 ───────────────────────
def test_empty_wbs_from_a_live_provider_still_retries_once(monkeypatch, tmp_path):
    """★ 이 수정이 **기존 재시도를 죽이면 안 된다.**

    공급자가 살아 있고 모델이 형식만 틀린 경우는 지시 강화가 실제로 듣는다 — 그 경로는 유지."""
    spy = _Spy("{}", _GOOD_WBS)
    out = _run(_state(tmp_path), spy, monkeypatch, tmp_path)
    assert spy.calls == 2, "형식 실패에 대한 1회 재시도가 사라졌다"
    assert out.get("current_required_agents") == ["Backend"]


def test_provider_failure_on_the_retry_is_also_caught(monkeypatch, tmp_path):
    """첫 호출은 형식 실패, 재시도에서 공급자가 죽는 경우도 루프에 넣지 않는다."""
    out = _run(_state(tmp_path), _Spy("{}", _SENTINEL), monkeypatch, tmp_path)
    assert out["needs_revision"] is False
    assert "공급자" in out["supervisor_feedback"]


# ── ⑤ 센티넬이 «유효한 JSON» 이라는 사실 자체를 못박는다 ────────────────────
def test_sentinel_parses_as_valid_json_which_is_why_it_was_invisible():
    """★★★ 이 결함의 뿌리 — 오류 센티넬은 파싱에 **성공한다.**

    그래서 「파싱 실패」로도 잡히지 않았고 텔레메트리에도 실패로 남지 않았다.
    이 사실이 변하면(센티넬 형식이 바뀌면) 위 가드들의 전제가 무너지므로 여기서 고정한다."""
    parsed = json.loads(_SENTINEL)
    assert parsed.get("tasks", []) == [], "센티넬이 빈 WBS 로 위장되지 않는다면 가드 전제가 바뀐 것"

    from core.llm_gateway import is_llm_error_text
    assert is_llm_error_text(_SENTINEL) is True
    assert is_llm_error_text(_GOOD_WBS) is False
