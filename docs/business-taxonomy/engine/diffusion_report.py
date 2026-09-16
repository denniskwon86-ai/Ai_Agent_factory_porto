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


# ─────────────────────────────────────────────── 데이터셋 커버리지
#
# ⚠️ 아래 두 표는 **사람의 판단**이다. 그 아래 계산은 기계가 한다.
#    둘을 갈라 두는 이유는, 「업태별로 몇 종이 남나」를 표로만 적어 두면 **어디까지가
#    근거이고 어디부터가 의견인지 보이지 않기** 때문이다. 판단을 고치면 숫자가
#    따라 바뀌고, 그 판단은 여기 한 곳에만 있다.

#: 데이터셋이 성립하려면 회사에 있어야 하는 것. 비어 있으면 어느 업태에서나 선다.
#: 근거는 그 데이터셋의 필드 전체가 무엇을 서술하는가다 (계약의 `required` 가
#: 아니다 — 그것은 데이터셋당 ID 하나뿐이라 아무것도 가리지 못한다).
DATASET_PREMISE: dict = {
    # 기반 — 회사라면 있다
    'FND-01': set(), 'FND-02': set(), 'FND-03': set(),
    'MDM-01': set(),          # 품목 개념은 보편. 단 material_type=RAW/WIP 은 물성 전제
    'MDM-02': {'물품구매'},     # 공급사 = 물건을 대는 곳
    'MDM-03': set(),          # 고객은 어느 업태에나 있다
    'MDM-04': {'물리재고'},     # 공장·창고·저장 위치
    'MDM-05': {'물성변환'},     # BOM·수율·부산물
    'MDM-06': {'물성변환', '설비'},   # Routing·설비·생산능력
    'MDM-07': set(),          # 계정·원가센터
    'MDM-08': {'국제운송'},     # Incoterms·항만·운송구간
    # 조달·물류
    'PRC-01': {'물품구매'}, 'PRC-02': {'물품구매'},
    'LOG-01': {'국제운송'}, 'LOG-02': {'국제운송'}, 'LOG-03': {'국제운송'},
    'LOG-04': {'국제운송'}, 'LOG-05': {'국제운송'},
    # 재고·생산·품질
    'INV-01': {'물리재고'}, 'INV-02': {'물리재고'},
    'MFG-01': {'물성변환'}, 'MFG-02': {'물성변환'}, 'MFG-03': {'설비'},
    'QLT-01': {'물성변환'},    # 입고·공정·제품 품질 — 규격과 판정
    # 판매·재무
    'SLS-01': set(),          # 수주·출하. 용역도 판다
    'FIN-01': set(), 'FIN-02': set(), 'FIN-03': set(),
    # 지식·외부·시뮬레이션·결정
    'KNW-01': set(), 'EXT-01': set(), 'EXT-02': set(), 'EXT-03': set(),
    'SIM-01': set(), 'SIM-02': set(), 'DEC-01': set(),
}

#: 업태(A 세분류)가 가진 것. ⚠️ 여기가 가장 논쟁적인 판단이다.
SECTOR_PREMISE: dict = {
    '소재제조':   {'물성변환', '물리재고', '국제운송', '물품구매', '설비'},
    '부품제조':   {'물성변환', '물리재고', '국제운송', '물품구매', '설비'},
    '완제품제조': {'물성변환', '물리재고', '국제운송', '물품구매', '설비'},
    #: 채취는 「물질을 바꾸는」 것이 아니라 꺼내는 것이다. 선광·정제가 붙으면 달라진다
    '자원채취':   {'물리재고', '물품구매', '설비'},
    #: 현장 수주라 재고·수율의 성격이 다르다. 자재 구매와 장비는 있다
    '시공·건설':  {'물품구매', '설비'},
    '도매·상사':  {'물리재고', '국제운송', '물품구매'},
    '소매':      {'물리재고', '물품구매'},
    #: 운송업은 국제운송이 **본업**이다 — 남의 화물을 옮긴다
    '운송·보관':  {'물리재고', '국제운송', '설비'},
    '시설·자산운영': {'설비'},
    '인적서비스':  set(),
    '콘텐츠·SW':  set(),
    '플랫폼·중개': set(),
    '금융':      set(),
    '지주·투자':  set(),
}

#: 업무키트 = 데이터셋 접두어 묶음 (`core/data_preparation/business_kits.py`)
KIT_PREFIX = [
    ('FOUNDATION', ('FND', 'MDM')), ('BK-01 구매', ('PRC',)), ('BK-02 물류', ('LOG',)),
    ('BK-03 재고', ('INV',)), ('BK-04 생산', ('MFG',)), ('BK-05 품질', ('QLT', 'KNW')),
    ('BK-06 판매', ('SLS',)), ('BK-07 원가', ('FIN',)), ('BK-08 시나리오', ('EXT', 'SIM', 'DEC')),
]


def surviving(sector: str) -> set:
    """그 업태에서 **서는** 데이터셋. 전제가 전부 충족돼야 한다."""
    have = SECTOR_PREMISE.get(sector, set())
    return {ds for ds, need in DATASET_PREMISE.items() if need <= have}


def coverage_table() -> list:
    out = []
    for sector in SECTOR_PREMISE:
        live = surviving(sector)
        per_kit = []
        for name, pre in KIT_PREFIX:
            ds = [d for d in DATASET_PREMISE if d.split('-')[0] in pre]
            per_kit.append((name, sum(1 for d in ds if d in live), len(ds)))
        out.append((sector, len(live), len(DATASET_PREMISE), per_kit))
    out.sort(key=lambda r: -r[1])
    return out


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
    ap.add_argument('--coverage', action='store_true',
                    help='업태별로 35 종 중 몇 종이 서는가 (전제 기반 계산)')
    o = ap.parse_args()

    if o.coverage:
        rows = targets(o.min, o.snapshot)
        n, sm, _ = by_sector(rows)
        print('업태별 데이터셋 커버리지 — 전제가 충족되는 것만 센다')
        print('⚠️ DATASET_PREMISE · SECTOR_PREMISE 두 표는 **사람의 판단**이고, '
              '아래 숫자는 거기서 계산된다.\n')
        head = '  %-14s %5s %7s %10s  ' % ('A세분류', '데이터셋', '회사수', '매출(억)')
        print(head + ' '.join('%-6s' % k.split()[0][:6] for k, _ in KIT_PREFIX))
        for sector, live, total, per_kit in coverage_table():
            cells = ' '.join('%-6s' % ('%d/%d' % (a, b)) for _, a, b in per_kit)
            print('  %-14s %2d/%-2d %7d %10s  %s'
                  % (sector, live, total, n.get(sector, 0),
                     format(int(sm.get(sector, 0)), ','), cells))
        print('\n  전제: ' + ' · '.join(sorted(
            {p for v in DATASET_PREMISE.values() for p in v})))
        return 0

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
