"""FinOps 리스크 분석기 단위 테스트 — 전부 LLM 0콜 순수 함수."""
from core.risk_analyzer import LOW, MEDIUM, HIGH, classify_file, assess_changes, format_risk_report


# ── classify_file: 확장자/경로/내용 신호 ─────────────────────────────────────
def test_low_for_static_assets():
    assert classify_file("src/styles/app.css", "body{}")["level"] == LOW
    assert classify_file("README.md", "# 문서")["level"] == LOW


def test_high_for_dependency_manifest():
    c = classify_file("frontend/package.json", '{"dependencies": {"axios": "^1"}}')
    assert c["level"] == HIGH and "의존성" in c["reason"]


def test_high_for_schema_and_auth_paths():
    assert classify_file("backend/models.py", "class User: pass")["level"] == HIGH
    assert classify_file("src/auth/LoginForm.tsx", "export default ...")["level"] == HIGH


def test_medium_default_for_plain_code():
    assert classify_file("src/utils/helpers.ts", "export const x = 1")["level"] == MEDIUM


def test_high_only_when_route_count_changes():
    old = "@app.get('/a')\ndef a(): ...\n"
    same_routes = old + "# 내부 로직만 수정(라우트 수 동일)\n"
    added = old + "@app.post('/b')\ndef b(): ...\n"
    # 라우트 수 동일(내용만 변경) → 기존부터 있던 엔드포인트이므로 HIGH 아님(오탐 방지)
    assert classify_file("backend/main_api.py", same_routes, old_code=old)["level"] == MEDIUM
    # 라우트 추가 → API 계약 변경 = HIGH
    c = classify_file("backend/main_api.py", added, old_code=old)
    assert c["level"] == HIGH and "엔드포인트" in c["reason"]


def test_unchanged_file_excluded():
    c = classify_file("src/App.tsx", "same", old_code="same")
    assert c["level"] == "UNCHANGED"


# ── assess_changes: 종합 판정 ────────────────────────────────────────────────
def test_assess_overall_is_max_level():
    files = [
        {"file_path": "a.css", "code": "x"},
        {"file_path": "backend/models.py", "code": "y"},
    ]
    r = assess_changes(files)
    assert r["level"] == HIGH and len(r["high_reasons"]) == 1 and r["changed"] == 2


def test_assess_low_when_styles_only():
    r = assess_changes([{"file_path": "a.css", "code": "x"}, {"file_path": "docs/b.md", "code": "y"}])
    assert r["level"] == LOW


def test_assess_all_unchanged_is_low_zero_changed():
    files = [{"file_path": "a.py", "code": "same"}]
    r = assess_changes(files, read_old=lambda rel: "same")
    assert r["level"] == LOW and r["changed"] == 0


def test_assess_read_old_exception_is_safe():
    def boom(rel):
        raise RuntimeError("git 없음")
    r = assess_changes([{"file_path": "a.py", "code": "x"}], read_old=boom)
    assert r["level"] == MEDIUM and r["changed"] == 1  # 콜백 실패 시 baseline 없음으로 간주


# ── format_risk_report ───────────────────────────────────────────────────────
def test_report_contains_levels_and_paths():
    r = assess_changes([
        {"file_path": "a.css", "code": "x"},
        {"file_path": "package.json", "code": "{}"},
    ])
    md = format_risk_report(r)
    assert "HIGH" in md and "package.json" in md and "a.css" in md
