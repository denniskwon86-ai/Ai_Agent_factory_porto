"""[D-018 ⑤] 조직 범위 저장분을 **정본 `node_id`** 로 승격한다.

## 무엇을 하는가

`departments.scope_node_id` 처럼 조직 범위를 담는 컬럼에 업무 코드(`LS_MNM`)나 부서 id(`hq`)로
저장된 값이 있다. `[D-018]` 은 정본을 `organization_nodes.node_id` 로 확정했으므로, 그 값들을
해석해 `node_id` 로 바꾼다.

## 무엇을 하지 **않는가** — 불변 이력은 건드리지 않는다

⚠️⚠️ `data/decision_ledger.db` 는 **제외한다**(실측 기준 백필 후보의 91%, 513건). 이유 둘:

  1. Decision Ledger 는 «수정하지 않는다. 정정 이벤트로 보완한다» 가 설계 원칙이고 `update`/
     `delete` 가 아예 없다. 틀린 기록도 «그때 그렇게 판단했다» 는 사실이므로 고치면 이력이
     거짓이 된다.
  2. 각 이벤트가 `prev_hash + payload` 의 SHA-256 을 `event_hash` 로 남겨 **체인**을 이룬다.
     중간 이벤트를 고치면 **이후 전부 불일치**가 되어 변조 탐지가 영구히 깨진다.

  → 이력의 코드 값은 **읽는 시점에** `resolve_scope_ref` 가 정본으로 해석한다(D-005 입력 호환
    계약). 저장분을 고칠 필요가 없다.
  ⚠️ `agent_asset_versions` 처럼 «버전 이력» 성격의 표도 같은 이유로 제외 목록에 둔다.

## 안전 장치

- **기본은 dry-run.** `--commit` 없이는 아무것도 쓰지 않는다.
- 쓰기 전 각 DB 를 `<파일>.bak_backfill_<타임스탬프>` 로 **복사**한다.
- **모호·미해석 값은 건너뛰고 목록으로 남긴다.** 임의로 하나를 고르지 않는다(D-018 ②).
- **멱등**하다. 이미 `node_*` 인 값은 손대지 않으므로 여러 번 돌려도 같다.
- 값을 지우지 않는다. 해석 실패 시 원본을 그대로 둔다 — 빈 값으로 만들면 «범위 미지정» 이 되어
  fail-closed 로 아무에게도 보이지 않게 된다(데이터가 사라진 것처럼 보인다).

사용법:
    python scripts/backfill_scope_node_ids.py              # 계획만 본다
    python scripts/backfill_scope_node_ids.py --commit     # 실제로 쓴다
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context.resolver import ecm_resolver  # noqa: E402
from core.paths import DATA_DIR  # noqa: E402

#: 백필 대상 — `(DB 파일, 표, 컬럼)`. **명시 목록**이다.
#  ⚠️ 자동 탐색으로 넓히지 않는다: 새 표가 생겼을 때 «이력인가 상태인가» 는 사람이 판단해야
#    하고, 자동으로 잡으면 불변 이력을 조용히 고치게 된다.
#  ★ 기본키를 쓰지 않고 **값 기준**으로 갱신한다(`SET col=새값 WHERE col=옛값`). 이유 둘:
#      · `decision_participants` 처럼 **복합 기본키**인 표가 있어 단일 키를 전제할 수 없다.
#      · 백필의 본질이 «이 코드를 이 node_id 로» 이므로 값 기준이 의도를 그대로 표현한다.
#    멱등성도 값 조건에서 나온다 — 이미 `node_*` 면 어느 옛값에도 걸리지 않는다.
TARGETS = [
    ("master/master.db", "departments", "scope_node_id"),
    ("master/master.db", "agent_assets", "owner_scope_id"),
    ("planning.db", "plan_facts", "owner_organization_id"),
    ("planning.db", "scenarios", "owner_organization_id"),
    ("collaboration.db", "decision_cases", "scope_id"),
    ("collaboration.db", "decision_participants", "scope_id"),
    ("collaboration.db", "publications", "scope_id"),
]

#: **절대 건드리지 않는 것.** 이유는 모듈 주석 참조.
EXCLUDED = [
    ("decision_ledger.db", "decision_ledger_events", "불변 이력 + event_hash 체인"),
    ("master/master.db", "agent_asset_versions", "버전 이력(과거 정의의 스냅샷)"),
]


def _resolve(value: str):
    """값 하나를 정본으로 해석한다. `(node_id, 사유)` — `node_id` 가 비면 건너뛴다."""
    r = ecm_resolver.resolve_scope_ref(value)
    node = r.get("node_id") or ""
    return node, r.get("kind") or ""


def _plan_for(db_rel: str, table: str, col: str):
    """이 표에서 무엇을 바꿀지 계산한다(읽기만). **값별로** 계획을 세운다."""
    path = os.path.join(DATA_DIR, db_rel)
    if not os.path.exists(path):
        return None, f"DB 파일이 없습니다: {path}"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if col not in cols:
            return None, f"컬럼이 없습니다: {table}.{col}"
        counts = list(con.execute(
            f"SELECT {col} AS v, COUNT(*) AS n FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col} <> '' GROUP BY {col}"))
    except sqlite3.OperationalError as e:
        return None, f"읽기 실패: {e}"
    finally:
        con.close()

    plan, skipped, already, total = [], [], 0, 0
    for v_raw, n in counts:
        v = str(v_raw).strip()
        total += n
        if v.startswith("node_"):
            already += n
            continue
        node, kind = _resolve(v)
        if not node:
            # ⚠️ 건너뛴 것을 조용히 넘기지 않는다 — 목록으로 남겨야 사람이 고칠 수 있다.
            skipped.append({"value": v, "rows": n, "reason": kind or "unresolved"})
            continue
        plan.append({"old": v, "new": node, "kind": kind, "rows": n})
    return {"path": path, "table": table, "col": col, "plan": plan,
            "skipped": skipped, "already": already, "total": total}, ""


def _apply(item, ts: str) -> int:
    """계획을 적용한다. 쓰기 전에 **DB 를 복사**한다.

    ⚠️ `rowcount` 를 세어 계획과 대조한다 — 계획과 실제가 다르면 그 사이에 데이터가 바뀐 것이고,
      조용히 넘기면 «백필했다» 는 보고가 거짓이 된다."""
    if not item["plan"]:
        return 0
    bak = f"{item['path']}.bak_backfill_{ts}"
    if not os.path.exists(bak):
        shutil.copyfile(item["path"], bak)
        print(f"    백업 → {os.path.basename(bak)}")
    con = sqlite3.connect(item["path"])
    done = 0
    try:
        for ch in item["plan"]:
            cur = con.execute(
                f"UPDATE {item['table']} SET {item['col']}=? WHERE {item['col']}=?",
                (ch["new"], ch["old"]))
            if cur.rowcount != ch["rows"]:
                print(f"    ⚠️ 계획 {ch['rows']}행 · 실제 {cur.rowcount}행 "
                      f"({item['table']}.{item['col']} '{ch['old']}') — 그 사이 데이터가 바뀌었다")
            done += cur.rowcount
        con.commit()
    finally:
        con.close()
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="D-018 ⑤ 조직 범위 정본 백필")
    ap.add_argument("--commit", action="store_true",
                    help="실제로 쓴다(없으면 계획만 출력)")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 78)
    print(f"[D-018 ⑤] 조직 범위 정본 백필 — {'실행' if args.commit else 'DRY-RUN(쓰지 않음)'}")
    print("=" * 78)
    print("제외 대상(불변 이력 — 고치면 이력이 거짓이 되고 해시 체인이 깨진다):")
    for db, table, why in EXCLUDED:
        print(f"  · {db}:{table} — {why}")
    print()

    items, errors = [], []
    for db_rel, table, col in TARGETS:
        item, err = _plan_for(db_rel, table, col)
        if err:
            errors.append(f"{db_rel}:{table}.{col} — {err}")
            continue
        items.append(item)

    changed = skipped_total = 0
    by_value: defaultdict = defaultdict(int)
    for it in items:
        n = sum(c["rows"] for c in it["plan"])
        s = sum(c["rows"] for c in it["skipped"])
        changed += n
        skipped_total += s
        for ch in it["plan"]:
            by_value[(ch["old"], ch["new"], ch["kind"])] += ch["rows"]
        mark = "" if n or s else "  (바꿀 것 없음)"
        print(f"{os.path.basename(it['path']):<20} {it['table']:<24} {it['col']:<22} "
              f"대상 {n:<4} 건너뜀 {s:<3} 이미정본 {it['already']:<4} 총 {it['total']}{mark}")
        for sk in it["skipped"][:5]:
            print(f"    ⚠️ 건너뜀: '{sk['value']}' {sk['rows']}행 ({sk['reason']})")
        if len(it["skipped"]) > 5:
            print(f"    … 그리고 {len(it['skipped']) - 5}종 더")

    print()
    print("값별 변환 요약:")
    for (old, new, kind), n in sorted(by_value.items()):
        print(f"  {old:<22} → {new:<24} ({kind}) {n}건")

    if errors:
        print()
        print("⚠️ 검사하지 못한 표:")
        for e in errors:
            print(f"  · {e}")

    print()
    print(f"합계: 바꿀 것 {changed}건 · 건너뜀 {skipped_total}건")
    if not args.commit:
        print()
        print("DRY-RUN 이므로 아무것도 쓰지 않았습니다. 실제로 적용하려면 --commit 을 붙이십시오.")
        return 0

    print()
    print("적용 중…")
    applied = 0
    for it in items:
        n = _apply(it, ts)
        if n:
            print(f"  {os.path.basename(it['path'])}:{it['table']}.{it['col']} — {n}건 갱신")
            applied += n
    print()
    print(f"완료: {applied}건 갱신. 백업은 `*.bak_backfill_{ts}` 입니다.")
    print("⚠️ 되돌리려면 그 백업 파일을 원래 이름으로 복사하십시오(서버 정지 후).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
