# -*- coding: utf-8 -*-
"""[P4-T3] 저장소 사본으로 DB 를 되살린다.

    python restore_db.py               # samples/ 사본 → taxonomy.db
    python restore_db.py --verify      # 되살리지 않고 대조만
    python restore_db.py --freeze-all  # 되살린 뒤 원래 얼려 있던 판본을 다시 얼린다

## 왜 필요한가 — DB 가 정본인데 git 에 없다

`taxonomy.db` 는 20 MB 바이너리다. 판정을 한 번 돌릴 때마다 통째로 새 blob 이
되므로 git 에 넣을 수 없고, `.gitignore` 의 `*.db` 에 이미 걸려 있다.

그래서 **git 에 남는 것은 사본(CSV)이고, 그 사본에서 DB 를 다시 만들 수 있어야
한다.** 그러지 못하면 저장소를 새로 받은 기계에서 아무것도 못 한다 —
`.cache/` 도 `.gitignore` 라 수집물조차 없다.

    samples/sources/*.csv          → src_* (원천)
    samples/snapshots/{id}/*.csv   → 결과 + snapshots 대장
    samples/snapshots/{id}/snapshot.json  → 엔진 커밋 · 규칙 지문 · 동결 여부

## 동결은 마지막에 건다

얼어 있던 판본을 먼저 얼리면 그 스냅샷에 행을 넣을 수 없다 — 트리거가 막는다.
그래서 **행을 다 넣고 나서** `--freeze-all` 로 원래 상태를 되돌린다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import taxonomy_db as T
import export_snapshot as X


def snapshot_dirs() -> list:
    if not os.path.isdir(T.SNAPSHOT_DIR):
        return []
    out = []
    for n in sorted(os.listdir(T.SNAPSHOT_DIR)):
        p = os.path.join(T.SNAPSHOT_DIR, n)
        #: `_working-*` 은 얼지 않은 판본이라 git 에 없다. 있더라도 건너뛴다 —
        #: 파이프라인을 다시 돌리면 나오는 것이고, 확정된 판본과 섞이면 안 된다.
        if n.startswith('_working-'):
            continue
        if os.path.isdir(p) and os.path.exists(os.path.join(p, 'snapshot.json')):
            out.append((n, p))
    #: 만든 순서대로 되살린다 — `inherited_from` 이 앞선 판본을 가리킨다.
    out.sort(key=lambda kv: json.load(
        io.open(os.path.join(kv[1], 'snapshot.json'), encoding='utf-8')).get('created_at', ''))
    return out


def restore(db: T.TaxonomyDB, freeze_all: bool = False) -> dict:
    n = {'원천': 0, '결과': 0, '스냅샷': 0}

    for name in sorted(T.SOURCES):
        p = os.path.join(X.SOURCES_DIR, name + '.csv')
        if not os.path.exists(p):
            print('  · %-24s 사본 없음' % name)
            continue
        c = db.put_source(name, T.read_csv(p))
        n['원천'] += c
        print('  · %-24s %7d 행' % (name, c))

    to_freeze = []
    for sid, d in snapshot_dirs():
        meta = json.load(io.open(os.path.join(d, 'snapshot.json'), encoding='utf-8'))
        if not db.snapshot(sid):
            db.conn.execute(
                'INSERT INTO snapshots(snapshot_id, created_at, label, note, engine_sha,'
                ' rules_fp, source_fp, row_counts, inherited_from, stages)'
                ' VALUES (?,?,?,?,?,?,?,?,?,?)',
                (sid, meta.get('created_at', ''), meta.get('label', ''),
                 meta.get('note', ''), meta.get('engine_sha', ''), meta.get('rules_fp', ''),
                 json.dumps(meta.get('source_fp', {}), ensure_ascii=False, sort_keys=True),
                 json.dumps(meta.get('row_counts', {}), ensure_ascii=False, sort_keys=True),
                 meta.get('inherited_from', ''),
                 json.dumps(meta.get('stages', {}), ensure_ascii=False, sort_keys=True)))
            db.conn.commit()
        n['스냅샷'] += 1
        if meta.get('frozen'):
            to_freeze.append((sid, meta))
        print('  스냅샷 %s (%s)' % (sid, '동결' if meta.get('frozen') else '작업'))
        for name in T.RESULTS:
            p = os.path.join(d, name + '.csv')
            if not os.path.exists(p):
                continue
            c = db.put_result(sid, name, T.read_csv(p))
            n['결과'] += c
            print('    · %-22s %7d 행' % (name, c))

    #: ★ 행을 다 넣은 **뒤에** 얼린다 — 먼저 얼리면 트리거가 적재를 막는다.
    if freeze_all:
        for sid, meta in to_freeze:
            if not db.is_frozen(sid):
                db.freeze(sid, why=meta.get('frozen_why', '사본에서 복원'),
                          by=meta.get('frozen_by', 'restore_db'))
                print('  ❄ %s 를 다시 얼렸습니다' % sid)
    elif to_freeze:
        print('\n  ⚠️ 원래 얼려 있던 판본 %d 개가 **풀린 채**입니다: %s'
              % (len(to_freeze), ', '.join(s for s, _ in to_freeze)))
        print('     --freeze-all 로 되돌리십시오.')
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=T.DB_PATH)
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--freeze-all', action='store_true')
    a = ap.parse_args()

    db = T.TaxonomyDB(a.db)
    if a.verify:
        bad = []
        for sid, _ in snapshot_dirs():
            bad += ['%s: %s' % (sid, x) for x in X.verify(db, sid)]
        if bad:
            print('✗ 사본과 DB 가 다릅니다 (%d 건)' % len(bad))
            for x in bad[:20]:
                print('   - %s' % x)
            return 1
        print('✓ 사본과 DB 가 일치합니다.')
        return 0

    print('저장소 사본에서 DB 를 되살린다 → %s' % a.db)
    n = restore(db, a.freeze_all)
    print('\n✓ 원천 %d 행 · 결과 %d 행 · 스냅샷 %d 개' % (n['원천'], n['결과'], n['스냅샷']))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
