# -*- coding: utf-8 -*-
"""[P4-T5] 업무키트 대상 롱리스트를 **판본과 함께** 남긴다.

    python make_longlist.py --kit KIT-MFG-NONFERROUS-PROCUREMENT --b3 제련·정련
    python make_longlist.py --kit ... --a 소재제조 --b1 금속 --b2 비철금속 --min 1000
    python make_longlist.py --list                # 이 스냅샷의 롱리스트
    python make_longlist.py --list --snapshot 2026-09-11

## 왜 DB 에 남기는가

「제련 11 개사」라고 적어 둔 문서는 **반년 뒤에 재현되지 않는다.** 그 사이 판정
규칙이 바뀌고 매출이 갱신되면 같은 조건으로도 다른 명단이 나온다. 그래서 명단을
**어느 스냅샷에서 어떤 조건으로 뽑았는지**와 함께 둔다.

    스냅샷 2026-09-11-2 · 규칙 지문 b30bb629 · B1_3단=제련·정련 · 매출 1,000 억 이상
    → 11 개사 30.6 조

나중에 「그때 왜 이 명단이었나」를 물으면, 그 스냅샷을 그대로 다시 질의하면 된다.

## ⚠️ 롱리스트는 **실재하는 회사**다

회사 프로파일(`starter_kits/.../company_profiles/`)은 **가상 회사**다. 둘을 섞으면
실명에 합성 숫자가 붙어 「없는 숫자로 경영 판단」이 된다. 이 표는 영업 대상 명단이지
데이터 원천이 아니다.

## 무엇을 빼는가

- **묶음 노드** — 그 매출이 모수 안의 다른 인스턴스를 포함하므로 두 번 세어진다
- **모수밖** — 상장폐지·SPAC·매출 0
- 매출 하한 미달 — 기본 1,000 억. 목표 고객이 대기업·중견이다
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


def _brn_index(uni: list) -> dict:
    """회사명 → 법인등록번호. **동명이인은 뺀다** — 어느 쪽인지 가릴 수 없다(D-47)."""
    cnt = collections.Counter(r['회사명'] for r in uni if r['모수계층'] != '모수밖')
    return {r['회사명']: r['법인등록번호'] for r in uni
            if r['모수계층'] != '모수밖' and cnt[r['회사명']] == 1}


def select(*, a: str = '', b1: str = '', b2: str = '', b3: str = '',
           min_sales_억: float = 1000.0, sid: str = '') -> list:
    inst = tx.load('instances', sid or None)
    uni = tx.load('universe', sid or None)
    brn = _brn_index(uni)
    #: 인스턴스에는 모수계층이 없다 — 이름으로 이어 붙인다.
    tier = {r['회사명']: r['모수계층'] for r in uni}

    conds = [('A세분류', a), ('B1주업종', b1), ('B1_2단', b2), ('B1_3단', b3)]
    want = [(k, v) for k, v in conds if v]
    if not want:
        raise SystemExit('조건이 하나도 없습니다 — --a/--b1/--b2/--b3 중 하나는 주십시오.')

    out = []
    for r in inst:
        if r['단위'] == '묶음':
            continue                      # 다른 인스턴스를 포함하므로 두 번 세어진다
        if any(r.get(k, '') != v for k, v in want):
            continue
        억 = num(r['매출']) / 100.0
        if 억 < min_sales_억:
            continue
        이름 = r['이름'] if r['단위'] != '세그먼트' else r['모법인']
        t = tier.get(이름, '')
        if t == '모수밖':
            continue
        out.append({
            '셀': '×'.join(v for _, v in want),
            '회사명': r['이름'], '법인등록번호': brn.get(이름, ''),
            '단위': r['단위'], '소속그룹': r['소속그룹'],
            'A세분류': r['A세분류'], 'B1주업종': r['B1주업종'],
            'B1_2단': r['B1_2단'], 'B1_3단': r['B1_3단'],
            '매출': r['매출'], '모수계층': t,
            '선정근거': ' · '.join('%s=%s' % (k, v) for k, v in want)
                      + ' · 매출 %s 억 이상' % format(int(min_sales_억), ',')
                      + (' · 모법인 %s 의 부문' % r['모법인'] if r['단위'] == '세그먼트' else ''),
        })
    out.sort(key=lambda r: -num(r['매출']))
    return out


def show(rows: list, title: str = '') -> None:
    if title:
        print(title)
    tot = 0.0
    for r in rows:
        억 = num(r['매출']) / 100.0
        tot += 억
        print('  %-26s %-8s %12s억  %-10s %s'
              % (r['회사명'][:26], r['단위'], format(int(억), ','),
                 r['소속그룹'] or '-', r['모수계층']))
    print('  %d 개 · 합계 %s 억 (%.1f 조)' % (len(rows), format(int(tot), ','), tot / 10000))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--kit', default='', help='업무키트 ID')
    ap.add_argument('--a', default='', help='A세분류')
    ap.add_argument('--b1', default='', help='B1 주업종')
    ap.add_argument('--b2', default='', help='B1 2단')
    ap.add_argument('--b3', default='', help='B1 3단 (공정·형태)')
    ap.add_argument('--min', type=float, default=1000.0, help='매출 하한 (억)')
    ap.add_argument('--snapshot', default='')
    ap.add_argument('--list', action='store_true', help='저장된 롱리스트를 본다')
    ap.add_argument('--dry', action='store_true', help='저장하지 않는다')
    a = ap.parse_args()

    if a.list:
        rows = tx.load('longlist', a.snapshot or None)
        if not rows:
            print('이 스냅샷에 롱리스트가 없습니다: %s' % (a.snapshot or tx.read_snapshot()))
            return 0
        for kit, g in collections.groupby(
                sorted(rows, key=lambda r: r['키트ID']), key=lambda r: r['키트ID']):
            g = list(g)
            show(g, '\n== %s  (%s)' % (kit, g[0]['선정근거']))
        return 0

    if not a.kit:
        raise SystemExit('--kit 으로 업무키트 ID 를 주십시오.')
    rows = select(a=a.a, b1=a.b1, b2=a.b2, b3=a.b3, min_sales_억=a.min,
                  sid=a.snapshot)
    for r in rows:
        r['키트ID'] = a.kit
    sid = a.snapshot or tx.read_snapshot()
    s = tx.db().snapshot(sid) or {}
    show(rows, '\n== %s\n   스냅샷 %s · 규칙 지문 %s · %s'
         % (a.kit, sid, s.get('rules_fp', '?'), rows[0]['선정근거'] if rows else '(없음)'))

    if a.dry:
        print('\n--dry 라 쓰지 않았다')
        return 0

    #: 같은 스냅샷에 여러 키트의 롱리스트가 쌓인다 — 다른 키트 것을 지우지 않는다.
    keep = [r for r in tx.load('longlist', sid) if r['키트ID'] != a.kit]
    tx.save('longlist', keep + rows, stage='longlist:%s' % a.kit)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
