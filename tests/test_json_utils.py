"""json_utils.loads_lenient 회귀 테스트 — 비정형 LLM JSON 복구."""
from nodes.utils.json_utils import loads_lenient


def test_clean_json():
    assert loads_lenient('{"a": 1}') == {"a": 1}


def test_trailing_comma():
    # critic/judge 응답에서 가장 흔한 실패 — 과거엔 {}로 유실됐음
    out = loads_lenient('{"checks": [{"id":"a","pass":true,},], "v": true,}')
    assert out == {"checks": [{"id": "a", "pass": True}], "v": True}


def test_markdown_fence():
    assert loads_lenient('```json\n{"scores": {"x": 0.4}}\n```') == {"scores": {"x": 0.4}}


def test_prose_around_object():
    assert loads_lenient('비평 결과: {"v": false} 이상.') == {"v": False}


def test_single_quotes():
    assert loads_lenient("{'a': 1}") == {"a": 1}


def test_garbage_returns_empty():
    assert loads_lenient('no json here at all') == {}


def test_empty_and_none():
    assert loads_lenient('') == {}
    assert loads_lenient(None) == {}


def test_array_top_level_returns_empty():
    # dict 계약 보장: 최상위가 dict 아니면 {}
    assert loads_lenient('[1, 2, 3]') == {}
