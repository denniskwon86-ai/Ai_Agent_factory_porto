"""agent_registry 회귀 테스트 — 로드/정규화/보정/영속화 폴백."""
import pytest
import core.agent_registry as ar


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    """REGISTRY_PATH 를 빈 tmp 경로로 격리 — 실제 파일에 의존/오염하지 않음."""
    p = tmp_path / "agents_registry.json"
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(p))
    return p


def test_default_registry_loads(isolated_registry):
    reg = ar.load_registry()  # 파일 없음 → DEFAULT
    ids = [a["id"] for a in reg["agents"]]
    assert reg["agents"]
    assert "RFP_Analyst" in ids and "Master_PMO" in ids and "Tech_Lead" in ids  # 노드 자체는 존재(게이트 여부와 무관)


def test_coerce_fills_missing_fields():
    a = ar._coerce_agent({"id": "X"})
    for k in ar._AGENT_FIELDS:
        assert k in a
    assert a["enabled"] is True
    assert isinstance(a["order"], int)


def test_normalize_sorts_and_drops_idless():
    reg = ar._normalize({"agents": [
        {"id": "B", "order": 2}, {"id": "A", "order": 1}, {"no_id": True}
    ]})
    assert [a["id"] for a in reg["agents"]] == ["A", "B"]


def test_get_interrupt_after_default(isolated_registry):
    # 현행 HOTL 게이트 5곳: 인터뷰·RFP·PRD·VisionQA(UI승인)·PMO(WBS승인)
    assert ar.get_interrupt_after(default=["X"]) == ["Requirement_Interviewer", "RFP_Analyst", "Master_PM", "VisionQA", "Master_PMO"]


def test_save_load_roundtrip(isolated_registry):
    reg = ar.load_registry()
    for a in reg["agents"]:
        if a["id"] == "Architect":
            a["hotl_after"] = True
    ar.save_registry(reg)
    assert isolated_registry.exists()
    again = ar.load_registry()
    hotl = [a["id"] for a in again["agents"] if a["hotl_after"]]
    assert "Architect" in hotl
    # 저장본의 hotl 변경이 get_interrupt_after 에 반영
    assert "Architect" in ar.get_interrupt_after(default=[])


def test_save_empty_raises(isolated_registry):
    with pytest.raises(ValueError):
        ar.save_registry({"agents": []})


def test_corrupt_file_falls_back_to_default(isolated_registry):
    isolated_registry.write_text("{ this is not valid json", encoding="utf-8")
    reg = ar.load_registry()  # 손상 → DEFAULT 폴백, 부팅 안 깨짐
    assert any(a["id"] == "RFP_Analyst" for a in reg["agents"])
