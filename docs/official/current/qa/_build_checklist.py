# -*- coding: utf-8 -*-
"""기능 점검표 HTML 생성. ★ 항목 정본은 `_checklist_items.py` 하나다."""
import html
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _checklist_items import GROUPS

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "functional-checklist.html")

def rich(value):
    """Escape first, then render the one emphasis form used by the canonical items."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", E(value))

rows = []
n = 0
for gi, (group, items) in enumerate(GROUPS):
    rows.append('<tr class="grp"><td colspan="6">%s</td></tr>' % E(group))
    for how, act, expect in items:
        n += 1
        rid = "r%d" % n
        rows.append(
            '<tr data-id="{rid}" data-grp="{gi}">\n'
            '  <td class="no">{n}</td>\n'
            '  <td class="item"><strong>{how}</strong></td>\n'
            '  <td class="act">{act}</td>\n'
            '  <td class="exp">{exp}</td>\n'
            '  <td class="verdict">\n'
            '    <label><input type="radio" name="v_{rid}" value="ok">'
            '<span class="p ok">정상</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="ng">'
            '<span class="p ng">문제</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="part">'
            '<span class="p part">일부</span></label>\n'
            '    <label><input type="radio" name="v_{rid}" value="na">'
            '<span class="p na">해당없음</span></label>\n'
            '  </td>\n'
            '  <td class="note"><textarea rows="2" data-note="{rid}" '
            'placeholder="특이사항 — 무엇이 어떻게 달랐는지, 화면·값·재현 방법">'
            '</textarea></td>\n'
            '</tr>'.format(rid=rid, gi=gi, n=n, how=E(how), act=rich(act), exp=rich(expect)))

TOTAL = n
TABLE = "\n".join(rows)

TPL = io.open(os.path.join(HERE, "_checklist_tpl.html"), encoding="utf-8").read()
DOC = TPL.replace("__TABLE__", TABLE).replace("__TOTAL__", str(TOTAL))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, "w", encoding="utf-8").write(DOC)
print("작성: %s  (%d항목, %s bytes)" % (OUT, TOTAL, format(len(DOC), ",")))
