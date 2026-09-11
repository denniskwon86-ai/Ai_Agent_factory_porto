# -*- coding: utf-8 -*-
"""
판정만 다시 매긴다 — 재수집 없이
==================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 따로 있는가.** `fetch_ftc.py` 는 수집과 판정을 한 번에 하므로, 분류 규칙을
고칠 때마다 공정위 포털을 3,539 번 다시 긁게 된다. KSIC 는 이미 수집돼 있고
바뀐 건 `ksic_rules.MAP` 뿐이니, 다시 판정해서 새 스냅샷에 쓰면 된다.

    python reclassify.py            # src_ftc 재판정 → ftc_classified
    python reclassify.py --dry      # 무엇이 바뀌는지만 본다

★ [P4] **원천을 덮지 않는다.** 예전에는 `ftc-all-2026-classified.csv` 한 파일에
  공정위 원천과 우리 판정이 섞여 있어서, 재판정이 원천을 덮어썼다. 이제 원천은
  `src_ftc` 에 남고 판정은 스냅샷별 `ftc_classified` 로 나간다 — 어제 판정과
  오늘 판정을 나란히 놓고 볼 수 있다.
"""
from __future__ import annotations
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
import taxonomy_io as tx  # noqa: E402
from ksic_rules import classify  # noqa: E402

FIELDS = ('A대분류', 'A세분류', 'B1주업종', 'B1_2단', 'B1_3단', '묶음노드', '모수계층', '판정근거')


def main(dry: bool = False) -> None:
    rows = tx.load('src_ftc')                      # ★ 원천에서 읽는다
    #: 직전 판정과 견준다 — 예전에는 같은 파일 안에서 비교했으므로 「무엇이 바뀌었나」가
    #: 판정을 덮어쓴 뒤에는 영영 확인되지 않았다.
    prev = {(r['기업집단명'], r['소속회사명'], r['법인등록번호']): r
            for r in tx.load('ftc_classified')}

    moved = collections.Counter()
    for r in rows:
        p = prev.get((r['기업집단명'], r['소속회사명'], r['법인등록번호']), {})
        before = (p.get('A대분류'), p.get('A세분류'), p.get('B1주업종'))
        res = classify(r['KSIC'], r['매출액'], r['소속회사명'], r.get('종업원수'))
        after = (res['A대분류'], res['A세분류'], res['B1주업종'])
        if p and before != after:
            moved[(before, after)] += 1
        for f in FIELDS:
            r[f] = res.get(f, '')

    print(f'{len(rows)}건 재판정 · 바뀐 곳 {sum(moved.values())}건')
    for (b, a), n in moved.most_common(20):
        print(f'  {n:>5}  {b[0]}>{b[1]}>{b[2]}  →  {a[0]}>{a[1]}>{a[2]}')

    if dry:
        print('\n--dry 라 쓰지 않았다')
        return
    tx.save('ftc_classified', rows, stage='reclassify')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main('--dry' in sys.argv)
