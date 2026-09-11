# -*- coding: utf-8 -*-
"""
출자 관계로 지배 사업 영역을 채운다 — 그리고 손자회사 연결고리를 잇는다
=======================================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**두 가지를 한다.**

1. **손자회사 연결고리** (`samples/ownership-edges-2026.csv` · 인스턴스의 `지배법인` 열)
   공정위 「기업집단명」은 「삼성 소속」만 알려 주고 누가 누구를 지배하는지는 모른다.
   출자현황은 상장 모회사가 **비상장 자회사·손자회사 지분을 다 적으므로** 그 엣지가
   모수 안에서 이어지면 지배 사슬이 드러난다.

2. **묶음(지주회사)의 B축** (D-12 · D-39 미이행분)
   묶음 1,711 건의 B축이 전부 「다품목·범용」이었다 — HD한국조선해양은 조선,
   한국앤컴퍼니는 타이어를 지배하는데 구분이 없었다. 출자 대상들의 업종을 모아 채운다.

설계 결정
---------
- **지배 임계 30%.** 50% 로 자르면 중간지주를 놓친다 — 일진홀딩스→일진전기가 49.3%,
  일진다이아몬드가 50.1% 다. 20% 는 단순 지분법 관계까지 들어온다.
- **펀드·조합·리츠·유동화는 배제.** 「골든오크 오퍼튜니티 펀드」·「SKS위즈도메인
  제1호 투자조합」은 출자 목록의 다수를 차지하지만 지배 사업 영역이 아니다.
- **한 영역이 절반을 넘을 때만 붙인다.** 그러지 않으면 「다품목·범용」이 맞다 —
  진짜 여러 사업을 지배하는 묶음(삼성물산·SK)에 억지로 하나를 붙이지 않는다.
- **근거가 얇으면 판정하지 않는다.** 잡힌 자회사 매출 합이 1,000 억 미만이면 비운다.
  SK(주)는 주력을 해외법인과 중간지주로 지배해 모수 안에서는 애커튼테크놀로지
  (393 억)·휘찬(22 억)만 잡혔다 — 그 셋으로 「전자·정밀」이라 단정할 수 없다.
- **매출 가중.** 건수로 세면 소액 출자 여러 건이 주력을 이기고, **장부가액으로 세면
  실질이 뒤집힌다**(`_wt` 주석 참조). 매출이 없으면 장부가액, 그것도 없으면 1 로 둔다.
- **최대주주(`hyslrSttus`)는 쓰지 않는다.** 관계 분포가 「특수관계인·친인척·임원·
  본인」이라 개인 오너 일가 정보였다. 법인 지배 구조에는 쓸모가 없다 — 받아 두되
  판정에 넣지 않는다.

한계 셋
-------
1. **출자현황은 상장사만 낸다.** 비상장 지주 1,647 건의 지배 영역은 알 수 없다.
2. **해외법인은 모수 밖이다.** SK(주)의 상위 출자 대부분이 Golden Pearl EV·
   Einstein Cayman 같은 해외법인이라 국내 모수에서 이어지지 않는다.
3. **중간지주를 통한 지배는 한 단계 끊긴다.** 사슬 자체는 엣지 CSV 에 남으므로
   따라갈 수 있지만, 묶음 B 축 판정에서는 「다품목·범용」 자회사를 세지 않는다.

    python apply_ownership.py       # apply_segments 다음, dump_datasets 앞

출처: DART `otrCprInvstmntSttus`(타법인 출자현황) 2025 사업보고서.
"""
from __future__ import annotations
import collections
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache')
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')

sys.path.insert(0, HERE)
import taxonomy_io as tx      # noqa: E402

지배임계 = 30.0
우세임계 = 0.5
# 잡힌 자회사들의 매출 합이 이보다 작으면 판정하지 않는다 (백만원 = 1,000 억)
근거임계 = 100_000

# 펀드·조합·리츠·유동화 — 지분이 높아도 사업을 지배하는 관계가 아니다
_투자기구 = re.compile(
    r'펀드|투자조합|사모투자|투자신탁|수익증권|리츠|부동산투자회사|유동화|특수목적|'
    r'제\d+호|파트너십|Fund|Trust|Partners L\.?P', re.I)
