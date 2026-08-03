"""★★★ [CL-0] App-in-App Manifest · 자체 인증 정적 게이트.

## 무엇을 막는가

생성된 앱은 플랫폼 안에서 돌고 인증을 **호스트에서 상속**한다. 그런데 생성기는 "로그인 화면"을
아주 자연스럽게 만든다 — 대부분의 예제 코드가 그렇게 생겼다. 그 앱은 동작하고 화면도 그럴듯하지만
**회사 권한 체계 밖에서 사용자를 인증**한다. 조직 범위·등급·감사가 전부 우회되고, 이 저장소가
권한 모델에 들인 통제가 앱 하나로 무력화된다.

⚠️ 그래서 고정값(`PLATFORM_INHERITED`·`HOST_CONTEXT`·`PLATFORM_LEDGER`)은 권장이 아니라
  **거부 규칙**이다.

## 검사기의 어려운 쪽은 "무엇을 놓아줄까"다

업무 앱에는 인증과 무관한 `승인`·`전자서명 확인`·외부 API 키·일반 입력 폼이 늘 있다. 그것까지
잡으면 개발자는 검사기를 **끈다.** 꺼진 검사는 없는 것과 같으므로, 오탐 테스트가 차단 테스트만큼
중요하다 — 이 파일의 절반이 오탐 테스트다.
"""
import pytest

from core.app_manifest import (APP_CLASSES, AUDIT_MODE, AUTH_MODE, MANIFEST_VERSION,
                               REQUIRED_FORBIDDEN, SCOPE_MODE, ManifestError, assert_valid,
                               build, canonical_json, fingerprint, minimal, snapshot,
                               validate)
from nodes.utils.platform_auth_checker import assert_platform_auth, scan_paths, scan_text


# ── Manifest: 고정값은 협상 대상이 아니다 ──────────────────────────────────
def test_build_fixes_the_platform_contract():
    """★★★ 세 고정값과 금지 기능이 항상 들어간다."""
    m = build(capabilities=["material_plan.read"])
    assert m["auth_mode"] == AUTH_MODE == "PLATFORM_INHERITED"
    assert m["enterprise_scope_mode"] == SCOPE_MODE == "HOST_CONTEXT"
    assert m["audit_mode"] == AUDIT_MODE == "PLATFORM_LEDGER"
    assert set(REQUIRED_FORBIDDEN) <= set(m["forbidden_features"])
    assert m["version"] == MANIFEST_VERSION


def test_standalone_auth_is_refused():
    """★★★ `standalone_auth=True` 는 곧 "앱이 자기 로그인을 갖는다"는 선언이다 — 거부한다."""
    with pytest.raises(ManifestError, match="standalone_auth"):
        build(standalone_auth=True)


def test_host_auth_cannot_be_turned_off():
    """★★★ 호스트 인증 없이 도는 앱은 플랫폼 권한 밖에 있다."""
    with pytest.raises(ManifestError, match="host_auth_required"):
        build(host_auth_required=False)


def test_validate_rejects_tampered_modes():
    """★★ 저장된 Manifest 가 나중에 바뀌어도 검증에서 걸린다(파일을 직접 고치는 경로가 있다)."""
    m = build()
    m["auth_mode"] = "LOCAL"
    errs = validate(m)
    assert any("auth_mode" in e for e in errs)
    with pytest.raises(ManifestError):
        assert_valid(m)


def test_missing_forbidden_entry_is_not_permission():
    """★★★ `forbidden_features` 에서 항목이 빠진 것을 **허용으로 읽지 않는다.**"""
    m = build()
    m["forbidden_features"] = ["local_login"]          # jwt_issuer·local_user_store 누락
    errs = validate(m)
    assert any("누락은 허용이 아닙니다" in e for e in errs)


def test_bad_app_class_is_refused():
    """★ 모르는 분류를 받아 두면 나중에 권한 판단의 근거로 쓰인다."""
    with pytest.raises(ManifestError, match="app_class"):
        build(app_class="whatever")
    assert "departmental" in APP_CLASSES


# ── 두 문서의 형태를 모두 받는다 ───────────────────────────────────────────
def test_flat_capability_strings_are_accepted():
    """★★ 작업서 §6 형태(`"resource.action"`)."""
    m = build(capabilities=["material_plan.read", "arrival.update"])
    assert m["capabilities"] == ["arrival.update", "material_plan.read"]
    assert {c["resource"] for c in m["required_capabilities"]} == {"arrival", "material_plan"}


