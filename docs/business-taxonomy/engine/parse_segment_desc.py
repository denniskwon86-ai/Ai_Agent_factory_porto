# -*- coding: utf-8 -*-
"""
부문 설명을 본문에서 찾는다 — 약어 부문의 실체
==============================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 부문명이 약어면 이름으로 판정할 수 없다. LG전자 「ES」가
「전력·중전기」로 잘못 들어가 있었다 — 실제로는 냉난방공조(HVAC, 매출 9.3 조)다.
지금까지는 `segment_rules.ABBREV` 에 손으로 22 개를 적어 왔는데, 회사가 조직을
개편하면(LG전자는 2024 년에 HS 에서 공조를 떼어 ES 를 신설했다) 그때마 틀린다.

**사업보고서 본문에 답이 있다.** 「사업의 내용」에 부문 정의 표가 있다.

    사업부문                          약어   주요 제품
    Home appliance Solution          HS    냉장고, 세탁기, 청소기 …
    Eco Solution                     ES    에어컨, HVAC 등
    Media entertainment Solution     MS    TV, 모니터, PC, 사이니지 등

부문 표(매출)에는 이 열이 없는 경우가 많다 — 수집한 801 개 부문 중 「주요제품」이
채워진 건 24% 뿐이다. 그래서 **본문의 다른 표**를 따로 찾는다.

찾는 방법 — **부문명이 가장 많이 나오는 표**를 고른다. 부문 정의 표는 부문 전체를
한 번씩 싣기 때문이다. 임원 명단에도 「ES사업본부장」이 나오지만 그 표에는 부문이
하나뿐이라 지지 않는다.

    python parse_segment_desc.py 20260313000662     # 접수번호로 시험
"""
from __future__ import annotations
import re
import sys

_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'\s+')


def _text(x: str) -> str:
    return _WS.sub(' ', _TAG.sub(' ', x)).strip()


def _tables(xml: str):
    """(행 목록) — 표마다. parse_segment 와 달리 단위·배수를 보지 않는다"""
    for m in re.finditer(r'<TABLE[^>]*>.*?</TABLE>', xml, re.S):
        rows = []
        for tr in re.findall(r'<TR[^>]*>(.*?)</TR>', m.group(0), re.S):
            cells = [_text(c) for c in re.findall(r'<T[DEHU][^>]*>(.*?)</T[DEHU]>', tr, re.S)]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2:
            yield rows


def _norm(s: str) -> str:
    return re.sub(r'[\s·ㆍ/()]', '', (s or '')).upper()


def descriptions(xml: str, seg_names: list[str]) -> dict[str, str]:
    """
    부문명 → 설명. 부문명이 가장 많이 맞는 표를 골라, 그 행의 **다른 칸**을 설명으로 쓴다.

    xml       : 사업보고서 본문(document.xml)
    seg_names : 이미 얻은 부문명 목록 (예: ['HS', 'MS', 'VS', 'ES', '이노텍'])
    """
    want = {_norm(n): n for n in seg_names if n}
    if not want:
        return {}

    best, best_hit = None, 0
    for rows in _tables(xml):
        hit = 0
        for r in rows:
            for c in r[:3]:                     # 부문명은 앞쪽 칸에 온다
                if _norm(c) in want:
                    hit += 1
                    break
        # **부문 수보다 많이 맞을 수는 없다.** 같으면 먼저 나온 표를 쓴다(정의 표가 앞에 있다)
        if hit > best_hit:
            best, best_hit = rows, hit
        if best_hit >= len(want):
            break
    if not best or best_hit < 2:                # 하나만 맞으면 우연이다
        return {}

    out: dict[str, str] = {}
    for r in best:
        idx = next((i for i, c in enumerate(r[:3]) if _norm(c) in want), None)
        if idx is None:
            continue
        nm = want[_norm(r[idx])]
        # 설명 = 그 행의 나머지 칸 중 숫자가 아닌 것. **한글이 든 칸을 먼저 쓴다** —
        # 정의 표는 「Eco Solution | ES | 에어컨, HVAC 등」처럼 약어의 영문 전체명을
        # 함께 싣는데, 그게 더 길어서 제품 설명을 이겼다(ES → 「Eco Solution」).
        # 판정에 쓸모 있는 건 제품 쪽이다
        # 괄호까지 넣어 뺀다 — 대신증권 「Retail」이 「(84,585,458)」을 설명으로 잡았다
        cand = [c for j, c in enumerate(r) if j != idx and len(c) > 3
                and not re.fullmatch(r'[\d,.\-%\s()△▲()]+', c)]
        if cand:
            ko = [c for c in cand if re.search(r'[가-힣]', c)]
            out.setdefault(nm, max(ko or cand, key=len)[:200])
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, '.')
    import fetch_dart as F
    import json
    import io
    import os

    import segment_rules as R
    rcept = sys.argv[1] if len(sys.argv) > 1 else '20260313000662'   # LG전자
    segs = json.load(io.open(os.path.join('.cache', 'segments.json'), encoding='utf-8'))
    import taxonomy_io as tx          # * [P4] CSV 가 아니라 DB 원천에서
    rep = {r['접수번호']: r['회사명'] for r in tx.load('src_reports')}
    # **두 파일의 회사명 표기가 다르다** — reports 는 「LG전자」, segments 는 「엘지전자(주)」.
    # `_norm_corp` 가 법인표기와 영문/한글 약칭을 맞춰 준다
    회사 = rep.get(rcept, '?')
    key = R._norm_corp(회사)
    names = next((([s['명칭'] for s in r['segments']]) for r in segs
                  if R._norm_corp(r['회사명']) == key), [])
    print(f'{회사} · 부문 {names}')
    d = descriptions(F.document_xml(rcept), names)
    for k, v in d.items():
        print(f'  {k:<14} → {v[:90]}')
    if not d:
        print('  (정의 표를 못 찾았다)')
