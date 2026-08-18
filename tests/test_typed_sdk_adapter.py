"""★★★ [I-4 5a·5b] Typed SDK Adapter 와 Host Runtime 우회 정적 검사.

이 시험이 전제하는 것: **조직도·DB·LLM 을 쓰지 않는다.** 생성기는 순수 함수이고
검사기는 문자열만 본다.

## 두 그물

⚠️⚠️ 어댑터는 **두 번째 그물**이다. 서버의 2차 판정이 첫 번째다 — 어댑터만 믿으면
  브라우저에서 고쳐 부르는 순간 통제가 없다. 여기서 지키는 것은 «실수를 막는 도구»가
  제 일을 하는가이지, 그것이 권한 경계라는 주장이 아니다.

⚠️ 검사기의 어려운 부분은 「무엇을 잡을까」가 아니라 **「무엇을 놓아줄까」**다.
  오탐이 늘면 검사기는 꺼지고, 꺼진 검사기는 없는 것과 같다. 그래서 이 파일의 절반은
  **놓아줘야 하는 것**을 지킨다.
"""
import json
import os

import pytest

from core import typed_sdk_adapter as sdk
from nodes.utils import platform_auth_checker as checker


def _ds(name, actions=("read",), fields=(("qty", "number", True),), **kw):
    d = {"name": name, "label": name, "purpose": "설명",
         "allowed_actions": list(actions),
         "data_role": "NATIVE_SUPPLEMENT", "source_intent": "AFS_NATIVE",
         "duplicate_entry_policy": "NO_DUPLICATE_CHECK_REQUIRED",
         "fields": [{"name": n, "type": t, "required": r,
                     "classification": "INTERNAL"} for n, t, r in fields]}
    d.update(kw)
    return d


def _contract(*datasets, approved=True, app_class="departmental"):
    from core import host_contract_compiler as hcc

    res = hcc.compile_contract({"app_class": app_class, "capability_intents": [],
                                "datasets": list(datasets)}, project_id="p1")
    assert not res.errors, res.errors
    c = res.contract
    if approved:
        #: ⚠️ `decision_ledger_id` 는 스키마 필수다 — 승인에는 **원장 id 가 남아야**
        #:   하고, 그것이 「누가 무엇을 보고 승인했는가」의 유일한 연결이다.
        c = dict(c, status="APPROVED",
                 approval={"status": "APPROVED", "approved_by": "t_admin@test.invalid",
                           "approved_at": "2026-08-17T00:00:00+00:00",
                           "decision_ledger_id": "dle_test0000001"})
    return c


# ── 이름 만들기 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("material_arrivals", "materialArrivals"),
    ("production", "production"),
    ("a_b_c", "aBC"),
    ("2024_plan", "ds2024Plan"),          # 숫자로 시작하면 문법 오류가 난다
    ("생산-실적", ""),                     # 식별자로 쓸 수 없는 문자만 있으면 빈 값
])
def test_identifier_names_are_valid_typescript(raw, expected):
    """⚠️ 숫자로 시작하는 이름을 그대로 두면 **문법 오류가 나는 파일**을 만들고,
    그 실패는 빌드 단계에서야 드러난다."""
    assert sdk.camel(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("string", "string"), ("number", "number"), ("boolean", "boolean"),
    ("json", "Record<string, unknown>"),
    ("모르는타입", "unknown"), ("", "unknown"), (None, "unknown"),
])
def test_unknown_types_become_unknown_not_any(raw, expected):
    """★★★ `any` 로 두면 타입 검사가 **그 필드에서만 꺼지고**, 꺼진 줄 아무도 모른다.
    `unknown` 은 쓰려면 좁혀야 하므로 작성자가 알아챈다."""
    assert sdk.ts_type(raw) == expected


