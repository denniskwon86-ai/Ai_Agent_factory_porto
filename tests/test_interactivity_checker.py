"""nodes/utils/interactivity_checker.py — 동결 입력 정적 검증 테스트.
고정밀(false positive 최소) 보장: 정상 패턴은 통과, 진짜 동결만 차단."""
from nodes.utils.interactivity_checker import check_frontend_interactivity


def _f(code: str):
    return [{"file_path": "src/App.tsx", "code": code}]


def test_empty_is_skipped():
    r = check_frontend_interactivity([])
    assert r["ok"] is True and r.get("skipped") is True


def test_frozen_input_value_without_onchange_fails():
    code = 'export default function App(){return <input value={name} placeholder="이름" />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is False
    assert len(r["frozen"]) == 1
    assert r["frozen"][0]["tag"] == "input"


def test_controlled_input_with_onchange_passes():
    code = (
        'export default function App(){const [n,setN]=useState("");'
        'return <input value={n} onChange={(e)=>setN(e.target.value)} />;}'
    )
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_arrow_function_does_not_break_tag_parsing():
    # onChange 의 `=>` 와 문자열 속 `>` 가 태그를 조기 종료시키면 오탐/누락이 난다 — 그러면 안 됨
    code = (
        'function App(){return <input value={q} placeholder="a > b" '
        'onChange={(e) => setQ(e.target.value)} />;}'
    )
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_defaultvalue_uncontrolled_passes():
    code = 'function App(){return <input defaultValue="hi" />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_readonly_display_field_passes():
    code = 'function App(){return <input value={total} readOnly />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_disabled_field_passes():
    code = 'function App(){return <input value={x} disabled />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_submit_button_value_is_label_passes():
    code = 'function App(){return <input type="submit" value="저장" />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_custom_component_not_flagged():
    # 대문자 컴포넌트 <Input> 은 자체 onChange 처리 가정 — 네이티브가 아니므로 검사 제외
    code = 'function App(){return <Input value={x} />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_frozen_checkbox_fails():
    code = 'function App(){return <input type="checkbox" checked={agree} />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is False


def test_frozen_textarea_fails():
    code = 'function App(){return <textarea value={memo} />;}'
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is False
    assert r["frozen"][0]["tag"] == "textarea"


def test_select_with_onchange_passes():
    code = (
        'function App(){return <select value={v} onChange={(e)=>setV(e.target.value)}>'
        '<option>a</option></select>;}'
    )
    r = check_frontend_interactivity(_f(code))
    assert r["ok"] is True, r["errors"]


def test_non_jsx_file_ignored():
    r = check_frontend_interactivity([{"file_path": "data.json", "code": '{"value": 1}'}])
    assert r["ok"] is True
