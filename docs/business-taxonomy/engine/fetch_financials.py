# -*- coding: utf-8 -*-
"""
상장사의 매출·직원수를 받는다 — 롱리스트 규모 필터의 빈칸을 채운다
====================================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 모수의 매출은 공정위 계열사 3,539 건에만 있다. DART 에서 온
상장사 3,452 건은 매출이 비어 있어서, 「매출 1,000억 이상」으로 롱리스트를 걸면
대기업집단 계열사만 남고 **독립 상장사가 통째로 빠진다** — 목표 고객의 핵심층이다.

종업원수도 같은 이유로 받는다. 매출 1,000억이 넘는데 종업원이 0~5 명인 PFV·
개발 SPC 가 40 건 있다. 업무키트는 조직이 있는 회사에 적용되므로 걸러야 한다.

    python fetch_financials.py            # 매출 미상 상장사 전부 (~3,500 × 2 회)
    python fetch_financials.py 200        # 앞 200 건만

API: fnlttSinglAcnt(주요계정 — 매출액) · empSttus(직원 현황). 회사당 2 회.
일일 한도 20,000 회라 하루에 끝난다. 중간에 끊겨도 `.cache/financials.json` 에
쌓아 두므로 다시 실행하면 이어서 받는다. `dump_datasets.py` 가 CSV 로 내보낸다.
"""
from __future__ import annotations
import csv
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
CACHE = os.path.join(HERE, '.cache')
DST = os.path.join(CACHE, 'financials.json')

sys.path.insert(0, HERE)
import fetch_dart as F  # noqa: E402

# 결산연도. 12월 결산사의 2025 사업보고서는 2026년 3월에 나왔다. 없으면 한 해 전
YEARS = ('2025', '2024')
매출계정 = ('매출액', '수익(매출액)', '영업수익', '매출', '수익')


def _n(v) -> int | None:
    v = str(v or '').replace(',', '').strip()
    if not v or v in ('-', '—'):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def sales_of(corp_code: str) -> tuple[int | None, str]:
    """매출액(백만원)과 근거. 연결(CFS)을 먼저, 없으면 개별(OFS)."""
    for y in YEARS:
        r = F._get_json('fnlttSinglAcnt.json', corp_code=corp_code, bsns_year=y, reprt_code='11011')
        st = r.get('status')
        if st == '020':
            raise RuntimeError('한도 초과(020)')
        if st != '000':
            continue
        rows = r.get('list') or []
        for fs in ('CFS', 'OFS'):
            for acct in 매출계정:
                for x in rows:
                    if x.get('fs_div') == fs and x.get('account_nm', '').strip() == acct:
                        v = _n(x.get('thstrm_amount'))
                        if v is not None:
                            return v // 1_000_000, f'{y} {fs} {acct}'
        # 보고서는 있는데 매출 계정이 없다(금융사·지주). 「없음」과 구분해야 직원수
        # 호출을 건너뛸지 정할 수 있다
        return None, f'{y} 계정없음'
    return None, '없음'


def employees_of(corp_code: str) -> tuple[int | None, str]:
    """직원수 합계. 사업부문·성별로 나뉜 행의 `sm`(합계)을 더한다."""
    for y in YEARS:
        r = F._get_json('empSttus.json', corp_code=corp_code, bsns_year=y, reprt_code='11011')
        st = r.get('status')
        if st == '020':
            raise RuntimeError('한도 초과(020)')
        if st != '000':
            continue
        rows = r.get('list') or []
        tot = sum(_n(x.get('sm')) or 0 for x in rows)
        if rows:
            return tot, f'{y} {len(rows)}행'
    return None, '없음'


