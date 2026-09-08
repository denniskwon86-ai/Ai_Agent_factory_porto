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

# A 축은 2 단이다 — 대분류(제조·유통·서비스) 아래 세분류가 온다. 세그먼트 판정은
# 세분류만 내놓으므로 여기서 대분류를 되짚는다
A대분류 = {}
for _r in csv.DictReader(io.open(os.path.join(SAMP, 'ftc-all-2026-classified.csv'), encoding='utf-8-sig')):
    if _r.get('A세분류') and _r.get('A대분류'):
        A대분류.setdefault(_r['A세분류'], _r['A대분류'])
A대분류.update({'시공·건설': '제조', '자원채취': '제조', '지주·투자': '서비스'})

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

# **모수 안의 법인 이름 색인.** 지주회사의 부문은 계열사명인 경우가 많고, 그 계열사가
# 이미 인스턴스로 서 있다 — (주)두산의 「두산에너빌리티」 부문과 두산에너빌리티(주)
# 법인이 둘 다 세어지면 같은 사업이 두 번 계상된다. 두산퓨얼셀은 (주)두산 부문 ·
# 두산에너빌리티 부문 · 두산퓨얼셀 법인으로 **세 번** 잡혔다.
# README 의 「묶음 노드 = 그 매출이 모수 안의 다른 인스턴스 매출을 포함하는 경우」가
# 이 경우다. 그래서 **이름이 다른 법인과 겹치는 부문은 인스턴스로 세우지 않는다.**
CORP = {}
for r in uni:
    if r['모수계층'] == '모수밖':
        continue
    for c in R._cands(r['회사명']):
        CORP.setdefault(c, r['회사명'])


def is_affiliate(seg_name: str, parent: str) -> str | None:
    """부문명이 모수 안의 **다른** 법인이면 그 법인명을 돌려준다"""
    pn = R._norm_corp(parent)
    for c in R._cands(seg_name):
        hit = CORP.get(c)
        if hit and R._norm_corp(hit) != pn:
            return hit
    return None

inst, replaced, held = [], 0, 0
dropped = []          # 계열사명이라 뺀 부문 — 이중계상 방지
for r in uni:
    if r['모수계층'] == '모수밖':
        continue
    k = r['법인등록번호']
    sr = seg_map.get(k)
    # **지주회사의 부문은 세우지 않는다.** 그 부문은 사업부가 아니라 계열사 묶음이고,
    # 그 계열사가 이미 모수에 법인으로 있다 — (주)LS 「동제련부문」(14.94조)은
    # LS엠앤엠(주)(14.36조) + 토리컴(0.59조) 의 연결이고, KB금융 「은행부문」은
    # (주)국민은행이다. 부문으로 또 세우면 같은 사업이 두 번 계상되고, 매출도
    # 기준이 달라(부문은 연결 · 법인은 개별) 나란히 둘 수 없다.
    #
    # 세그먼트가 진짜 필요한 건 **법인 안의 사업부**다 — 삼성전자 DX·DS,
    # LG전자 HS·MS, 이마트 유통업·식음료업처럼 별개 법인이 아닌 것들.
    if sr and r['묶음노드'] == 'Y':
        held += 1
        continue
    if sr:
        parent = {'A대분류': r.get('A대분류', ''), 'A세분류': r['A세분류'],
                  'B1주업종': r['B1주업종'], 'B1_2단': r['B1_2단'],
                  '_법인명': r['회사명'], '_기업집단': GROUP.get(R._norm_corp(r['회사명']), '')}
        kept = 0
        for s in sr['segments']:
            dup = is_affiliate(s['명칭'], r['회사명'])
            if dup:
                dropped.append((r['회사명'], s['명칭'], dup))
                continue                       # 그 계열사가 이미 인스턴스다 — 이중계상
            j = R.classify_segment(s['명칭'], parent, AIDX)
            if not j['A세분류']:
                continue                       # 지역 세그먼트 등
            inst.append({'단위': '세그먼트', '모법인': r['회사명'], '이름': s['명칭'],
                         '계층': r['모수계층'], '소속그룹': r.get('기업집단명들', ''),
                         'A대분류': A대분류.get(j['A세분류'], ''),
                         'A세분류': j['A세분류'], 'B1주업종': j['B1주업종'],
                         'B1_2단': j['B1_2단'], '매출': s['매출'], '판정근거': j['판정근거']})
            kept += 1
        replaced += 1
        # 부문이 전부 계열사명이었으면 그 회사는 남는 사업이 없다. 지주회사면
        # 그대로 빼고(자회사가 인스턴스다), 아니면 법인 자체를 세운다
        if kept == 0 and r['묶음노드'] != 'Y' and r['A세분류']:
            inst.append({'단위': '법인', '모법인': '', '이름': r['회사명'],
                         '계층': r['모수계층'], '소속그룹': r.get('기업집단명들', ''),
                         'A대분류': r.get('A대분류') or A대분류.get(r['A세분류'], ''),
                         'A세분류': r['A세분류'], 'B1주업종': r['B1주업종'],
                         'B1_2단': r['B1_2단'], '매출': r['매출액'], '판정근거': 'KSIC'})
        continue
    if r['묶음노드'] == 'Y':
        held += 1                              # 부문을 못 얻은 지주회사는 여전히 뺀다
        continue
    if not r['A세분류']:
        continue
    inst.append({'단위': '법인', '모법인': '', '이름': r['회사명'],
                 '계층': r['모수계층'], '소속그룹': r.get('기업집단명들', ''),
                 'A대분류': r.get('A대분류') or A대분류.get(r['A세분류'], ''),
                 'A세분류': r['A세분류'], 'B1주업종': r['B1주업종'],
                 'B1_2단': r['B1_2단'], '매출': r['매출액'], '판정근거': 'KSIC'})

