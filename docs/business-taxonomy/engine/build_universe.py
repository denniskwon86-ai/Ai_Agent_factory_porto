# -*- coding: utf-8 -*-
"""
통합 모수 만들기 — 공정위 계열사 + 상장 법인
============================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**이게 이 폴더의 산출물이다.** 업무키트를 어느 사업형태에 만들지 정하려면
셀마다 대상 회사가 몇 개인지 알아야 한다.

두 출처를 **법인등록번호로 잇는다.**

- 공정위 기업집단포털 — 대기업집단 소속 3,539 개사. 재무·종업원수까지 온다.
  다만 **비상장 독립기업이 없고** 금융전업집단(KB금융·신한지주…)도 빠진다
- DART 기업개황 — 모든 공시법인. `induty_code` 를 `to_ksic()` 로 되돌려 쓴다

    python build_universe.py            # 상장 법인 수집 → 통합 → 셀 분포
    python build_universe.py --report   # 이미 받아둔 것으로 집계만

상장 법인 3,988 건을 하나씩 조회하므로 처음 실행은 20 분쯤 걸린다. 중간에 끊겨도
`.cache/listed.json` 에 쌓아 두므로 다시 실행하면 이어서 받는다.
"""
from __future__ import annotations
import collections
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
CACHE = os.path.join(HERE, '.cache')

sys.path.insert(0, HERE)
import fetch_dart as F          # noqa: E402
import fetch_ftc as T           # noqa: E402
from ksic_rules import classify  # noqa: E402

FTC_CSV = os.path.join(SAMPLES, 'ftc-all-2026-classified.csv')
OUT_CSV = os.path.join(SAMPLES, 'universe-2026.csv')
LISTED = os.path.join(CACHE, 'listed.json')


def _jurir(v: str) -> str:
    return re.sub(r'\D', '', v or '')


# ────────────────────────────────────────────── ① 상장 법인 수집