# 이름 정규화에서 떼는 법인 형태 표기
_형태 = re.compile(r'\((주|유|재|사|합|주식회사)\)|㈜|주식회사|유한회사|합자회사|유한책임회사')
# **각주가 이름에 붙어 온다** — 「코오롱베니트(주1)」·「OCI 스페셜티(주)(*3)」·
# 「코오롱글로벌 보통주 (주1)」·「코오롱모빌리티그룹 보통주 (주1),(주7)」.
# 이걸 안 떼면 코오롱글로벌(건설)·코오롱제약·코오롱모빌리티가 전부 「모수밖」으로
# 빠지고 주변부 자회사만 남아 「전문서비스」 같은 엉뚱한 답이 나온다.
# `(주)` 는 법인 표기이고 `(주1)` 은 각주다 — **숫자가 붙었는지로 가른다.**
_각주 = re.compile(r'\(\s*(?:주|\*|note|참고)\s*\d+\s*\)|\(\s*\*+\s*\d*\s*\)|\(\s*\d+\s*\)')
_주식종류 = re.compile(r'보통주|우선주|종류주|전환우선주|상환전환우선주')


def norm(s: str) -> str:
    """DART 원문에는 줄바꿈이 들어 있다 — 「미래에셋콘텐츠판다\niMBC콘텐츠투자조합」"""
    s = (s or '').replace('\n', '').replace('\r', '')
    s = _주식종류.sub('', _각주.sub('', s))
    return re.sub(r'[\s.,\-·\'"]', '', _형태.sub('', s)).lower()


def _num(v) -> float:
    try:
        return float(str(v or 0).replace(',', ''))
    except ValueError:
        return 0.0


def _wt(e: dict) -> float:
    """
    자회사의 크기 — **매출이 실질이다.**

    장부가액으로 재면 뒤집힌다. 세아제강지주에서 세아스틸인터내셔날(장부 3,658억·
    매출 317억·전문서비스)이 세아제강(장부 829억·**매출 13,721억**·금속)을 이겨
    「전문서비스」가 나왔다. 장부가액은 취득원가라 오래 보유한 주력을 과소평가한다.
    """
    return max(_num(e.get('대상매출')) or _num(e.get('장부가액')) / 1e6, 1.0)


