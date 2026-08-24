# -*- coding: utf-8 -*-
"""화면 지도 HTML 생성. ★ 항목 정본은 `_screenmap_items.py` 하나다."""
import html
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _screenmap_items import GROUPS

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "screen-map.html")

rows = []
n = 0
for gi, (group, items) in enumerate(GROUPS):
    core = " core" if group.startswith("①") else ""
    rows.append('<tr class="grp%s"><td colspan="8">%s</td></tr>' % (core, E(group)))
    for name, where, what, act, pre in items:
        n += 1
        rid = "s%d" % n
        sub = " sub" if name.startswith("└") else ""
        rows.append(
            '<tr data-id="{rid}" class="{sub}">\n'
            '  <td class="no">{n}</td>\n'
            '  <td class="name"><strong>{name}</strong></td>\n'
            '  <td class="where"><code>{where}</code></td>\n'
            '  <td class="what">{what}</td>\n'
            '  <td class="act">{act}</td>\n'
            '  <td class="pre">{pre}</td>\n'
            '  <td class="verdict">\n'
            '    <label><input type="radio" name="v_{rid}" value="ok">'
            '<span class="p ok">열림</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="ng">'
            '<span class="p ng">안 열림</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="part">'
            '<span class="p part">열리나 빔</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="na">'
            '<span class="p na">권한 없음</span></label>\n'
            '  </td>\n'
            '  <td class="note"><textarea rows="2" data-note="{rid}" '
            'placeholder="특이사항 — 어디서 막혔는지, 무엇이 비었는지, 문구가 이상한지">'
            '</textarea></td>\n'
            '</tr>'.format(rid=rid, sub=sub, n=n, name=E(name), where=E(where),
                           what=E(what), act=E(act), pre=E(pre)))

TABLE = "\n".join(rows)
TPL = io.open(os.path.join(HERE, "_screenmap_tpl.html"), encoding="utf-8").read()
DOC = TPL.replace("__TABLE__", TABLE).replace("__TOTAL__", str(n))
io.open(OUT, "w", encoding="utf-8").write(DOC)
print("작성: %s  (%d화면, %s bytes)" % (OUT, n, format(len(DOC), ",")))
