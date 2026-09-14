"""Non-overwriting encrypted or user-approved plaintext data transport.

Encrypted bundles require a separately held key; plaintext ZIPs do not.
This is a configuration/data backup, not a running-worker/checkpointer migration.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"AFS-SESSION-DATA-1\x00"
DATABASES = (
    "data/master/master.db", "data/enterprise_context.db",
    "data/data_preparation.db", "data/decision_ledger.db",
    "data/app_data.db", "data/app_data_preview.db", "data/ontology.db",
    "data/collaboration.db", "data/planning.db", "data/program_lifecycle.db",
    "data/workspace.db", "data/asset_usage.db", "data/policy_shadow.db",
    "data/shadow_runs.db", "data/external_intelligence.db",
)
CONFIGS = (
    "data/company_profile.json", "data/instance.json", "data/slice_rebase.json",
    "data/reference_registry.json", "data/scope_policy.json",
    "data/model_routing_policy.json", "agents_registry.json",
)
EXCLUDED = [".env and credentials", "auth.db/passwords/sessions", "connectors.db",
            "advisor.db/private conversations", "interaction/access/LLM logs",
            "projects and running checkpoints", "library and knowledge caches",
            "external_raw and archives", "outputs and test runtime databases"]


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative(name: str) -> str:
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute():
        raise ValueError("Unsafe archive path")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("Unsafe archive path")
    return p.as_posix()


def allowed(name: str) -> bool:
    if name in DATABASES or name in CONFIGS:
        return True
    if not name.startswith(("data/raw/", "raw/")):
        return False
    # Current approved RAW format is CSV only. Do not sweep arbitrary key/DB/
    # environment files into a transport just because they live in a RAW folder.
    parts = PurePosixPath(name).parts
    forbidden = ("secret", "credential", "password", "session", "token", "id_rsa", "auth.")
    return PurePosixPath(name).suffix.lower() == ".csv" and not any(
        p.startswith(".") or any(word in p.lower() for word in forbidden) for p in parts)


def regular(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path leaves selected root")
    for entry in (path, *path.parents):
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            raise ValueError("Links/junctions are not supported")
        if entry == root:
            break


def exclusive_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def export_snapshot(root: Path, bundle: Path, key_file: Path, report: Path) -> dict:
    root = root.resolve()
    if not key_file.resolve().is_relative_to(root / "output"):
        raise ValueError("Export key must stay under ignored output/; never commit it")
    outputs = [bundle, key_file, report]
    if len({p.resolve() for p in outputs}) != 3 or any(p.exists() for p in outputs):
        raise ValueError("Output already exists or paths overlap; no overwrite")
    selected = [root / p for p in (*DATABASES, *CONFIGS) if (root / p).is_file()]
    selected += sorted(p for p in (root / "data/raw").rglob("*") if p.is_file())
    # Older actual snapshots use <root>/raw, not <root>/data/raw. Include only
    # referenced files there, never an unrestricted root-directory glob.
    dp_path = root / "data/data_preparation.db"
    raw_refs = []
    if dp_path.is_file():
        regular(dp_path, root)
        with closing(sqlite3.connect(dp_path.as_uri() + "?mode=ro", uri=True)) as conn:
            raw_refs = list(conn.execute("SELECT raw_path, checksum FROM dataset_snapshots"))
        for raw_path, checksum in raw_refs:
            path = Path(raw_path)
            if not path.is_absolute():
                path = root / path
            regular(path, root)
            if not path.is_file() or not path.relative_to(root).as_posix().startswith(("data/raw/", "raw/")):
                raise ValueError("Snapshot has a missing or unsupported RAW reference")
            if digest(path.read_bytes()) != checksum:
                raise ValueError("Snapshot RAW checksum mismatch")
            selected.append(path)
    selected = sorted(set(selected))
    if not selected:
        raise ValueError("No data found")
    for path in selected:
        regular(path, root)
        if not allowed(safe_relative(path.relative_to(root).as_posix())):
            raise ValueError("Selected data contains an unsupported or sensitive filename")
    watched = selected + [Path(str(p) + "-wal") for p in selected if p.suffix == ".db"]
    before = {str(p): digest(p.read_bytes()) if p.exists() else None for p in watched}
    files, database_counts = {}, {}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        with tempfile.TemporaryDirectory(prefix="afs-session-") as staging:
            for index, path in enumerate(selected):
                relative = safe_relative(path.relative_to(root).as_posix())
                if path.suffix == ".db":
                    copy = Path(staging) / f"{index}.db"
                    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
                        with closing(sqlite3.connect(copy)) as target:
                            source.backup(target)
                            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                                raise ValueError("SQLite integrity check failed")
                            tables = [r[0] for r in target.execute(
                                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                            database_counts[relative] = {
                                table: target.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                                for table in tables}
                    raw = copy.read_bytes()
                else:
                    raw = path.read_bytes()
                files[relative] = {"bytes": len(raw), "sha256": digest(raw)}
                archive.writestr(relative, raw)
        after = {str(p): digest(p.read_bytes()) if p.exists() else None for p in watched}
        if before != after:
            changed = [str(Path(p).relative_to(root)) for p in before if before[p] != after[p]]
            raise ValueError("Source data changed during export; stop writers and retry: " + ", ".join(changed))
        manifest = {"format": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_root": str(root), "files": files, "tables": database_counts,
                    "source_main_and_wal_unchanged": True, "excluded": EXCLUDED,
                    "cross_database_atomic_transaction": False}
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    cipher = MAGIC + nonce + AESGCM(key).encrypt(nonce, stream.getvalue(), MAGIC)
    # Persist the only decryption key before publishing ciphertext. No key in stdout/report.
    exclusive_write(key_file, base64.urlsafe_b64encode(key) + b"\n")
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass  # Windows ACLs are inherited; protect this file using the local account.
    exclusive_write(bundle, cipher)
    public = {"format": 1, "created_at": manifest["created_at"], "cipher": "AES-256-GCM",
              "bundle_sha256": digest(cipher), "bundle_bytes": len(cipher),
              "file_count": len(files), "database_count": len(database_counts),
              "raw_file_count": sum(p.startswith(("data/raw/", "raw/")) for p in files),
              "snapshot_raw_references": len(raw_refs),
              "plaintext_bytes": sum(f["bytes"] for f in files.values()),
              "source_main_and_wal_unchanged": True, "excluded": EXCLUDED,
              "key_committed": False, "requires_separate_key": True}
    exclusive_write(report, (json.dumps(public, ensure_ascii=False, indent=2) + "\n").encode())
    return public


def read_snapshot(bundle: Path, key_file: Path | None = None):
    cipher = bundle.read_bytes()
    if zipfile.is_zipfile(io.BytesIO(cipher)):
        return read_archive(cipher)
    if not cipher.startswith(MAGIC) or len(cipher) < len(MAGIC) + 28:
        raise ValueError("Unknown bundle format")
    if key_file is None:
        raise ValueError("Encrypted bundle requires --key-file")
    key = base64.urlsafe_b64decode(key_file.read_bytes().strip())
    if len(key) != 32:
        raise ValueError("Invalid key length")
    nonce = cipher[len(MAGIC):len(MAGIC) + 12]
    plain = AESGCM(key).decrypt(nonce, cipher[len(MAGIC) + 12:], MAGIC)
    return read_archive(plain)


def read_archive(plain: bytes):
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive paths")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != 1 or set(names) != set(manifest["files"]) | {"manifest.json"}:
            raise ValueError("Invalid manifest")
        files = {}
        for name, info in manifest["files"].items():
            if safe_relative(name) != name or not allowed(name):
                raise ValueError("Archive contains unapproved path")
            raw = archive.read(name)
            if len(raw) != info["bytes"] or digest(raw) != info["sha256"]:
                raise ValueError("File hash mismatch")
            files[name] = raw
    return manifest, files


def decrypt_snapshot(bundle: Path, key_file: Path, output_bundle: Path) -> dict:
    """기존 승인 범위만 평문 ZIP으로 전달하며 원본과 키를 보존한다."""
    if output_bundle.exists() or output_bundle.resolve() in (bundle.resolve(), key_file.resolve()):
        raise ValueError("Output already exists or overlaps input; no overwrite")
    manifest, files = read_snapshot(bundle, key_file)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    plain = stream.getvalue()
    # 검증을 마친 뒤에만 새 파일을 생성한다. 본문/키는 출력하지 않는다.
    if read_archive(plain) != (manifest, files):
        raise ValueError("Plaintext round-trip mismatch")
    exclusive_write(output_bundle, plain)
    return {"file_count": len(files), "database_count": len(manifest["tables"]),
            "bundle_sha256": digest(plain), "bundle_bytes": len(plain),
            "encrypted": False, "requires_separate_key": False,
            "source_snapshot_created_at": manifest["created_at"],
            "excluded": manifest["excluded"]}


def restore_snapshot(bundle: Path, key_file: Path | None, destination: Path, *, copy_only=False) -> dict:
    manifest, files = read_snapshot(bundle, key_file)
    destination = destination.absolute()
    regular(destination, destination)
    relocated = os.path.normcase(str(destination.resolve())) != os.path.normcase(manifest["source_root"])
    if relocated and not copy_only:
        raise ValueError("Different root: DB absolute references are unchanged. Use --copy-only for inspection, not runtime")
    if (destination / "SESSION_DATA_INSPECTION_ONLY.json").exists():
        raise ValueError("Inspection marker already exists")
    # Never populate <checkout>/data for an inspection operation. There is no
    # application code beneath this private payload directory to consume it.
    payload_root = destination / "inspection-files" if copy_only else destination
    if copy_only and payload_root.exists():
        raise ValueError("Inspection payload already exists")
    # Complete preflight before writing: no existing DB/config is replaced.
    unchanged = set()
    for name in files:
        target = payload_root / name
        regular(target, destination)
        if name in CONFIGS and target.is_file() and target.read_bytes() == files[name]:
            unchanged.add(name)
            continue
        if target.exists() or any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm")):
            raise ValueError(f"Destination already contains {name}; use a fresh directory")
    result = {"files_restored": len(files), "relocated": relocated,
              "inspection_only": copy_only, "payload_directory": str(payload_root),
              "absolute_root_matches": not relocated, "credentials_restored": False,
              "note": "File restore only; authentication, referenced assets and application acceptance still need checks"}
    if copy_only:
        # Write warning before any plaintext payload, including partial failures.
        exclusive_write(destination / "SESSION_DATA_INSPECTION_ONLY.json", json.dumps(result, indent=2).encode())
    for name, raw in files.items():
        if name not in unchanged:
            exclusive_write(payload_root / name, raw)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "verify", "restore", "decrypt"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--output-bundle", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--copy-only", action="store_true")
    args = parser.parse_args()
    if args.operation == "export":
        if args.report is None or args.key_file is None:
            parser.error("export requires --report and --key-file")
        result = export_snapshot(ROOT, args.bundle, args.key_file, args.report)
    elif args.operation == "decrypt":
        if args.key_file is None or args.output_bundle is None:
            parser.error("decrypt requires --key-file and --output-bundle")
        result = decrypt_snapshot(args.bundle, args.key_file, args.output_bundle)
    elif args.operation == "verify":
        manifest, files = read_snapshot(args.bundle, args.key_file)
        result = {"verified_files": len(files), "verified_databases": len(manifest["tables"]),
                  "authenticated_decryption": args.bundle.read_bytes().startswith(MAGIC),
                  "all_file_hashes_match": True}
    else:
        if args.destination is None:
            parser.error("restore requires --destination")
        result = restore_snapshot(args.bundle, args.key_file, args.destination, copy_only=args.copy_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
