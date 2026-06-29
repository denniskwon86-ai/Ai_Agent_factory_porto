"""core/llm_gateway.py — JSON 제어문자 보정 검증.
LLM이 code 필드에 escape 안 된 리터럴 개행/탭을 넣어 파싱이 통째로 깨지는(=파일 전량 폐기)
가장 흔한 실패를, 문자열 '밖' 구조를 건드리지 않고 보정해야 한다."""
import json
from core.llm_gateway import LLMGateway

esc = LLMGateway._escape_raw_control_chars


def test_raw_newline_in_code_value_becomes_parseable():
    # code 값 안에 리터럴 개행 → 표준 파서는 'Invalid control character' 로 실패
    broken = '{"files": [{"file_path": "a.py", "code": "print(1)\nprint(2)"}]}'
    try:
        json.loads(broken)
        raised = False
    except json.JSONDecodeError:
        raised = True
    assert raised, "전제: 원본은 표준 파싱 실패해야 함"

    parsed = json.loads(esc(broken))
    assert parsed["files"][0]["code"] == "print(1)\nprint(2)"


def test_tab_and_cr_in_string_escaped():
    broken = '{"code": "a\tb\r\nc"}'
    parsed = json.loads(esc(broken))
    assert parsed["code"] == "a\tb\r\nc"


def test_escaped_quote_not_treated_as_string_end():
    # 이미 escape된 따옴표가 있는 유효 JSON은 손상되지 않아야 함
    valid = '{"code": "say \\"hi\\" now"}'
    parsed = json.loads(esc(valid))
    assert parsed["code"] == 'say "hi" now'


def test_valid_json_roundtrips_unchanged():
    valid = '{"files": [{"file_path": "x.tsx", "code": "const a = 1;"}]}'
    assert json.loads(esc(valid)) == json.loads(valid)


def test_structure_newlines_preserved():
    # 문자열 밖 개행(들여쓰기 등)은 JSON 구조상 무의미 — 파싱에 영향 없어야 함
    pretty = '{\n  "code": "ok"\n}'
    parsed = json.loads(esc(pretty))
    assert parsed["code"] == "ok"
