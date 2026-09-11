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
import parse_segment_desc as PD  # noqa: E402

DST = os.path.join(HERE, '.cache', 'segments.json')


def _rcept_index() -> dict:
    """회사명 → 접수번호. **`reports.json` 캐시에 없는 회사를 위한 대안이다** —
    `latest_annual` 은 캐시에 없으면 API 를 부르는데 한도가 소진되면 실패한다.
    그래서 32 건이 매번 「원문 없어 건너뜀」으로 빠졌고, 그 안에 오탐 부문이 남아
    있었다(신세계푸드 「중단영업조정」·한솔아이원스 「복리후생비」). ZIP 은 캐시에
    있으므로 접수번호만 알면 API 없이 파싱된다"""
    import re
    import sys as _s
    _s.path.insert(0, HERE)
    import taxonomy_io as tx          # * [P4] CSV 가 아니라 DB 원천에서
    _법인 = re.compile(r'㈜|\(주\)|\(유\)|주식회사|유한회사')

    def key(s):
        return _법인.sub('', s or '').replace(' ', '').upper()
    out = {}
    for r in tx.load('src_reports'):
        if r.get('회사명') and r.get('접수번호'):
            out.setdefault(key(r['회사명']), r['접수번호'])
    return out


def main(dry: bool = False) -> None:
    recs = json.load(io.open(DST, encoding='utf-8'))
    RIDX = _rcept_index()
    print(f'{len(recs)}건 다시 파싱한다 (ZIP 은 캐시에서 읽는다 · 접수번호 색인 {len(RIDX)}건)',
          flush=True)

    changed, gone, born, skipped = [], 0, 0, 0
    for i, rec in enumerate(recs, 1):
        before = [s['명칭'] for s in rec.get('segments') or []]
        try:
            rpt = None
            try:
                rpt = F.latest_annual(F.resolve(rec['종목코드']))
            except Exception:
                pass                   # API 한도 등 — 아래 색인으로 대신한다
            if not rpt:
                import re as _re
                k = _re.sub(r'㈜|\(주\)|\(유\)|주식회사|유한회사', '',
                            rec['회사명']).replace(' ', '').upper()
                rc = RIDX.get(k)
                if rc:
                    rpt = {'rcept_no': rc, 'report_nm': ''}
            if not rpt:
                skipped += 1
                continue
            note = F.note_xml(rpt['rcept_no'])
            if not note:
                # **주석을 못 읽는 32 건.** ZIP 은 있는데 주석 파일(_00760/_00761)이
                # 없다(신세계푸드·신세계톰보이). 다시 파싱할 수는 없지만, 옛 결과에
                # **부문명 필터만 다시 적용**하면 오탐은 걷을 수 있다 — 그러지 않으면
                # 「중단영업조정」·「집합평가대상채권 금액」이 영원히 남는다
                keep = [s for s in (rec.get('segments') or []) if P._부문명(s['명칭'])]
                if len(keep) != len(rec.get('segments') or []):
                    before = [s['명칭'] for s in rec['segments']]
                    rec['segments'] = keep
                    changed.append((rec['회사명'], before, [s['명칭'] for s in keep]))
                    gone += len(before) - len(keep)
                skipped += 1
                continue
        except Exception as e:
            rec['error'] = f'{type(e).__name__}: {str(e)[:50]}'
            skipped += 1
            continue
        rec['단일부문'] = P.single_segment(note)
        rec['segments'] = P.parse(note)
        rec['error'] = None
        # 부문 매출이 **어느 해 사업보고서**에서 왔는지 남긴다 — 「사업보고서 (2025.12)」.
        # 법인 매출(공정위 2025 개별 · DART 연결)과 나란히 둘 때 기준이 드러나야 한다
        rec['보고서'] = rpt.get('report_nm', '')
        # **부문 설명을 본문에서 찾아 붙인다.** 부문명이 약어면 이름으로 판정할 수 없다 —
        # LG전자 「ES」가 「전력·중전기」로 잘못 들어가 있었다(실제 에어컨·HVAC).
        # 「사업의 내용」의 부문 정의 표가 답을 갖고 있다. API 를 쓰지 않고 캐시된 ZIP 을 읽는다
        if len(rec['segments']) >= 2:
            try:
                desc = PD.descriptions(F.document_xml(rpt['rcept_no']),
                                       [s['명칭'] for s in rec['segments']])
                for s in rec['segments']:
                    if desc.get(s['명칭']):
                        s['부문설명'] = desc[s['명칭']]
            except Exception:
                pass                   # 본문이 없거나 표를 못 찾으면 그냥 넘어간다
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
