# -*- coding: utf-8 -*-
"""[P4-T3] DB → CSV 내보내기. **보존 층**을 만든다.

    python export_snapshot.py                 # 최신 스냅샷 + 원천
    python export_snapshot.py --snapshot 2026-09-11
    python export_snapshot.py --all           # 모든 스냅샷
    python export_snapshot.py --verify        # 내보낸 CSV 가 DB 와 같은가
    python export_snapshot.py --list          # 스냅샷 목록

## 왜 CSV 를 계속 내보내는가 — DB 로 옮겼는데

두 가지가 다르다.

| | 정본(DB) | 보존(CSV) |
|---|---|---|
| 무엇 | 파이프라인이 읽고 쓴다 | 사람이 읽고 git 이 이력을 남긴다 |
| git | ✗ `*.db` 는 gitignore — 20 MB 바이너리를 매번 새로 커밋할 수 없다 | ✓ |
| 고칠 수 있나 | 얼면 트리거가 막는다 | **고쳐도 소용없다** — 다음 내보내기에 되돌아간다 |

★ 예전 CSV 와 결정적으로 다른 점: **이제 CSV 는 입력이 아니다.** 파이프라인은 DB 를
  읽는다. CSV 를 손으로 고쳐도 판정에 반영되지 않고, `--verify` 가 그 사실을 찍는다.

## 어디에 두는가

    samples/sources/*.csv          원천 — 재수집할 때만 바뀐다
    samples/snapshots/{id}/*.csv   판정 결과 — 스냅샷별. 얼면 다시 나오지 않는다
    samples/snapshots/{id}/snapshot.json   엔진 커밋 · 규칙 지문 · 원천 지문 · 행 수
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import taxonomy_db as T

SOURCES_DIR = os.path.join(T.SAMPLES, 'sources')

_README = """# 스냅샷 {sid}

⚠️ **이 디렉터리는 손으로 고치지 마십시오.** `taxonomy.db` 에서 나온 사본이고,
`python engine/export_snapshot.py` 를 돌리면 다시 덮어써집니다. 고쳐야 할 것이
있으면 판정 규칙을 고치고 **새 스냅샷**을 뜨십시오.

| | |
|---|---|
| 만든 때 | {created_at} |
| 설명 | {label} |
| 엔진 커밋 | `{engine_sha}` |
| 규칙 지문 | `{rules_fp}` |
| 동결 | {frozen} |

{note}

## 행 수

{counts}

## 원천 지문

판정이 **어떤 수집물 위에서** 나왔는지. 원천이 바뀌면 이 값이 달라집니다.

