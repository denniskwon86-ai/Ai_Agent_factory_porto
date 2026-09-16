# -*- coding: utf-8 -*-
"""확산 적용 대상화 집계 — 업태별·셀별로 롱리스트가 얼마나 있나.

    python diffusion_report.py              # 업태별 + 셀 상위
    python diffusion_report.py --min 1000   # 매출 하한 (억, 기본 1,000)
    python diffusion_report.py --cells 40   # 셀을 40 칸까지
    python diffusion_report.py --a 소재제조   # 한 업태만 셀 전부
    python diffusion_report.py --csv         # 표를 CSV 로

## 왜 스크립트로 두는가

`docs/data-kits/DIFFUSION_READINESS_ANALYSIS_2026-09-16.md` 의 숫자가 여기서
나온다. **스냅샷이 바뀌면 숫자가 달라지므로**, 문서를 고칠 때 손으로 다시 세면
반드시 어긋난다.

## 무엇을 세는가 — 그리고 무엇을 빼는가

- **묶음 노드를 뺀다.** 지주회사의 매출은 모수 안의 다른 인스턴스를 포함하므로
  두 번 세어진다(D-38).
- **매출 하한**을 둔다. 목표 고객이 대기업·중견이라 1,000 억 미만은 대상이 아니다.
- 인스턴스 단위라 **세그먼트(부문)도 한 건**으로 센다 — 다부문 회사는 부문별로
  다른 셀에 설 수 있고, 업무키트는 부문 단위로 적용된다.
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import taxonomy_io as tx  # noqa: E402


def num(v) -> float:
    try:
        return float(str(v or 0).replace(',', '') or 0)
    except ValueError:
        return 0.0


def targets(min_억: float, sid: str = ''):
    """롱리스트 대상 인스턴스. 묶음과 하한 미달을 뺀다."""
    return [r for r in tx.load('instances', sid or None)
            if r['단위'] != '묶음' and num(r['매출']) / 100 >= min_억]


def by_sector(rows):
    n, s, cells = collections.Counter(), collections.Counter(), collections.defaultdict(set)
    for r in rows:
        a = r['A세분류'] or '(미판정)'
        n[a] += 1
        s[a] += num(r['매출']) / 100
        cells[a].add((r['B1주업종'], r['B1_2단']))
    return n, s, cells


def by_cell(rows):
    n, s = collections.Counter(), collections.Counter()
    for r in rows:
        k = (r['A세분류'] or '(미판정)', r['B1주업종'], r['B1_2단'])
        n[k] += 1
        s[k] += num(r['매출']) / 100
    return n, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--min', type=float, default=1000.0, help='매출 하한 (억)')
    ap.add_argument('--cells', type=int, default=25, help='셀을 몇 칸까지 볼까')
    ap.add_argument('--a', default='', help='이 A세분류만 (셀 전부)')
    ap.add_argument('--snapshot', default='')
    ap.add_argument('--csv', action='store_true')
    o = ap.parse_args()

    rows = targets(o.min, o.snapshot)
    sid = o.snapshot or tx.read_snapshot()
    s = tx.db().snapshot(sid) or {}
    print('스냅샷 %s (%s) · 매출 %s 억 이상 · 묶음 제외'
          % (sid, '동결' if s.get('frozen') else '작업 중', format(int(o.min), ',')))
    print('대상 %s 건 · 매출합 %s 억\n' % (format(len(rows), ','),
                                     format(int(sum(num(r['매출']) for r in rows) / 100), ',')))

    if o.a:
        n, sm = by_cell([r for r in rows if r['A세분류'] == o.a])
        print('== %s — 셀 %d 칸' % (o.a, len(n)))
        for (a, b1, b2), c in n.most_common():
            print('  %-16s %-16s %5d 건 %12s 억'
                  % (b1[:16], (b2 or '-')[:16], c, format(int(sm[(a, b1, b2)]), ',')))
        return 0

    n, sm, cells = by_sector(rows)
    if o.csv:
        print('A세분류,회사수,매출합_억,셀수')
        for a, c in n.most_common():
            print('%s,%d,%d,%d' % (a, c, int(sm[a]), len(cells[a])))
        return 0

    print('== 업태(A세분류)별')
    print('  %-14s %7s %14s %6s' % ('', '회사수', '매출합(억)', '셀수'))
    for a, c in n.most_common():
        print('  %-14s %7d %14s %6d' % (a, c, format(int(sm[a]), ','), len(cells[a])))

    cn, cs = by_cell(rows)
    print('\n== 셀 상위 %d' % o.cells)
    print('  %-14s %-16s %-14s %7s %14s' % ('A세분류', 'B1주업종', '2단', '회사수', '매출합(억)'))
    for (a, b1, b2), c in cn.most_common(o.cells):
        print('  %-14s %-16s %-14s %7d %14s'
              % (a[:14], b1[:16], (b2 or '-')[:14], c, format(int(cs[(a, b1, b2)]), ',')))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
