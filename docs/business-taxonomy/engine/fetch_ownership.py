# -*- coding: utf-8 -*-
"""
최대주주·출자 관계를 받는다 — 손자회사의 연결고리
==================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 지금 회사 간 연결은 공정위 「기업집단명」 하나뿐이다. 그래서
「삼성 소속」은 알지만 **삼성전자 → 삼성디스플레이 → 그 자회사**처럼 누가 누구를
지배하는지는 모른다. 지주회사·단순 자회사는 이름과 KSIC 로 짐작되지만, 손자회사와
공동 출자 계열회사는 짐작이 안 된다.

두 방향을 함께 받는다 — 한쪽만으로는 그래프가 끊긴다.

| API | 방향 | 무엇을 알 수 있나 |
|---|---|---|
| `hyslrSttus` 최대주주 현황 | **위로** | 내 최대주주가 누구인가(중간지주가 드러난다) |
| `otrCprInvstmntSttus` 타법인 출자현황 | **아래로** | 내가 어디에 몇 % 출자했나 |

`otrCprInvstmntSttus` 가 핵심이다. 상장 모회사 하나를 조회하면 **비상장 손자회사까지**
출자 목록이 나온다 — 손자회사 자신은 사업보고서를 내지 않아도 잡힌다.

    python fetch_ownership.py            # 상장 T1 전부 (회사당 2회)
    python fetch_ownership.py 300        # 앞 300건만

개인정보 — **최대주주가 개인이면 이름을 저장하지 않고 「개인」으로 적는다.** 법인은
공개 법인 식별자라 그대로 남긴다(대표자명을 CSV 에 넣지 않는 것과 같은 기준이다).
"""
from __future__ import annotations
import csv
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
CACHE = os.path.join(HERE, '.cache')
DST = os.path.join(CACHE, 'ownership.json')

sys.path.insert(0, HERE)
import fetch_dart as F  # noqa: E402

YEARS = ('2025', '2024')

# 법인으로 보는 표기 — 이게 없으면 개인으로 보고 이름을 지운다
_법인 = re.compile(
    r'㈜|\(주\)|\(유\)|주식회사|유한회사|합자회사|재단|법인|공사|공단|조합|기금|은행|증권|'
    r'생명|화재|캐피탈|홀딩스|지주|파트너스|인베스트|자산운용|투자|펀드|Corp|Inc|Ltd|LLC|'
    r'Holdings|Group|Co\.', re.I)


def _mask(nm: str) -> str:
    """개인은 이름을 남기지 않는다 — 지배 구조에 필요한 건 「개인인가」뿐이다"""
    nm = (nm or '').strip()
    return nm if _법인.search(nm) else ('개인' if nm else '')


def _n(v) -> int | None:
    v = str(v or '').replace(',', '').replace('%', '').strip()
    if not v or v in ('-', '—'):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _rt(v) -> float | None:
    v = str(v or '').replace(',', '').replace('%', '').strip()
    try:
        return float(v)
    except ValueError:
        return None


def largest_holder(corp_code: str) -> tuple[list[dict], str]:
    """최대주주 현황 — 나를 지배하는 쪽(위로)"""
    for y in YEARS:
        r = F._get_json('hyslrSttus.json', corp_code=corp_code, bsns_year=y, reprt_code='11011')
        st = r.get('status')
        if st == '020':
            raise RuntimeError('한도 초과(020)')
        if st != '000':
            continue
        out = []
        for x in r.get('list') or []:
            nm = _mask(x.get('nm'))
            if not nm:
                continue
            out.append({'주주': nm, '관계': (x.get('relate') or '').strip(),
                        '지분율': _rt(x.get('trmend_posesn_stock_qota_rt'))})
        if out:
            return out, y
    return [], ''


def investments(corp_code: str) -> tuple[list[dict], str]:
    """
    타법인 출자현황 — 내가 지배하는 쪽(아래로).

    **이게 손자회사를 잡는다.** 상장 모회사가 비상장 자회사·손자회사 지분을 다 적는다.
    """
    for y in YEARS:
        r = F._get_json('otrCprInvstmntSttus.json', corp_code=corp_code,
                        bsns_year=y, reprt_code='11011')
        st = r.get('status')
        if st == '020':
            raise RuntimeError('한도 초과(020)')
        if st != '000':
            continue
        out = []
        for x in r.get('list') or []:
            nm = (x.get('inv_prm') or '').strip()      # 법인명
            if not nm:
                continue
            out.append({'출자대상': nm,
                        '지분율': _rt(x.get('trmend_blce_qota_rt')),
                        '장부가액': _n(x.get('trmend_blce_acntbk_amount'))})
        if out:
            return out, y
    return [], ''


def targets() -> list[dict]:
    """상장 T1 — 이쪽만 사업보고서를 내므로 출자 목록이 나온다"""
    uni = list(csv.DictReader(io.open(os.path.join(SAMPLES, 'universe-2026.csv'), encoding='utf-8-sig')))
    corp = list(csv.DictReader(io.open(os.path.join(SAMPLES, 'dart-corp-2026.csv'), encoding='utf-8-sig')))
    by_jurir = {}
    for c in corp:
        k = ''.join(ch for ch in (c.get('법인등록번호') or '') if ch.isdigit())
        if k and c.get('고유번호'):
            by_jurir.setdefault(k, c['고유번호'])
    out = []
    for r in uni:
        if r['모수계층'] != 'T1':
            continue
        cc = by_jurir.get(r['법인등록번호'])
        if cc:
            out.append({'법인등록번호': r['법인등록번호'], '회사명': r['회사명'], '고유번호': cc})
    return out


def main(limit: int | None = None) -> None:
    os.makedirs(CACHE, exist_ok=True)
    done = {}
    if os.path.exists(DST):
        for r in json.load(io.open(DST, encoding='utf-8')):
            done[r['법인등록번호']] = r
    todo = [t for t in targets() if t['법인등록번호'] not in done]
    if limit:
        todo = todo[:limit]
    print(f'대상 {len(todo)}건 (이미 {len(done)}건) · 회사당 API 2회', flush=True)

    out = list(done.values())
    t0 = time.time()
    for i, t in enumerate(todo, 1):
        rec = dict(t, 최대주주=[], 최대주주연도='', 출자=[], 출자연도='', error=None)
        try:
            rec['최대주주'], rec['최대주주연도'] = largest_holder(t['고유번호'])
            rec['출자'], rec['출자연도'] = investments(t['고유번호'])
        except RuntimeError as e:
            print(f'\n{e} — 여기까지 저장하고 멈춘다. 다음 날 같은 명령으로 이어 받는다', flush=True)
            break
        except Exception as e:
            rec['error'] = f'{type(e).__name__}: {str(e)[:60]}'
        out.append(rec)
        if i % 100 == 0 or i == len(todo):
            json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
            h = sum(1 for r in out if r.get('최대주주'))
            v = sum(len(r.get('출자') or []) for r in out)
            print(f'  {i}/{len(todo)} · 최대주주 {h} · 출자 엣지 {v} · {time.time()-t0:.0f}s', flush=True)
    json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
    h = sum(1 for r in out if r.get('최대주주'))
    v = sum(len(r.get('출자') or []) for r in out)
    print(f'\n{len(out)}건 → {DST}  (최대주주 {h}건 · 출자 엣지 {v}건)')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
