# -*- coding: utf-8 -*-
"""
산업 커버리지 맵 만들기
=======================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

`instances-2026.csv` 를 읽어 `dashboard.tpl.html` 에 끼워 단일 HTML 을 만든다.
Artifact 로 발행해 격자에서 사업묶음을 고르고 롱리스트를 뽑는 데 쓴다.

    python make_dashboard.py            # → .cache/coverage-map.html

**격자·커버리지는 T1·T2 만 센다.** T1u(비상장 공시법인)는 매출을 모르고 SPC·펀드가
대량 섞여 있어 함께 세면 커버리지가 왜곡된다 — 롱리스트에서는 체크박스로 켠다.
"""
import sys, csv, io, os, json, collections
sys.stdout.reconfigure(encoding='utf-8')
BASE = r'C:\AI Workspace\Ai_Agent_factory_porto-dev\docs\business-taxonomy'
inst = list(csv.DictReader(io.open(os.path.join(BASE, 'samples/instances-2026.csv'), encoding='utf-8-sig')))
uni = list(csv.DictReader(io.open(os.path.join(BASE, 'samples/universe-2026.csv'), encoding='utf-8-sig')))

def num(v):
    try:
        return int(float((v or '0').replace(',', '')))
    except Exception:
        return 0

# A 축은 2 단이다 — 대분류(자원·제조·건설·유통·서비스) 아래 세분류가 온다.
# 격자 행을 대분류로 묶어야 「제조 > 소재제조」로 읽힌다.
# **자원채취와 시공·건설을 「제조」에서 뺐다** — 농장은 물성을 바꾸지 않고,
# 건설은 현장에서 수주 단위로 일한다. 업무키트가 겹치지 않으니 갈라 둔다
G = ['자원', '제조', '건설', '유통', '서비스']
sub2big = {}
for r in inst:
    if r.get('A세분류') and r.get('A대분류'):
        sub2big.setdefault(r['A세분류'], r['A대분류'])
A = sorted({r['A세분류'] for r in inst if r['A세분류']})
B = sorted({r['B1주업종'] for r in inst if r['B1주업종']})
ai = {v: i for i, v in enumerate(A)}
bi = {v: i for i, v in enumerate(B)}
mo = sorted({r['모법인'] for r in inst if r['모법인']})
mi = {v: i for i, v in enumerate(mo)}
# 소속그룹 — 공동 소유 법인은 「엘에스|카카오」처럼 여럿일 수 있다
gr = sorted({r.get('소속그룹') for r in inst if r.get('소속그룹')})
gri = {v: i for i, v in enumerate(gr)}

# 밸류체인 사전 — 행에는 인덱스만 실어 파일 크기를 줄인다
VC = sorted({x for r in inst for x in (r.get('밸류체인') or '').split('|') if x})
vci = {v: i for i, v in enumerate(VC)}

rows = []
for r in inst:
    if not r['A세분류'] or not r['B1주업종']:
        continue
    # 단위 — 0 법인 · 1 세그먼트(부문) · **2 묶음(지주회사)**.
    # 묶음은 롱리스트에 보이지만 격자·커버리지 집계에서는 뺀다 (D-38)
    rows.append([2 if r['단위'] == '묶음' else (1 if r['단위'] == '세그먼트' else 0), r['이름'][:40],
                 mi.get(r['모법인'], -1), ai[r['A세분류']], bi[r['B1주업종']],
                 r['B1_2단'][:20], num(r['매출']),
                 1 if r.get('계층') == 'T1u' else 0,
                 gri.get(r.get('소속그룹'), -1),
                 # 매출기준 — 「2025 개별(공정위)」「2025 연결(DART)」「2025 연결 부문(사업보고서)」.
                 # 출처마다 연도·연결/개별이 달라 숫자만 나란히 두면 오해한다.
                 # 종업원수는 필터에서 뺐으므로 행에 싣지 않는다(CSV 에는 남아 있다)
                 r.get('매출기준', ''),
                 # 3 단 — 같은 품목 안의 공정·형태(제련·압연·강관…). **제조업에만 있다**(D-37)
                 (r.get('B1_3단') or '')[:20],
                 # 밸류체인(복수) · 가치사슬 단계. 밸류체인으로 걸러 단계로 정렬하면
                 # 생태계 안의 층이 재구성된다 — 셀 간 「공급」 엣지가 필요 없다
                 [vci[x] for x in (r.get('밸류체인') or '').split('|') if x in vci],
                 int(r['가치사슬단계']) if (r.get('가치사슬단계') or '').strip() else 0,
                 # 나를 지배하는 법인 — 공정위 소속그룹은 「삼성 소속」만 알려 주지만
                 # 이건 삼성전자 → 삼성디스플레이 → 그 자회사까지 사슬을 잇는다 (D-41)
                 r.get('지배법인', '')])

# KSIC 대분류별 두께 — 산업 커버리지 판단용
KO = {'A': '농림어업', 'B': '광업', 'C': '제조', 'D': '전기가스', 'E': '수도하수', 'F': '건설',
      'G': '도소매', 'H': '운수창고', 'I': '숙박음식', 'J': '정보통신', 'K': '금융보험',
      'L': '부동산', 'M': '전문과학', 'N': '사업시설', 'P': '교육', 'Q': '보건복지',
      'R': '예술스포츠', 'S': '협회수리'}
live = [r for r in uni if r['A세분류'] and r['모수계층'] != '모수밖']
ksic = collections.Counter((r['KSIC'] or '?')[0] for r in live)
industry = [{'code': k, 'name': KO[k], 'n': ksic.get(k, 0)} for k in sorted(KO)]

out = {
    'meta': {
        'universe': len(uni),
        'instances': len(rows),
        'corp': sum(1 for r in rows if r[0] == 0),
        'seg': sum(1 for r in rows if r[0] == 1),
        'hold': sum(1 for r in rows if r[0] == 2),
        'core': sum(1 for r in rows if r[7] == 0 and r[0] != 2),
        'tier1u': sum(1 for r in rows if r[7] == 1),
        'listed': sum(1 for r in uni if r['상장'] == 'Y'),
        'holding': sum(1 for r in uni if r['묶음노드'] == 'Y'),
        'outside': sum(1 for r in uni if r['모수계층'] == '모수밖'),
    },
    'A': A, 'B': B, 'mo': mo, 'vc': VC, 'rows': rows, 'industry': industry,
    'G': G, 'sub2big': sub2big, 'gr': gr,
}
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'dashboard-data.json')
json.dump(out, io.open(dst, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f"인스턴스 {len(rows)}건 · A축 {len(A)} · B축 {len(B)} · 모법인 {len(mo)}")
print(f"셀 {len({(r[3], r[4]) for r in rows})}칸")
print(f"→ {dst} ({os.path.getsize(dst)/1024:.0f}KB)")


# ────────────────────────────────────────────── HTML 조립

TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.tpl.html')
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'coverage-map.html')
tpl = io.open(TPL, encoding='utf-8').read()
data = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
io.open(HTML, 'w', encoding='utf-8').write(tpl.replace('__DATA__', data))
print(f"→ {HTML} ({os.path.getsize(HTML)/1024:.0f}KB)")
print('  Artifact 로 발행하면 격자·롱리스트를 쓸 수 있다')
