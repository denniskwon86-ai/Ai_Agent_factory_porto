# -*- coding: utf-8 -*-
"""
수집 데이터를 저장소에 남긴다
=============================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 수집 결과가 `.cache/` 에만 있으면 그 환경에서만 쓸 수 있다.
`.cache/` 는 공시 ZIP 이 248MB 라 `.gitignore` 에 걸려 있고, 그래서 API 한도와
시간을 들여 받은 것이 통째로 로컬에 묶인다. 다른 사람이 클론하면 처음부터 다시
받아야 하고, 일일 한도(20,000회) 때문에 하루에 끝나지도 않는다.

그래서 **추출한 데이터는 `samples/` 에 파일로 남긴다.** 원천 ZIP 은 캐시에 두고
(용량이 크고 언제든 다시 받을 수 있다), 그것을 읽어 얻은 값만 커밋한다.

    python dump_datasets.py

내보내는 것

| 파일 | 내용 | 다시 만드는 비용 |
|---|---|---|
| `dart-corp-2026.csv` | 공시법인의 업종코드·법인등록번호 | API 2만 회 · 일일 한도에 걸린다 |
| `segments-2026.csv` | 420 개사의 영업부문 목록 | ZIP 420 건(수 GB) 다운로드 + 파싱 |
| `dart-reports-2026.csv` | 사업보고서 접수번호 | API 회사 수만큼 |
| `dart-financials-2026.csv` | 상장사 매출·직원수 (롱리스트 규모 필터) | API 7,000 회 · 하루치 한도의 1/3 |

`universe-2026.csv` · `instances-2026.csv` 는 판정 **결과**라 다른 스크립트가 만든다.
이쪽은 판정 이전의 **원천 데이터**다 — 판정 규칙을 고쳐도 다시 받을 필요가 없다.
"""
from __future__ import annotations
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
CACHE = os.path.join(HERE, '.cache')


def _load(name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding='utf-8'))


def _write(path, cols, rows):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'  {len(rows):>6,}건 → {os.path.basename(path)} ({os.path.getsize(path)/1024:.0f}KB)')


def dump_corp() -> int:
    """상장·비상장 공시법인의 업종코드·법인등록번호를 한 파일로"""
    out = []
    for name, kind in [('listed.json', '상장'), ('unlisted.json', '비상장')]:
        d = _load(name) or []
        for r in d:
            if r.get('error'):
                continue
            out.append({'구분': kind, '고유번호': r.get('corp_code'),
                        '종목코드': r.get('stock', ''), '회사명': r.get('name'),
                        'induty_code': r.get('induty'), '법인등록번호': r.get('jurir')})
    out.sort(key=lambda r: (r['구분'] != '상장', r['회사명'] or ''))
    _write(os.path.join(SAMPLES, 'dart-corp-2026.csv'),
           ['구분', '고유번호', '종목코드', '회사명', 'induty_code', '법인등록번호'], out)
    return len(out)


def dump_segments() -> int:
    """부문 수집 결과 — 한 행이 한 부문이다"""
    d = _load('segments.json') or []
    out = []
    for r in d:
        base = {'회사명': r['회사명'], '종목코드': r['종목코드'],
                '법인등록번호': r['법인등록번호'], 'KSIC': r['KSIC'],
                '묶음노드': r['묶음노드'], '보고서': r.get('보고서', '')}
        if not r['segments']:
            out.append({**base, '부문명': '', '주요제품': '', '매출': '',
                        '수익행': '', '상태': '단일부문' if r.get('단일부문')
                        else (r.get('error') or '부문없음')})
            continue
        for s in r['segments']:
            out.append({**base, '부문명': s['명칭'], '주요제품': s.get('주요제품') or '',
                        '부문설명': s.get('부문설명') or '',
                        '매출': s.get('매출') if s.get('매출') is not None else '',
                        '수익행': s.get('수익행') or '', '상태': '부문'})
    _write(os.path.join(SAMPLES, 'segments-2026.csv'),
           ['회사명', '종목코드', '법인등록번호', 'KSIC', '묶음노드', '보고서',
            '부문명', '주요제품', '부문설명', '매출', '수익행', '상태'], out)
    return len(out)


def dump_reports() -> int:
    """사업보고서 접수번호 — 이게 있으면 ZIP 을 바로 받을 수 있다"""
    d = _load('reports.json') or {}
    out = []
    for k, v in d.items():
        cc = k.split(':')[0]
        out.append({'고유번호': cc,
                    '접수번호': (v or {}).get('rcept_no', ''),
                    '보고서명': (v or {}).get('report_nm', ''),
                    '회사명': (v or {}).get('corp_name', '')})
    out.sort(key=lambda r: r['고유번호'])
    _write(os.path.join(SAMPLES, 'dart-reports-2026.csv'),
           ['고유번호', '접수번호', '보고서명', '회사명'], out)
    return len(out)


def dump_financials() -> int:
    """상장사 매출·직원수 — 롱리스트 규모 필터의 근거. API 7,000 회짜리다"""
    d = _load('financials.json') or []
    out = [{'법인등록번호': r['법인등록번호'], '회사명': r['회사명'], '고유번호': r['고유번호'],
            '매출액_백만원': r['매출액'] if r.get('매출액') is not None else '',
            '매출근거': r.get('매출근거', ''),
            '종업원수': r['종업원수'] if r.get('종업원수') is not None else '',
            '종업원근거': r.get('종업원근거', ''),
            '사업보고서': r.get('사업보고서', ''), '오류': r.get('error') or ''} for r in d]
    out.sort(key=lambda r: r['회사명'] or '')
    _write(os.path.join(SAMPLES, 'dart-financials-2026.csv'),
           ['법인등록번호', '회사명', '고유번호', '매출액_백만원', '매출근거',
            '종업원수', '종업원근거', '사업보고서', '오류'], out)
    return len(out)


def dump_cached() -> int:
    """
    받아둔 공시 원문 목록.

    `reports.json` 은 캐시를 뒤늦게 붙였으므로 아직 비어 있다. 그런데 ZIP 파일명이
    곧 접수번호이므로, 그 목록만 남겨도 **무엇을 확보했는지**는 기록된다 —
    접수번호가 있으면 `document.xml` 을 바로 받을 수 있다.
    """
    import glob
    rows = []
    for q in glob.glob(os.path.join(CACHE, '*.zip')):
        rows.append({'접수번호': os.path.basename(q)[:-4],
                     '크기MB': round(os.path.getsize(q) / 1048576, 1)})
    rows.sort(key=lambda r: r['접수번호'])
    _write(os.path.join(SAMPLES, 'dart-cached-reports.csv'), ['접수번호', '크기MB'], rows)
    return len(rows)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print('수집 데이터를 samples/ 로 내보낸다')
    dump_corp()
    dump_segments()
    dump_reports()
    dump_financials()
    dump_cached()
    print('\n원천 ZIP 은 .cache/ 에 남긴다 — 248MB 라 저장소에 넣지 않는다.')
    print('접수번호가 위 CSV 에 있으므로 필요할 때 다시 받을 수 있다.')
