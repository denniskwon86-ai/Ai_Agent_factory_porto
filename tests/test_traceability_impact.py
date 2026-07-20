"""G1-4 리비전 영향 분석 단위 테스트 — 전부 LLM 0콜 순수 함수."""
from nodes.utils.traceability_manager import (
    build_reverse_index, impact_of, analyze_feedback_impact,
)

_MAPPINGS = [
    {"task_id": "T1", "fr_ids": ["FR-001", "FR-002"], "files": ["src/a.tsx", "src/shared.ts"]},
    {"task_id": "T2", "fr_ids": ["FR-003"], "files": ["src/b.tsx", "src/shared.ts"]},
]


def test_reverse_index_both_directions():
    idx = build_reverse_index(_MAPPINGS)
    assert set(idx["by_fr"]["FR-001"]["files"]) == {"src/a.tsx", "src/shared.ts"}
    assert idx["by_fr"]["FR-001"]["tasks"] == ["T1"]
    assert set(idx["by_file"]["src/shared.ts"]["tasks"]) == {"T1", "T2"}


def test_impact_of_fr_includes_shared_file_and_1hop():
    # FR-001 변경 → a.tsx, shared.ts 영향 → shared.ts 는 T2/FR-003 도 공유하므로 1홉 확장
    r = impact_of(_MAPPINGS, fr_ids=["FR-001"])
    assert "src/shared.ts" in r["affected_files"]
    assert "T2" in r["affected_tasks"]           # 공유 파일 경유 확장
    assert "FR-003" in r["affected_frs"]         # 공유 파일이 물린 다른 요구


def test_impact_of_normalizes_fr_notation():
    r = impact_of(_MAPPINGS, fr_ids=["fr_1"])     # 표기 변형도 FR-001 로 정규화
    assert "src/a.tsx" in r["affected_files"]


def test_impact_of_file_seed():
    r = impact_of(_MAPPINGS, files=["src/b.tsx"])
    assert "T2" in r["affected_tasks"] and "FR-003" in r["affected_frs"]


def test_analyze_feedback_extracts_fr():
    r = analyze_feedback_impact("FR-002 의 검증 로직을 고쳐줘", _MAPPINGS)
    assert r["seed_frs"] == ["FR-002"]
    assert "src/a.tsx" in r["affected_files"]     # FR-002 는 T1(a.tsx, shared.ts)


def test_analyze_feedback_without_fr_is_empty_seed():
    r = analyze_feedback_impact("전반적으로 색상을 밝게", _MAPPINGS)
    assert r["seed_frs"] == [] and r["affected_files"] == []
