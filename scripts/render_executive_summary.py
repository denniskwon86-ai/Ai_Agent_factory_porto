from __future__ import annotations

import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs/official/current/internal/executive-summary/index.html"
PDF = ROOT / "docs/official/current/pdf/LAXS-M_v1.0_Executive_Summary_16x10.pdf"
CURRENT_PDF = ROOT / "docs/official/current/pdf/LAXS-M_Executive_Summary_16x10.pdf"
QA_DIR = ROOT / "tmp/executive-summary-qa"


def main() -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    PDF.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(HTML.resolve().as_uri(), wait_until="load")

        page.emulate_media(media="print")
        page.pdf(
            path=str(PDF),
            width="10in",
            height="6.25in",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        shutil.copyfile(PDF, CURRENT_PDF)

        page.emulate_media(media="screen")
        pages = page.locator(".page")
        for index in range(pages.count()):
            pages.nth(index).screenshot(path=str(QA_DIR / f"page-{index + 1:02d}.png"))

        metrics = page.evaluate(
            """() => [...document.querySelectorAll('.page')].map((node, index) => ({
                page: index + 1,
                clientWidth: node.clientWidth,
                scrollWidth: node.scrollWidth,
                clientHeight: node.clientHeight,
                scrollHeight: node.scrollHeight,
            }))"""
        )
        print({"pages": pages.count(), "metrics": metrics, "pdf": str(PDF)})
        browser.close()


if __name__ == "__main__":
    main()
