"""nodes/utils/regression_checker.py — 심볼 회귀 게이트 검증.
직전 버전 대비 '순감소'한 기능만 차단(리네임 오탐 방지), 삭제 의도 명시 시 우회."""
from nodes.utils.regression_checker import check_symbol_regression, is_deletion_intended


def _baseliner(mapping):
    return lambda rel: mapping.get(rel)


def test_lost_input_field_is_regression():
    prev = 'export default function App(){return (<form><input value={a} onChange={f}/><input value={b} onChange={g}/></form>);}'
    new = 'export default function App(){return (<form><input value={a} onChange={f}/></form>);}'
    r = check_symbol_regression([{"file_path": "src/App.tsx", "code": new}], _baseliner({"src/App.tsx": prev}))
    assert r["ok"] is False
    assert "입력요소" in " ".join(r["errors"])


def test_lost_handler_is_regression():
    prev = 'const handleSubmit=()=>{}; const handleDelete=()=>{}; export const Form=()=>null;'
    new = 'const handleSubmit=()=>{}; export const Form=()=>null;'
    r = check_symbol_regression([{"file_path": "src/Form.tsx", "code": new}], _baseliner({"src/Form.tsx": prev}))
    assert r["ok"] is False
    assert "handleDelete" in " ".join(r["errors"])


def test_lost_backend_route_is_regression():
    prev = '@app.get("/parts")\ndef a():...\n@app.post("/parts")\ndef b():...\n@app.delete("/parts/{id}")\ndef c():...'
    new = '@app.get("/parts")\ndef a():...\n@app.post("/parts")\ndef b():...'
    r = check_symbol_regression([{"file_path": "backend/main.py", "code": new}], _baseliner({"backend/main.py": prev}))
    assert r["ok"] is False
    assert "/parts/{id}" in " ".join(r["errors"])


def test_pure_rename_not_flagged():
    # 핸들러 1:1 리네임 → 개수 동일(net 0) → 회귀 아님(오탐 방지)
    prev = 'const handleSave=()=>{}; export const Form=()=>null;'
    new = 'const handleSubmit=()=>{}; export const Form=()=>null;'
    r = check_symbol_regression([{"file_path": "src/Form.tsx", "code": new}], _baseliner({"src/Form.tsx": prev}))
    assert r["ok"] is True, r["errors"]


def test_addition_only_not_flagged():
    prev = 'export const A=()=>null;'
    new = 'export const A=()=>null; export const B=()=>null;'
    r = check_symbol_regression([{"file_path": "src/x.tsx", "code": new}], _baseliner({"src/x.tsx": prev}))
    assert r["ok"] is True, r["errors"]


def test_new_file_no_baseline_skipped():
    new = 'export const A=()=>null;'
    r = check_symbol_regression([{"file_path": "src/new.tsx", "code": new}], _baseliner({}))
    assert r["ok"] is True


def test_deletion_intent_bypasses_gate():
    prev = 'const handleA=()=>{}; const handleB=()=>{}; export const F=()=>null;'
    new = 'const handleA=()=>{}; export const F=()=>null;'
    r = check_symbol_regression([{"file_path": "src/F.tsx", "code": new}],
                                _baseliner({"src/F.tsx": prev}), allow_deletion=True)
    assert r["ok"] is True and r.get("skipped") is True


def test_is_deletion_intended():
    assert is_deletion_intended("이 필드는 삭제해주세요") is True
    assert is_deletion_intended("please remove the old endpoint") is True
    assert is_deletion_intended("정렬 기능을 추가하세요") is False


def test_empty_files_skipped():
    r = check_symbol_regression([], _baseliner({}))
    assert r["ok"] is True and r.get("skipped") is True