# ── 허용되지 않은 동작은 «생성되지 않는다» ──────────────────────────────
def test_only_allowed_actions_become_functions():
    """★★★ 이것이 5a 의 전부다 — 없는 함수는 **타입 검사에서 먼저** 걸린다."""
    src = sdk.generate(_contract(_ds("production", actions=("read",)))).source
    assert "list:" in src and "get:" in src
    for forbidden in ("create:", "update:", "remove:"):
        assert forbidden not in src, f"{forbidden} 가 허용되지 않았는데 생성됐다"


def test_full_actions_generate_every_method():
    src = sdk.generate(_contract(
        _ds("production", actions=("read", "create", "update", "delete")))).source
    for m in ("list:", "get:", "create:", "update:", "remove:"):
        assert m in src


def test_missing_methods_are_explained_not_just_absent():
    """⚠️ 없는 이유를 못 보면 작성자는 「어댑터가 불완전하다」고 읽고
    `window.afs.data.*` 를 직접 부른다 — 그러면 통제가 통째로 새어 나간다."""
    src = sdk.generate(_contract(_ds("production", actions=("read",)))).source
    assert "생성하지 않은 동작" in src
    assert "재승인" in src


def test_delete_is_exposed_as_remove():
    """⚠️ `delete` 는 JS 예약어다. 두 이름이 갈리면 「계약에는 있는데 어댑터에는
    없다」가 되고, 그 원인은 아무도 못 찾는다."""
    src = sdk.generate(_contract(_ds("p", actions=("read", "delete")))).source
    assert "remove:" in src
    assert "window.afs.data.remove('p'" in src


# ── 승인 전에는 만들지 않는다 ───────────────────────────────────────────
def test_an_unapproved_contract_produces_nothing():
    """⚠️ 만들면 앱 코드가 **승인 전 계약에 맞춰** 작성되고, 계약이 바뀌면 코드가
    통째로 어긋난다."""
    r = sdk.generate(_contract(_ds("production"), approved=False))
    assert r.ok is False
    assert "승인되지 않은" in r.reason


@pytest.mark.parametrize("bad", [None, "문자열", 42, {}, {"datasets": []}])
def test_garbage_produces_nothing_and_says_why(bad):
    r = sdk.generate(bad)
    assert r.ok is False and r.reason


def test_a_zero_dataset_contract_still_produces_a_file():
    """★ 데이터셋 0개도 **유효한 계약**이다(0개라는 선언 자체가 통제다).
    ⚠️ 파일이 없으면 「생성이 실패했다」로 읽힌다 — 왜 비었는지 적어 둔다."""
    r = sdk.generate(_contract())
    assert r.ok is True
    assert "데이터셋을 선언하지 않았습니다" in r.source
    assert r.dataset_names == []


def test_the_same_contract_always_produces_the_same_file():
    """★ 결정론적이다 — 같은 계약이 늘 같은 파일을 낸다(지문과 같은 이유)."""
    a = _contract(_ds("quality"), _ds("production"))
    b = _contract(_ds("production"), _ds("quality"))
    assert sdk.generate(a).source == sdk.generate(b).source


def test_the_fingerprint_is_written_into_the_file():
    """★ 파일만 보고 「어느 계약에서 나왔나」에 답할 수 있어야 한다."""
    c = _contract(_ds("production"))
    src = sdk.generate(c).source
    assert c["semantic_fingerprint"] in src
    assert "손으로 고치지 않는다" in src


def test_required_fields_are_not_optional_in_the_record_type():
    src = sdk.generate(_contract(_ds(
        "production", fields=(("qty", "number", True), ("memo", "string", False))))).source
    assert "qty: number;" in src
    assert "memo?: string;" in src


# ── [5b] 정적 검사 신호 ─────────────────────────────────────────────────
def _sigs(text, path="src/App.tsx"):
    return {f["signal"] for f in checker.scan_text(text, path)
            if f["severity"] == "block"}


@pytest.mark.parametrize("code", [
    "localStorage.setItem('auth_token', t)",
    "sessionStorage.setItem('jwt', t)",
    "localStorage['api_key'] = k",
    "document.cookie = 'session_id=' + s",
])
def test_tokens_in_browser_storage_are_blocked(code):
    assert "token_in_browser_store" in _sigs(code)


