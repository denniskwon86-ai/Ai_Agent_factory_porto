"""명확화 답변 제출 본문의 서버 재현. 질문을 만들거나 고르지 않는다.

## 왜 서버에도 두는가

화면(`frontend/src/factory/clarifyAnswers.ts`)이 질문·선택지·설명을 **한 문자열로 엮어**
제출한다. 저장 초안은 `selections` 와 `text` 를 구조로 보관한다. 서버가 「이 초안이 이
제출을 만들었다」를 확인하려면 같은 조합을 재현할 수 있어야 한다.

⚠️⚠️ **표시 문구가 화면과 여기 두 곳에 있다.** 한쪽만 고치면 정상 제출이 대조 실패로
  닫힌다. 그것을 막으려고 `GOLDEN` 을 두고 양쪽 시험이 각자 같은 값과 비교한다
  (`tests/test_b5_clarify_answers.py`, `frontend/scripts/check-studio-contracts.mjs`).
  ★ 이 잠금은 **예제를 한쪽만 고치면 잡지 못한다** — 형식을 바꿀 때는 양쪽 예제를 함께
  고쳐야 하고, 그 사실을 여기 적어 두는 것이 잠금의 절반이다.

★ 재료(`question`·`options[].label`·`options[].description`)는 전부 서버 체크포인트의
  `clarification_questions` 에 있다. 화면 질문과 같다는 것은 `questions_digest` 가 보증한다.
"""
from typing import Any, Mapping, Sequence

HEADER = "[요구 확인 인터뷰 답변]"
NOTE_HEADER = "[추가 의견]"
NO_SELECTION = "→ 선택 없음 (전문가 추천안대로 진행)"

#: 형식 고정용 예제. 화면 계약 시험과 **같은 값**이어야 한다.
GOLDEN_QUESTIONS = [
    {"id": "q1", "question": "원료 도입 주기를 어떻게 잡습니까?",
     "options": [{"label": "월 1회", "description": "재고 부담이 크다"}, {"label": "주 1회"}]},
    {"id": "q2", "question": "품질 기준을 누가 정합니까?", "multi": True,
     "options": [{"label": "품질팀"}, {"label": "생산팀"}]},
]
GOLDEN_SELECTIONS = {"q1": ["월 1회"]}
GOLDEN_NOTE = "  추가로 확인할 것이 있습니다.  "
GOLDEN_TEXT = (
    "[요구 확인 인터뷰 답변]\n"
    "1. 원료 도입 주기를 어떻게 잡습니까?\n"
    "→ 선택: 월 1회 (재고 부담이 크다)\n"
    "2. 품질 기준을 누가 정합니까?\n"
    "→ 선택 없음 (전문가 추천안대로 진행)\n"
    "\n"
    "[추가 의견]\n"
    "추가로 확인할 것이 있습니다."
)


class ClarifyFormatError(ValueError):
    """질문 형태를 신뢰할 수 없어 본문을 재현하지 못한다. 조용히 빈 값으로 만들지 않는다."""


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise ClarifyFormatError("문자열이 아닌 질문 항목")
    return value


def serialize(questions: Sequence[Any], selections: Mapping[str, Sequence[str]], note: str = "") -> str:
    """화면 `serializeClarifyAnswers` 와 같은 문자열을 만든다. 순서를 바꾸지 않는다.

    ⚠️ 고른 항목의 출력 순서는 **선택 순서가 아니라 질문의 선택지 순서**다. 화면이
      `options.filter(...)` 로 만들기 때문이다. 여기서 `selections` 순서로 쓰면 어긋난다."""
    if not isinstance(questions, (list, tuple)) or not isinstance(selections, Mapping):
        raise ClarifyFormatError("질문 목록과 선택 사전이 필요합니다.")
    lines = [HEADER]
    for index, question in enumerate(questions):
        if not isinstance(question, Mapping):
            raise ClarifyFormatError("질문 항목이 객체가 아닙니다.")
        chosen = selections.get(_text(question.get("id", "")), ())
        if not isinstance(chosen, (list, tuple)) or any(not isinstance(label, str) for label in chosen):
            raise ClarifyFormatError("선택값은 문자열 목록이어야 합니다.")
        lines.append(f"{index + 1}. {_text(question.get('question', ''))}")
        options = question.get("options") or ()
        if not isinstance(options, (list, tuple)):
            raise ClarifyFormatError("선택지가 목록이 아닙니다.")
        picked = []
        for option in options:
            if not isinstance(option, Mapping):
                raise ClarifyFormatError("선택지 항목이 객체가 아닙니다.")
            label = _text(option.get("label", ""))
            if label in chosen:
                description = option.get("description")
                picked.append(f"→ 선택: {label}" + (f" ({_text(description)})" if description else ""))
        lines.extend(picked or [NO_SELECTION])
    if note.strip():
        lines.extend(["", NOTE_HEADER, note.strip()])
    return "\n".join(lines)
