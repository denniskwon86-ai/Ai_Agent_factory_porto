# -*- coding: utf-8 -*-
"""
수집물을 DB 원천 표에 올린다 — 수집 뒤에 한 번
================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

    python sync_sources.py            # .cache/*.json → DB 원천 표
    python sync_sources.py --status   # 지금 DB 에 무엇이 얼마나 있나

## 무엇이 바뀌었나 — 예전 `dump_datasets.py`

이 파일은 **캐시 JSON 을 `samples/*.csv` 로 내보내는** 일을 했다. 이유는
`.cache/` 가 `.gitignore` 라 그 환경에서만 쓸 수 있었기 때문이다.

이제 그 자리를 **DB 가 받는다.** 수집물은 `src_*` 표에 올라가고, 사람이 볼 CSV 는
`export_snapshot.py` 가 낸다. 판정 스크립트는 캐시를 보지 않고 DB 만 본다 —
그래서 `.cache/` 가 없는 환경에서도 재판정이 된다.

| | 예전 | 지금 |
|---|---|---|
| 수집물의 집 | `.cache/*.json` (그 기계에만) | `src_*` 표 |
| 사람이 보는 것 | `samples/*.csv` (파이프라인이 덮어씀) | `samples/sources/*.csv` (DB 사본) |
| 판정의 입력 | CSV 와 캐시가 섞여 있었다 | **DB 하나** |

## 재수집이 원천을 바꾸면

스냅샷에 **원천 지문**이 박혀 있으므로, 다음 판정을 뜨면 지문이 달라진 것이 보인다.
얼어 있는 스냅샷은 그대로 남는다 — 「그때는 이 수집물이었다」가 증거로 남는다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache')
sys.path.insert(0, HERE)

import taxonomy_db as T  # noqa: E402


def _load(name: str):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding='utf-8'))


def sync_corp(db: T.TaxonomyDB) -> int:
    """상장·비상장 공시법인. ⚠️ `error` 행은 넣지 않는다 — 업종코드가 없어
    판정에 쓸 수 없고, 넣으면 원천 행 수가 「받은 것」과 「쓸 수 있는 것」 사이에서
    흔들린다."""
    out = []
    for name, kind in [('listed.json', '상장'), ('unlisted.json', '비상장')]:
        for r in _load(name) or []:
            if r.get('error'):
                continue
            out.append({'구분': kind, '고유번호': r.get('corp_code'),
                        '종목코드': r.get('stock', ''), '회사명': r.get('name'),
                        'induty_code': r.get('induty'), '법인등록번호': r.get('jurir')})
    out.sort(key=lambda r: (r['구분'] != '상장', r['회사명'] or ''))
    return db.put_source('src_corp', out) if out else 0


def sync_financials(db: T.TaxonomyDB) -> int:
    d = _load('financials.json')
    if not d:
        return 0
    out = [{'법인등록번호': r['법인등록번호'], '회사명': r['회사명'], '고유번호': r['고유번호'],
            '매출액_백만원': r['매출액'] if r.get('매출액') is not None else '',
            '매출근거': r.get('매출근거', ''),
            '종업원수': r['종업원수'] if r.get('종업원수') is not None else '',
            '종업원근거': r.get('종업원근거', ''),
            '사업보고서': r.get('사업보고서', ''), '오류': r.get('error') or ''} for r in d]
    out.sort(key=lambda r: r['회사명'] or '')
    return db.put_source('src_financials', out)


def sync_reports(db: T.TaxonomyDB) -> int:
    d = _load('reports.json')
    if not d:
        return 0
    out = [{'고유번호': k.split(':')[0], '접수번호': (v or {}).get('rcept_no', ''),
            '보고서명': (v or {}).get('report_nm', ''),
            '회사명': (v or {}).get('corp_name', '')} for k, v in d.items()]
    out.sort(key=lambda r: r['고유번호'])
    return db.put_source('src_reports', out)


def sync_segments(db: T.TaxonomyDB) -> int:
    """한 행이 한 부문. 부문을 못 찾은 회사도 **한 행 남긴다** — 「확인했는데 없었다」와
    「확인하지 않았다」는 다르다."""
    d = _load('segments.json')
    if not d:
        return 0
    out = []
    for r in d:
        base = {'회사명': r['회사명'], '종목코드': r['종목코드'],
                '법인등록번호': r['법인등록번호'], 'KSIC': r['KSIC'],
                '묶음노드': r['묶음노드'], '보고서': r.get('보고서', '')}
        if not r['segments']:
            out.append({**base, '부문명': '', '주요제품': '', '부문설명': '', '매출': '',
                        '수익행': '', '상태': '단일부문' if r.get('단일부문')
                        else (r.get('error') or '부문없음')})
            continue
        for s in r['segments']:
            out.append({**base, '부문명': s['명칭'], '주요제품': s.get('주요제품') or '',
                        '부문설명': s.get('부문설명') or '',
                        '매출': s.get('매출') if s.get('매출') is not None else '',
                        '수익행': s.get('수익행') or '', '상태': '부문'})
    return db.put_source('src_segments', out)


def sync_ownership(db: T.TaxonomyDB) -> dict:
    """최대주주·타법인출자를 세 표로 정규화한다.

    ⚠️ 최대주주가 개인이면 수집 단계(`fetch_ownership._mask`)에서 이미 「개인」으로
      바뀌어 있다. 여기서 이름을 되살리지 않는다.
    """
    d = _load('ownership.json')
    if not d:
        return {}
    head, hold, inv = [], [], []
    for r in d:
        cc = r.get('고유번호', '')
        head.append({'고유번호': cc, '법인등록번호': r.get('법인등록번호', ''),
                     '회사명': r.get('회사명', ''),
                     '최대주주연도': r.get('최대주주연도', ''),
                     '출자연도': r.get('출자연도', ''), '오류': r.get('error') or ''})
        for i, h in enumerate(r.get('최대주주') or []):
            hold.append({'고유번호': cc, '순번': i, '주주': h.get('주주', ''),
                         '관계': h.get('관계', ''), '지분율': h.get('지분율', '')})
        for i, v in enumerate(r.get('출자') or []):
            inv.append({'고유번호': cc, '순번': i, '출자대상': v.get('출자대상', ''),
                        '지분율': v.get('지분율', ''), '장부가액': v.get('장부가액', '')})
    return {'src_ownership': db.put_source('src_ownership', head),
            'src_ownership_holder': db.put_source('src_ownership_holder', hold),
            'src_ownership_invest': db.put_source('src_ownership_invest', inv)}


def sync_ftc(db: T.TaxonomyDB, path: str = '') -> int:
    """공정위 명단. `fetch_ftc.py` 는 CSV 로 내놓으므로 파일에서 받는다.

    ★ **원천 8 열만 넣는다.** 판정 열(`A세분류`·`B1주업종`…)은 `reclassify.py` 가
      스냅샷별 `ftc_classified` 로 낸다 — 재판정이 원천을 덮는 일이 없어야 한다.
    """
    p = path or os.path.join(T.SAMPLES, 'sources', 'src_ftc.csv')
    if not os.path.exists(p):
        return 0
    cols = T.SOURCES['src_ftc'].cols
    return db.put_source('src_ftc', [{c: r.get(c, '') for c in cols}
                                     for r in T.read_csv(p)])


ALL = [('src_corp', sync_corp), ('src_financials', sync_financials),
       ('src_reports', sync_reports), ('src_segments', sync_segments)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=T.DB_PATH)
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--ftc', default='', help='공정위 CSV 경로 (fetch_ftc.py 산출물)')
    a = ap.parse_args()
    db = T.TaxonomyDB(a.db)

    if a.status:
        print('원천 (수집물 — 스냅샷을 타지 않는다)')
        for n, t in sorted(T.SOURCES.items()):
            print('  %-24s %7d 행   %s' % (n, db.count(n), t.note))
        print('\n스냅샷')
        for s in db.snapshots():
            print('  %-14s %-19s %-4s %s' % (s['snapshot_id'], s['created_at'],
                                             '동결' if s['frozen'] else '작업', s['label']))
        return 0

    print('수집물을 DB 원천 표로 올린다 — .cache/*.json')
    total = 0
    for name, fn in ALL:
        n = fn(db)
        total += n
        print('  · %-24s %7d 행 %s' % (name, n, '' if n else '(캐시 없음 — 건너뜀)'))
    for k, v in sorted(sync_ownership(db).items()):
        total += v
        print('  · %-24s %7d 행' % (k, v))
    n = sync_ftc(db, a.ftc)
    total += n
    print('  · %-24s %7d 행 %s' % ('src_ftc', n, '(원천 8 열만)' if n else '(없음)'))

    print('\n원천 지문')
    for k, v in sorted(db.source_fingerprint().items()):
        print('  %-24s %s' % (k, v))
    print('\n✓ %d 행. 다음: reclassify → build_universe → apply_segments → apply_ownership'
          % total)
    print('  사람이 볼 CSV 는 export_snapshot.py 가 냅니다.')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