@pytest.mark.parametrize("code", [
    "localStorage.setItem('sidebarOpen', 'true')",
    "localStorage.setItem('theme', 'dark')",
    "sessionStorage.setItem('lastTab', '3')",
    "const draft = localStorage.getItem('form_draft')",
])
def test_app_ui_state_in_storage_is_left_alone(code):
    """★★★ **놓아줘야 하는 것.** 앱이 자기 화면 상태를 저장하는 것은 정상이다 —
    브리지가 가짜 저장소로 갈아끼운다. 잡을 것은 토큰·자격증명이다.

    ⚠️ 여기가 깨지면 검사기가 평범한 화면 코드를 막고, 개발자는 검사기를 끈다."""
    assert "token_in_browser_store" not in _sigs(code)


@pytest.mark.parametrize("code", [
    "await fetch('/api/v1/appdata/datasets')",
    "const url = `/api/v1/appdata/records/${id}`",
    "axios.get('/api/v1/runtime/proof')",
])
def test_direct_appdata_calls_are_blocked(code):
    assert "direct_appdata_call" in _sigs(code)


@pytest.mark.parametrize("code", [
    "fetch('/api/v1/anything')",
    "axios.post('/api/v1/x', body)",
    "new WebSocket('/api/v1/stream')",
])
def test_generic_host_calls_are_blocked(code):
    assert "generic_host_fetch" in _sigs(code)


@pytest.mark.parametrize("code", [
    #: ⚠️ 여기에 `example.com` 을 쓰면 안 된다 — `example` 이 **테스트 문맥 면제**에
    #:   걸려 신호가 통째로 무시되고, 그러면 이 시험은 «호스트만 잡는다» 가 아니라
    #:   «아무것도 안 잡는다» 를 확인하게 된다(변이 검사에서 실측으로 드러났다).
    "fetch('https://weather.kma.go.kr/today')",
    "axios.get('https://partner.acme.co.kr/v1/rates')",
    "fetch(props.externalUrl)",
])
def test_calls_to_the_outside_world_are_left_alone(code):
    """★ 외부 시스템 호출은 앱이 할 수 있는 일이다 — 호스트를 향한 것만 잡는다."""
    assert "generic_host_fetch" not in _sigs(code)


def test_the_test_context_exemption_does_not_hide_the_signal():
    """★★★ 면제 낱말이 **신호를 통째로 지우지 않는지** 확인한다.

    ⚠️ 같은 줄에 `example` 이 있다는 이유로 호스트 호출까지 봐주면, 시험 코드처럼
      보이는 한 줄이 곧 우회로가 된다. 면제는 좁아야 한다 — 여기서는 신호가
      **잡히되 «ignored» 로** 기록되는 것까지 본다(감사 가능하게)."""
    found = checker.scan_text("fetch('/api/v1/x')  // example", "src/App.tsx")
    hit = [f for f in found if f["signal"] == "generic_host_fetch"]
    assert hit, "면제 낱말이 신호 자체를 지웠다"
    assert hit[0]["severity"] == "ignored"
    assert "example" in hit[0].get("ignored_because", [])


@pytest.mark.parametrize("code", [
    "indexedDB.open('appdb')",
    "const db = new Dexie('mydb')",
    "CREATE TABLE permissions (id TEXT)",
    "create table if not exists roles (id text)",
])
def test_app_local_databases_are_blocked(code):
    assert "app_local_db" in _sigs(code)


def test_direct_sdk_calls_are_blocked_in_app_code():
    code = "const rows = await window.afs.data.list('production')"
    assert "undeclared_dataset" in _sigs(code, "src/pages/Home.tsx")


