# -*- coding: utf-8 -*-
"""
공정거래위원회 기업집단포털 — 대규모기업집단 소속회사 수집기
==========================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

두 가지 경로를 지원한다.

A. **Open API** (권장) — 공공데이터포털에서 인증키를 발급받아 쓴다.
   https://www.data.go.kr/data/15091894/openapi.do  (소속회사 개요)
   https://www.data.go.kr/data/15091895/openapi.do  (소속회사 재무현황)
   환경변수 `FTC_API_KEY` 에 키를 넣고 실행한다.

B. **웹 엔드포인트** — 인증키 없이 포털이 쓰는 AJAX 엔드포인트를 직접 호출한다.
   POST /egps/ps/io/kap/selectAjaxPsitnCmpnySumryList.do
   `pageUnit` 을 크게 주면 한 번에 전체를 받는다(3,539건 확인).
   비공식 경로이므로 사이트 개편 시 깨질 수 있다.

수집 결과는 `classify()` 가 그대로 받을 수 있는 형태로 돌려준다.
"""
from __future__ import annotations
import os
import re
import csv
import io
import sys
import urllib.parse
import urllib.request

PORTAL = 'https://www.egroup.go.kr'
AJAX = '/egps/ps/io/kap/selectAjaxPsitnCmpnySumryList.do'

# 공정위 표에서 우리가 쓰는 열의 위치 (0-based)
COLS = {
    '공개년월': 0, '기업집단명': 1, '소속회사명': 2, '대표자': 3, '설립일': 4,
    '계열편입일': 5, 'KSIC': 6, '영위업종': 7, '종업원수': 8, '결산기일': 9,
    '결산주총일': 10, '기업공개일': 11, '자산총액': 12, '부채총액': 13,
    '자본총액': 14, '자본금': 15, '매출액': 16, '당기순이익': 17,
    '구분': 18, '법인등록번호': 19, '사업자등록번호': 20,
}


def fetch_web(group_id: str = 'ALL', ym: str = '202605', unit: int = 4000) -> list[dict]:
    """웹 AJAX 엔드포인트로 수집한다. group_id 는 포털의 기업집단 코드(예: 엘지=K1000051)."""
    body = urllib.parse.urlencode({
        'sch_unityGrupId': group_id, 'sch_unityGrupNm': '',
        'sch_entrprsId': '', 'sch_entrprsNm': '', 'sch_othbcYm': '',
        'sch_startYm': ym, 'sch_endYm': ym, 'sch_applYear': ym[:4],
        'pageUnit': str(unit), 'pageIndex': '1',
    }).encode()
    req = urllib.request.Request(
        PORTAL + AJAX, data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                 'X-Requested-With': 'XMLHttpRequest',
                 'User-Agent': 'Mozilla/5.0', 'Referer': PORTAL + '/'})
    with urllib.request.urlopen(req, timeout=120) as r:
        html = r.read().decode('utf-8', 'replace')
    return _parse_table(html)


def _parse_table(html: str) -> list[dict]:
    """HTML 표에서 행을 뽑는다. 의존성을 늘리지 않으려고 정규식으로 처리한다."""
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) <= 15:
            continue
        cells = [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip() for c in tds]
        rows.append({k: (cells[i] if i < len(cells) else '') for k, i in COLS.items()})
    return rows


def fetch_api(group_code: str, ym: str = '202605', key: str | None = None) -> list[dict]:
    """공공데이터포털 Open API 경로. 인증키가 있어야 한다."""
    key = key or os.environ.get('FTC_API_KEY')
    if not key:
        raise RuntimeError('FTC_API_KEY 가 없다. 공공데이터포털에서 인증키를 발급받아라.')
    base = 'https://apis.data.go.kr/1130000/MdrpsCmpnySumryService/getMdrpsCmpnySumry'
    qs = urllib.parse.urlencode({
        'serviceKey': key, 'pageNo': 1, 'numOfRows': 5000,
        'resultType': 'json', 'bsnsYm': ym, 'grupCd': group_code})
    with urllib.request.urlopen(f'{base}?{qs}', timeout=120) as r:
        import json
        data = json.loads(r.read().decode('utf-8'))
    # 응답 스키마는 포털 문서를 따른다. 키 이름이 바뀌면 여기만 고친다.
    items = (data.get('response', {}).get('body', {}).get('items') or [])
    return items


# ────────────────────────────────────────────── 유일화

def _jurir(v: str) -> str:
    return re.sub(r'\D', '', v or '')


def dedupe(rows: list[dict]) -> list[dict]:
    """
    법인등록번호로 유일화한다.

    **업무키트 대상 목록에 같은 회사가 두 번 나오면 안 된다.** 공동 소유 법인이
    두 집단에 모두 신고되기 때문이다 — 3,539 건에 18 건이 그렇다. 롯데지에스화학
    ·롯데에스케이에너루트·지에너지처럼 이름에 양쪽이 들어간 합작사다.
    **지분법상 양쪽 반영은 틀린 게 아니다.**

    다행히 **사업형태 판정은 어느 집단으로 보나 같다**(18 건 전부 동일). 같은
    법인이니 KSIC 도 같아서다. 그래서 분류에는 영향이 없고 목록 중복만 문제다.
    집단 소속은 버리지 않고 `기업집단명들` 에 모아 남긴다 — 그룹 단위로 볼 때 쓴다.

    지배 집단을 가려야 할 때의 기준은 README 의 「공동 소유 법인은 어디로
    귀속시키나」를 따른다.
    """
    out, seen = [], {}
    for r in rows:
        k = _jurir(r.get('법인등록번호')) or ('name:' + (r.get('소속회사명') or ''))
        if k in seen:
            prev = seen[k]
            g = r.get('기업집단명', '')
            if g and g not in prev['기업집단명들']:
                prev['기업집단명들'].append(g)
            continue
        rec = dict(r)
        rec['기업집단명들'] = [r.get('기업집단명', '')] if r.get('기업집단명') else []
        seen[k] = rec
        out.append(rec)
    return out


def to_csv(rows: list[dict], path: str) -> None:
    if not rows:
        print('수집된 행이 없다', file=sys.stderr)
        return
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'{len(rows)}건 → {path}')


if __name__ == '__main__':
    # 사용 예: python fetch_ftc.py ALL out.csv
    gid = sys.argv[1] if len(sys.argv) > 1 else 'ALL'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'ftc_affiliates.csv'
    got = fetch_web(gid)
    print(f'수집 {len(got)}건')

    # 판정까지 이어 붙인다
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ksic_rules import classify
    for r in got:
        r.update(classify(r['KSIC'], r['매출액'], r['소속회사명'], r['종업원수']))
    to_csv(got, dst)
