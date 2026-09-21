# -*- coding: utf-8 -*-
"""[P05.1] 첫 경로 **사본 이관** — 백업 번들의 «행» 을 새 schema 로 옮기고 대사한다.

## 왜 새로 만드나 — 그리고 무엇을 «안» 만드나

`scripts/session_data_snapshot.py` 가 이미 **파일 수송**을 한다: SQLite 일관 백업
(`source.backup` + `PRAGMA quick_check`), 원본 main+wal 불변 확인, 표별 건수 manifest,
비덮어쓰기 preflight, 심볼릭링크·junction 차단, auth·credential 배제, AES-GCM.
**그것을 다시 만들지 않는다.** 합성 루트에 실제로 돌려 동작을 확인하고 그대로 쓴다.

없는 것은 **「별도 새 schema 로의 행 단위 이관과 대사」** 하나다. 파일을 옮기는 것과
**다른 저장소에 행을 앉히고 그게 맞는지 대조하는 것**은 다르다 — 단순 파일 복사를
ETL 완료라고 부르지 않기 위해 이 층이 필요하다.

## 흐름

    번들(일관 백업) ──추출──▶ 읽기 전용 원본 사본
                                    │  명시 필드 대응 · 동일값 보존
                                    ▼
    설치 도구로 만든 «빈 새 schema» ──▶ 대사(키·건수·필드·참조)

## 지키는 것

    새 대상만        비어 있지 않으면 **거절**. 덮어쓰지 않는다
    겹치지 않게      원본과 대상의 상·하위 중첩, 같은 경로, 링크 우회를 «적용 전에» 막는다
    운영 무접촉      `PROJECT_ROOT/data` 아래는 입력으로도 출력으로도 받지 않는다
    한 트랜잭션      중간에 죽으면 대상에 **행이 남지 않는다**
    성공에만 기록    대사를 통과해야 리포트를 쓴다. 부분 산출물을 ready 로 표시하지 않는다
    재실행           **명시적 거절**(같은 대상 재사용 아님) — 계약을 애매하게 두지 않는다

⚠️ 업무 의미를 임의로 바꾸지 않는다. 컬럼을 **이름으로 하나씩 적어** 같은 값을 옮긴다.
  `SELECT *` 를 쓰지 않는 이유: 스키마가 달라졌을 때 조용히 «자리로» 맞춰지면 안 된다.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util as _ilu  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OPERATIONAL = PROJECT_ROOT / "data"
_SCRIPTS = PROJECT_ROOT / "scripts"


def _load(name: str, filename: str):
    spec = _ilu.spec_from_file_location(name, str(_SCRIPTS / filename))
    module = _ilu.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


#: 기존 도구를 «그대로» 쓴다 — 백업·복원·경로 가드는 여기 있다.
snapshot = _load("_p051_snapshot", "session_data_snapshot.py")
installer = _load("_p051_installer", "install_first_db_schema.py")

STORE_DB = "data/enterprise_context.db"

#: ── 명시적 표·컬럼 대응 ────────────────────────────────────────────────
#:   ⚠️ 이름으로 적는다. `SELECT *` 면 스키마가 달라졌을 때 «자리로» 맞춰져
#:     tenant_id 에 entity_id 가 들어가는 식의 사고가 조용히 난다.
#:   ⚠️ 첫 경로 ECM 묶음만 옮긴다. 무관한 저장소 전체를 훑지 않는다.
TABLES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("tenants", "tenant_id",
     ("tenant_id", "name_ko", "legal_name", "status", "created_at", "updated_at")),
    ("enterprise_entities", "entity_id",
     ("entity_id", "tenant_id", "entity_type", "entity_mode", "legal_name", "name_ko",
      "industry_code", "base_entity_id", "status", "effective_from", "effective_to",
      "version", "approved_by", "approved_at", "source_ref", "evidence_ref",
      "created_at", "updated_at")),
    ("organization_nodes", "node_id",
     ("node_id", "entity_id", "tenant_id", "node_type", "code", "name_ko",
      "default_parent_id", "path_hint", "dept_id", "status", "effective_from",
      "effective_to", "created_at", "updated_at")),
    ("organization_edges", "edge_id",
     ("edge_id", "tenant_id", "from_node_id", "to_node_id", "relation_type", "weight",
      "effective_from", "effective_to", "status", "created_at")),
    ("organization_node_code_aliases", "alias_id",
     ("alias_id", "node_id", "code", "tenant_id", "replaced_by", "reason",
      "recorded_at")),
)

#: 참조 무결성 — (자식표, 자식컬럼) → (부모표, 부모컬럼)
REFERENCES: Tuple[Tuple[str, str, str, str], ...] = (
    ("enterprise_entities", "tenant_id", "tenants", "tenant_id"),
    ("organization_nodes", "entity_id", "enterprise_entities", "entity_id"),
    ("organization_nodes", "tenant_id", "tenants", "tenant_id"),
    ("organization_edges", "from_node_id", "organization_nodes", "node_id"),
    ("organization_edges", "to_node_id", "organization_nodes", "node_id"),
    ("organization_node_code_aliases", "node_id", "organization_nodes", "node_id"),
)


class MigrationRefused(RuntimeError):
    """적용 «전에» 막았다. 원본도 기존 대상도 건드리지 않았다."""


# ── 경계 ────────────────────────────────────────────────────────────────
def _under_operational(path: Path) -> bool:
    """★ 기준을 `PROJECT_ROOT` 로 **고정**한다 — 작업 디렉터리로 판단하면 격리 실행에서
    판정이 반대로 뒤집힌다."""
    try:
        return Path(os.path.commonpath([path.resolve(), _OPERATIONAL])) == _OPERATIONAL
    except ValueError:
        return False


def reject_links(path: Path, label: str) -> None:
    """경로 **자체와 존재하는 모든 상위**가 심볼릭링크·junction 이 아님을 본다.

    ⚠️⚠️ [CR-P05-1] 처음에는 **입력만** 막고 출력을 열어 뒀다. 출력은 `resolve()` 와
      「비어 있나」만 봤는데, `resolve()` 는 **링크를 풀어 원래 모양을 지운다** — 그래서
      지정된 경로가 junction 이어도 통과했고, 뒤이어 `mkdir` 와 설치 도구가 그 링크
      너머에 썼다. 한쪽 문만 막고 반대편을 안 본 것이다.

    ⚠️ `snapshot.regular(p, p.parent)` 를 그대로 쓰지 않는 이유: 그건 검사 root 를 바로
      부모로 두어 **그 위의 링크를 놓친다.** 여기서는 드라이브 루트까지 올라간다.

    ⚠️ 판정은 `os.path.abspath` 위에서 한다 — `resolve()` 를 쓰면 검사하려던 링크가
      이미 풀려 버려서 «검사할 대상이 사라진다»."""
    current = Path(os.path.abspath(path))
    while True:
        if current.is_symlink() or (hasattr(current, "is_junction")
                                    and current.is_junction()):
            raise MigrationRefused(
                f"{label} 경로에 심볼릭링크/junction 이 있습니다 — 실제 경로를 주십시오.")
        parent = current.parent
        if parent == current:
            return
        current = parent


def guard_paths(bundle: Path, target_dir: Path) -> None:
    """**적용 전에** 전부 본다. 하나라도 걸리면 아무것도 쓰지 않는다."""
    #: ★ 링크 검사를 «가장 먼저». 뒤의 검사들은 resolve 를 쓰므로 그 전에 봐야 한다.
    reject_links(bundle, "번들")
    reject_links(target_dir, "대상")
    for label, path in (("번들", bundle), ("대상", target_dir)):
        if _under_operational(path):
            raise MigrationRefused(f"{label} 경로가 운영 data/ 아래입니다 — 격리 경로를 주십시오.")
    if not bundle.is_file():
        raise MigrationRefused("번들을 찾을 수 없습니다.")
    #: 파일 자체의 성질은 기존 도구 것도 함께 쓴다(두 층).
    snapshot.regular(bundle, bundle.parent)
    source_dir = bundle.resolve().parent
    target = target_dir.resolve()
    if target == source_dir:
        raise MigrationRefused("대상이 번들과 같은 디렉터리입니다.")
    if target.is_relative_to(source_dir) or source_dir.is_relative_to(target):
        #: ⚠️ 상·하위 중첩이면 쓰는 도중에 읽는 것을 건드린다.
        raise MigrationRefused("번들 경로와 대상 경로가 상·하위로 겹칩니다.")
    if target.exists() and any(target.iterdir()):
        #: ★ 재실행 계약: **명시적 거절**. 같은 대상을 조용히 재사용하지 않는다.
        raise MigrationRefused(
            "대상 디렉터리가 비어 있지 않습니다 — 새 빈 경로를 주십시오(덮어쓰지 않습니다).")


# ── 추출 ────────────────────────────────────────────────────────────────
def extract_source(bundle: Path, key_file: Optional[Path], staging: Path) -> Path:
    """번들에서 **첫 경로 저장소 하나만** 꺼낸다. 번들 전체를 풀지 않는다."""
    _, files = snapshot.read_snapshot(bundle, key_file)
    raw = files.get(STORE_DB)
    if raw is None:
        raise MigrationRefused(f"번들에 {STORE_DB} 가 없습니다.")
    path = staging / "source.db"
    snapshot.exclusive_write(path, raw)
    return path


def _read_rows(conn: sqlite3.Connection, table: str,
               columns: Sequence[str]) -> List[Tuple[Any, ...]]:
    names = ", ".join(f'"{c}"' for c in columns)
    return list(conn.execute(f'SELECT {names} FROM "{table}"'))


# ── 이관 ────────────────────────────────────────────────────────────────
def migrate_rows(source: Path, target_db: Path) -> Dict[str, int]:
    """**한 트랜잭션.** 중간에 죽으면 대상에 행이 남지 않는다."""
    moved: Dict[str, int] = {}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target_db, timeout=10)) as dst:
            dst.isolation_level = None
            dst.execute("BEGIN")
            try:
                for table, _key, columns in TABLES:
                    rows = _read_rows(src, table, columns)
                    if rows:
                        names = ", ".join(f'"{c}"' for c in columns)
                        marks = ", ".join("?" * len(columns))
                        dst.executemany(
                            f'INSERT INTO "{table}" ({names}) VALUES ({marks})', rows)
                    moved[table] = len(rows)
                dst.execute("COMMIT")
            except Exception:
                dst.execute("ROLLBACK")
                raise
    return moved


# ── 대사 ────────────────────────────────────────────────────────────────
def reconcile(source: Path, target_db: Path) -> Dict[str, Any]:
    """키 집합 · 건수 · **모든 옮긴 필드의 값** · 참조 무결성.

    ⚠️ 제외한 변동값: 번들 manifest 의 `created_at`(백업 «시각» 이라 매번 다르다).
      업무 행의 `created_at`/`updated_at` 은 **제외하지 않는다** — 사본 이관은 값을
      새로 만드는 것이 아니라 «그대로 옮기는» 것이므로 달라지면 그게 결함이다."""
    findings: List[str] = []
    counts: Dict[str, Dict[str, int]] = {}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, \
            closing(sqlite3.connect(target_db.as_uri() + "?mode=ro", uri=True)) as dst:
        for table, key, columns in TABLES:
            before = _read_rows(src, table, columns)
            after = _read_rows(dst, table, columns)
            counts[table] = {"source": len(before), "target": len(after)}
            if len(before) != len(after):
                findings.append(f"{table}: 건수 {len(before)} → {len(after)}")
            index = columns.index(key)
            keys_before = {r[index] for r in before}
            keys_after = {r[index] for r in after}
            if keys_before != keys_after:
                findings.append(f"{table}: 키 집합 불일치 "
                                f"({len(keys_before ^ keys_after)}건)")
            if sorted(before) != sorted(after):
                findings.append(f"{table}: 필드 값이 다릅니다")
        for child, child_col, parent, parent_col in REFERENCES:
            row = dst.execute(
                f'SELECT count(*) FROM "{child}" c WHERE c."{child_col}" <> \'\' '
                f'AND NOT EXISTS (SELECT 1 FROM "{parent}" p '
                f'WHERE p."{parent_col}" = c."{child_col}")').fetchone()
            if row[0]:
                findings.append(f"참조 끊김 {child}.{child_col} → "
                                f"{parent}.{parent_col}: {row[0]}건")
    return {"ok": not findings, "counts": counts, "findings": findings,
            "excluded_volatile": ["번들 manifest.created_at (백업 시각)"],
            "business_timestamps_compared": True}


# ── 실행 ────────────────────────────────────────────────────────────────
def run(bundle: Path, key_file: Optional[Path], target_dir: Path) -> Dict[str, Any]:
    guard_paths(bundle, target_dir)
    before_bundle = snapshot.digest(bundle.read_bytes())
    target_dir.mkdir(parents=True, exist_ok=True)
    data_dir = target_dir / "data"
    installer.install(installer.SQLITE, ["enterprise_context"], str(data_dir))
    target_db = data_dir / "enterprise_context.db"

    with tempfile.TemporaryDirectory(prefix="afs-p051-") as staging:
        source = extract_source(bundle, key_file, Path(staging))
        moved = migrate_rows(source, target_db)
        report = reconcile(source, target_db)

    report["moved_rows"] = moved
    report["target_database"] = str(target_db)
    #: ⚠️ 원본(번들)이 그대로인지 **끝에서 다시 본다.** 읽기 전용이라는 주장 말고 값으로.
    report["bundle_unchanged"] = snapshot.digest(bundle.read_bytes()) == before_bundle
    if not report["ok"] or not report["bundle_unchanged"]:
        raise MigrationRefused(
            "대사에 실패했습니다: " + "; ".join(report["findings"][:4] or ["번들이 변했습니다"]))
    #: ★ 성공했을 때만 리포트를 남긴다 — 부분 산출물을 ready 로 표시하지 않는다.
    snapshot.exclusive_write(target_dir / "migration_report.json",
                             (json.dumps(report, ensure_ascii=False, indent=2)
                              + "\n").encode())
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="백업 번들의 첫 경로 ECM 행을 «새 빈 schema» 로 이관하고 대사한다.")
    ap.add_argument("--bundle", type=Path, required=True, help="일관 백업 번들")
    ap.add_argument("--key-file", type=Path, help="암호화 번들의 키 파일")
    ap.add_argument("--target-dir", type=Path, required=True,
                    help="**새 빈** 디렉터리 (덮어쓰지 않습니다)")
    args = ap.parse_args(argv)
    try:
        result = run(args.bundle, args.key_file, args.target_dir)
    except MigrationRefused as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
