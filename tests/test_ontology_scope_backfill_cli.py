"""Safety contract for the explicit ontology scope-index maintenance command."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.data_preparation.store import DataPreparationStore
from scripts import backfill_ontology_scope_index as cli


@pytest.fixture
def prepared_db(tmp_path: Path) -> Path:
    path = tmp_path / "data_preparation.db"
    store = DataPreparationStore(str(path))
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO kit_registry_versions "
            "(kit_version_id,kit_id,version,name,mode,source_path,fingerprint,profile_json,"
            "status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("kv-test", "KIT-T", "1", "test", "DEMO/SYNTHETIC", "test", "fp", "{}",
             "active", "2026-08-28T00:00:00Z", "2026-08-28T00:00:00Z"))
    # The command is intentionally stricter than ordinary product reads: it
    # accepts only the stopped-server state in which committed WAL pages have
    # been checkpointed into the main file.
    with sqlite3.connect(str(path)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


def test_dry_run_uses_disposable_copy_and_does_not_change_source(
        prepared_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_before = prepared_db.read_bytes()
    visited: list[Path] = []

    def fake_backfill(store):
        visited.append(Path(store.db_path).resolve())
        with store.transaction() as conn:
            conn.execute("CREATE TABLE copy_only_marker(value TEXT)")
        return {}

    monkeypatch.setattr(cli.scope_index, "backfill_supported_snapshots", fake_backfill)
    result = cli.run(prepared_db, temporary_root=tmp_path / "rehearsal")

    assert result["mode"] == "dry-run"
    assert result["source_changed"] is False
    assert visited and visited[0] != prepared_db.resolve()
    assert prepared_db.read_bytes() == source_before
    with sqlite3.connect(str(prepared_db)) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='copy_only_marker'"
        ).fetchone() is None
    assert not list((tmp_path / "rehearsal").glob("ontology-scope-backfill-*"))


def test_apply_requires_explicit_backup(prepared_db: Path):
    with pytest.raises(cli.BackfillSafetyError, match="requires a new --backup"):
        cli.run(prepared_db, apply=True)


def test_apply_refuses_to_overwrite_backup(prepared_db: Path, tmp_path: Path):
    backup = tmp_path / "existing.db"
    backup.write_bytes(b"keep")
    with pytest.raises(cli.BackfillSafetyError, match="refusing overwrite"):
        cli.run(prepared_db, apply=True, backup=backup, temporary_root=tmp_path / "run")
    assert backup.read_bytes() == b"keep"


def test_non_empty_wal_is_fail_closed(prepared_db: Path):
    wal = Path(f"{prepared_db}-wal")
    wal.write_bytes(b"committed-facts-not-in-main-file")
    with pytest.raises(cli.BackfillSafetyError, match="non-empty WAL"):
        cli.run(prepared_db)


def test_protected_table_content_change_is_rejected(
        prepared_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def corrupting_backfill(store):
        with store.transaction() as conn:
            conn.execute("UPDATE kit_registry_versions SET name='changed'")
        return {}

    monkeypatch.setattr(cli.scope_index, "backfill_supported_snapshots", corrupting_backfill)
    with pytest.raises(cli.BackfillSafetyError, match="protected source tables"):
        cli.run(prepared_db, temporary_root=tmp_path / "run")


def test_apply_creates_verified_backup_and_is_idempotent(prepared_db: Path, tmp_path: Path):
    backup = tmp_path / "archive" / "before.db"
    result = cli.run(
        prepared_db, apply=True, backup=backup, temporary_root=tmp_path / "run")

    assert result["mode"] == "apply"
    assert result["backup_quick_check"] == "ok"
    assert result["protected_tables_unchanged"] is True
    assert backup.is_file()
    assert cli._table_fingerprints(backup) == cli._table_fingerprints(prepared_db)

    second_backup = tmp_path / "archive" / "before-second.db"
    second = cli.run(
        prepared_db, apply=True, backup=second_backup, temporary_root=tmp_path / "run2")
    assert second["before_index_rows"] == second["after_index_rows"] == 0
