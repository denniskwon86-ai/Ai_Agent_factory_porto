# -*- coding: utf-8 -*-
"""
비상장 공시법인 수집기
======================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 필요한가.** 르노코리아는 DART 에 등재돼 있고 업종코드도 정확한데(`30121` →
`C30121` 자동차 제조업) 모수에서 빠졌다. `corp_code_map()` 이 **종목코드 있는 것만**
담기 때문이다. 타타대우모빌리티도 같다. 완성차 대상을 뽑으면 이 둘이 빠진다.

`corpCode.xml` 의 비상장 법인은 114,953 건이다. 대부분 SPC·펀드·폐업이라 전수 조회는
값이 없고 **일일 한도(20,000회)도 넘는다.** 그래서 `modify_date` 가 최근인 것부터
받는다 — 공시법인은 정보가 갱신되므로 최근 수정분이 활동 중인 곳이다.

    python fetch_unlisted.py 2026          # 2026 년 수정분(7,722건)
    python fetch_unlisted.py 2025          # 2025 년 이후(16,236건)

중간에 끊겨도 `.cache/unlisted.json` 에 쌓아 두므로 다시 실행하면 이어서 받는다.
한도 초과(status 020)면 그 자리에서 멈추고 저장한다.
"""
from __future__ import annotations
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_dart as F  # noqa: E402

DST = os.path.join(F.CACHE, 'unlisted.json')


def candidates(since: str = '2026') -> list[tuple[str, str]]:
    """비상장 법인 중 `modify_date` 가 `since` 년 이후인 것 → [(고유번호, 이름)]"""
    raw = F._get('corpCode.xml')
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read(z.namelist()[0]).decode('utf-8', 'replace')
    out = []
    for m in re.finditer(r'<list>(.*?)</list>', xml, re.S):
        b = m.group(1)
        stock = (re.search(r'<stock_code>(.*?)</stock_code>', b) or [None, ''])[1].strip()
        if stock:
            continue                      # 상장사는 fetch_listed 가 받는다
        mod = (re.search(r'<modify_date>(.*?)</modify_date>', b) or [None, '0'])[1].strip()
        if mod[:4] < since:
            continue
        code = re.search(r'<corp_code>(.*?)</corp_code>', b)
        name = re.search(r'<corp_name>(.*?)</corp_name>', b)
        if code and name:
            out.append((code.group(1).strip(), name.group(1)))
    return out


def collect(since: str = '2026') -> list[dict]:
    os.makedirs(F.CACHE, exist_ok=True)
    done = {}
    if os.path.exists(DST):
        for r in json.load(io.open(DST, encoding='utf-8')):
            done[r['corp_code']] = r
        print(f'이미 받은 것 {len(done)}건 — 이어서 받는다', flush=True)

    cand = [c for c in candidates(since) if c[0] not in done]
    print(f'받을 것 {len(cand)}건 ({since}년 이후 수정된 비상장 법인)', flush=True)

    out, quota = list(done.values()), False
    for i, (cc, nm) in enumerate(cand, 1):
        try:
            c = F._get_json('company.json', corp_code=cc)
            if c.get('status') == '020':          # 사용한도 초과
                quota = True
                print('  일일 한도 초과 — 여기서 멈춘다', flush=True)
                break
            out.append({'corp_code': cc, 'name': c.get('corp_name') or nm,
                        'induty': c.get('induty_code'), 'jurir': c.get('jurir_no')})
        except Exception as e:
            out.append({'corp_code': cc, 'name': nm, 'error': str(e)[:60]})
        if i % 300 == 0:
            json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'  {i}/{len(cand)} · 누적 {len(out)}', flush=True)

    json.dump(out, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
    ok = sum(1 for r in out if r.get('induty'))
    jur = sum(1 for r in out if r.get('jurir'))
    print(f'\n=== 총 {len(out)}건 · 업종코드 {ok} · 법인등록번호 {jur}'
          + (' · 한도로 중단' if quota else '') + ' ===')
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    collect(sys.argv[1] if len(sys.argv) > 1 else '2026')
