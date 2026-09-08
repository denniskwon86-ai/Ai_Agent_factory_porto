# -*- coding: utf-8 -*-
"""
세그먼트를 인스턴스로 반영해 셀 분포를 다시 낸다.

**인스턴스는 실질 단위다.** 다부문 회사는 법인 대신 부문을 세운다 — 그러지 않으면
KB금융이 「지주·투자」로 남아 은행 키트 대상에서 빠진다.
"""
import sys, io, os, csv, json, collections
sys.stdout.reconfigure(encoding='utf-8')
ENG = os.path.dirname(os.path.abspath(__file__))
SAMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
sys.path.insert(0, ENG); os.chdir(ENG)
import fetch_dart as F, segment_rules as R

HERE = os.path.join(ENG, ".cache")
uni = list(csv.DictReader(io.open(os.path.join(SAMP, 'universe-2026.csv'), encoding='utf-8-sig')))
segs = json.load(io.open(os.path.join(HERE, 'segments.json'), encoding='utf-8'))
ftc = list(csv.DictReader(io.open(os.path.join(SAMP, 'ftc-all-2026-classified.csv'), encoding='utf-8-sig')))
# **계열사 색인은 universe 로 만든다.** 공정위 CSV 로 만들면 지주코드 보정이
# 빠져서, SK(주)의 「SK이노베이션」 부문이 다시 「지주·투자」로 판정된다 —
# 부문을 갈라 놓고도 키트 대상이 못 되니 목적을 놓친다
AIDX = {}
for _r in uni:
    _val = (_r['A세분류'], _r['B1주업종'], _r['B1_2단'])
    if not any(_val):
        continue
    for _g in (_r['기업집단명들'] or '').split('|'):
        if not _g:
            continue
        for _c in R._cands(_r['회사명']):
            AIDX.setdefault(R._norm_corp(_g), {}).setdefault(_c, _val)
GROUP = {}
for r in ftc:
    for c in R._cands(r['소속회사명']):
        GROUP.setdefault(c, r['기업집단명'])

seg_map = {r['법인등록번호']: r for r in segs if len(r['segments']) >= 2}
print(f'다부문 회사 {len(seg_map)}건 · 부문 {sum(len(r["segments"]) for r in seg_map.values())}건')

inst, replaced, held = [], 0, 0
for r in uni:
    if r['모수계층'] == '모수밖':
        continue
    k = r['법인등록번호']
    sr = seg_map.get(k)
    if sr:
        parent = {'A세분류': r['A세분류'], 'B1주업종': r['B1주업종'], 'B1_2단': r['B1_2단'],
                  '_법인명': r['회사명'], '_기업집단': GROUP.get(R._norm_corp(r['회사명']), '')}
        for s in sr['segments']:
            j = R.classify_segment(s['명칭'], parent, AIDX)
            if not j['A세분류']:
                continue                       # 지역 세그먼트 등
            inst.append({'단위': '세그먼트', '모법인': r['회사명'], '이름': s['명칭'],
                         'A세분류': j['A세분류'], 'B1주업종': j['B1주업종'],
                         'B1_2단': j['B1_2단'], '매출': s['매출'], '판정근거': j['판정근거']})
        replaced += 1
        continue
    if r['묶음노드'] == 'Y':
        held += 1                              # 부문을 못 얻은 지주회사는 여전히 뺀다
        continue
    if not r['A세분류']:
        continue
    inst.append({'단위': '법인', '모법인': '', '이름': r['회사명'],
                 'A세분류': r['A세분류'], 'B1주업종': r['B1주업종'],
                 'B1_2단': r['B1_2단'], '매출': r['매출액'], '판정근거': 'KSIC'})

print(f'세그먼트로 대체한 회사 {replaced}건 · 부문 못 얻은 지주 {held}건 제외')
print(f'인스턴스 {len(inst)}건 (법인 {sum(1 for x in inst if x["단위"]=="법인")} · 세그먼트 {sum(1 for x in inst if x["단위"]=="세그먼트")})')

cells = collections.Counter((x['A세분류'], x['B1주업종']) for x in inst)
tot = len(inst)
print(f'\n관측 셀 {len(cells)}칸')
print('\n=== 커버리지 (누적) ===')
acc = 0
marks = {1, 3, 5, 10, 15, 20, 25, 30, 40, 50, len(cells)}
for i, (_, n) in enumerate(cells.most_common(), 1):
    acc += n
    if i in marks:
        print(f'  상위 {i:>2}칸 → {acc:>5}건 / {tot} = {acc/tot*100:>5.1f}%')
print('\n=== 상위 15 셀 ===')
for (a, b), n in cells.most_common(15):
    print(f'  {n:>5}건  {a:<12} × {b}')

# 세그먼트가 새로 채운 셀
seg_cells = collections.Counter((x['A세분류'], x['B1주업종']) for x in inst if x['단위'] == '세그먼트')
print('\n=== 세그먼트가 기여한 셀 상위 10 ===')
for (a, b), n in seg_cells.most_common(10):
    print(f'  {n:>4}건  {a:<12} × {b}')

json.dump(inst, io.open(os.path.join(HERE, 'instances.json'), 'w', encoding='utf-8'), ensure_ascii=False)
dst = os.path.join(SAMP, 'instances-2026.csv')
with io.open(dst, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['단위', '모법인', '이름', 'A세분류', 'B1주업종', 'B1_2단', '매출', '판정근거'])
    w.writeheader(); w.writerows(inst)
print(f'\n{len(inst)}건 → {dst}')