def test_structured_capabilities_are_accepted():
    """★★ 도메인 설계 §5.3 형태(`{resource, actions}`)."""
    m = build(capabilities=[{"resource": "arrival_event", "actions": ["create", "update"]}])
    assert m["capabilities"] == ["arrival_event.create", "arrival_event.update"]
    assert m["required_capabilities"][0]["actions"] == ["create", "update"]


def test_both_representations_must_agree():
    """★★★ 평면·구조화 목록이 갈라지면 **어느 쪽이 실제 요구인지 알 수 없다.**"""
    m = build(capabilities=["a.read"])
    m["capabilities"] = ["a.read", "b.write"]           # 구조화 쪽에는 없는 능력
    assert any("일치하지 않습니다" in e for e in validate(m))


def test_action_is_not_invented_when_absent():
    """★★★ 동작이 없는 능력에 `read` 를 가정하지 않는다 — 없는 권한을 선언하게 된다."""
    m = build(capabilities=["some_resource"])
    assert m["required_capabilities"][0]["actions"] == []
    assert m["capabilities"] == ["some_resource"]


def test_entrypoint_requires_id_and_path():
    """★ 진입점에 id·path 가 없으면 화면이 앱을 열 수 없다."""
    with pytest.raises(ManifestError, match="entrypoint"):
        build(entrypoints=[{"purpose": "물류 입력"}])


# ── 지문 ──────────────────────────────────────────────────────────────────
def test_fingerprint_is_order_independent():
    """★★★ 키 순서가 다르면 같은 내용이 다른 지문을 갖는다 — 그러면 "바뀌었다"는 판정이
    거짓이 되고, 아무도 그 판정을 믿지 않게 된다."""
    a = {"x": 1, "y": [2, 3]}
    b = {"y": [2, 3], "x": 1}
    assert canonical_json(a) == canonical_json(b)
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_changes_when_capability_changes():
    """★★ 능력이 하나 늘면 지문이 바뀐다 — 수락한 앱과 실행되는 앱이 다른 것을 잡는 근거다."""
    m1 = build(capabilities=["a.read"])
    m2 = build(capabilities=["a.read", "b.write"])
    assert fingerprint(m1) != fingerprint(m2)


def test_snapshot_carries_validation_result():
    """★★ 릴리스에 저장되는 형태 — 지문과 검증 결과가 함께 간다."""
    s = snapshot(build(capabilities=["a.read"]))
    assert s["valid"] is True and s["errors"] == [] and len(s["fingerprint"]) == 32


def test_snapshot_of_nothing_is_the_narrowest_manifest():
    """★★★ 선언이 없는 릴리스에 **능력을 추측해 채우지 않는다.** 빈 능력이 안전한 방향이다."""
    s = snapshot(None)
    assert s["valid"] is True
    assert s["manifest"]["capabilities"] == [] and s["manifest"]["required_data_scopes"] == []
    assert minimal()["auth_mode"] == AUTH_MODE


def test_snapshot_reports_invalid_declaration_instead_of_fixing_it():
    """★★ 잘못된 선언을 조용히 고치지 않는다 — 고치면 개발자는 자기 선언이 무시된 것을 모른다."""
    s = snapshot({"auth_mode": "LOCAL", "version": "1.0"})
    assert s["valid"] is False and s["errors"]


# ── 정적 게이트: 잡아야 하는 것 ────────────────────────────────────────────
@pytest.mark.parametrize("code,signal", [
    ('<form class="login-form">', "local_login_form"),
    ('<input type="password" name="pw" />', "local_login_form"),
    ('@app.post("/api/login")', "local_login_route"),
    ('password_hash = bcrypt.hashpw(pw, salt)', "password_storage"),
    ('token = jwt.encode({"sub": uid}, SECRET)', "jwt_issuer"),
    ('CREATE TABLE users (id INTEGER, name TEXT);', "local_user_store"),
])
def test_auth_signals_are_detected(code, signal):
    """★★★ 자체 인증 코드를 잡는다 — 이것이 없으면 앱이 회사 권한 밖에서 사용자를 인증한다."""
    hits = [h for h in scan_text(code, "app.py") if h["severity"] == "block"]
    assert any(h["signal"] == signal for h in hits), f"{signal} 미탐지: {hits}"


def test_evidence_line_is_included():
    """★★ 근거 줄이 없으면 개발자가 반박할 수 없고, 반박할 수 없는 판정은 신뢰받지 못한다."""
    h = [x for x in scan_text('token = jwt.encode(a, b)', "svc.py")
         if x["severity"] == "block"][0]
    assert h["line"] == 1 and "jwt.encode" in h["evidence"] and h["path"] == "svc.py"