def targets(tier: str = 'T1') -> list[dict]:
    """매출 미상인 법인 — universe 에서 계층(T1 상장 · T1u 비상장)으로 고르고
    dart-corp 로 고유번호를 잇는다.

    **T1u 는 사업보고서가 있는 회사만 매출이 나온다.** 비상장 공시법인 대부분은
    감사보고서만 내고(SPC·펀드), 사채 발행 등으로 의무가 생긴 회사(르노코리아·
    한국지엠·홈플러스)만 사업보고서를 낸다. 확보율은 낮아도 그 회사들이 정확히
    목표 고객(대기업·중견 비상장)이다. 13,000 건 × 2 회라 하루 한도를 넘는다 —
    020 이 오면 저장하고 멈추므로 다음 날 같은 명령으로 이어 받는다"""
    uni = list(csv.DictReader(io.open(os.path.join(SAMPLES, 'universe-2026.csv'), encoding='utf-8-sig')))
    corp = list(csv.DictReader(io.open(os.path.join(SAMPLES, 'dart-corp-2026.csv'), encoding='utf-8-sig')))
    by_jurir = {}
    for c in corp:
        k = ''.join(ch for ch in (c.get('법인등록번호') or '') if ch.isdigit())
        if k and c.get('고유번호'):
            by_jurir.setdefault(k, c['고유번호'])
    out = []
    for r in uni:
        if r['모수계층'] != tier or (r['매출액'] or '').strip() or r['묶음노드'] == 'Y':
            continue
        cc = by_jurir.get(r['법인등록번호'])
        if cc:
            out.append({'법인등록번호': r['법인등록번호'], '회사명': r['회사명'], '고유번호': cc})
    return out


def main(limit: int | None = None, tier: str = 'T1') -> None:
    os.makedirs(CACHE, exist_ok=True)
    done = {}
    if os.path.exists(DST):
        for r in json.load(io.open(DST, encoding='utf-8')):
            done[r['법인등록번호']] = r
    todo = [t for t in targets(tier) if t['법인등록번호'] not in done]
    if limit:
        todo = todo[:limit]
    print(f'[{tier}] 대상 {len(todo)}건 (이미 {len(done)}건) · 회사당 API 2회', flush=True)

    out = list(done.values())
    t0 = time.time()
    for i, t in enumerate(todo, 1):
        rec = dict(t, 매출액=None, 매출근거='', 종업원수=None, 종업원근거='', error=None)
        try:
            rec['매출액'], rec['매출근거'] = sales_of(t['고유번호'])
            # 사업보고서가 없으면(013 두 해 연속) 직원 현황도 없다 — 비상장 13,000 건은
            # 대부분 이 경우라, 여기서 2 회를 아끼면 하루 한도 안에 두 배를 받는다
            if rec['매출근거'] == '없음':
                rec['종업원수'], rec['종업원근거'] = None, '없음'
            else:
                rec['종업원수'], rec['종업원근거'] = employees_of(t['고유번호'])
        except RuntimeError as e:
            print(f'\n{e} — 여기까지 저장하고 멈춘다', flush=True)
            break
        except Exception as e:
            rec['error'] = f'{type(e).__name__}: {str(e)[:60]}'
        # **둘 다 없으면 사업보고서가 없는 회사다.** 뜻은 계층마다 다르다 —
        # 상장(T1)이면 상장폐지·미제출이라 모수에서 뺀다(3,470 건 중 937 건).
        # 비상장(T1u)이면 감사보고서만 내는 정상 회사다 — 모수에 남긴다.
        # 해석은 build_universe.py 가 한다. 여기서는 사실만 적는다
        rec['사업보고서'] = 'N' if (rec['매출근거'] == '없음' and rec['종업원근거'] == '없음'
                                  and not rec['error']) else 'Y'
        out.append(rec)
        if i % 100 == 0 or i == len(todo):
            json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
            got = sum(1 for r in out if r.get('매출액') is not None)
            print(f'  {i}/{len(todo)} · 매출 확보 {got} · {time.time()-t0:.0f}s', flush=True)
    json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
    got = sum(1 for r in out if r.get('매출액') is not None)
    emp = sum(1 for r in out if r.get('종업원수') is not None)
    print(f'\n{len(out)}건 → {DST}  (매출 {got} · 직원수 {emp})')


if __name__ == '__main__':
    #   python fetch_financials.py            상장(T1) 전부
    #   python fetch_financials.py T1u        비상장 공시법인 전부 — 하루 한도에 걸리면 멈추고 다음 날 이어 받는다
    #   python fetch_financials.py T1u 500    앞 500 건만
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    tier = next((a for a in args if a.startswith('T')), 'T1')
    limit = next((int(a) for a in args if a.isdigit()), None)
    main(limit, tier)
