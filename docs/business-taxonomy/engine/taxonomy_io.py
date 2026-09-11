# -*- coding: utf-8 -*-
"""[P4-T4] 파이프라인의 입출력 — 이제 CSV 가 아니라 DB 다.

## 스크립트는 이것만 부른다

    import taxonomy_io as tx
    uni  = tx.load('universe')        # 작업 스냅샷에서 읽는다
    tx.save('instances', rows)        # 작업 스냅샷에 쓴다 (얼었으면 거부)

경로도, 인코딩도, 스냅샷 이름도 스크립트가 알 필요가 없다. **여섯 개 스크립트가
제각각 `os.path.join(SAMP, '...csv')` 를 적고 있던 것**이 문제의 절반이었다.

## 작업 스냅샷은 무엇인가

**얼지 않은 최신 스냅샷.** 없으면 새로 뜬다. 그래서

- 파이프라인을 처음 돌리면 → 새 스냅샷이 생기고 직전 결과를 상속받는다
- 이어서 다른 단계를 돌리면 → **같은 스냅샷**에 쌓인다
- 사람이 `freeze` 하면 → 다음 실행은 또 새 스냅샷을 뜬다

확정한 판본을 다시 돌려도 덮이지 않는다. 그것이 이 전환의 목적이다.

## 왜 캐시 JSON 을 안 쓰는가

`.cache/segments.json` 은 `.gitignore` 라 그 환경에서만 있다. DB 의
`src_segments` 에서 같은 모양으로 되살리면 **캐시 없이도 재판정이 된다.**
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taxonomy_db as T  # noqa: E402

_DB: Optional[T.TaxonomyDB] = None
_WORKING: Optional[str] = None

#: 환경변수로 스냅샷을 고정할 수 있다 — 재현 실행에 쓴다.
ENV_SNAPSHOT = 'TAXONOMY_SNAPSHOT'


def db() -> T.TaxonomyDB:
    global _DB
    if _DB is None:
        _DB = T.TaxonomyDB(os.environ.get('TAXONOMY_DB') or T.DB_PATH)
    return _DB


def working(create: bool = True, *, label: str = '') -> str:
    """작업 스냅샷. **얼지 않은 최신**이 있으면 그것, 없으면 새로 뜬다."""
    global _WORKING
    if _WORKING:
        return _WORKING
    forced = os.environ.get(ENV_SNAPSHOT)
    if forced:
        if not db().snapshot(forced):
            raise KeyError('%s 로 지정한 스냅샷이 없습니다: %s' % (ENV_SNAPSHOT, forced))
        _WORKING = forced
        return _WORKING
    sid = db().latest()
    if sid and not db().is_frozen(sid):
        _WORKING = sid
        return sid
    if not create:
        raise RuntimeError(
            '쓸 수 있는 스냅샷이 없습니다 — 최신 %s 는 동결돼 있습니다.' % sid)
    _WORKING = db().snapshot_new(label=label or '파이프라인 실행',
                                 note='이전 스냅샷 %s 를 상속' % (sid or '(없음)'))
    print('[스냅샷] 새로 떴습니다: %s  ← %s' % (_WORKING, sid or '(처음)'))
    return _WORKING


def read_snapshot() -> str:
    """읽기 기준. 작업 스냅샷이 있으면 그것, 아니면 최신 — **새로 뜨지 않는다.**"""
    return _WORKING or os.environ.get(ENV_SNAPSHOT) or db().latest() or ''


def load(table: str, sid: Optional[str] = None) -> List[Dict[str, Any]]:
    t = T.TABLES[table]
    if not t.scoped:
        return db().rows(table)
    return db().rows(table, sid or read_snapshot())


def save(table: str, rows: Sequence[Dict[str, Any]], *, stage: str = '') -> int:
    """작업 스냅샷에 쓴다. **얼어 있으면 예외가 난다** — 그게 목적이다."""
    sid = working()
    n = db().put_result(sid, table, rows)
    db().mark_stage(sid, stage or table)
    print('[DB] %s ← %d 행  (스냅샷 %s)' % (table, n, sid))
    return n


def save_source(table: str, rows: Sequence[Dict[str, Any]], *, replace: bool = True) -> int:
    n = db().put_source(table, rows, replace=replace)
    print('[DB] %s ← %d 행  (원천)' % (table, n))
    return n


# ── 중첩 구조 복원 — `.cache/segments.json` 을 대신한다

def _num(v: Any) -> Any:
    """CSV 를 거치며 문자열이 된 숫자를 되돌린다 — 부문 매출은 정수였다.

    ⚠️ **빈 값은 `''` 가 아니라 `None` 이다.** 원천 JSON 에서 숫자 필드의 빈 값은
      전부 `None` 이었고(매출 77 · 장부가액 7,185 · 지분율 5,995), `''` 로 되돌리면
      `None` 을 전제한 비교가 달라진다. 문자 필드는 반대로 `''` 가 맞다.
    """
    if not isinstance(v, str):
        return v
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def load_segments_nested() -> List[Dict[str, Any]]:
    """`src_segments` 를 회사 단위로 되묶는다 — `segments.json` 과 같은 모양.

    한 회사가 여러 행으로 펼쳐져 있고, `상태 == '부문'` 인 행만 실제 부문이다.
    나머지(`부문없음`·`단일부문`·`사업보고서 없음`·`주석 못찾음`)는 **그 회사를
    확인했다는 기록**이라 회사 항목은 만들되 부문은 넣지 않는다.
    """
    out: Dict[Any, Dict[str, Any]] = {}
    for r in db().rows('src_segments'):
        k = r['법인등록번호'] or ('@' + r['회사명'])
        e = out.get(k)
        if e is None:
            e = out[k] = {'회사명': r['회사명'], '종목코드': r['종목코드'],
                          '법인등록번호': r['법인등록번호'], 'KSIC': r['KSIC'],
                          '묶음노드': r['묶음노드'], '보고서': r['보고서'],
                          '상태': r['상태'], 'segments': []}
        if r['보고서'] and not e['보고서']:
            e['보고서'] = r['보고서']
        if r['상태'] == '부문' and r['부문명']:
            e['segments'].append({'명칭': r['부문명'], '주요제품': r['주요제품'],
                                  '매출': _num(r['매출']), '수익행': r['수익행'],
                                  '부문설명': r['부문설명']})
    return list(out.values())


def load_corp(unlisted: bool = False) -> List[Dict[str, Any]]:
    """`src_corp` 을 `listed.json` / `unlisted.json` 모양으로.

    ⚠️ 수집 캐시에는 `error` 행이 있었지만 DB 에는 들어오지 않는다 — `dump_corp`
      가 걸렀기 때문이다. 읽는 쪽이 `if r.get('error'): continue` 하므로 결과는 같다.
    """
    kind = '비상장' if unlisted else '상장'
    return [{'stock': r['종목코드'], 'corp_code': r['고유번호'], 'name': r['회사명'],
             'induty': r['induty_code'], 'jurir': r['법인등록번호']}
            for r in db().rows('src_corp') if r['구분'] == kind]


def load_financials() -> List[Dict[str, Any]]:
    """`src_financials` 를 `financials.json` 모양으로. 열 이름이 다르다 —
    저장은 `매출액_백만원`, 읽는 쪽은 `매출액` 이다."""
    return [{'법인등록번호': r['법인등록번호'], '회사명': r['회사명'],
             '고유번호': r['고유번호'], '매출액': _num(r['매출액_백만원']),
             '매출근거': r['매출근거'], '종업원수': _num(r['종업원수']),
             '종업원근거': r['종업원근거'], '사업보고서': r['사업보고서'],
             'error': r['오류'] or None}
            for r in db().rows('src_financials')]


def load_ownership_nested() -> List[Dict[str, Any]]:
    """`src_ownership*` 세 표를 `ownership.json` 모양으로 되묶는다."""
    head = {r['고유번호']: {'법인등록번호': r['법인등록번호'], '회사명': r['회사명'],
                         '고유번호': r['고유번호'], '최대주주': [], '출자': [],
                         '최대주주연도': r['최대주주연도'], '출자연도': r['출자연도'],
                         'error': r['오류'] or None}
            for r in db().rows('src_ownership')}
    for r in db().rows('src_ownership_holder'):
        h = head.get(r['고유번호'])
        if h is not None:
            h['최대주주'].append({'주주': r['주주'], '관계': r['관계'],
                                '지분율': _num(r['지분율'])})
    for r in db().rows('src_ownership_invest'):
        h = head.get(r['고유번호'])
        if h is not None:
            h['출자'].append({'출자대상': r['출자대상'], '지분율': _num(r['지분율']),
                            '장부가액': _num(r['장부가액'])})
    return list(head.values())


# ── 사람이 쓰는 것

def summary() -> str:
    d = db()
    sid = read_snapshot()
    s = d.snapshot(sid) or {}
    return '스냅샷 %s (%s) | universe %d · instances %d' % (
        sid or '(없음)', '동결' if s.get('frozen') else '작업 중',
        d.count('universe', sid), d.count('instances', sid))


if __name__ == '__main__':
    print(summary())
    for s in db().snapshots():
        print('  %-14s %s  %s  %s' % (s['snapshot_id'], s['created_at'],
                                      '동결' if s['frozen'] else '작업', s['label']))
