"""Stdlib-only isolated tests: no repository conftest or runtime store imports."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.exceptions import InvalidTag
from scripts.session_data_snapshot import (
    allowed, export_snapshot, read_snapshot, restore_snapshot, safe_relative,
)


class SessionDataSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        (self.root / "data").mkdir(parents=True)
        with closing(sqlite3.connect(self.root / "data/enterprise_context.db")) as db:
            db.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY, label TEXT)")
            db.execute("INSERT INTO tenants VALUES ('sample', 'synthetic test')")
            db.commit()
        (self.root / "data/auth.db").write_bytes(b"must not leave source")
        (self.root / ".env").write_bytes(b"must not leave source")
        (self.root / "data/company_profile.json").write_text('{"sample":true}', encoding="utf-8")
        (self.root / "data/raw").mkdir()
        (self.root / "data/raw/sample.csv").write_bytes(b"value\n1\n")
        self.bundle = Path(self.temp.name) / "state.aesgcm"
        self.key = self.root / "output/key"
        self.report = Path(self.temp.name) / "public.json"

    def export(self):
        return export_snapshot(self.root, self.bundle, self.key, self.report)

    def test_round_trip_and_exclusions(self):
        before = (self.root / "data/enterprise_context.db").read_bytes()
        report = self.export()
        manifest, files = read_snapshot(self.bundle, self.key)
        self.assertEqual(len(files), 3)
        self.assertEqual(manifest["tables"]["data/enterprise_context.db"]["tenants"], 1)
        self.assertNotIn("data/auth.db", files)
        self.assertNotIn(".env", files)
        self.assertNotIn(self.key.read_text().strip(), json.dumps(report))
        self.assertEqual(before, (self.root / "data/enterprise_context.db").read_bytes())
        target = Path(self.temp.name) / "copy"
        result = restore_snapshot(self.bundle, self.key, target, copy_only=True)
        self.assertTrue(result["relocated"])
        self.assertTrue((target / "SESSION_DATA_INSPECTION_ONLY.json").is_file())
        self.assertFalse((target / "data").exists())
        with closing(sqlite3.connect(target / "inspection-files/data/enterprise_context.db")) as db:
            self.assertEqual(db.execute("SELECT label FROM tenants").fetchone()[0], "synthetic test")

    def test_ciphertext_tampering_fails_before_writes(self):
        self.export()
        raw = bytearray(self.bundle.read_bytes())
        raw[-1] ^= 1
        self.bundle.write_bytes(raw)
        with self.assertRaises(InvalidTag):
            restore_snapshot(self.bundle, self.key, Path(self.temp.name) / "copy", copy_only=True)
        self.assertFalse((Path(self.temp.name) / "copy").exists())

    def test_wrong_key_rejected(self):
        self.export()
        self.key.write_bytes(b"QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE=\n")
        with self.assertRaises(InvalidTag):
            read_snapshot(self.bundle, self.key)

    def test_relocated_runtime_restore_refused(self):
        self.export()
        target = Path(self.temp.name) / "different"
        with self.assertRaisesRegex(ValueError, "Different root"):
            restore_snapshot(self.bundle, self.key, target)
        self.assertFalse(target.exists())

    def test_existing_data_preflight_no_partial_write(self):
        self.export()
        target = Path(self.temp.name) / "copy"
        (target / "inspection-files/data").mkdir(parents=True)
        (target / "inspection-files/data/enterprise_context.db").write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            restore_snapshot(self.bundle, self.key, target, copy_only=True)
        self.assertEqual((target / "inspection-files/data/enterprise_context.db").read_bytes(), b"existing")
        self.assertFalse((target / "data/company_profile.json").exists())

    def test_inspection_leaves_existing_runtime_data_untouched(self):
        self.export()
        target = Path(self.temp.name) / "copy"
        (target / "data").mkdir(parents=True)
        (target / "data/company_profile.json").write_bytes((self.root / "data/company_profile.json").read_bytes())
        self.assertEqual(restore_snapshot(self.bundle, self.key, target, copy_only=True)["files_restored"], 3)
        self.assertFalse((target / "data/enterprise_context.db").exists())

    def test_same_root_existing_db_refused(self):
        self.export()
        original = (self.root / "data/enterprise_context.db").read_bytes()
        with self.assertRaisesRegex(ValueError, "already contains"):
            restore_snapshot(self.bundle, self.key, self.root)
        self.assertEqual(original, (self.root / "data/enterprise_context.db").read_bytes())

    def test_sensitive_raw_filename_refused(self):
        for name in ("data/raw/.env", "data/raw/auth.db", "raw/api.key", "data/raw/tokens.csv"):
            with self.subTest(name=name):
                self.assertFalse(allowed(name))
        (self.root / "data/raw/.env").write_bytes(b"not allowed")
        with self.assertRaisesRegex(ValueError, "sensitive filename"):
            self.export()
        self.assertFalse(self.bundle.exists())

    def test_key_outside_ignored_directory_refused(self):
        with self.assertRaisesRegex(ValueError, "ignored output"):
            export_snapshot(self.root, self.bundle, self.root / "public.key", self.report)
        self.assertFalse(self.bundle.exists())

    def test_output_overwrite_refused(self):
        self.export()
        before = self.bundle.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.export()
        self.assertEqual(before, self.bundle.read_bytes())

    def test_archive_path_traversal_rejected(self):
        for name in ("../bad", "/absolute", "data/../bad", "data//bad", "data/x:stream", "C:\\bad"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_relative(name)

    def test_legacy_root_raw_reference_is_included(self):
        import hashlib
        (self.root / "raw").mkdir()
        raw = self.root / "raw/referenced.csv"
        raw.write_bytes(b"synthetic\n2\n")
        (self.root / "raw/not-referenced.csv").write_bytes(b"not selected")
        with closing(sqlite3.connect(self.root / "data/data_preparation.db")) as db:
            db.execute("CREATE TABLE dataset_snapshots(raw_path TEXT, checksum TEXT)")
            db.execute("INSERT INTO dataset_snapshots VALUES (?, ?)", (str(raw), hashlib.sha256(raw.read_bytes()).hexdigest()))
            db.commit()
        self.export()
        _, files = read_snapshot(self.bundle, self.key)
        self.assertIn("raw/referenced.csv", files)
        self.assertNotIn("raw/not-referenced.csv", files)


if __name__ == "__main__":
    unittest.main()
