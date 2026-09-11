"""Isolated product-form interaction; never open the user's profile or operational API."""
from pathlib import Path
import json
import tempfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(tempfile.mkdtemp(prefix="decision-ui-", dir=ROOT / "output"))
ORIGIN = "http://127.0.0.1:18764"
reports = []
errors = []
blocked = []
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    try:
        for width, height in ((1440, 900), (390, 844)):
            context = browser.new_context(viewport={"width": width, "height": height})
            def restrict(route):
                if route.request.url.startswith(ORIGIN + "/"):
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()
            context.route("**/*", restrict)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ORIGIN + "/tests/decision-create.fixture.html")
            basis = page.get_by_label("근거 종류 (필수)")
            submit = page.get_by_role("button", name="Decision Package 만들기", exact=True)
            expect(basis).to_have_value("")
            expect(submit).to_be_disabled()
            page.locator("#nc-q").fill("합성 시험: 증설 여부")
            page.locator("#pk-baseline").fill("무행동")
            page.locator("#pk-options").fill("유지\n증설")
            expect(submit).to_be_disabled()  # all other required fields are filled
            expect(basis.locator("option")).to_have_count(5)
            expect(page.locator("#legacy-basis")).to_have_text("미기재(이전 기록)")
            for index, (value, label) in enumerate((
                ("SIMULATION", "시뮬레이션 계산"), ("MEASURED", "실측 자료"),
                ("EXTERNAL", "외부 공표 자료"), ("JUDGMENT", "전문가 판단")), 1):
                basis.select_option(value)
                expect(submit).to_be_enabled()
                submit.click()
                receipt = page.locator("#request-receipt")
                expect(receipt).to_contain_text(f'"count": {index}')
                captured = json.loads(receipt.inner_text())
                assert captured["label"] == label
                assert captured["request"]["body"]["evidence_basis"] == value
                assert captured["request"]["body"]["package"]["options"] == ["유지", "증설"]
                assert not {"baseline_id", "scenario_id", "scope_id"}.intersection(captured["request"]["body"])
                reports.append({"viewport": [width, height], **captured})
            basis.select_option("")
            expect(submit).to_be_disabled()
            assert page.locator("#request-receipt").inner_text().count('"count": 4') == 1
            basis.scroll_into_view_if_needed()
            page.screenshot(path=str(RUN / f"basis-{width}.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal overflow"
            context.close()
    finally:
        browser.close()
assert not errors, errors
assert not blocked, blocked
report = {"passed": True, "viewports": 2, "submissions": reports,
          "page_errors": errors, "blocked_network": blocked,
          "scope": "actual CreateScreen + decisionApi + closedLoopFetch; in-memory response only"}
(RUN / "browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": True, "viewports": 2, "submissions": len(reports), "output": str(RUN)}, ensure_ascii=False))
