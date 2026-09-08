# -*- coding: utf-8 -*-
"""
받아둔 공시 원문을 다시 파싱한다 — API 호출 없이
=================================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**왜 따로 있는가.** `collect_segments.py` 는 이미 받은 것을 건너뛴다(`done`).
그러니 파서를 고쳐도 `segments.json` 이 그대로 남아, 고친 규칙이 반영되지 않는다.
공시 ZIP 은 `.cache/` 에 419 건 있으므로 **다시 받지 않고 파싱만** 하면 된다.

    python reparse.py           # 다시 파싱해 segments.json 을 덮는다
    python reparse.py --dry     # 무엇이 바뀌는지만 본다
"""
from __future__ import annotations
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import fetch_dart as F          # noqa: E402
import parse_segment as P       # noqa: E402

DST = os.path.join(HERE, '.cache', 'segments.json')


def main(dry: bool = False) -> None:
    recs = json.load(io.open(DST, encoding='utf-8'))
    print(f'{len(recs)}건 다시 파싱한다 (ZIP 은 캐시에서 읽는다)', flush=True)

    changed, gone, born, skipped = [], 0, 0, 0
    for i, rec in enumerate(recs, 1):
        before = [s['명칭'] for s in rec.get('segments') or []]
        try:
            cc = F.resolve(rec['종목코드'])
            rpt = F.latest_annual(cc)
            if not rpt:
                skipped += 1
                continue
            note = F.note_xml(rpt['rcept_no'])
            if not note:
                skipped += 1
                continue
        except Exception as e:
            rec['error'] = f'{type(e).__name__}: {str(e)[:50]}'
            skipped += 1
            continue
        rec['단일부문'] = P.single_segment(note)
        rec['segments'] = P.parse(note)
        rec['error'] = None
        after = [s['명칭'] for s in rec['segments']]
        if before != after:
            changed.append((rec['회사명'], before, after))
            gone += len(set(before) - set(after))
            born += len(set(after) - set(before))
        if i % 100 == 0:
            print(f'  {i}/{len(recs)}', flush=True)

    print(f'\n바뀐 회사 {len(changed)}건 · 사라진 부문 {gone} · 새로 잡힌 부문 {born}'
          f' · 원문 없어 건너뜀 {skipped}')
    for nm, b, a in changed[:25]:
        d = sorted(set(b) - set(a))
        n = sorted(set(a) - set(b))
        line = f'  {nm[:16]:<18}'
        if d:
            line += ' 뺐다: ' + ' · '.join(x[:12] for x in d)
        if n:
            line += ' 넣었다: ' + ' · '.join(x[:12] for x in n)
        print(line)

    if dry:
        print('\n--dry 라 쓰지 않았다')
        return
    json.dump(recs, io.open(DST, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'\n{len(recs)}건 → {DST}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main('--dry' in sys.argv)
