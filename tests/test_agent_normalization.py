"""요구 에이전트 정규화 + 정확-id 라우팅 — _has_role substring 오탐 제거 검증.

PMO 는 정규 영문 id 를 내지만, 비정형(한글/변형) 입력도 정규화로 복구되어 라우팅이 보존되는지 확인.
"""
import core.agent_graph as ag


def test_canonicalize_exact_ids_passthrough():
    for cid in ["Architect", "Tech_Lead", "Backend", "Frontend", "QA"]:
        assert ag._canonicalize(cid) == cid


def test_canonicalize_korean_and_variants():
    assert ag._canonicalize("백엔드") == "Backend"
    assert ag._canonicalize("프론트엔드") == "Frontend"
    assert ag._canonicalize("Tech Lead") == "Tech_Lead"
    assert ag._canonicalize("테스트") == "QA"


def test_normalize_dedupes_and_maps():
    assert ag._normalize_agents(["Architect", "백엔드", "QA", "Backend"]) == ["Architect", "Backend", "QA"]


def test_has_role_is_exact_membership():
    assert ag._has_role(["Backend"], "Backend", "백엔드") is True
    assert ag._has_role(["Frontend"], "Backend", "백엔드") is False
    # 정규화된 명단 기준 — QA 정확 일치
    assert ag._has_role(["QA"], "QA", "테스트") is True
    assert ag._has_role(["Frontend"], "QA", "테스트") is False


def test_korean_required_agents_still_route(tmp_path):
    # WBS 가 한글/변형으로 들어와도 정규화되어 라우팅 입력이 정규 id 가 된다
    import json
    from types import SimpleNamespace
    wbs = {"tasks": [{"task_id": "T1", "required_agents": ["백엔드", "프론트엔드"]}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs, ensure_ascii=False), encoding="utf-8")
    s = SimpleNamespace(workspace_root=str(tmp_path), current_sprint_task_id="T1", current_required_agents=[])
    assert ag._get_required_agents(s) == ["Backend", "Frontend"]