{srcfp}
"""


def _md_rows(d: dict) -> str:
    if not d:
        return '(없음)'
    return '\n'.join('- `%s` — %s' % (k, v) for k, v in sorted(d.items()))


def export_sources(db: T.TaxonomyDB) -> int:
    n = 0
    for name, t in sorted(T.SOURCES.items()):
        rows = db.rows(name)
        if not rows:
            continue
        p = os.path.join(SOURCES_DIR, name + '.csv')
        n += T.write_csv(p, t.cols, rows)
        print('  · sources/%-28s %7d 행' % (name + '.csv', len(rows)))
    return n


def out_dir(sid: str, frozen: bool) -> str:
    """얼지 않은 판본은 `_working-` 로 나간다.

    ★ 작업 스냅샷은 파이프라인을 돌릴 때마다 바뀐다. 그것까지 git 에 들어가면
      6 MB 짜리 CSV 뭉치가 커밋마다 쌓이고, **정작 확정된 판본이 묻힌다.**
      `.gitignore` 가 `_working-*` 를 거른다 — 잃어도 파이프라인을 다시 돌리면 나온다.
    """
    return os.path.join(T.SNAPSHOT_DIR, sid if frozen else '_working-' + sid)


def export_snapshot(db: T.TaxonomyDB, sid: str) -> int:
    s = db.snapshot(sid)
    if not s:
        raise KeyError('없는 스냅샷: %s' % sid)
    out = out_dir(sid, bool(s['frozen']))
    os.makedirs(out, exist_ok=True)
    total, counts = 0, {}
    for name, t in T.RESULTS.items():
        rows = db.rows(name, sid)
        if not rows:
            continue
        T.write_csv(os.path.join(out, name + '.csv'), t.cols, rows)
        counts[name] = len(rows)
        total += len(rows)
        print('  · %s/%-24s %7d 행' % (os.path.basename(out), name + '.csv', len(rows)))

    meta = dict(s)
    meta['row_counts'] = counts
    #: ⚠️ JSON 문자열로 담긴 열은 **여기서 풀어 둔다.** 문자열인 채로 두면
    #:   복원할 때 한 번 더 감싸져 `'"{}"'` 가 되고, 읽는 쪽이 dict 를 기대하다 깨진다.
    meta['source_fp'] = json.loads(s['source_fp'] or '{}')
    meta['stages'] = json.loads(s['stages'] or '{}')
    io.open(os.path.join(out, 'snapshot.json'), 'w', encoding='utf-8').write(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))
    io.open(os.path.join(out, 'README.md'), 'w', encoding='utf-8').write(
        _README.format(sid=sid, created_at=s['created_at'], label=s['label'] or '(없음)',
                       engine_sha=s['engine_sha'] or '?', rules_fp=s['rules_fp'],
                       frozen=('예 — %s %s' % (s['frozen_at'], s['frozen_why']))
                       if s['frozen'] else '아니오 (작업 중)',
                       note=s['note'] or '',
                       counts=_md_rows({k: '{:,} 행'.format(v) for k, v in counts.items()}),
                       srcfp=_md_rows(meta['source_fp'])))
    return total


def verify(db: T.TaxonomyDB, sid: str) -> list:
    """내보낸 CSV 가 DB 와 같은가. **다르면 누군가 사본을 고친 것이다.**"""
    problems = []
    checks = [(os.path.join(SOURCES_DIR, n + '.csv'), n, None) for n in sorted(T.SOURCES)]
    d = out_dir(sid, db.is_frozen(sid))
    checks += [(os.path.join(d, n + '.csv'), n, sid) for n in T.RESULTS]
    for path, name, scope in checks:
        rows = db.rows(name, scope) if scope else db.rows(name)
        if not os.path.exists(path):
            if rows:
                problems.append('%s: 내보낸 적이 없다' % os.path.basename(path))
            continue
        got = T.read_csv(path)
        if len(got) != len(rows):
            problems.append('%s: 행 수 DB %d ≠ 파일 %d' % (name, len(rows), len(got)))
            continue
        cols = T.TABLES[name].cols
        bad = next((('%d 행 「%s」' % (i + 2, c))
                    for i, (a, b) in enumerate(zip(rows, got)) for c in cols
                    if T._s(a.get(c)) != T._s(b.get(c))), '')
        if bad:
            problems.append('%s: 내용이 다르다 — %s' % (name, bad))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=T.DB_PATH)
    ap.add_argument('--snapshot', default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--no-sources', action='store_true', help='원천은 내보내지 않는다')
    ap.add_argument('--freeze', default='', metavar='WHY',
                    help='내보내기 전에 이 스냅샷을 얼린다 (되돌릴 수 없다)')
    a = ap.parse_args()

    db = T.TaxonomyDB(a.db)
    if a.list:
        print('%-14s %-19s %-6s %-10s %s' % ('스냅샷', '만든 때', '동결', '엔진', '설명'))
        for s in db.snapshots():
            print('%-14s %-19s %-6s %-10s %s'
                  % (s['snapshot_id'], s['created_at'], '동결' if s['frozen'] else '작업',
                     s['engine_sha'] or '?', s['label']))
        return 0

    sid = a.snapshot or db.latest()
    if not sid:
        print('스냅샷이 없습니다.')
        return 1

    if a.verify:
        problems = verify(db, sid)
        if problems:
            print('✗ 사본이 DB 와 다릅니다 (%d 건) — 사본을 고쳐도 판정은 바뀌지 않습니다.'
                  % len(problems))
            for x in problems:
                print('   - %s' % x)
            print('\n  다시 내보내려면: python export_snapshot.py --snapshot %s' % sid)
            return 1
        print('✓ 내보낸 CSV 가 DB 와 일치합니다 (%s)' % sid)
        return 0

    if a.freeze:
        if db.is_frozen(sid):
            print('이미 얼어 있습니다: %s' % sid)
        else:
            db.freeze(sid, why=a.freeze, by=os.environ.get('USERNAME', ''))
            print('❄ %s 를 얼렸습니다 — 이제 이 판본은 고칠 수 없습니다.' % sid)

    if not a.no_sources:
        print('원천 내보내기 → samples/sources/')
        export_sources(db)
    targets = [s['snapshot_id'] for s in db.snapshots()] if a.all else [sid]
    for t in targets:
        print('\n스냅샷 내보내기 → samples/snapshots/%s/'
              % os.path.basename(out_dir(t, db.is_frozen(t))))
        export_snapshot(db, t)
    print('\n✓ 완료. 이 파일들은 DB 의 사본입니다 — 고쳐도 판정에 반영되지 않습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