def fetch_listed(refresh: bool = False) -> list[dict]:
    """상장 법인의 업종코드·법인등록번호. 3,988 건이라 이어받기를 둔다."""
    os.makedirs(CACHE, exist_ok=True)
    done = {}
    if os.path.exists(LISTED) and not refresh:
        for r in json.load(io.open(LISTED, encoding='utf-8')):
            done[r['stock']] = r

    cmap = F.corp_code_map()
    todo = [(s, c) for s, c in cmap.items() if s not in done]
    if todo:
        print(f'상장 법인 {len(todo)}건 받는다 (이미 {len(done)}건)', flush=True)
    out = list(done.values())
    for i, (stock, cc) in enumerate(todo, 1):
        try:
            c = F._get_json('company.json', corp_code=cc)
            out.append({'stock': stock, 'corp_code': cc, 'name': c.get('corp_name'),
                        'induty': c.get('induty_code'), 'jurir': c.get('jurir_no')})
        except Exception as e:
            out.append({'stock': stock, 'corp_code': cc, 'error': str(e)[:60]})
        if i % 200 == 0 or i == len(todo):
            json.dump(out, io.open(LISTED, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'  {i}/{len(todo)}', flush=True)
    json.dump(out, io.open(LISTED, 'w', encoding='utf-8'), ensure_ascii=False)
    return out


# ────────────────────────────────────────────── ② 통합

def build() -> list[dict]:
    """
    두 출처를 법인등록번호로 합친다.

    겹치는 회사는 **공정위를 기본으로 쓴다** — 자릿수가 고르고 재무까지 온다.
    다만 공정위가 지주코드(K6499·M7151)인데 DART 가 사업코드를 주면 DART 로
    고친다. 지주회사 체제라 개별 신고가 실질을 가린 경우다(SK이노베이션·SKC).
    """
    ftc = list(csv.DictReader(io.open(FTC_CSV, encoding='utf-8-sig')))
    ftc_u = T.dedupe(ftc)       # 공동 소유 법인이 두 집단에 신고돼 18 건 중복한다
    print(f'공정위 {len(ftc)} → 유일화 {len(ftc_u)}')

    uni: dict[str, dict] = {}
    for r in ftc_u:
        k = _jurir(r.get('법인등록번호'))
        if not k:
            continue
        uni[k] = {
            '법인등록번호': k, '회사명': r['소속회사명'], '종목코드': '', 'KSIC': r['KSIC'],
            'A대분류': r.get('A대분류', ''), 'A세분류': r['A세분류'],
            'B1주업종': r['B1주업종'], 'B1_2단': r['B1_2단'],
            '묶음노드': r['묶음노드'], '모수계층': r['모수계층'], '매출액': r['매출액'],
            '상장': bool((r.get('기업공개일') or '').strip()), '출처': '공정위',
            '종업원수': (r.get('종업원수') or '').strip(),
            '기업집단명들': r.get('기업집단명들') or [],
        }

    listed = fetch_listed()
    # **비상장 공시법인도 합친다.** 르노코리아는 DART 에 있고 업종코드도 정확한데
    # (30121 → C30121) 상장이 아니라서 빠져 있었다. 다만 이쪽은 매출을 모르고
    # SPC·펀드가 대량 섞이므로(64 금융 · 68 부동산) **계층을 갈라 둔다**
    unlisted = []
    up = os.path.join(CACHE, 'unlisted.json')
    if os.path.exists(up):
        unlisted = [dict(r, _un=True) for r in json.load(io.open(up, encoding='utf-8'))]
        print(f'비상장 공시법인 {len(unlisted)}건도 합친다')

    # **상장사 매출·직원수 보강.** DART 기업개황에는 재무가 없어 상장 T1 3,452 건의
    # 매출이 비어 있었다 — 「매출 1,000억 이상」으로 걸면 대기업집단 계열사만 남고
    # 독립 상장사(목표 고객의 핵심층)가 통째로 빠진다. fetch_financials.py 가
    # 받아둔 것을 잇는다. 사업보고서가 없는 회사(상장폐지·SPAC)는 모수 밖으로 보낸다
    fin = {}
    fp = os.path.join(CACHE, 'financials.json')
    if os.path.exists(fp):
        for r in json.load(io.open(fp, encoding='utf-8')):
            fin[_jurir(r.get('법인등록번호'))] = r
        print(f'재무 보강 {len(fin)}건 (fetch_financials.py)')

    same = add = fixed = addu = 0
    for r in listed + unlisted:
        if r.get('error'):
            continue
        k, ks = _jurir(r.get('jurir')), F.to_ksic(r.get('induty'))
        if not k or not ks:
            continue
        cur = uni.get(k)
        if cur:
            same += 1
            if not r.get('_un'):
                cur['상장'] = True
                cur['종목코드'] = r.get('stock', '')
            if F._지주코드.match(cur['KSIC'] or '') and not F._지주코드.match(ks):
                res = classify(ks, cur.get('매출액') or '1', cur['회사명'], '')
                cur.update({'KSIC': ks, '출처': '공정위+DART(지주보정)'})
                cur.update({x: res.get(x, '') for x in ('A대분류', 'A세분류', 'B1주업종', 'B1_2단')})
                fixed += 1
            continue
        res = classify(ks, '1', r.get('name') or '', '')
        uni[k] = {
            '법인등록번호': k, '회사명': r.get('name'), '종목코드': r.get('stock', ''), 'KSIC': ks,
            'A대분류': res.get('A대분류', ''), 'A세분류': res.get('A세분류', ''),
            'B1주업종': res.get('B1주업종', ''),
            'B1_2단': res.get('B1_2단', ''), '묶음노드': res.get('묶음노드', ''),
            '모수계층': 'T1u' if r.get('_un') else 'T1', '매출액': '',
            '상장': not r.get('_un'),
            '출처': 'DART(비상장)' if r.get('_un') else 'DART', '기업집단명들': [],
            '종업원수': '',
        }
        f = fin.get(k)
        if f:
            if f.get('매출액') is not None:
                uni[k]['매출액'] = str(f['매출액'])
                if f['매출액'] == 0:
                    uni[k]['모수계층'] = '모수밖'      # classify 가 '1' 로 판정했으므로 여기서 잡는다
            if f.get('종업원수') is not None:
                uni[k]['종업원수'] = str(f['종업원수'])
            if f.get('사업보고서') == 'N':
                uni[k]['모수계층'] = '모수밖'
                uni[k]['출처'] += '(사업보고서 없음)'
        if r.get('_un'):
            addu += 1
        else:
            add += 1
    print(f'상장 {len(listed)}건 → 겹침 {same} (지주보정 {fixed}) · 신규 {add}')
    if unlisted:
        print(f'비상장 {len(unlisted)}건 → 신규 {addu}')
    print(f'통합 모수 {len(uni)}건')
    return list(uni.values())


# ────────────────────────────────────────────── ③ 셀 분포·커버리지

def report(rows: list[dict]) -> None:
    """
    셀마다 대상이 몇 개인지 센다. **업무키트 우선순위의 근거다.**

    모수밖(매출 0 인 껍데기)과 묶음노드(지주회사 — 매출이 자회사와 겹친다)는 뺀다.
    """
    # **T1u(비상장 공시법인)는 기본 집계에서 뺀다.** 매출을 모르고 SPC·펀드가
    # 섞여 있어 상장사와 같이 세면 셀 분포가 왜곡된다 — 아래에 따로 센다
    live = [r for r in rows
            if r['A세분류'] and r['모수계층'] not in ('모수밖', 'T1u') and r['묶음노드'] != 'Y']
    cells = collections.Counter((r['A세분류'], r['B1주업종']) for r in live)
    tot = len(live)
    print(f'\n사업 인스턴스 {tot}건 · 관측 셀 {len(cells)}칸')

    print('\n=== 커버리지 (누적) ===')
    acc = 0
    marks = {1, 3, 5, 10, 15, 20, 25, 30, 40, 50, len(cells)}
    for i, (_, n) in enumerate(cells.most_common(), 1):
        acc += n
        if i in marks:
            print(f'  상위 {i:>2}칸 → {acc:>5}건 / {tot} = {acc / tot * 100:>5.1f}%')

    print('\n=== 대상이 많은 셀 상위 15 ===')
    for (a, b), n in cells.most_common(15):
        print(f'  {n:>5}건  {a:<12} × {b}')

    print('\n=== A 대분류별 ===')
    for a0, n0 in collections.Counter(r.get('A대분류') or '(없음)' for r in live).most_common():
        print(f'  {n0:>5}건  {a0}')

    print('\n=== A 업태별(세분류) ===')
    for a, n in collections.Counter(r['A세분류'] for r in live).most_common():
        print(f'  {n:>5}건  {a}')

    u = [r for r in rows if r['모수계층'] == 'T1u' and r['A세분류'] and r['묶음노드'] != 'Y']
    if u:
        print(f'\n=== 비상장 공시법인(T1u) {len(u)}건 — 별도 집계 ===')
        for a2, n2 in collections.Counter(r['A세분류'] for r in u).most_common(8):
            print(f'  {n2:>5}건  {a2}')
        print('  매출을 모르므로 규모로 걸러낼 수 없다. SPC·펀드가 섞여 있다')


def to_csv(rows: list[dict], path: str = OUT_CSV) -> None:
    cols = ['법인등록번호', '회사명', '종목코드', 'KSIC', 'A대분류', 'A세분류',
            'B1주업종', 'B1_2단', '묶음노드', '모수계층', '매출액', '종업원수', '상장',
            '출처', '기업집단명들']
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            rec = dict(r)
            rec['기업집단명들'] = '|'.join(rec.get('기업집단명들') or [])
            rec['상장'] = 'Y' if rec.get('상장') else ''
            w.writerow(rec)
    print(f'\n{len(rows)}건 → {path}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    universe = build()
    report(universe)
    to_csv(universe)