print(f'세그먼트로 대체한 회사 {replaced}건 · 부문 못 얻은 지주 {held}건 제외')
if dropped:
    print(f'이중계상으로 뺀 부문 {len(dropped)}건 (부문명이 모수 안의 다른 법인이다)')
    for mo, nm, hit in dropped[:8]:
        print(f'    {mo[:16]:<18} 「{nm[:14]}」 → 법인 {hit[:20]} 가 이미 있다')
print(f'인스턴스 {len(inst)}건 (법인 {sum(1 for x in inst if x["단위"]=="법인")} · 세그먼트 {sum(1 for x in inst if x["단위"]=="세그먼트")})')

# **셀 분포는 T1·T2 만 센다.** T1u(비상장 공시법인)는 매출을 모르고 SPC·펀드가
# 대량 섞여 있어 함께 세면 커버리지가 왜곡된다 — 롱리스트에는 남긴다
core = [x for x in inst if x.get('계층') != 'T1u']
cells = collections.Counter((x['A세분류'], x['B1주업종']) for x in core)
tot = len(core)
print(f'  그중 T1·T2 {tot}건 · T1u {len(inst)-tot}건(집계 제외)')
print(f'\n관측 셀 {len(cells)}칸')
print('\n=== 커버리지 (누적) ===')
acc = 0
marks = {1, 3, 5, 10, 15, 20, 25, 30, 40, 50, len(cells)}
for i, (_, n) in enumerate(cells.most_common(), 1):
    acc += n
    if i in marks:
        print(f'  상위 {i:>2}칸 → {acc:>5}건 / {tot} = {acc/tot*100:>5.1f}%')
print()
print('=== A 대분류별 ===')
for a0, n0 in collections.Counter(x.get('A대분류') or '(없음)' for x in core).most_common():
    print(f'  {n0:>5}건  {a0}')
print('\n=== 상위 15 셀 ===')
for (a, b), n in cells.most_common(15):
    print(f'  {n:>5}건  {a:<12} × {b}')

# 세그먼트가 새로 채운 셀
seg_cells = collections.Counter((x['A세분류'], x['B1주업종']) for x in core if x['단위'] == '세그먼트')
print('\n=== 세그먼트가 기여한 셀 상위 10 ===')
for (a, b), n in seg_cells.most_common(10):
    print(f'  {n:>4}건  {a:<12} × {b}')

json.dump(inst, io.open(os.path.join(HERE, 'instances.json'), 'w', encoding='utf-8'), ensure_ascii=False)
dst = os.path.join(SAMP, 'instances-2026.csv')
with io.open(dst, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['단위', '계층', '소속그룹', '모법인', '이름',
                                      'A대분류', 'A세분류', 'B1주업종', 'B1_2단',
                                      '매출', '판정근거'])
    w.writeheader(); w.writerows(inst)
print(f'\n{len(inst)}건 → {dst}')
