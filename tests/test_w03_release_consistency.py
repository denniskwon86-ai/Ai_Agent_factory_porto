"""[W03.3] 릴리스 정본 파일과 사용여부 DB 가 어긋난 자리를 **식별**하는가.

⚠️ 이 단계는 **고치지 않는다.** 복구는 DB 의 결정 기록이나 정본 중 하나를 잃으므로
  사람이 정할 일이다(W03.3 지시: 「자료삭제/정본선택이 필요한 충돌은 임의로 덮어쓰지
  말고 주요결정으로 올린다」). 그래서 여기서는 **찾아내는 것과, 찾은 사실을 숨기지
  않는 것**까지만 본다.
"""
import json
import os

import pytest

from core import library_paths, release_consistency
from core import program_lifecycle as pl


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """격리 보관소 + 격리 DB. 운영 `library/` 와 `data/program_lifecycle.db` 무접촉."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(library_root))
    lifecycle = pl.ProgramLifecycle(db_path=str(tmp_path / "program_lifecycle.db"))
    return lifecycle, library_root


def publish(library_root, release_id, **fields):
    """정본 파일 한 판. 소유문맥을 담는다 — 문맥 판정의 유일한 재료다."""
    from core import atomic_write

    folder = library_root / release_id
    folder.mkdir(parents=True, exist_ok=True)
    atomic_write.replace_json(folder / "release.json", {
        "release_id": release_id, "project_id": "proj_" + release_id,
        "tenant_id": "t_w03", "entity_mode": "REAL",
        "enterprise_scope_id": "n_w03_scope", "owner_dept_id": "dept_w03", **fields,
    }, indent=2)
    return folder


def test_a_matched_pair_is_not_reported(isolated):
    """파일과 기록이 맞으면 아무 말도 하지 않는다 — 정상까지 경보로 띄우지 않는다."""
    lifecycle, library_root = isolated
    publish(library_root, "rel_ok")
    lifecycle.set_status("rel_ok", pl.DISABLED, actor="admin@example.invalid",
                         reason="후속 버전으로 대체")

    report = release_consistency.scan(lifecycle=lifecycle)
    assert report["consistent"] is True
    assert report["orphaned_status"] == []


def test_a_file_without_a_record_is_not_a_mismatch(isolated):
    """★ 「파일 있고 DB 행 없음」은 **불일치가 아니다.**

    `get_status` 가 미기록을 `active` + `recorded=False` 로 답하도록 설계돼 있다.
    이것까지 불일치로 세면 이 기능 이전에 게시된 릴리스가 매번 경보로 뜬다.
    """
    lifecycle, library_root = isolated
    publish(library_root, "rel_legacy")

    report = release_consistency.scan(lifecycle=lifecycle)
    assert report["consistent"] is True
    assert report["unrecorded_artifacts"] == ["rel_legacy"]
    status = lifecycle.get_status("rel_legacy")
    assert status["status"] == pl.ACTIVE and status["recorded"] is False


def test_a_record_without_its_file_is_reported(isolated):
    """★★ 정본이 사라지고 기록만 남은 자리를 찾는다 — 이것이 W03.3 이 노리는 불일치다."""
    lifecycle, library_root = isolated
    publish(library_root, "rel_gone")
    lifecycle.set_status("rel_gone", pl.DISABLED, actor="admin@example.invalid",
                         reason="보안 문제")
    #: 정본만 사라진다(수동 삭제·복원 실패·이관 중단 등). DB 행은 남는다.
    os.remove(library_root / "rel_gone" / "release.json")

    report = release_consistency.scan(lifecycle=lifecycle)
    assert report["consistent"] is False
    assert [row["release_id"] for row in report["orphaned_status"]] == ["rel_gone"]
    row = report["orphaned_status"][0]
    assert row["status"] == pl.DISABLED
    assert row["reason"] == "보안 문제"
    #: ⚠️ 누구 것인지 **알 수 없다** — 파일이 유일한 소유문맥 재료였다.
    assert row["ownership"] is None
    assert report["context_unavailable"] == ["rel_gone"]


def test_the_status_answer_does_not_hide_the_missing_file(isolated):
    """★★ 같은 질문에 두 답이 되지 않게, `get_status` 가 사실을 함께 말한다.

    종전에는 파일이 없어도 「사용 가능」이라고만 답했다. 그 답만 보고 판단하는 호출자가
    다섯 곳 있다(app_data_control · app_data_runtime · calculation_control ·
    data_preparation_control · factory_control).
    """
    lifecycle, library_root = isolated
    publish(library_root, "rel_gone")
    lifecycle.set_status("rel_gone", pl.ACTIVE, actor="admin@example.invalid",
                         reason="재승인")
    assert lifecycle.get_status("rel_gone")["artifact_present"] is True

    os.remove(library_root / "rel_gone" / "release.json")
    answer = lifecycle.get_status("rel_gone")
    assert answer["status"] == pl.ACTIVE, "기존 필드는 그대로여야 한다(호출자 호환)"
    assert answer["artifact_present"] is False, "없는 정본을 있다고 말한다"
    assert "정본 파일이 없습니다" in answer["note"]
    #: 미기록 + 파일 없음도 같은 사실을 말한다.
    assert lifecycle.get_status("rel_never")["artifact_present"] is False


def test_ownership_is_unknown_not_unrestricted_when_the_file_is_gone(isolated):
    """⚠️ 판정 불가를 「제한 없음」으로 읽지 않는다 — `ownership_visible` 과 같은 계약이다."""
    lifecycle, library_root = isolated
    publish(library_root, "rel_ctx")
    assert release_consistency.ownership_of("rel_ctx")["owner_dept_id"] == "dept_w03"

    os.remove(library_root / "rel_ctx" / "release.json")
    assert release_consistency.ownership_of("rel_ctx") is None

    from core.project_visibility import ownership_visible

    #: `own is None` 이면 무제한 권한자에게도 보이지 않는다(차단).
    from core.org_directory import AccessScope

    assert ownership_visible(AccessScope(unrestricted=True), "anyone", None) is False


def test_scan_reads_only(isolated):
    """식별은 아무것도 바꾸지 않는다 — 고치는 것은 사람이 정한 뒤의 일이다."""
    lifecycle, library_root = isolated
    publish(library_root, "rel_gone")
    lifecycle.set_status("rel_gone", pl.DISABLED, actor="admin@example.invalid", reason="x")
    os.remove(library_root / "rel_gone" / "release.json")

    before_rows = json.dumps(lifecycle.list_statuses(), sort_keys=True, default=str)
    before_tree = sorted(str(p.relative_to(library_root)) for p in library_root.rglob("*"))

    release_consistency.scan(lifecycle=lifecycle)

    assert json.dumps(lifecycle.list_statuses(), sort_keys=True, default=str) == before_rows
    assert sorted(str(p.relative_to(library_root)) for p in library_root.rglob("*")) == before_tree


def test_path_shaped_ids_never_reach_the_filesystem(isolated):
    """경로 모양 id 는 `_release_exists` 와 **같은 판정**으로 끊는다."""
    lifecycle, _ = isolated
    for bad in ("../etc", "a/b", "a\\b", ""):
        assert release_consistency._artifact_present(bad) is False
        assert release_consistency.ownership_of(bad) is None