def test_the_generated_adapter_is_allowed_to_call_the_sdk():
    """★★★ 어댑터 **자신**은 그것이 일이다.

    ⚠️ 이 면제가 없으면 검사기가 자기가 만든 파일을 막고, 아무도 어댑터를 쓰지
      않게 된다 — 통제를 만들어 놓고 통제 때문에 못 쓰는 상태다."""
    code = "  list: (page) => window.afs.data.list('production', page),"
    assert "undeclared_dataset" not in _sigs(code, "src/generated/afs-contract.ts")
    #: ⚠️ 놓아준 이유가 남아야 한다 — 남지 않으면 나중에 왜 통과했는지 알 수 없다
    found = checker.scan_text(code, "src/generated/afs-contract.ts")
    assert any(f["signal"] == "undeclared_dataset" and f["severity"] == "ignored"
               and "generated_adapter" in f.get("ignored_because", []) for f in found)


def test_the_exemption_is_by_path_not_by_content():
    """⚠️ 「내용에 «자동 생성» 이라고 적혀 있으면 면제」로 하면 그 한 줄을 베껴
    넣는 것이 곧 우회로가 된다."""
    code = ("// ⚠️ 자동 생성 — 손으로 고치지 않는다\n"
            "window.afs.data.list('production')")
    assert "undeclared_dataset" in _sigs(code, "src/pages/Sneaky.tsx")


def test_a_generated_adapter_still_gets_the_other_signals():
    """⚠️ 어댑터라고 **모든** 신호를 놓아주지 않는다 — 면제는 한 신호뿐이다."""
    code = "localStorage.setItem('auth_token', t)"
    assert "token_in_browser_store" in _sigs(code, "src/generated/afs-contract.ts")


# ── 생성 → 검사 연결 ────────────────────────────────────────────────────
def test_the_generated_adapter_passes_its_own_checker():
    """★★★ 생성기가 만든 파일이 검사기를 통과해야 한다.

    ⚠️ 여기가 깨지면 파이프라인이 **자기가 만든 앱을 자기가 막는다.**"""
    src = sdk.generate(_contract(
        _ds("production", actions=("read", "create", "update", "delete")))).source
    findings = checker.scan_text(src, "src/generated/afs-contract.ts")
    blocking = [f for f in findings if f["severity"] == "block"]
    assert blocking == [], blocking


def test_the_compiler_node_writes_the_adapter(tmp_path):
    """★ 승인된 계약이 있으면 컴파일러 노드가 어댑터를 남긴다."""
    import asyncio

    from nodes import contract as cn
    from nodes.utils.wbs_manager import WBSManager

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    WBSManager(ws).initialize_wbs("p", [{"task_id": "A", "title": "앱",
                                         "artifact_kind": "APP"}],
                                  runtime_contract_profile="v1")
    d = os.path.join(ws, "contracts", "drafts")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "A.json"), "w", encoding="utf-8") as f:
        json.dump({"app_class": "departmental", "capability_intents": [],
                   "datasets": [_ds("production", actions=("read", "create"))]}, f)

    #: ① 최초 컴파일 — 아직 승인 전이므로 어댑터는 나오지 않는다
    asyncio.run(cn.run_host_contract_compiler(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1"}))
    assert not os.path.exists(cn.adapter_path(ws)), "승인 전에 어댑터가 나왔다"

    #: ② 승인된 계약을 정본에 넣고 다시 컴파일하면 어댑터가 나온다
    path = cn.contract_path(ws)
    c = json.load(open(path, encoding="utf-8"))
    c["status"] = "APPROVED"
    c["approval"] = {"status": "APPROVED", "approved_by": "t_admin@test.invalid",
                     "approved_at": "2026-08-17T00:00:00+00:00",
                     "decision_ledger_id": "dle_test0000001"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

    asyncio.run(cn.run_host_contract_compiler(
        {"project_name": "p", "workspace_root": ws, "runtime_contract_profile": "v1"}))
    written = open(cn.adapter_path(ws), encoding="utf-8").read()
    assert "export const production" in written
    assert "create:" in written and "remove:" not in written
