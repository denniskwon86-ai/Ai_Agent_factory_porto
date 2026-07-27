# ==========================================
# 업무표준(규정/지침) 기준정보 (2026-07-27)
#
# 에이전트가 "나는 어떤 기준으로 일하고 무엇을 확인해 다음으로 넘기는가"를
# 코드 상수가 아니라 관리되는 기준정보에서 조회하게 한다.
#
# 두 분류로 나눈 이유:
#   규정(regulation) — 판정 에이전트. 통과/반려 권한이 있고 기준값을 엄격히 따른다.
#   지침(guideline)  — 생성 에이전트. 어떻게 작성하는지를 안내하며 판정 권한이 없다.
# 한 분류에 섞으면 지침을 규정처럼 강제해 생성이 막히거나, 규정을 지침처럼 느슨하게 써서
# 가짜 통과가 난다.
# ==========================================
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.work_standard import (
    KIND_GUIDELINE, KIND_REGULATION,
    WORK_GUIDELINE_TYPE, WORK_REGULATION_TYPE,
    get_standard, render_standard_brief, standard_code,
)
from core.work_standard_seed import _JUDGING_STAGES, ensure_type, seed_from_criteria


def test_standard_code_format():
    assert standard_code("code_review") == "STD-CODE_REVIEW"


def test_seed_is_idempotent_and_splits_kinds():
    ensure_type()
    seed_from_criteria(force=False)
    res = seed_from_criteria(force=False)
    assert all(v.startswith("skip") for v in res.values()), f"재시드가 멱등이 아닙니다: {res}"


def test_judging_stages_are_regulations():
    for stage in ("CODE_REVIEW", "QA", "SUPERVISOR", "PMO"):
        std = get_standard(stage)
        assert std, f"{stage} 표준 조회 실패"
        if std["_meta"]["source"] == "registered":
            assert std.get("standard_kind") == KIND_REGULATION, f"{stage} 는 규정이어야 합니다"


def test_authoring_stages_are_guidelines():
    for stage in ("RFP", "PLANNING", "ARCHITECTURE", "TECH_SPEC"):
        std = get_standard(stage)
        assert std, f"{stage} 표준 조회 실패"
        assert stage not in _JUDGING_STAGES
        if std["_meta"]["source"] == "registered":
            assert std.get("standard_kind") == KIND_GUIDELINE, f"{stage} 는 지침이어야 합니다"


def test_guideline_brief_denies_gate_authority():
    """생성 에이전트에게 통과/반려 권한이 없음을 고지문이 명시해야 한다."""
    brief = render_standard_brief("TECH_SPEC")
    assert "업무지침" in brief
    assert "통과/반려 권한이 없습니다" in brief


def test_regulation_brief_states_pass_line():
    """판정 에이전트에게는 통과선이 수치로 제시되어야 한다."""
    brief = render_standard_brief("CODE_REVIEW")
    assert "업무규정" in brief
    assert "통과선" in brief
    # 품질 반려 금지 같은 must_not 이 고지문에 실려야 실효가 있다
    assert "금지" in brief


def test_supervisor_brief_says_it_is_not_a_gate():
    """슈퍼바이저는 심판이 아니다 — 고지문이 그 사실을 명시해야 한다."""
    brief = render_standard_brief("SUPERVISOR")
    assert "관문이 아닙니다" in brief


def test_unknown_stage_returns_none():
    assert get_standard("NO_SUCH_STAGE") is None
    assert render_standard_brief("NO_SUCH_STAGE") == ""


def test_fallback_when_not_registered(monkeypatch):
    """등록본 조회가 실패해도 코드 기본값으로 폴백해 판정이 멈추지 않아야 한다."""
    import core.work_standard as ws

    class _Boom:
        def get_record(self, *a, **k):
            raise RuntimeError("db down")

    import core.master_data as md
    monkeypatch.setattr(md, "master_data", _Boom(), raising=False)
    std = ws.get_standard("CODE_REVIEW")
    assert std is not None and std["_meta"]["source"] == "fallback"
    assert std.get("checks"), "폴백 루브릭에 checks 가 있어야 합니다"


def test_types_are_distinct():
    assert WORK_REGULATION_TYPE != WORK_GUIDELINE_TYPE
