# -*- coding: utf-8 -*-
"""★★★ 라우터가 내는 이름은 **전부 그래프에 선언돼 있어야** 한다. (2026-08-28)

## ⚠️⚠️ 무엇이 있었나

`route_from_reviewer` 는 QA 가 없고 수용검수만 배정된 태스크에서 `"Supervisor"` 를
반환한다. 그런데 `_wire_edges` 의 매핑에는 그 이름이 없었다(`ManualWriter` 만 있었다).

LangGraph 가 어떻게 하는지 작은 그래프로 **실물 확인**했다:

    반환 'B'(선언 있음) → 통과
    반환 'C'(선언 없음) → KeyError: 'C'

즉 **가동 중에 죽는다.** 지금까지 안 터진 이유는 실제 WBS 107개 태스크가 전부
Supervisor 를 QA 와 함께 배정했고 라우터가 QA 를 먼저 보기 때문이다 — PMO 가
수용검수만 있는 태스크를 하나 내는 순간 원인 불명의 크래시가 된다.

## 왜 «소스에서 문자열 찾기» 가 아니라 «돌려 보기» 인가

⚠️ 라우터는 `_get_required_agents` 같은 헬퍼를 거쳐 이름을 만든다. 소스에서
  `return "..."` 만 찾으면 그 경로를 통째로 놓친다 — 실제로 이 결함이 그 경로에 있었다.
★ 그래서 상태 축을 돌려 **라우터를 실제로 부른다.** 새 분기가 생겨도 자동으로 덮인다.
"""
import contextlib
import inspect
import io
import itertools
import re

import pytest
from langgraph.graph import END

import core.agent_graph as G
from state_models import ProjectState

#: ⚠️ 값은 **정본에서 읽은 것**만 쓴다. 지어낸 값(`'host_bound_v1'`)을 쓰면 라우터가
#:   조용히 기본 분기로 떨어지고 「이 분기는 도달 불가」라는 거짓 결론이 나온다.
#:   실제로 그렇게 한 번 속았다 — 정본은 `wbs_artifact_kind.PROFILE_V1` 이다.
_AXES = {
    "terminal_status": ("", "FAILED_REVIEW"),
    "reviewer_decision": ("PASS", "REWORK_DEV", "ESCALATE_PM"),
    "supervisor_hops": (0, 8),
    "supervisor_verdict": ("", "PASS", "REJECT"),
    "stage_attempt_counts": ({}, {"SUPERVISOR": 2}),
    "qa_verdict": ("", "PASS", "FAIL"),
    "build_status": ("success", "failed"),
    "developer_retry_count": (0, 3),
    "failed_node": ("Frontend", "Backend", ""),
    "needs_revision": (False, True),
    "factory_mode": ("PLANNING", "EXECUTION", "REVISION"),
    "contract_review_request_event_id": ("", "evt1"),
    "architecture_summary": ("", "arch"),
    "runtime_contract_profile": ("", "v1"),
}

#: 라우터가 태스크 명단으로 갈리므로 이 축이 없으면 결함을 못 본다.
_AGENT_SETS = (["Frontend"], ["Backend"], ["Backend", "Frontend"], ["QA"],
               ["Supervisor"], ["QA", "Supervisor"], ["Tech_Lead"],
               ["Architect"], ["Reviewer"], [])

_FIELDS = set(ProjectState.model_fields)
_HELPERS = {n: inspect.getsource(getattr(G, n)) for n in dir(G)
            if n.startswith("_") and callable(getattr(G, n, None))
            and getattr(getattr(G, n), "__module__", "") == "core.agent_graph"}


def _declared():
    """`add_conditional_edges("노드", 라우터, {…})` 를 소스에서 그대로 읽는다."""
    src = inspect.getsource(G)
    out = {}
    for m in re.finditer(
            r'add_conditional_edges\(\s*"(\w+)"\s*,\s*(\w+)\s*,\s*\{(.*?)\}\s*\)', src, re.S):
        node, router, body = m.groups()
        keys = set(re.findall(r'"([^"]+)"\s*:', body))
        if re.search(r'(^|[\s,])END\s*:', body):
            keys.add(str(END))
        out[router] = (node, keys)
    return out


def _read_fields(fn):
    src = inspect.getsource(fn)
    for name, hsrc in _HELPERS.items():
        if re.search(rf"\b{name}\s*\(", src):
            src += "\n" + hsrc
    got = set(re.findall(r"state\.([a-z_]+)", src))
    got |= set(re.findall(r'getattr\(\s*state\s*,\s*["\']([a-z_]+)', src))
    return sorted((got & _FIELDS) & set(_AXES))


def _outputs(fn):
    """상태 축을 돌려 라우터가 **실제로 내는** 이름을 모은다."""
    keys = _read_fields(fn)
    seen = set()
    with contextlib.redirect_stdout(io.StringIO()):          # 라우터의 print 억제
        for agents in _AGENT_SETS:
            for combo in itertools.product(*(_AXES[k] for k in keys)) or [()]:
                #: WBS 에 없는 태스크 id → `current_required_agents` 로 폴백한다.
                #:   디스크를 안 타므로 이 시험은 프로젝트 유무와 무관하다.
                st = ProjectState(project_name="t", initial_idea="x", workspace_root="",
                                  current_sprint_task_id="NOT-IN-ANY-WBS",
                                  current_required_agents=agents,
                                  **dict(zip(keys, combo)))
                with contextlib.suppress(Exception):
                    seen.add(str(fn(st)))
    return seen


_DECL = _declared()


def test_선언을_읽어냈다():
    """⚠️ 계측기부터 증명한다 — 정규식이 빗나가면 아래가 **전부 공회전**한다."""
    assert len(_DECL) >= 10, f"조건부 간선을 {len(_DECL)}개밖에 못 읽었다"
    assert "route_from_reviewer" in _DECL


@pytest.mark.parametrize("router", sorted(_DECL))
def test_라우터가_내는_이름이_전부_선언돼_있다(router):
    fn = getattr(G, router, None)
    if fn is None:
        pytest.skip(f"{router} 가 모듈에 없다")
    node, declared = _DECL[router]
    produced = _outputs(fn)
    assert produced, f"{router} 가 아무 값도 못 냈다 — 축이 부족하다(시험이 헛돈다)"
    missing = sorted(produced - declared)
    assert not missing, (
        f"{node} 의 간선 선언에 없는 이름을 {router} 가 낸다: {missing}\n"
        f"  선언: {sorted(declared)}\n  산출: {sorted(produced)}\n"
        f"→ LangGraph 는 이 값을 받으면 KeyError 로 가동 중에 죽는다.")


def test_수용검수만_배정된_태스크가_Supervisor_로_간다():
    """★★★ 위 시험이 **실제로 이 경우를 덮는지** 고정한다.

    ⚠️ 일반 시험만 두면 축이 줄었을 때 조용히 안 덮이고, 그래도 초록이다."""
    with contextlib.redirect_stdout(io.StringIO()):
        st = ProjectState(project_name="t", initial_idea="x", workspace_root="",
                          current_sprint_task_id="NOT-IN-ANY-WBS",
                          current_required_agents=["Supervisor"],
                          reviewer_decision="PASS")
        got = G.route_from_reviewer(st)
    assert got == "Supervisor", got
    assert "Supervisor" in _DECL["route_from_reviewer"][1]
