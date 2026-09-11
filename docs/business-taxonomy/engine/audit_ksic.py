# -*- coding: utf-8 -*-
"""
KSIC 신고 오류 후보를 찾는다
============================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 판정 오류의 남은 절반은 규칙이 아니라 **회사의 신고가 실질과 다른 것**이다.

| 회사 | 신고 | 실질 |
|---|---|---|
| 한화임팩트 2.6조 | 공정위 `M7160`(엔지니어링) · DART `K64992`(기타 금융) | 석유화학·수소 |
| 마녀공장 1,130억 | `C204`(정밀화학) | 화장품 브랜드 |
| 파워로직스 6,865억 | `C2812`(전기변환장치) | 카메라모듈·배터리 보호회로 |

**자동으로 고칠 수는 없다.** 무엇이 맞는지는 자료 밖에 있다. 대신 **후보를 좁혀
사람이 볼 수 있게** 한다.

쓰는 신호는 **출처 간 불일치** 하나다 — 공정위와 DART 의 KSIC 가 대분류부터 다르면
최소한 한쪽이 틀렸다. 한화임팩트가 공정위 `M7160`(엔지니어링) · DART `K64992`(기타
금융)로 신고돼 있어 둘 다 실질(석유화학)과 다른 것이 이렇게 드러났다.

**「KSIC 안의 매출 이상치」는 넣어 봤다가 뺐다.** 서비스업 코드에 조 단위 매출이 있으면
의심스럽다고 봤는데, 뽑히는 것이 메리츠증권 34.8조 · 농협은행 22.5조 · KT 19.3조 ·
네이버 7조였다 — **전부 판정이 정확하고 단지 그 업종의 대기업일 뿐이다.** 대기업은
원래 매출이 크므로 이 신호는 신고 오류와 무관하다.

    python audit_ksic.py            # 후보를 뽑아 samples/ 에 남긴다
    python audit_ksic.py 50         # 상위 50건만 화면에

**이 목록은 판정을 바꾸지 않는다.** 사람이 확인해 `MANUAL-DICTIONARIES.md` 의 사전에
넣거나, KSIC 매핑을 고칠 근거로 쓴다. 어느 쪽이 맞는지는 사업보고서를 봐야 안다.
"""
from __future__ import annotations
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), 'samples')

sys.path.insert(0, HERE)
import fetch_dart as F  # noqa: E402
import taxonomy_io as tx  # noqa: E402

# 대분류 문자 → 성격. 불일치가 「서비스↔제조」처럼 성격이 갈릴 때 우선순위를 올린다
_성격 = {'A': '자원', 'B': '자원', 'C': '제조', 'D': '시설', 'E': '시설', 'F': '건설',
        'G': '유통', 'H': '운송', 'I': '서비스', 'J': '정보', 'K': '금융', 'L': '부동산',
        'M': '서비스', 'N': '서비스', 'P': '서비스', 'Q': '서비스', 'R': '서비스', 'S': '서비스'}


def _num(v) -> float:
    try:
        return float(str(v or '0').replace(',', ''))
    except ValueError:
        return 0.0


def _jurir(v: str) -> str:
    return ''.join(c for c in (v or '') if c.isdigit())


def load() -> tuple[list[dict], dict, dict]:
    uni = [r for r in tx.load('universe')
        if r['모수계층'] != '모수밖']
    ftc = {}
    for r in tx.load('src_ftc'):          # ★ [P4] 공정위 **원천** KSIC — 판정 전 값
        k = _jurir(r.get('법인등록번호'))
        if k:
            ftc[k] = r.get('KSIC', '')
    dart = {}
    for r in tx.load('src_corp'):
        k = _jurir(r.get('법인등록번호'))
        ks = F.to_ksic(r.get('induty_code')) if r.get('induty_code') else None
        if k and ks:
            dart[k] = ks
    return uni, ftc, dart


def audit() -> list[dict]:
    uni, ftc, dart = load()
    out: list[dict] = []
    for r in uni:
        k = _jurir(r['법인등록번호'])
        ks, s = r['KSIC'] or '', _num(r['매출액'])
        f, d = ftc.get(k), dart.get(k)
        if not (f and d and f[:1] != d[:1]):
            continue
        # **불일치의 성격으로 우선순위를 매긴다.** 「서비스 ↔ 제조」처럼 A축이 갈리는
        # 것이 급하다 — 업무키트 대상이 아예 달라진다. 한쪽이 지주코드인 것은
        # `resolve_ksic` 가 이미 처리하므로 뒤로 보낸다
        fp, dp = _성격.get(f[:1], '?'), _성격.get(d[:1], '?')
        지주 = F._지주코드.match(f) or F._지주코드.match(d)
        점수 = 1.0 if 지주 else (3.0 if {fp, dp} & {'제조'} else 2.0)
        # 매출이 크면 영향이 크다 — 순서에만 쓰고 판단 근거로는 쓰지 않는다
        점수 += min(s / 1_000_000, 2.0)
        사유 = [f'{fp}({f}) ↔ {dp}({d})' + ('  · 한쪽이 지주코드' if 지주 else '')]
        if True:
            out.append({
                '회사명': r['회사명'], '법인등록번호': k, 'KSIC': ks,
                '매출액_백만원': r['매출액'], '매출_억': int(s) // 100,
                '현재판정': f"{r['A세분류']}×{r['B1주업종']}"
                            + (f">{r['B1_2단']}" if r['B1_2단'] else ''),
                '공정위KSIC': f or '', 'DART_KSIC': d or '',
                '의심점수': round(점수, 1), '사유': ' · '.join(사유),
            })
    out.sort(key=lambda r: (-r['의심점수'], -r['매출_억']))
    return out


COLS = ['회사명', 'KSIC', '매출_억', '현재판정', '공정위KSIC', 'DART_KSIC',
        '의심점수', '사유', '법인등록번호', '매출액_백만원']


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
    rows = audit()
    p = os.path.join(SAMPLES, 'reports', 'ksic-audit-2026.csv')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    제조 = sum(1 for r in rows if '제조(' in r['사유'])
    지주 = sum(1 for r in rows if '지주코드' in r['사유'])
    print(f'후보 {len(rows)}건 — A축이 갈리는 것(제조 ↔ 서비스 등) {제조} · '
          f'한쪽이 지주코드 {지주}')
    print(f'  {p}\n')
    print(f'=== 상위 {min(n, len(rows))}건 (사람이 확인할 순서) ===')
    for r in rows[:n]:
        print(f"  {r['의심점수']:>4} {r['회사명'][:20]:<22} {r['KSIC']:<8} "
              f"{r['매출_억']:>7,}억  {r['현재판정'][:26]:<28} {r['사유'][:52]}")
