# -*- coding: utf-8 -*-
"""
수동 사전 관리 대장을 만든다
============================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 판정 규칙은 대부분 KSIC 로 검증되지만, 자료로 가를 수 없는 곳에는
**회사명 사전**을 뒀다(D-26 · D-31 · D-32 · D-33). 「검증 가능성」 원칙의 예외이므로
사람이 주기적으로 봐야 하는데, 사전이 세 파일에 흩어져 있어 무엇이 있는지 한눈에
보이지 않았다.

**손으로 적은 목록은 코드와 어긋난다.** 그래서 코드에서 뽑는다.

    python dump_dictionaries.py

내보내는 것

| 파일 | 무엇 |
|---|---|
| `samples/manual-dictionaries.csv` | 사전 항목 전체 — 실제 판정 결과·매출과 함께 |
| `MANUAL-DICTIONARIES.md` | 사람이 읽는 관리 대장 |

**언제 갱신해야 하나**

1. 회사가 사업을 바꿨을 때 — LG전자 ES 가 2024 년 조직개편으로 공조 본부가 됐는데
   사전에 「전력·중전기」로 남아 있었다(D-26 에서 발견)
2. 신규 상장·인수로 대상이 늘었을 때 — 목록은 상장사 위주다
3. 회사명이 바뀌었을 때 — 사전은 이름으로 찾는다

**미검출은 손해가 작고 오탐은 크다.** 확실하지 않으면 넣지 않는다.
"""
from __future__ import annotations
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')
DOCS = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import ksic_rules as K        # noqa: E402
import segment_rules as R    # noqa: E402
import valuechain_rules as V  # noqa: E402


def _universe() -> dict:
    """회사명(정규화) → 모수 행. 사전 항목이 실제로 무엇으로 판정됐나 보려고 쓴다"""
    p = os.path.join(SAMPLES, 'universe-2026.csv')
    if not os.path.exists(p):
        return {}
    out = {}
    for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
        if r['모수계층'] != '모수밖':
            out.setdefault(R._norm_corp(r['회사명']), r)
    return out


def _num(v) -> int:
    try:
        return int(float(str(v or '0').replace(',', '')))
    except ValueError:
        return 0


def collect() -> list[dict]:
    """사전 전체를 한 표로. 각 항목이 어느 회사에 걸리는지 모수에서 찾아 붙인다"""
    uni = _universe()
    rows: list[dict] = []

    def add(사전, 키, 판정, 근거, 파일):
        # 사전 키는 이름의 **일부**다. 모수에서 그 조각을 포함하는 회사를 찾는다.
        # **키도 같은 방식으로 정규화한다** — `_norm_corp` 가 한글↔영문 약칭을 바꾸므로
        # (「에스케이실트론」→「SK실트론」) 날것으로 비교하면 못 찾는다
        조각 = R._norm_corp(키)
        hit = [r for k, r in uni.items() if 조각 in k]
        hit.sort(key=lambda r: -_num(r['매출액']))
        if not hit:
            rows.append({'사전': 사전, '키': 키, '판정': 판정, '근거': 근거, '파일': 파일,
                         '걸린회사': '(모수에 없음)', 'KSIC': '', '매출액_백만원': '',
                         '현재판정': ''})
            return
        for r in hit[:3]:            # 셋까지만 — 대장이 목적이라 전수 나열은 필요없다
            rows.append({
                '사전': 사전, '키': 키, '판정': 판정, '근거': 근거, '파일': 파일,
                '걸린회사': r['회사명'], 'KSIC': r['KSIC'],
                '매출액_백만원': r['매출액'],
                '현재판정': f"{r['A세분류']}×{r['B1주업종']}"
                            + (f">{r['B1_2단']}" if r['B1_2단'] else ''),
            })

    for k in K._후공정:
        add('반도체 후공정(OSAT)', k, '전자·정밀 > 반도체 후공정·부품',
            'KSIC C2611/C2612 에 IDM·파운드리와 섞여 있다', 'ksic_rules._후공정')
    for k in K._팹리스:
        add('반도체 팹리스', k, '전자·정밀 > 팹리스',
            '설계 전문 — 제조 설비가 없는데 IDM 과 같은 코드다', 'ksic_rules._팹리스')
    for k in K._반도체소재_전자:
        add('반도체 소재(무기재료계)', k, '전자·정밀 > 반도체 소재',
            '웨이퍼·쿼츠·SiC — 소자로 신고돼 있다', 'ksic_rules._반도체소재_전자')
    for k in K._반도체소재_화학:
        add('반도체 소재(화학계)', k, '화학·소재 > 전자·전지소재',
            '전구체·특수가스·PR — 일반 화학과 같은 코드다', 'ksic_rules._반도체소재_화학')
    for (co, ab), val in R.ABBREV.items():
        rows.append({'사전': '회사별 약어 부문', '키': f'{co} 「{ab}」',
                     '판정': f"{val[0] or '(상속)'} × {val[1]}"
                             + (f" > {val[2]}" if len(val) > 2 and val[2] else ''),
                     '근거': '부문명이 약어라 이름으로 판정할 수 없다',
                     '파일': 'segment_rules.ABBREV', '걸린회사': co,
                     'KSIC': '', '매출액_백만원': '', '현재판정': ''})
    for (co, ab), corp in R.ABBREV_법인.items():
        rows.append({'사전': '약어→법인(이중계상 방지)', '키': f'{co} 「{ab}」',
                     '판정': f'→ {corp} 로 본다(부문 제외)',
                     '근거': '약어는 법인명과 겹치지 않아 is_affiliate 가 못 잡는다',
                     '파일': 'segment_rules.ABBREV_법인', '걸린회사': corp,
                     'KSIC': '', '매출액_백만원': '', '현재판정': ''})
    for k, val in V.KEYWORDS:
        if any(x in k for x in ('에코프로', '실트론', '테스나', '아이피에스', '모비스',
                                '에너지머티리얼')):
            rows.append({'사전': '밸류체인 회사특정 키워드', '키': k,
                         '판정': f"밸류체인 {' · '.join(val)}",
                         '근거': '소재·장비사는 자기 KSIC 가 화학·기계다',
                         '파일': 'valuechain_rules.KEYWORDS', '걸린회사': '',
                         'KSIC': '', '매출액_백만원': '', '현재판정': ''})
    return rows