def main() -> None:
    # ★ [P4] 캐시 JSON·CSV 가 아니라 DB 에서. 같은 작업 스냅샷을 읽고 거기에 쓴다 —
    #   `apply_segments` 가 방금 넣은 인스턴스에 「지배법인」을 채우는 단계다.
    own = tx.load_ownership_nested()
    inst = tx.load('instances')
    uni = tx.load('universe')

    # 모수 이름 색인. **이름이 겹치면 아예 빼 둔다** — 출자현황 API 는 법인등록번호를
    # 주지 않아 이름으로만 이을 수 있는데, 동명이인이면 어느 쪽인지 가릴 방법이 없다.
    # 제련 「(주)지알엠」(LS)과 부동산 「지알엠(주)」가 합쳐져 서울도시가스가 제련사를
    # 지배하는 것처럼 보였다. 엣지의 1.2%(26 건)를 잃고 나머지의 신뢰를 얻는다 (D-47)
    _cnt: collections.Counter = collections.Counter(norm(r['회사명']) for r in uni
                                                    if r['모수계층'] != '모수밖')
    U: dict[str, dict] = {}
    for r in uni:
        k = norm(r['회사명'])
        if _cnt[k] > 1:
            continue
        U.setdefault(k, r)

    # ── 1. 지배 엣지
    edges, skipped = [], collections.Counter()
    for r in own:
        src = r['회사명']
        for x in r.get('출자') or []:
            nm = (x.get('출자대상') or '').replace('\n', ' ').strip()
            if not nm:
                continue
            if _투자기구.search(nm):
                skipped['투자기구'] += 1
                continue
            rt = x.get('지분율')
            u = U.get(norm(nm))
            if not u:
                skipped['모수밖'] += 1
                continue
            if rt is None or rt < 지배임계:
                skipped['지분율미달'] += 1
                continue
            edges.append({
                '지배법인': src, '지배법인등록번호': r['법인등록번호'],
                '대상': u['회사명'], '대상법인등록번호': u['법인등록번호'],
                '지분율': rt, '장부가액': x.get('장부가액') or '',
                '대상계층': u['모수계층'], '대상소속그룹': u.get('소속그룹', ''),
                '대상A세분류': u['A세분류'], '대상B1주업종': u['B1주업종'],
                '대상매출': u['매출액'], '대상묶음': u['묶음노드'],
                '연도': r.get('출자연도', ''),
            })
    edges.sort(key=lambda e: (e['지배법인'], -e['지분율']))
    tx.save('ownership_edges', edges, stage='apply_ownership')
    print(f'  걸러낸 것 — {dict(skipped)}')

    # ── 2. 묶음 B축 = 지배 사업 영역
    #    **「다품목·범용」 자회사도 센다.** 빼면 두 번째로 큰 사업이 대표가 되어
    #    실질과 어긋났다 — 롯데지주는 롯데쇼핑 8.2 조·코리아세븐 4.8 조가 빠져
    #    롯데웰푸드 3.3 조로 「식품·음료」가, 현대지에프홀딩스는 현대그린푸드 2.3 조가
    #    빠져 현대리바트 1.5 조로 「생활용품·가구」가 됐다. 모르는 덩어리가 가장 클 때는
    #    **판정을 포기한다** — 억지로 채우지 않는 것이 이 설계의 원칙이다.
    #    중간지주(묶음)만 제외한다. 사슬 자체는 엣지 CSV 에 남아 따라갈 수 있다.
    by_src: dict[str, list[dict]] = collections.defaultdict(list)
    for e in edges:
        if e['대상묶음'] != 'Y' and e['대상B1주업종']:
            by_src[norm(e['지배법인'])].append(e)

    filled = collections.Counter()
    changed = []
    for r in inst:
        if r.get('단위') != '묶음':
            continue
        kids = by_src.get(norm(r['이름']))
        if not kids:
            filled['출자정보없음'] += 1
            continue
        w: dict[str, float] = collections.Counter()
        for e in kids:
            w[e['대상B1주업종']] += _wt(e)
        tot = sum(w.values())
        if tot < 근거임계:
            filled['근거부족'] += 1
            continue
        top, tw = w.most_common(1)[0]
        if top == '다품목·범용':
            filled['지배영역혼재'] += 1
            continue
        if tw / tot < 우세임계:
            filled['우세업종없음'] += 1
            continue
        # 2 단도 함께 — 그 업종 안에서 같은 방식으로 우세한 것만
        w2: dict[str, float] = collections.Counter()
        for e in kids:
            if e['대상B1주업종'] != top:
                continue
            k = next((k['B1_2단'] for k in inst
                      if k['이름'] == e['대상'] and k.get('단위') == '법인'), '')
            if k:
                w2[k] += _wt(e)
        two = ''
        if w2:
            t2, t2w = w2.most_common(1)[0]
            if t2w / sum(w2.values()) >= 우세임계:
                two = t2
        before = r['B1주업종']
        r['B1주업종'], r['B1_2단'] = top, two
        r['판정근거'] = (f'묶음 — 지배 사업 영역(출자 {len(kids)}건 중 {tw/tot*100:.0f}% {top})'
                     f' · 매출은 자회사와 겹쳐 집계에서 뺀다')
        filled['채움'] += 1
        changed.append((r['이름'], before, top, two, len(kids), tw / tot))

    # ── 3. 각 법인에 「나를 지배하는 법인」을 붙인다 — 롱리스트에서 사슬이 보인다.
    #    공정위 소속그룹은 「삼성 소속」만 알려 준다. 이 열이 있으면 삼성전자 →
    #    삼성디스플레이 → 그 자회사까지 누가 누구를 지배하는지 읽힌다.
    parent: dict[str, tuple[str, float]] = {}
    for e in edges:
        k = norm(e['대상'])
        if k not in parent or e['지분율'] > parent[k][1]:
            parent[k] = (e['지배법인'], e['지분율'])
    linked = 0
    for r in inst:
        p = parent.get(norm(r['이름'])) if r.get('단위') != '세그먼트' else None
        r['지배법인'] = f'{p[0]} {p[1]:g}%' if p else ''
        linked += 1 if p else 0
    print(f'\n인스턴스에 지배법인 표시 {linked}건')

    # ★ [P4] 예전에는 캐시 json 과 CSV 두 곳에 썼고, **한쪽만 고치면 어긋났다.**
    #   이제 쓰는 곳이 하나다 — 같은 스냅샷의 `instances` 를 지배법인까지 채워 덮는다.
    tx.save('instances', inst, stage='apply_ownership')
    print(f'\n묶음 {sum(filled.values())}건 — {dict(filled)}')
    print('\n=== 지배 사업 영역이 정해진 묶음 (지분 큰 순 30) ===')
    for nm, b4, top, two, n, share in sorted(changed, key=lambda x: -x[4])[:30]:
        print(f'  {nm[:22]:<24} {b4} → {top}{("›" + two) if two else ""}  (자회사 {n} · {share*100:.0f}%)')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
