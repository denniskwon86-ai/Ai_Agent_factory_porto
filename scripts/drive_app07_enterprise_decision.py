"""로컬 제품 UI로 부서 계산 → 전사 조합 → 결정 → 대내 보고본을 관통한다.

운영 외부 발송은 하지 않는다. 모든 쓰기는 localhost 제품 API를 실제 화면에서
누르는 방식으로만 수행하며, 같은 이름의 산출물이 있으면 이어서 실행한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page, sync_playwright


ADMIN = "admin"
REVIEWER = "hikwon_20@lsmnm.com"
DECIDER = "hikwon@lsmnm.com"
PASSWORD = "pass1"
SCENARIO_NAME = "2026 하반기 원료 수급·판매 대응 · 브라우저 검증 20260903"
SCENARIO_PURPOSE = "구매 지연이 재고·생산·판매와 전사 재무 영향에 미치는 경로를 동일 기준선으로 검토"
DECISION_QUESTION = "원료 도입 지연 대응안과 생산·판매 조정안을 실행할 것인가?"
REPORT_TITLE = "2026 하반기 원료 수급·생산·판매 대응 의사결정 보고"
AS_OF_LOCAL = "2026-09-03T08:00"


def local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise argparse.ArgumentTypeError("localhost/127.0.0.1 만 허용합니다.")
    return value.rstrip("/")


def note(message: str) -> None:
    print(message, flush=True)


def wait_idle(page: Page, ms: int = 500) -> None:
    page.wait_for_timeout(ms)


def login(page: Page, user: str) -> None:
    if page.get_by_role("button", name="로그아웃").count():
        return
    page.get_by_label("아이디").fill(user)
    page.get_by_label("비밀번호").fill(PASSWORD)
    page.get_by_role("button", name="로그인", exact=True).click()
    page.get_by_role("button", name="로그아웃", exact=True).wait_for(timeout=20_000)
    wait_idle(page, 800)
    note(f"LOGIN {user}")


def logout(page: Page) -> None:
    button = page.get_by_role("button", name="로그아웃", exact=True)
    if button.count():
        button.click()
        page.get_by_role("button", name="로그인", exact=True).wait_for(timeout=15_000)


def switch_user(page: Page, user: str) -> None:
    logout(page)
    login(page, user)


def open_menu(page: Page, label: str) -> None:
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button", name="로그아웃", exact=True).wait_for(timeout=15_000)
    page.get_by_role("button", name="전체 메뉴", exact=True).click()
    menu = page.locator('[role="menu"]')
    menu.wait_for(timeout=10_000)
    menu.get_by_role("menuitem", name=re.compile(re.escape(label))).first.click()
    wait_idle(page, 700)
    note(f"OPEN {label}")


def choose_containing(select: Locator, text: str) -> bool:
    values = select.locator("option").evaluate_all(
        "(opts, needle) => opts.filter(o => (o.textContent || '').includes(needle)).map(o => o.value)",
        text,
    )
    if not values:
        return False
    select.select_option(values[0])
    return True


def screenshot(page: Page, out: Path, name: str) -> None:
    page.screenshot(path=out / name, full_page=True)


def open_calc_approval(page: Page) -> None:
    open_menu(page, "계산 실행 승인")
    page.locator(".calc-approval-panel").wait_for(timeout=15_000)


def approve_capabilities(page: Page, out: Path) -> None:
    open_calc_approval(page)
    panel = page.locator(".calc-approval-panel")
    first = panel.locator("select").first
    first.select_option(index=1)
    wait_idle(page, 700)
    if "계산 3종 실행 승인됨" in panel.inner_text():
        note("APPROVED capabilities=3 (existing current binding)")
        screenshot(page, out, "01-calculation-capabilities.png")
        return
    page.locator("button").filter(has_text="계산 실행 승인").last.click()
    page.get_by_placeholder("왜 이 산식으로 계산해도 되는가").wait_for(timeout=15_000)
    selects = panel.locator("select")
    if selects.count() > 1:
        selects.nth(1).select_option("DEMO/SYNTHETIC")
    enabled = panel.locator('input[type="checkbox"]:not([disabled])')
    for i in range(enabled.count()):
        if not enabled.nth(i).is_checked():
            enabled.nth(i).check()
    if enabled.count():
        page.get_by_placeholder("왜 이 산식으로 계산해도 되는가").fill(
            "로컬 DEMO/SYNTHETIC 전사 시나리오 검증을 위해 현재 코드·데이터 결속 지문과 산식·단위·부호를 재확인했습니다."
        )
        button = panel.get_by_role("button", name=re.compile(r"선택한 \d+건 실행 승인"))
        if button.count() and button.is_enabled():
            button.click()
            page.get_by_text(re.compile(r"\d+건 승인됨")).wait_for(timeout=30_000)
            note(f"APPROVED capabilities={enabled.count()}")
    screenshot(page, out, "01-calculation-capabilities.png")


def open_app(page: Page, app_label: str, action_label: str) -> None:
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button", name="로그아웃", exact=True).wait_for(timeout=15_000)
    page.get_by_role("button", name="앱 운영", exact=True).click()
    app_list = page.locator('aside[aria-label="업무 앱 목록"]')
    app_list.wait_for(timeout=20_000)
    app_list.get_by_role("button").filter(has_text=app_label).first.click()
    page.get_by_role("button", name=action_label, exact=True).click()
    page.locator(".path-calc-panel").wait_for(timeout=20_000)
    wait_idle(page, 700)


def select_scenario(page: Page, create: bool = False) -> None:
    panel = page.locator(".path-calc-panel")
    scenario_select = panel.locator("select").first
    if choose_containing(scenario_select, SCENARIO_NAME):
        wait_idle(page, 500)
        return
    if not create:
        raise AssertionError(f"전사 시나리오가 없습니다: {SCENARIO_NAME}")
    scenario_select.select_option("")
    page.get_by_placeholder("예: 2026 하반기 원료 수급 대응").fill(SCENARIO_NAME)
    page.get_by_placeholder("예: 구매 지연이 생산·판매에 미치는 전사 영향 검토").fill(SCENARIO_PURPOSE)
    page.get_by_role("button", name="전사 시나리오 만들기", exact=True).click()
    page.get_by_text("전사 시나리오를 만들었습니다. 부서별 계산 결과를 같은 곳에 저장합니다.", exact=True).wait_for(timeout=20_000)
    note(f"CREATED scenario={SCENARIO_NAME}")


def run_department(page: Page, out: Path, app_id: str, app_label: str, create_scenario: bool) -> None:
    open_app(page, app_label, "전사 영향 시뮬레이션")
    panel = page.locator(".path-calc-panel")
    select_scenario(page, create=create_scenario)
    selects = panel.locator("select")
    if not selects.nth(1).input_value():
        selects.nth(1).select_option(index=1)
    panel.locator('input[type="datetime-local"]').fill(AS_OF_LOCAL)
    panel.locator("select").nth(3).wait_for(timeout=20_000)
    wait_idle(page, 900)
    selects = panel.locator("select")
    if not choose_containing(selects.nth(2), "shipment"):
        if not choose_containing(selects.nth(2), "선적"):
            raise AssertionError("시작점 shipment/선적을 찾지 못했습니다.")
    selects.nth(3).select_option("sales-line")
    page.get_by_role("button", name="경로 찾기", exact=True).click()
    page.get_by_text(re.compile(r"찾은 경로 [1-9]\d*개")).wait_for(timeout=30_000)
    radios = panel.locator('input[type="radio"][name="path"]')
    if radios.count() and not radios.first.is_checked():
        radios.first.check()
    for fragment in ("예약 수량이 자료에 없는 것을", "날짜만 있는 값을"):
        cb = panel.get_by_role("checkbox", name=re.compile(fragment))
        if not cb.is_checked():
            cb.check()
    page.get_by_role("button", name="이 경로로 계산", exact=True).click()
    page.get_by_text("계산했습니다", exact=True).wait_for(timeout=45_000)
    page.get_by_role("button", name="부서 결과 저장", exact=True).click()
    page.get_by_text(re.compile(
        r"결과를 같은 전사 시나리오에 저장했습니다|같은 계산 결과가 이미 저장되어 있어 중복 기록하지 않았습니다"
    )).wait_for(timeout=45_000)
    note(f"SAVED {app_id} {app_label}")
    screenshot(page, out, f"02-{app_id.lower()}-department-result.png")


def compose_app07(page: Page, out: Path) -> str:
    open_app(page, "전사 시나리오·실적 통합", "전사 통합 시뮬레이션 실행")
    select_scenario(page)
    page.get_by_role("button", name="전사 운영 영향 조합", exact=True).click()
    page.get_by_text("세 부서 운영 영향 결합 완료", exact=True).wait_for(timeout=45_000)
    screenshot(page, out, "03-enterprise-composition-before-bridge.png")
    return page.locator(".path-calc-panel").inner_text()


def create_bridge_draft(page: Page, out: Path) -> None:
    text = compose_app07(page, out)
    if "검토 초안 만들기" in text:
        page.get_by_role("button", name="검토 초안 만들기", exact=True).click()
        page.get_by_text(re.compile(r"검토 대기 · 제 \d+판")).wait_for(timeout=30_000)
        note("CREATED financial bridge draft")
    screenshot(page, out, "04-financial-bridge-draft.png")


def approve_bridge_and_create_decision(page: Page, out: Path) -> None:
    compose_app07(page, out)
    reason = page.get_by_placeholder("검토 근거를 입력하십시오")
    if reason.count():
        reason.fill(
            "DEMO/SYNTHETIC 전사 시나리오의 구매·생산·판매 결과를 인증된 계정과목·환율 기준으로 연결하는 계약을 검토했습니다."
        )
        page.get_by_role("button", name="검토 완료 후 적용", exact=True).click()
        page.get_by_text(re.compile(r"적용 중 · 제 \d+판")).wait_for(timeout=30_000)
        note("APPROVED financial bridge")
        wait_idle(page, 1000)
        compose = page.get_by_role("button", name="전사 운영 영향 조합", exact=True)
        if compose.is_enabled():
            compose.click()
    page.get_by_role("button", name="의사결정 안건으로 저장", exact=True).wait_for(timeout=45_000)
    screenshot(page, out, "05-enterprise-financial-impact.png")
    existing = fetch_json(page, "/api/v1/decisions/queue")
    if any(row.get("question") == DECISION_QUESTION for row in existing):
        note(f"EXISTING decision={DECISION_QUESTION}")
        screenshot(page, out, "06-decision-created.png")
        return
    question = page.get_by_placeholder("예: 원료 도입 지연 대응안을 실행할 것인가?")
    question.fill(DECISION_QUESTION)
    page.locator('input[type="date"]').fill("2026-09-30")
    page.get_by_role("button", name="의사결정 안건으로 저장", exact=True).click()
    page.get_by_role("button", name="안건 저장 완료", exact=True).wait_for(timeout=30_000)
    note(f"CREATED decision={DECISION_QUESTION}")
    screenshot(page, out, "06-decision-created.png")


def open_collaboration(page: Page, rail: str) -> None:
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button", name="로그아웃", exact=True).wait_for(timeout=15_000)
    page.get_by_role("button", name="결정·보고", exact=True).click()
    wait_idle(page, 700)
    heading = page.get_by_role("heading", name=rail, exact=True)
    if not heading.count():
        page.locator("button").filter(has_text=rail).last.click()
    wait_idle(page, 700)


def open_decision(page: Page) -> None:
    open_collaboration(page, "의사결정 센터")
    page.get_by_role("heading", name="의사결정 센터", exact=True).wait_for(timeout=20_000)
    item = page.get_by_role("button", name=re.compile(re.escape(DECISION_QUESTION)))
    if not item.count():
        page.get_by_role("button", name="전체", exact=True).last.click()
        item.first.wait_for(timeout=20_000)
    item.first.click()
    page.get_by_role("heading", name=DECISION_QUESTION, exact=True).first.wait_for(timeout=20_000)


def request_review(page: Page, out: Path) -> None:
    open_decision(page)
    if page.get_by_role("button", name="검토 요청", exact=True).count():
        page.get_by_role("button", name="검토 요청", exact=True).click()
        participant = page.get_by_label("참여자 1")
        participant.locator(f'option[value="{DECIDER}"]').wait_for(
            state="attached", timeout=15_000,
        )
        participant.select_option(DECIDER)
        page.get_by_role("button", name="검토 요청 보내기", exact=True).click()
        note(f"REQUESTED review from {DECIDER}")
    screenshot(page, out, "07-decision-review-requested.png")


def decide(page: Page, out: Path) -> None:
    open_decision(page)
    agree = page.get_by_role("button", name="동의", exact=True)
    if agree.count():
        agree.click()
        page.get_by_role("button", name="의견 저장", exact=True).click()
        wait_idle(page, 600)
    approve = page.get_by_role("button", name="승인", exact=True)
    if approve.count():
        approve.click()
        page.locator("#dc-rat").fill("동일 기준선과 인증판에 결속된 부서별 영향 및 전사 재무 브리지 결과를 검토했습니다.")
        page.get_by_role("button", name="결정 기록하기", exact=True).click()
        page.get_by_text("결정 기록", exact=True).last.wait_for(timeout=30_000)
        note(f"DECIDED approved by {DECIDER}")
    screenshot(page, out, "08-decision-approved.png")


def create_and_render_report(page: Page, out: Path) -> None:
    open_collaboration(page, "대내외 발간")
    page.get_by_role("heading", name="대내외 보고 발간", exact=True).wait_for(timeout=20_000)
    existing = page.get_by_role("button").filter(has_text=REPORT_TITLE)
    if existing.count():
        existing.first.click()
        page.get_by_role("heading", name=REPORT_TITLE, exact=True).first.wait_for(timeout=20_000)
        wait_idle(page, 700)
    else:
        page.get_by_role("button", name="새 발간 초안", exact=True).click()
        page.locator("#np-src").select_option(label=DECISION_QUESTION)
        page.locator("#np-title").fill(REPORT_TITLE)
        page.get_by_role("button", name="발간 초안 만들기", exact=True).click()
        page.get_by_role("heading", name=REPORT_TITLE, exact=True).first.wait_for(timeout=20_000)
        note(f"CREATED report={REPORT_TITLE}")
    preview = page.locator('[role="document"][aria-label="발간 문서 미리보기"]')
    if not preview.count():
        render = page.get_by_role("button", name="문서 생성", exact=True)
        render.wait_for(timeout=20_000)
        render.click()
        preview.wait_for(timeout=30_000)
        note("RENDERED internal report")
    preview.wait_for(timeout=20_000)
    screenshot(page, out, "09-internal-report-rendered.png")


def fetch_json(page: Page, path: str):
    return page.evaluate(
        """async (path) => {
          const token = localStorage.getItem('factory.sessionToken') || '';
          const url = path.startsWith('http') ? path : `http://127.0.0.1:8080${path}`;
          const r = await fetch(url, {
            credentials: 'include', headers: {'X-Session-Token': token},
          });
          const body = await r.json();
          if (!r.ok) throw new Error(`${r.status} ${JSON.stringify(body)}`);
          return Object.prototype.hasOwnProperty.call(body, 'data') ? body.data : body;
        }""",
        path,
    )


def verify(page: Page) -> dict:
    decisions = fetch_json(page, "/api/v1/decisions/queue")
    decision = next((x for x in decisions if x.get("question") == DECISION_QUESTION), None)
    if not decision:
        raise AssertionError("검증할 의사결정 안건을 찾지 못했습니다.")
    publications = fetch_json(page, "/api/v1/publications")
    publication = next((x for x in publications if x.get("title") == REPORT_TITLE), None)
    if not publication:
        raise AssertionError("검증할 내부 보고본을 찾지 못했습니다.")
    detail = fetch_json(page, f"/api/v1/publications/{publication['publication_id']}")
    decision_detail = fetch_json(page, f"/api/v1/decisions/{decision['decision_id']}")
    version = detail.get("current_version") or {}
    source_evidence_hash = (((version.get("document") or {}).get("evidence") or {})
                            .get("source_evidence_hash"))
    if source_evidence_hash != decision_detail.get("evidence_hash"):
        raise AssertionError("보고본과 의사결정 안건의 근거 지문이 다릅니다.")
    return {
        "scenario_name": SCENARIO_NAME,
        "decision_id": decision_detail.get("decision_id"),
        "decision_status": decision_detail.get("status"),
        "decision_evidence_hash": decision_detail.get("evidence_hash"),
        "publication_id": detail.get("publication_id"),
        "publication_status": detail.get("status"),
        "publication_evidence_hash": version.get("evidence_hash"),
        "publication_source_evidence_hash": source_evidence_hash,
        "evidence_chain_equal": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--front", type=local_url, default="http://127.0.0.1:5173")
    parser.add_argument("--out", type=Path, default=Path("output/uiux-audit/app07-complete-20260903"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "RUNNING",
        "stage": "startup",
        "steps": [],
        "console_errors": [],
        "network_failures": [],
        "aborted_requests": [],
    }
    started = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.on(
            "console",
            lambda msg: report["console_errors"].append(
                {"stage": report["stage"], "text": msg.text, "location": msg.location}
            )
            if msg.type == "error"
            else None,
        )
        def record_failed_request(req) -> None:
            item = {"url": req.url, "reason": req.failure or "unknown"}
            bucket = "aborted_requests" if item["reason"] == "net::ERR_ABORTED" else "network_failures"
            report[bucket].append(item)

        page.on("requestfailed", record_failed_request)
        try:
            page.goto(args.front, wait_until="networkidle", timeout=30_000)
            report["stage"] = "login-admin"
            login(page, ADMIN)
            report["stage"] = "calculation-capabilities"
            approve_capabilities(page, args.out)
            report["stage"] = "app-01"
            run_department(page, args.out, "APP-01", "원료 도입계획·추적", True)
            report["stage"] = "app-03"
            run_department(page, args.out, "APP-03", "재고·생산 영향 분석", False)
            report["stage"] = "app-06"
            run_department(page, args.out, "APP-06", "판매·납기·매출 영향", False)
            report["stage"] = "financial-bridge-draft"
            create_bridge_draft(page, args.out)
            report["stage"] = "login-reviewer"
            switch_user(page, REVIEWER)
            report["stage"] = "bridge-approval-and-decision"
            approve_bridge_and_create_decision(page, args.out)
            report["stage"] = "decision-review-request"
            request_review(page, args.out)
            report["stage"] = "login-decider"
            switch_user(page, DECIDER)
            report["stage"] = "decision-approval"
            decide(page, args.out)
            report["stage"] = "internal-report-render"
            create_and_render_report(page, args.out)
            report["stage"] = "evidence-verification"
            report.update(verify(page))
            if report["console_errors"] or report["network_failures"]:
                raise RuntimeError("브라우저 콘솔 또는 네트워크 오류가 남아 있습니다.")
            report["status"] = "PASS"
        except Exception as exc:
            report["status"] = "FAIL"
            report["error"] = str(exc)
            report["body_text"] = page.locator("body").inner_text()[:20_000]
            screenshot(page, args.out, "99-failure.png")
            raise
        finally:
            report["elapsed_seconds"] = round(time.time() - started, 1)
            (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            context.close()
            browser.close()
    note(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
