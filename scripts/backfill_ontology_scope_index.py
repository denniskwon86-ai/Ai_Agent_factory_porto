# -*- coding: utf-8 -*-
"""Materialize supported ontology scope indexes without silently changing source facts.

The default mode is a dry run against a SQLite backup copy.  ``--apply`` is an
explicit maintenance operation and requires a new, non-existing backup path.

Safety contract:

* refuse a non-empty WAL because a file-only view can omit committed facts;
* never overwrite a backup;
* verify the copy and the backup with ``PRAGMA quick_check``;
* allow changes only in ``object_scope_index``;
* require the materialized object-type set to equal the set implied by the
  active, supported certified snapshots;
* never restore or delete an operational file automatically.

The web server must be stopped before ``--apply``.  A preflight lock catches a
writer already holding the database, but it is not a process supervisor and
therefore cannot replace that operational procedure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data_preparation import models as m  # noqa: E402
from core.data_preparation import scope_index  # noqa: E402
from core.data_preparation.store import DataPreparationStore  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


PROTECTED_TABLES: Tuple[str, ...] = (
    "kit_registry_versions",
    "kit_instances",
    "source_bindings",
    "dataset_snapshots",
    "readiness_evaluations",
    "baseline_builds",
    "dataset_ownership_bindings",
)


class BackfillSafetyError(RuntimeError):
    """The requested maintenance operation violated a fail-closed guard."""


def _uri(path: Path, query: str) -> str:
    return f"file:{path.resolve().as_posix()}?{query}"


def _wal_size(path: Path) -> int:
    wal = Path(f"{path}-wal")
    return wal.stat().st_size if wal.exists() else 0


def _assert_clean_source(path: Path) -> None:
    if not path.is_file():
        raise BackfillSafetyError(f"database does not exist: {path}")
    wal_size = _wal_size(path)
    if wal_size:
        raise BackfillSafetyError(
            f"non-empty WAL blocks backfill: {path}-wal ({wal_size} bytes)")


def _quick_check(path: Path) -> None:
    conn = sqlite3.connect(_uri(path, "mode=ro"), uri=True)
    try:
        result = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        conn.close()
    if result.lower() != "ok":
        raise BackfillSafetyError(f"SQLite quick_check failed for {path}: {result}")


def _assert_no_active_writer(path: Path) -> None:
    """Fail when another connection already prevents an exclusive transaction."""
    conn = sqlite3.connect(str(path), timeout=0.0)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.rollback()
    except sqlite3.OperationalError as exc:
        raise BackfillSafetyError(
            "database is busy; stop the backend and every writer before --apply") from exc
    finally:
        conn.close()


def _backup(source: Path, destination: Path) -> None:
    if destination.exists():
        raise BackfillSafetyError(f"backup already exists; refusing overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(_uri(source, "mode=ro"), uri=True)
    try:
        destination_conn = sqlite3.connect(str(destination))
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    except Exception:
        # An incomplete file is not a forensic backup.  Remove only the exact
        # destination created by this call; never touch the source.
        destination.unlink(missing_ok=True)
        raise
    finally:
        source_conn.close()
    _quick_check(destination)


def _table_fingerprints(path: Path,
                        tables: Iterable[str] = PROTECTED_TABLES) -> Dict[str, str]:
    """Hash every protected table including its ordered column names and values."""
    conn = sqlite3.connect(_uri(path, "immutable=1"), uri=True)
    try:
        fingerprints: Dict[str, str] = {}
        for table in tables:
            columns = sorted(str(row[1]) for row in conn.execute(
                f'PRAGMA table_info("{table}")'))
            if not columns:
                raise BackfillSafetyError(f"protected table is missing: {table}")
            selected = ", ".join(f'"{column}"' for column in columns)
            rows = conn.execute(f'SELECT {selected} FROM "{table}"').fetchall()
            canonical = "\n".join(sorted(repr(tuple(row)) for row in rows))
            payload = ",".join(columns) + "\n" + canonical
            fingerprints[table] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return fingerprints
    finally:
        conn.close()


def _index_row_count(store: DataPreparationStore) -> int:
    with store.transaction() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM object_scope_index").fetchone()[0])


def _expected_types(store: DataPreparationStore) -> Dict[str, Tuple[str, ...]]:
    """Derive exact expected coverage from active supported certified snapshots."""
    with store.transaction() as conn:
        keys = [str(row[0]) for row in conn.execute(
            "SELECT DISTINCT dataset_contract_key FROM dataset_snapshots "
            "WHERE state=? AND status='active' ORDER BY dataset_contract_key",
            (m.DEMO_CERTIFIED,)).fetchall()]
    grouped: Dict[str, set[str]] = {}
    for key in keys:
        for namespace, object_type, _ in scope_index.object_specs(key):
            grouped.setdefault(namespace, set()).add(object_type)
    return {namespace: tuple(sorted(types)) for namespace, types in sorted(grouped.items())}


def _canonical_types(value: Mapping[str, Iterable[str]]) -> Dict[str, Tuple[str, ...]]:
    return {str(namespace): tuple(sorted(str(item) for item in items))
            for namespace, items in sorted(value.items())}


def _backfill_and_verify(path: Path) -> Dict[str, Any]:
    protected_before = _table_fingerprints(path)
    store = DataPreparationStore(str(path))
    expected = _expected_types(store)
    before_types = _canonical_types(scope_index.materialized_object_types(store))
    before_rows = _index_row_count(store)

    written = scope_index.backfill_supported_snapshots(store)

    protected_after = _table_fingerprints(path)
    if protected_after != protected_before:
        changed = sorted(table for table in PROTECTED_TABLES
                         if protected_before.get(table) != protected_after.get(table))
        raise BackfillSafetyError(
            "backfill changed protected source tables: " + ", ".join(changed))

    after_types = _canonical_types(scope_index.materialized_object_types(store))
    after_rows = _index_row_count(store)
    if after_types != expected:
        raise BackfillSafetyError(
            "materialized object types do not match certified sources: "
            f"expected={expected!r}, actual={after_types!r}")
    return {
        "expected_object_types": expected,
        "before_object_types": before_types,
        "after_object_types": after_types,
        "before_index_rows": before_rows,
        "after_index_rows": after_rows,
        "written_by_dataset": dict(sorted(written.items())),
        "protected_tables_unchanged": True,
    }


def run(database: Path, *, apply: bool = False, backup: Path | None = None,
        temporary_root: Path | None = None) -> Dict[str, Any]:
    database = database.resolve()
    _assert_clean_source(database)
    _quick_check(database)

    if not apply and backup is not None:
        raise BackfillSafetyError("--backup is valid only together with --apply")
    if apply and backup is None:
        raise BackfillSafetyError("--apply requires a new --backup path")

    # A rehearsal is mandatory even in apply mode.  It proves that raw bytes,
    # schemas and expected type coverage are coherent before the source is opened
    # for writes.
    temp_parent = temporary_root.resolve() if temporary_root else (ROOT / "tmp")
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="ontology-scope-backfill-", dir=temp_parent))
    rehearsal_db = temp_dir / "data_preparation.db"
    try:
        _backup(database, rehearsal_db)
        rehearsal = _backfill_and_verify(rehearsal_db)
    finally:
        shutil.rmtree(temp_dir)

    if not apply:
        return {
            "mode": "dry-run",
            "database": str(database),
            "source_changed": False,
            **rehearsal,
        }

    assert backup is not None
    backup = backup.resolve()
    if backup == database:
        raise BackfillSafetyError("backup path must differ from the source database")
    _assert_no_active_writer(database)
    _backup(database, backup)
    source_before = _table_fingerprints(database)
    applied = _backfill_and_verify(database)
    source_after = _table_fingerprints(database)
    if source_after != source_before:
        raise BackfillSafetyError("protected source tables changed after apply")
    return {
        "mode": "apply",
        "database": str(database),
        "backup": str(backup),
        "backup_quick_check": "ok",
        "source_changed": applied["after_index_rows"] != applied["before_index_rows"],
        "rehearsal": rehearsal,
        **applied,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data" / "data_preparation.db",
        help="data_preparation.db path (default: repository operational database)")
    parser.add_argument("--apply", action="store_true",
                        help="write the derived index after a successful rehearsal")
    parser.add_argument("--backup", type=Path,
                        help="required non-existing SQLite backup path for --apply")
    parser.add_argument("--temporary-root", type=Path,
                        help="directory for the disposable rehearsal copy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run(args.db, apply=args.apply, backup=args.backup,
                     temporary_root=args.temporary_root)
    except (BackfillSafetyError, sqlite3.Error, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"status": "OK", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