# ── 정적 게이트: 놓아줘야 하는 것(오탐 방지) ───────────────────────────────
@pytest.mark.parametrize("code,why", [
    ('def approve_purchase_order(po_id): ...', "업무 승인"),
    ('if verify_signature(doc): mark_approved(doc)', "전자서명 확인"),
    ('claims = jwt.decode(token, key)  # 검증만', "JWT 검증만"),
    ('headers = {"Authorization": f"Bearer {api_key}"}  # external_api', "외부 API 인증"),
    ('user = host_sdk.current_user()', "호스트 SDK"),
    ('def test_login_form_is_blocked(): ...', "테스트 코드"),
])
def test_business_patterns_are_not_flagged(code, why):
    """★★★ **이 테스트들이 검사기의 생존 조건이다.**

    업무 승인·전자서명·외부 API·JWT 검증까지 결함으로 잡으면 개발자는 검사기를 끈다.
    꺼진 검사는 없는 것과 같으므로, 오탐 방지가 차단만큼 중요하다."""
    blocking = [h for h in scan_text(code, "biz.py") if h["severity"] == "block"]
    assert blocking == [], f"오탐({why}): {blocking}"


def test_ignored_findings_record_why():
    """★★ 놓아준 이유를 남긴다 — 나중에 "왜 안 잡혔나"에 답할 수 있어야 한다."""
    ig = [h for h in scan_text('token = jwt.encode(x)  # test fixture', "t.py")
          if h["severity"] == "ignored"]
    assert ig and ig[0]["ignored_because"]


def test_ordinary_business_form_is_not_a_login():
    """★★★ 일반 업무 입력 폼은 로그인이 아니다 — 여기서 오탐하면 모든 앱이 차단된다."""
    code = ('<form class="arrival-input">'
            '<input type="text" name="lot_no" /><input type="number" name="qty" /></form>')
    assert [h for h in scan_text(code, "ui.tsx") if h["severity"] == "block"] == []


# ── 디렉터리 검사 ─────────────────────────────────────────────────────────
def test_scan_paths_counts_and_blocks(tmp_path):
    """★★ 디렉터리를 훑어 차단 신호를 모은다."""
    (tmp_path / "ok.py").write_text("def approve(x): return True\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text('t = jwt.encode({"sub": 1}, "k")\n', encoding="utf-8")
    r = scan_paths([str(tmp_path)])
    assert r["ok"] is False and r["summary"]["blocking"] >= 1 and r["scanned"] == 2


def test_unreadable_files_are_counted_not_ignored(tmp_path):
    """★★★ 검사하지 못한 파일을 **통과로 읽으면 게이트가 장식이 된다.**"""
    p = tmp_path / "bin.py"
    p.write_bytes(b"\xff\xfe\x00binary")
    r = scan_paths([str(tmp_path)])
    assert r["unreadable"], "읽지 못한 파일이 조용히 넘어갔다"


def test_node_modules_and_git_are_skipped(tmp_path):
    """★ 의존성·이력 폴더까지 훑으면 검사가 몇 분씩 걸리고, 느린 검사는 꺼진다."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("jwt.sign(a)", encoding="utf-8")
    (tmp_path / "app.py").write_text("print(1)", encoding="utf-8")
    r = scan_paths([str(tmp_path)])
    assert r["scanned"] == 1 and r["ok"] is True


def test_assert_platform_auth_tells_what_to_do_instead(tmp_path):
    """★★★ 금지만 알려주면 개발자는 우회 방법을 찾고, 우회된 자체 인증은 다음번엔 안 잡힌다."""
    (tmp_path / "auth.py").write_text('jwt.encode({"sub": 1}, "k")\n', encoding="utf-8")
    with pytest.raises(RuntimeError) as e:
        assert_platform_auth([str(tmp_path)])
    msg = str(e.value)
    assert "호스트 인증을 상속" in msg and "Runtime API" in msg


def test_clean_project_passes(tmp_path):
    """★ 정상 앱은 통과한다 — 통과가 없으면 게이트는 쓸 수 없다."""
    (tmp_path / "svc.py").write_text(
        "def list_arrivals(user):  # host_sdk.current_user() 로 받은 사용자\n"
        "    return db.query('select * from arrival_event')\n", encoding="utf-8")
    r = assert_platform_auth([str(tmp_path)])
    assert r["ok"] is True and r["scanned"] == 1
