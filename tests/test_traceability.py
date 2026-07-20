"""G1 추적성 엔진 단위 테스트 — 추출기/커버리지/게이트/리포트 전부 LLM 0콜 순수 함수."""
import json
from types import SimpleNamespace

from nodes.utils.traceability_manager import (
    extract_ids, extract_req_links, compute_coverage, read_mappings, build_coverage_report,
)
from criteria import DETERMINISTIC_CHECKS


# ── extract_ids: 표기 변형 흡수 + 정규화 + 순서 보존 중복 제거 ─────────────────
def test_extract_ids_variants_and_dedup():
    text = "FR-001 구현. fr_2 지원, FR-001 중복, FR-1234 대형"
    assert extract_ids(text, "FR") == ["FR-001", "FR-002", "FR-1234"]


def test_extract_ids_normalizes_zero_padding():
    # FR-1 과 FR-001 은 같은 요구로 취급(제로패딩 정규화)
    assert extract_ids("FR-1 과 FR-001 은 동일", "FR") == ["FR-001"]


def test_extract_ids_rejects_loose_forms():
    # 공백 구분('FR 3')과 접두사 붙은 오탐('XFR-1')은 제외
    assert extract_ids("FR 3 그리고 XFR-1", "FR") == []


# ── extract_req_links: 같은 줄의 FR↔REQ 만 연결 ──────────────────────────────
def test_extract_req_links_line_based():
    prd = "FR-001: 로그인 (REQ-001, REQ-002)\nFR-002: 대시보드\n(REQ-003) 연결 없음"
    assert extract_req_links(prd) == {"FR-001": ["REQ-001", "REQ-002"]}


# ── compute_coverage: 정의 vs 매핑 차집합 ────────────────────────────────────
def test_compute_coverage_missing_and_normalization():
    prd = "FR-001 FR-002 FR-003"
    mappings = [{"task_id": "T1", "fr_ids": ["FR-001", "fr_3"], "files": ["a.py"]}]
    cov = compute_coverage(prd, mappings)
    assert cov["defined"] == ["FR-001", "FR-002", "FR-003"]
    assert cov["missing"] == ["FR-002"]  # fr_3 은 FR-003 으로 정규화되어 매핑 인정


# ── read_mappings: 읽기 전용(파일 생성 부수효과 없음) ────────────────────────
def test_read_mappings_no_side_effect(tmp_path):
    assert read_mappings(str(tmp_path)) == []
    assert not (tmp_path / "traceability_map.json").exists()


# ── fr_coverage 결정론 게이트 ────────────────────────────────────────────────
def test_fr_coverage_vacuous_pass_without_fr_system(tmp_path):
    check = DETERMINISTIC_CHECKS["fr_coverage"]
    s = SimpleNamespace(prd_summary="FR 체계 없이 서술된 산출물", workspace_root=str(tmp_path))
    assert check(s) is True


def test_fr_coverage_fails_when_unmapped_then_passes(tmp_path):
    check = DETERMINISTIC_CHECKS["fr_coverage"]
    s = SimpleNamespace(prd_summary="FR-001: 필수 기능", workspace_root=str(tmp_path))
    assert check(s) is False  # 매핑 없음 → 미구현으로 간주
    (tmp_path / "traceability_map.json").write_text(
        json.dumps({"mappings": [{"task_id": "T1", "fr_ids": ["FR-001"], "files": ["x.py"]}]}),
        encoding="utf-8",
    )
    assert check(s) is True


# ── build_coverage_report: 수용검수 근거 표 ──────────────────────────────────
def test_build_coverage_report_contents():
    prd = "FR-001: 로그인 (REQ-001)\nFR-002: 리포트"
    mappings = [{"task_id": "T1", "fr_ids": ["FR-001"], "files": ["a.py", "b.py"]}]
    md = build_coverage_report("REQ-001 REQ-002", prd, mappings)
    assert "FR-001" in md and "REQ-001" in md and "T1" in md
    assert "FR-002" in md and "미매핑" in md          # 미구현 FR 노출
    assert "REQ-002" in md                             # RFP REQ 중 FR 미연결 참고 표기


def test_build_coverage_report_empty_without_frs():
    assert build_coverage_report("", "FR 없는 문서", []) == ""
