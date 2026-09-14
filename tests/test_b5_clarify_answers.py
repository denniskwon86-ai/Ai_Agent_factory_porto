"""B5 명확화 답변 본문의 서버 재현. 실행/수집은 main의 기존 strict-writes 런너 전용.

⚠️ 조합 규칙이 화면(`frontend/src/factory/clarifyAnswers.ts`)과 서버 두 곳에 있다.
`GOLDEN_TEXT` 는 프런트 계약 시험(`check-studio-contracts.mjs`)의 같은 예제와 **같은 값**
이어야 한다. 형식을 바꾸면 양쪽 예제를 함께 고쳐야 한다 — 한쪽만 고치면 이 잠금은
잡지 못한다(설계안 §4의 명시된 한계).
"""
import pytest

from core.clarify_answers import (GOLDEN_NOTE, GOLDEN_QUESTIONS, GOLDEN_SELECTIONS, GOLDEN_TEXT,
                                  ClarifyFormatError, serialize)


def test_golden_example_matches_the_frontend_format_byte_for_byte():
    assert serialize(GOLDEN_QUESTIONS, GOLDEN_SELECTIONS, GOLDEN_NOTE) == GOLDEN_TEXT


def test_unanswered_question_is_written_out_not_left_blank():
    """빈 줄로 두면 백엔드가 질문을 건너뛴 것으로 읽는다(화면 주석과 같은 이유)."""
    out = serialize(GOLDEN_QUESTIONS, {}, "")
    assert out.count("→ 선택 없음 (전문가 추천안대로 진행)") == 2
    assert "[추가 의견]" not in out


def test_multiple_choices_follow_option_order_not_selection_order():
    """화면이 `options.filter(...)` 로 만든다. 선택 순서로 쓰면 같은 답변이 다른 본문이 된다."""
    questions = [{"id": "q", "question": "누가?", "multi": True,
                  "options": [{"label": "가"}, {"label": "나"}, {"label": "다"}]}]
    assert serialize(questions, {"q": ["다", "가"]}, "") == (
        "[요구 확인 인터뷰 답변]\n1. 누가?\n→ 선택: 가\n→ 선택: 다")


def test_description_is_appended_only_when_present():
    questions = [{"id": "q", "question": "무엇?", "options": [{"label": "가", "description": ""}]}]
    assert serialize(questions, {"q": ["가"]}, "").endswith("→ 선택: 가")


@pytest.mark.parametrize("note,expected", [("", False), ("   ", False), (" 의견 ", True)])
def test_note_section_appears_only_for_a_non_blank_note(note, expected):
    out = serialize(GOLDEN_QUESTIONS, GOLDEN_SELECTIONS, note)
    assert ("[추가 의견]" in out) is expected
    if expected:
        assert out.endswith("\n\n[추가 의견]\n의견")


@pytest.mark.parametrize("questions", [
    "목록이 아님", [None], [{"id": "q", "question": 1}], [{"id": "q", "question": "?", "options": "x"}],
    [{"id": "q", "question": "?", "options": [{"label": 1}]}],
])
def test_untrusted_question_shape_fails_loudly_instead_of_producing_a_body(questions):
    """조합하지 못하면 빈 문자열이 아니라 오류다. 조용히 다른 본문을 만들지 않는다."""
    with pytest.raises(ClarifyFormatError):
        serialize(questions, {}, "")


def test_selection_values_must_be_a_string_list():
    with pytest.raises(ClarifyFormatError):
        serialize(GOLDEN_QUESTIONS, {"q1": "월 1회"}, "")
