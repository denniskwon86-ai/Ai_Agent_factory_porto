# -*- coding: utf-8 -*-
"""권한 상속·격리를 **화면에서** 확인한다 — 두 역할이 다른 것을 보는가."""
import io
import sys
from pathlib import Path

sys.path.insert(0, r"C:\WorkSpace\gemini_agent_team_verG")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

from scripts.capture_screens import FRONT, close_dialogs, login_as, open_panel  # noqa: E402

ADMIN = "hikwon@lsmnm.com"
BUYER = "pilot_buyer@lsmnm.com"


def instances_for(page, uid):
    page.goto(FRONT, wait_until="domcontentloaded")
    login_as(page, uid)
    close_dialogs(page)
    ok, why = open_panel(page, "업무 데이터 준비")
    if not ok:
        return None, f"화면 열기 실패: {why}"
    dlg = page.locator('[role="dialog"]').last
    page.wait_for_timeout(2000)
    body = dlg.inner_text()
    labels = [x for x in ("광양 1공장", "포항 2공장") if x in body]
    return labels, body[:300]


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})

        admin, admin_body = instances_for(page, ADMIN)
        print(f"· {ADMIN:24s} → {admin}")
        if admin is None:
            print("   ", admin_body)

        buyer, buyer_body = instances_for(page, BUYER)
        print(f"· {BUYER:24s} → {buyer}")
        if buyer is None:
            print("   ", buyer_body)
        b.close()

    if admin is None or buyer is None:
        return 1
    ok = True
    #: ★★★ 경영자는 둘 다 본다(상속). 구매 담당자는 자기 공장만 본다(격리).
    if sorted(admin) != ["광양 1공장", "포항 2공장"]:
        print(f"✗ 경영자가 두 공장을 다 보지 못한다 — 상속이 안 된다: {admin}")
        ok = False
    if buyer != ["광양 1공장"]:
        print(f"✗ 구매 담당자의 범위가 틀렸다: {buyer}")
        ok = False
    #: ⚠️ 대조군 — 둘이 **같은 것**을 보면 이 시험은 아무것도 증명하지 않는다.
    if admin == buyer:
        print("✗ 두 역할이 같은 것을 본다 — 격리를 증명하지 못한다")
        ok = False
    print("\n=== 권한 상속·격리 확인 ===" if ok else "\n=== 실패 ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
