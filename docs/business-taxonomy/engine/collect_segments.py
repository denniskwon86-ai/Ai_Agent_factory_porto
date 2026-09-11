# -*- coding: utf-8 -*-
"""
상위 셀 회사들의 세그먼트를 수집한다.

**대상 선정이 핵심이다.** KOSDAQ 에서 배운 대로 소형사는 부문이 없다. 그래서
① 지주회사(법인 판정이 「지주·투자」라 그대로는 키트 대상이 못 된다)와
② 매출 상위(다부문 확률이 높다)를 고른다.

**두 번 잘려 있었다** (D-44).
- `LIMIT` 기본값 150 에서 끊겨 매출 1 조가 넘는 회사가 대량으로 빠졌다.
- `상장 == 'Y'` 로 걸러 **비상장 공시법인이 아예 대상이 아니었다.** 사업보고서를
  내는 것은 상장 여부가 아닌데(D-41 의 `fetch_ownership` 과 정반대 방향의 같은 실수)
  GS칼텍스 42 조·SK에너지 39 조·삼성디스플레이 25 조가 한 칸에 뭉쳐 있었다.

그래서 종목코드가 없으면 **법인등록번호로 DART 고유번호를 찾는다.**
"""
import sys, io, os, csv, json
sys.stdout.reconfigure(encoding='utf-8')
ENG = os.path.dirname(os.path.abspath(__file__))
SAMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
sys.path.insert(0, ENG); os.chdir(ENG)
import fetch_dart as F, parse_segment as P, segment_rules as SR
import taxonomy_io as tx

HERE = os.path.join(ENG, ".cache")
DST = os.path.join(HERE, 'segments.json')

rows = tx.load('universe')               # * [P4] CSV 가 아니라 DB 스냅샷에서


def sales(r):
    try:
        return float((r['매출액'] or '0').replace(',', ''))
    except Exception:
        return 0.0


# 매출 하한(백만원)과 대상 수를 인자로 받는다.
#   python collect_segments.py                 지주 + 매출 1조 이상, 150 건
#   python collect_segments.py 100000 320      지주 + 매출 1000억 이상, 320 건
LOW = float(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 800

# 법인등록번호 → DART 고유번호. 비상장 공시법인은 종목코드가 없어 이 길로만 닿는다
_corp = tx.load('src_corp')
BY_JURIR = {}
for c in _corp:
    k = ''.join(ch for ch in (c.get('법인등록번호') or '') if ch.isdigit())
    if k and c.get('고유번호'):
        BY_JURIR.setdefault(k, c['고유번호'])


# 회사명 → 고유번호. **법인등록번호 색인에 없는 대형 비상장사가 여기서 잡힌다** —
# GS칼텍스 42 조·SK에너지 39 조·SK지오센트릭이 `dart-corp-2026.csv` 에 없었다.
# 공정위는 「지에스칼텍스(주)」, DART 는 「GS칼텍스」로 써서 표기가 어긋난 것인데
# `_cands()` 가 영문↔한글을 맞춰 준다
BY_NAME = F.corp_name_map()


def corp_code(r) -> str:
    """종목코드 → 법인등록번호 → **회사명** 순으로 DART 고유번호를 찾는다"""
    if r.get('종목코드'):
        try:
            cc = F.resolve(r['종목코드'])
            if cc:
                return cc
        except Exception:
            pass
    cc = BY_JURIR.get(r['법인등록번호'])
    if cc:
        return cc
    for c in SR._cands(r['회사명']):
        if c in BY_NAME:
            return BY_NAME[c]
    return ''


# **공시법인 전부**가 대상이다 — 상장 여부가 아니라 사업보고서를 내는가로 고른다
filed = [r for r in rows if r['모수계층'] != '모수밖'
         and (r['종목코드'] or r['법인등록번호'] in BY_JURIR
              or any(c in BY_NAME for c in SR._cands(r['회사명'])))]
# **지주에도 매출 하한을 건다.** 비상장을 대상에 넣자 매출 0 인 SPC 지주 1,616 건이
# 앞자리를 다 차지해 GS칼텍스 42 조가 밀려났다. 지주는 하한의 1/10(1,000 억)로 둔다 —
# 지주 매출은 배당·상표권이라 사업회사보다 작다
hold = sorted([r for r in filed if r['묶음노드'] == 'Y' and sales(r) >= LOW / 10],
              key=sales, reverse=True)
big = sorted([r for r in filed if sales(r) >= LOW], key=sales, reverse=True)

seen, targets = set(), []
for r in hold + big:                      # 지주회사를 먼저
    k = r['법인등록번호']
    if k in seen:
        continue
    seen.add(k)
    targets.append(r)
    if len(targets) >= LIMIT:
        break
print(f'대상 {len(targets)}건 (지주 {len(hold)} + 매출 {LOW/1e6:.2f}조 이상)', flush=True)

# **색인은 법인등록번호다** — 종목코드로 잡으면 비상장이 전부 빈 키가 되어
# 서로를 덮어쓴다(종목코드 '' 하나에 몰린다)
done = {}
if os.path.exists(DST):
    for r in json.load(io.open(DST, encoding='utf-8')):
        done[r.get('법인등록번호') or r.get('종목코드')] = r
    print(f'이미 받은 것 {len(done)}건 — 이어서 받는다', flush=True)

out = list(done.values())
todo = [t for t in targets if t['법인등록번호'] not in done]
for i, t in enumerate(todo, 1):
    rec = {'회사명': t['회사명'], '종목코드': t['종목코드'], '법인등록번호': t['법인등록번호'],
           'KSIC': t['KSIC'], 'A세분류': t['A세분류'], 'B1주업종': t['B1주업종'],
           '묶음노드': t['묶음노드'], 'segments': [], '단일부문': False, 'error': None}
    try:
        cc = corp_code(t)
        rpt = F.latest_annual(cc) if cc else None
        if not cc:
            rec['error'] = 'DART 고유번호 없음'
        elif not rpt:
            rec['error'] = '사업보고서 없음'
        else:
            rec['보고서'] = rpt.get('report_nm', '')   # 「사업보고서 (2025.12)」 — 부문 매출의 기준연도
            note = F.note_xml(rpt['rcept_no'])
            if not note:
                rec['error'] = '주석 못찾음'
            else:
                rec['단일부문'] = P.single_segment(note)
                rec['segments'] = P.parse(note)
    except Exception as e:
        rec['error'] = f'{type(e).__name__}: {str(e)[:50]}'
    out.append(rec)
    n = len(rec['segments'])
    tag = '단일' if rec['단일부문'] else (rec['error'] or f'{n}부문')
    print(f'  [{i:>3}/{len(todo)}] {rec["회사명"][:20]:<22} {tag}', flush=True)
    if i % 10 == 0 or i == len(todo):
        json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)

json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
multi = [r for r in out if len(r['segments']) >= 2]
one = [r for r in out if len(r['segments']) == 1]
none = [r for r in out if not r['segments']]
print(f'\n=== 다부문 {len(multi)} · 1부문 {len(one)} · 부문없음 {len(none)} (총 {len(out)}) ===')
print(f'    부문 총계 {sum(len(r["segments"]) for r in out)}건')
