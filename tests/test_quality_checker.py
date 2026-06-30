"""nodes/utils/quality_checker.py — 프론트 정적 품질 백스톱 테스트.
권고(advisory)라 오탐이 재작업을 폭증시키므로 false-positive 최소가 핵심 —
정상/깨끗한 코드는 통과, 진짜 결함(거대 단일 파일·빈상태 누락·임의 hex)만 잡는다."""
from nodes.utils.quality_checker import check_code_quality


def _f(code: str, path: str = "src/App.tsx"):
    return [{"file_path": path, "code": code}]


def test_empty_is_skipped():
    r = check_code_quality([])
    assert r["ok"] is True and r.get("skipped") is True


def test_clean_single_component_passes():
    code = (
        'export default function App(){\n'
        '  const [n,setN]=useState("");\n'
        '  return <div className="p-4 bg-white"><input value={n} '
        'onChange={(e)=>setN(e.target.value)} /></div>;\n'
        '}\n'
    )
    r = check_code_quality(_f(code))
    assert r["ok"] is True, r["warnings"]


def test_monolith_many_components_flagged():
    # 5개 컴포넌트 + 400줄 초과 → 분리 권고
    body = "\n".join([f"function Comp{i}(){{ return <div>x</div>; }}" for i in range(5)])
    code = body + "\n" + ("// pad line\n" * 410)
    r = check_code_quality(_f(code))
    assert r["ok"] is False
    assert any(it["kind"] == "monolith" for it in r["issues"])


def test_small_multi_component_file_not_flagged():
    # 컴포넌트가 여럿이어도 파일이 작으면 분리 강요하지 않음(오탐 방지)
    code = (
        "function Header(){return <h1>t</h1>;}\n"
        "function Footer(){return <footer>f</footer>;}\n"
        "function App(){return <div><Header/><Footer/></div>;}\n"
    )
    r = check_code_quality(_f(code))
    assert all(it["kind"] != "monolith" for it in r["issues"]), r["warnings"]


def test_list_render_without_empty_state_flagged():
    code = (
        "function App(){ return <ul>{items.map((it)=> <li key={it.id}>{it.name}</li>)}</ul>; }"
    )
    r = check_code_quality(_f(code))
    assert any(it["kind"] == "empty_state" for it in r["issues"]), r["warnings"]


def test_list_render_with_length_guard_passes():
    code = (
        "function App(){ return <ul>{items.length === 0 ? <li>비어 있습니다</li> : "
        "items.map((it)=> <li key={it.id}>{it.name}</li>)}</ul>; }"
    )
    r = check_code_quality(_f(code))
    assert all(it["kind"] != "empty_state" for it in r["issues"]), r["warnings"]


def test_list_render_with_empty_word_passes():
    code = (
        "function App(){ if(!items.length) return <Empty/>; "
        "return <ul>{items.map((it)=> <li key={it.id}>{it.name}</li>)}</ul>; }"
    )
    r = check_code_quality(_f(code))
    assert all(it["kind"] != "empty_state" for it in r["issues"]), r["warnings"]


def test_arbitrary_hex_in_classname_flagged():
    code = 'function App(){ return <div className="bg-[#ff0055] p-4">x</div>; }'
    r = check_code_quality(_f(code))
    assert any(it["kind"] == "design_token" for it in r["issues"]), r["warnings"]


def test_inline_style_hex_flagged():
    code = 'function App(){ return <div style={{ color: "#abcdef" }}>x</div>; }'
    r = check_code_quality(_f(code))
    assert any(it["kind"] == "design_token" for it in r["issues"]), r["warnings"]


def test_tailwind_tokens_no_design_warning():
    code = (
        'function App(){ return <div className="bg-indigo-600 text-white rounded-md p-4">'
        'ok</div>; }'
    )
    r = check_code_quality(_f(code))
    assert all(it["kind"] != "design_token" for it in r["issues"]), r["warnings"]


def test_non_jsx_file_ignored():
    r = check_code_quality([{"file_path": "data.json", "code": '{"color": "#ffffff"}'}])
    assert r["ok"] is True


def test_metrics_reported():
    code = "function App(){return <div>x</div>;}\n"
    r = check_code_quality(_f(code))
    assert r["metrics"]["files"] == 1
    assert r["metrics"]["max_components"] >= 1