COLS = ['사전', '키', '판정', '걸린회사', 'KSIC', '매출액_백만원', '현재판정', '근거', '파일']


def to_csv(rows: list[dict]) -> str:
    p = os.path.join(SAMPLES, 'manual-dictionaries.csv')
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    return p


def to_md(rows: list[dict]) -> str:
    """사람이 읽는 대장. 사전별로 묶고 매출 순으로 둔다"""
    import collections
    by = collections.OrderedDict()
    for r in rows:
        by.setdefault(r['사전'], []).append(r)

    L = ['# 수동 사전 관리 대장', '',
         '> ⚠️ **검토 중 — 확정된 설계가 아니다.** 현재 시스템에 연결·연계하지 않는다.',
         '>', '> 이 파일은 `engine/dump_dictionaries.py` 가 **코드에서 자동으로 만든다.**',
         '> 손으로 고치지 말고 코드를 고친 뒤 다시 돌린다.', '',
         '## 왜 사전이 필요한가', '',
         '판정은 **KSIC 로 검증 가능한 것**만 쓴다는 원칙이다(README 의 축 조건 ②).',
         '그런데 자료가 갈라 주지 않는 곳이 있다.', '',
         '| 무엇 | KSIC 가 못 가르는 이유 |',
         '|---|---|',
         '| 반도체 공정 단계 | `C2611` 34 건에 SK하이닉스(IDM 86.9조)·SK키파운드리(파운드리)·'
         '하나마이크론(OSAT)이 함께 있다. 5 자리도 메모리/비메모리(품목) 구분이다 |',
         '| 반도체 소재 | 웨이퍼는 `C2612`(소자)로, 전구체·특수가스는 `C20`(일반 화학)으로 신고된다 |',
         '| 약어 부문 | 「ES」·「DS」·「WM」은 이름에 단서가 없다. 사업보고서 본문의 정의 표를 '
         '판정에 써 봤으나 오판정 34% 로 철회했다(D-26) |', '',
         '**그래서 예외를 두고 셋을 지킨다.** ① 수를 최소로 ② KSIC 로 범위를 좁혀 안전망을 '
         '두고(반도체 사전은 `C26`·`C20` 등일 때만 본다) ③ 낡는다는 것을 여기 적어 둔다.', '',
         '## 언제 갱신해야 하나', '',
         '1. **회사가 사업을 바꿨을 때** — LG전자 「ES」가 2024 년 조직개편으로 냉난방공조 '
         '본부가 됐는데 사전에 「전력·중전기」로 남아 있었다(D-26 에서 발견)',
         '2. **신규 상장·인수로 대상이 늘었을 때** — 목록은 상장사 위주다',
         '3. **회사명이 바뀌었을 때** — 사전은 이름 조각으로 찾는다', '',
         '> **미검출은 손해가 작고 오탐은 크다.** 확실하지 않으면 넣지 않는다 — '
         '틀린 분류는 잘못된 롱리스트를 만든다.', '',
         f'## 한눈에 — 사전 {len(by)} 종 · 항목 '
         f'{len({(r["사전"], r["키"]) for r in rows})} 개', '',
         '| 사전 | 항목 | 무엇을 정하나 | 파일 |', '|---|---|---|---|']
    역할 = {
        '반도체 후공정(OSAT)': 'B축 2단 → 반도체 후공정·부품',
        '반도체 팹리스': 'B축 2단 → 팹리스',
        '반도체 소재(무기재료계)': 'B축 2단 → 반도체 소재',
        '반도체 소재(화학계)': 'B축 2단 → 전자·전지소재',
        '회사별 약어 부문': '약어 부문의 A·B축 전체',
        '약어→법인(이중계상 방지)': '그 부문을 인스턴스에서 뺀다',
        '밸류체인 회사특정 키워드': '밸류체인(생태계) 값',
    }
    for 사전, rs in by.items():
        키수 = len({r['키'] for r in rs})
        L.append(f'| {사전} | {키수} | {역할.get(사전, "—")} | `{rs[0]["파일"]}` |')
    L.append('')

    for 사전, rs in by.items():
        L += [f'## {사전}', '', f'> {rs[0]["근거"]}', f'> 코드: `{rs[0]["파일"]}`', '']
        if rs[0]['걸린회사'] and rs[0]['KSIC'] is not None and any(r['KSIC'] for r in rs):
            L += ['| 사전 키 | 걸리는 회사 | KSIC | 매출(백만원) | 현재 판정 |',
                  '|---|---|---|---|---|']
            for r in sorted(rs, key=lambda r: -_num(r['매출액_백만원'])):
                L.append(f'| `{r["키"]}` | {r["걸린회사"]} | {r["KSIC"] or "—"} | '
                         f'{_num(r["매출액_백만원"]):,} | {r["현재판정"] or "—"} |')
        else:
            L += ['| 사전 키 | 판정 |', '|---|---|']
            for r in rs:
                L.append(f'| `{r["키"]}` | {r["판정"]} |')
        L.append('')

    L += ['---', '',
          '## 사전을 쓰지 않기로 한 것들 (참고)', '',
          '| 무엇 | 왜 안 쓰나 |', '|---|---|',
          '| 부문 설명(본문 정의 표) | 수집은 52% 되지만 판정에 쓰면 오판정 34% — 품목 나열이라 '
          '부수 단어가 이긴다(LG이노텍 「모빌리티솔루션」이 설명의 「통신」에 걸렸다) |',
          '| 부문 표의 「주요제품」 열 | 같은 이유. 35 건 중 대부분이 나빠지는 방향이었다 |',
          '| 「유통」 키워드 | 「조미유통」(동원F&B)·「가공유통」(동원산업)의 정확한 상속을 망친다 |',
          '| 「개발」 키워드 | GS리테일은 부동산 개발, 다른 회사는 R&D·신사업을 뜻한다 |',
          '| 「패키징」 키워드 | 한국콜마(화장품 용기)·삼양패키징(PET 병)이 반도체가 됐다 |',
          '| 이름이 「홀딩스」인 것을 모두 지주로 | 원익홀딩스(반도체 장비 `C2927`)·트리밍버드홀딩스'
          '(의류 `C1411`)는 사업회사다 — KSIC 와 교집합으로만 본다 |', '']
    p = os.path.join(DOCS, 'MANUAL-DICTIONARIES.md')
    io.open(p, 'w', encoding='utf-8').write('\n'.join(L))
    return p


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    rows = collect()
    키수 = len({(r['사전'], r['키']) for r in rows})
    print(f'사전 항목 {키수}개 · 행 {len(rows)}개 (한 키가 여러 회사에 걸릴 수 있다)')
    print(f'  {to_csv(rows)}')
    print(f'  {to_md(rows)}')
    미검출 = [r for r in rows if r['걸린회사'] == '(모수에 없음)']
    if 미검출:
        print(f'\n모수에 없는 사전 키 {len(미검출)}개 — 비상장이거나 이름이 바뀐 것이다:')
        for r in 미검출:
            print(f'  {r["사전"]:<22} 「{r["키"]}」')
