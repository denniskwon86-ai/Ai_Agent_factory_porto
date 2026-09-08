# -*- coding: utf-8 -*-
"""
판정만 다시 매긴다 — 재수집 없이
==================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 따로 있는가.** `fetch_ftc.py` 는 수집과 판정을 한 번에 하므로, 분류 규칙을
고칠 때마다 공정위 포털을 3,539 번 다시 긁게 된다. KSIC 는 이미 CSV 에 있고
바뀐 건 `ksic_rules.MAP` 뿐이니, 읽어서 다시 판정하고 덮으면 된다.

    python reclassify.py            # ftc-all-2026-classified.csv 재판정
    python reclassify.py --dry      # 무엇이 바뀌는지만 본다
"""
from __future__ import annotations
import collections
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
CSV_PATH = os.path.join(SAMPLES, 'ftc-all-2026-classified.csv')

sys.path.insert(0, HERE)
from ksic_rules import classify  # noqa: E402

FIELDS = ('A대분류', 'A세분류', 'B1주업종', 'B1_2단', 'B1_3단', '묶음노드', '모수계층', '판정근거')


def main(dry: bool = False) -> None:
    rows = list(csv.DictReader(io.open(CSV_PATH, encoding='utf-8-sig')))
    cols = list(rows[0].keys()) if rows else []
    for f in FIELDS:
        if f not in cols:
            cols.append(f)

    moved = collections.Counter()
    for r in rows:
        before = (r.get('A대분류'), r.get('A세분류'), r.get('B1주업종'))
        res = classify(r['KSIC'], r['매출액'], r['소속회사명'], r.get('종업원수'))
        after = (res['A대분류'], res['A세분류'], res['B1주업종'])
        if before != after:
            moved[(before, after)] += 1
        for f in FIELDS:
            r[f] = res.get(f, '')

    print(f'{len(rows)}건 재판정 · 바뀐 곳 {sum(moved.values())}건')
    for (b, a), n in moved.most_common(20):
        print(f'  {n:>5}  {b[0]}>{b[1]}>{b[2]}  →  {a[0]}>{a[1]}>{a[2]}')

    if dry:
        print('\n--dry 라 쓰지 않았다')
        return
    with io.open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'\n{len(rows)}건 → {CSV_PATH}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main('--dry' in sys.argv)
