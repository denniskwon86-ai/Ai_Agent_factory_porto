"""명시적인 실패 근거만 정리 대상으로 분류하며 원본을 변경하지 않는다."""
import copy
import json

import pytest

from core.release_catalog_audit import inspect_release
from scripts import review_failed_releases as cli


def release(**changes):
    return {"release_id": "release-one", "project_id": "project-one", "project_name": "업무 앱",
            "wbs_tasks": [{"status": "DONE"}], **changes}


@pytest.mark.parametrize("changes", [
    {"terminal_status": "FAILED_REVIEW"},
    {"wbs_tasks": [{"status": "DONE"}, {"status": "FAILED"}, {"status": "TODO"}]},
])
def test_failed_build_is_flagged(changes):
    assert inspect_release(release(**changes))["reasons"] == ["INCOMPLETE_FAILED_BUILD"]


@pytest.mark.parametrize("signal", ["password_storage", "local_login_route", "jwt_issuer"])
def test_own_login_requires_two_explicit_signals(signal):
    row = release(platform_auth_scan={"ok": False, "blocking": [
        {"signal": "local_login_form"}, {"signal": signal}]})
    assert inspect_release(row)["reasons"] == ["APP_LOCAL_LOGIN"]


@pytest.mark.parametrize("changes", [
    {"project_name": "CRM003", "frontend_code_summary": ""},
    {"project_name": "CRM001"},
    {"release_id": "kitapp_valid_APP-01", "frontend_code_summary": ""},
    {"lifecycle_status": "candidate", "wbs_tasks": [{"status": "TODO"}]},
    {"platform_auth_scan": {"ok": False, "blocking": [{"signal": "local_login_form"}]}},
    {"platform_auth_scan": {"ok": False, "blocking": [{"signal": "password_storage"}]}},
])
def test_name_empty_code_or_single_signal_does_not_authorize_cleanup(changes):
    assert inspect_release(release(**changes))["reasons"] == []


def test_fingerprint_covers_code_and_inspection_changes_nothing():
    row = release(frontend_code_summary="old")
    before = copy.deepcopy(row)
    initial = inspect_release(row)
    assert row == before
    assert initial == inspect_release(dict(reversed(list(row.items()))))
    row["frontend_code_summary"] = "new"
    assert inspect_release(row)["content_fingerprint"] != initial["content_fingerprint"]


def test_audit_cli_only_writes_a_new_report(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    paths = []
    for identity, row in [("bad", release(terminal_status="FAILED_REVIEW")),
                          ("kit", release(release_id="kitapp_one", frontend_code_summary=""))]:
        path = root / "library" / identity / "release.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(row), encoding="utf-8")
        paths.append(path)
    before = [p.read_bytes() for p in paths]
    report = tmp_path / "audit.json"
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli.sys, "argv", ["audit", "--report", str(report)])
    cli.main()
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["mode"] == "READ_ONLY" and result["population"] == 2
    assert len(result["targets"]) == len(result["preserved"]) == 1
    assert before == [p.read_bytes() for p in paths]
    assert not (root / "data").exists()
    with pytest.raises(FileExistsError):
        cli.main()  # 이미 남긴 감사 증적은 덮어쓰지 않는다.


def test_changed_plan_is_rejected_before_authentication(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    (root / "library").mkdir(parents=True)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"mode": "READ_ONLY", "targets": [{"release_id": "old"}]}), encoding="utf-8")
    target = tmp_path / "before.json"
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli.sys, "argv", ["audit", "--apply-plan", str(plan), "--report", str(target)])
    with pytest.raises(RuntimeError, match="대상 내용"):
        cli.main()
    assert not target.exists()
