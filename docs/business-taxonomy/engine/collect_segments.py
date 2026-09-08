# -*- coding: utf-8 -*-
"""
상위 셀 회사들의 세그먼트를 수집한다.

**대상 선정이 핵심이다.** KOSDAQ 에서 배운 대로 소형사는 부문이 없다. 그래서
① 지주회사(법인 판정이 「지주·투자」라 그대로는 키트 대상이 못 된다)와
② 매출 상위(다부문 확률이 높다)를 고른다.
"""
import sys, io, os, csv, json
sys.stdout.reconfigure(encoding='utf-8')
ENG = os.path.dirname(os.path.abspath(__file__))
SAMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
sys.path.insert(0, ENG); os.chdir(ENG)
import fetch_dart as F, parse_segment as P

HERE = os.path.join(ENG, ".cache")
DST = os.path.join(HERE, 'segments.json')

rows = list(csv.DictReader(io.open(os.path.join(SAMP, 'universe-2026.csv'), encoding='utf-8-sig')))


def sales(r):
    try:
        return float((r['매출액'] or '0').replace(',', ''))
    except Exception:
        return 0.0


# 매출 하한(백만원)과 대상 수를 인자로 받는다.
#   python collect_segments.py                 지주 + 매출 1조 이상, 150 건
#   python collect_segments.py 100000 320      지주 + 매출 1000억 이상, 320 건
LOW = float(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 150

listed = [r for r in rows if r['상장'] == 'Y' and r['종목코드']]
hold = [r for r in listed if r['묶음노드'] == 'Y']
big = sorted([r for r in listed if sales(r) >= LOW], key=sales, reverse=True)

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

done = {}
if os.path.exists(DST):
    for r in json.load(io.open(DST, encoding='utf-8')):
        done[r['종목코드']] = r
    print(f'이미 받은 것 {len(done)}건 — 이어서 받는다', flush=True)

out = list(done.values())
todo = [t for t in targets if t['종목코드'] not in done]
for i, t in enumerate(todo, 1):
    rec = {'회사명': t['회사명'], '종목코드': t['종목코드'], '법인등록번호': t['법인등록번호'],
           'KSIC': t['KSIC'], 'A세분류': t['A세분류'], 'B1주업종': t['B1주업종'],
           '묶음노드': t['묶음노드'], 'segments': [], '단일부문': False, 'error': None}
    try:
        cc = F.resolve(t['종목코드'])
        rpt = F.latest_annual(cc)
        if not rpt:
            rec['error'] = '사업보고서 없음'
        else:
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
