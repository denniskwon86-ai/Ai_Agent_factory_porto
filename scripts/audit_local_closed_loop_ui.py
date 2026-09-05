"""합성 관리자 계정으로 로컬 핵심 여정을 읽기·계산 차단 상태까지 관통한다.

계산 능력을 승인하거나 시연 자료를 초기화하지 않는다. 현재 계약상 미승인 계산은
BLOCKED 여야 하며, 그 상태에서 숫자나 안건을 만들어 보이는 UI 회귀를 잡는다.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


DEMO_ADMIN = "demo.admin@afs.invalid"
DEMO_PASSWORD = "pass1"
VIEWPORTS = ((1440, 900), (1280, 720))


def _local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost", "127.0.0.1",
    }:
        raise argparse.ArgumentTypeError("로컬 폐루프 검증은 localhost/127.0.0.1 만 허용합니다.")
    return value.rstrip("/")


def _login(page: Page) -> None:
    page.get_by_label("아이디").fill(DEMO_ADMIN)
    page.get_by_label("비밀번호").fill(DEMO_PASSWORD)
    page.get_by_role("button", name="로그인").click()
    page.get_by_role("button", name="로그아웃").wait_for(timeout=20_000)
    page.wait_for_timeout(800)


def _open_menu(page: Page, label: str) -> None:
    page.get_by_role("button", name="전체 메뉴").click()
    page.locator('[role="menu"] button', has_text=label).first.click()
    page.get_by_role("dialog").wait_for(timeout=15_000)


def _close_dialog(page: Page) -> None:
    page.get_by_role("dialog").get_by_role(
        "button", name=re.compile(r"^닫기"),
    ).first.click()
    page.get_by_role("dialog").wait_for(state="detached", timeout=10_000)


def _dialog_metrics(page: Page) -> dict:
    return page.evaluate("""() => {
      const d = document.querySelector('[role="dialog"]');
      const r = d && d.getBoundingClientRect();
      const body = d && d.querySelector('.afs-dialog-body');
      return {
        visible: !!d,
        within_viewport: !!r && r.left >= -1 && r.right <= innerWidth + 1
          && r.top >= -1 && r.bottom <= innerHeight + 1,
        horizontal_overflow: !!body && body.scrollWidth > body.clientWidth + 1,
        text: (d?.innerText || '').slice(0, 12000),
      };
    }""")


def _choose_option_containing(select, fragment: str) -> bool:
    values = select.locator("option").evaluate_all(
        "(opts, needle) => opts.filter(o => (o.textContent || '').includes(needle)).map(o => o.value)",
        fragment,
    )
    if not values:
        return False
    select.select_option(values[0])
    return True


def _audit_once(page: Page, out: Path, key: str) -> dict:
    result: dict = {}
    _login(page)

    # 2단계: 승인 상태를 읽기만 한다. 체크·승인·초기화 버튼은 누르지 않는다.
    _open_menu(page, "계산 실행 승인")
    approval = page.get_by_role("dialog")
    approval.locator("select").first.select_option(index=1)
    page.get_by_role("button", name="실행 승인", exact=True).click()
    page.get_by_text("아직 아무것도 승인되지 않았습니다", exact=True).wait_for(timeout=15_000)
    page.screenshot(path=out / f"01-calculation-approval-{key}.png", full_page=False)
    result["approval"] = _dialog_metrics(page)
    result["approval"]["selected_capabilities"] = approval.locator(
        'input[type="checkbox"]:checked',
    ).count()
    _close_dialog(page)

    # 3단계: 실제 관계를 찾은 뒤 계산을 요청한다. 미승인이므로 숫자가 아니라 BLOCKED 여야 한다.
    _open_menu(page, "경로 계산")
    path_dialog = page.get_by_role("dialog")
    path_dialog.locator("select").first.select_option(index=1)
    # 화면 기본값(현재 현지시각) 그대로 검증한다. 고정된 과거 날짜나 당일 00:00으로
    # 되돌아가면 아래 시작점 선택 목록이 사라져 이 감사가 실패한다.
    path_dialog.locator('input[type="datetime-local"]').wait_for(timeout=10_000)
    page.wait_for_timeout(1_000)
    selects = path_dialog.locator("select")
    if selects.count() < 3:
        snapshot = path_dialog.inner_text()[:4000]
        raise AssertionError(
            f"경로 계산의 시작점 선택 목록을 불러오지 못했습니다(select={selects.count()}).\n"
            f"{snapshot}"
        )
    if not _choose_option_containing(selects.nth(1), "shipment"):
        raise AssertionError("시연 시작점 shipment 가 없습니다.")
    if not _choose_option_containing(selects.nth(2), "sales-line"):
        raise AssertionError("시연 도착점 sales-line 이 없습니다.")
    page.get_by_role("button", name="경로 찾기").click()
    page.get_by_text(re.compile(r"찾은 경로 \d+개")).wait_for(timeout=20_000)
    path_dialog.get_by_role("checkbox", name=re.compile("예약 수량이 자료에 없는 것을")).check()
    path_dialog.get_by_role("checkbox", name=re.compile("날짜만 있는 값을")).check()
    page.get_by_role("button", name="이 경로로 계산").click()
    page.get_by_text("아직 계산할 수 없습니다", exact=True).wait_for(timeout=30_000)
    page.screenshot(path=out / f"02-path-calculation-blocked-{key}.png", full_page=False)
    result["path_calculation"] = _dialog_metrics(page)
    result["path_calculation"]["calculated_numbers_visible"] = page.get_by_text(
        "계산했습니다", exact=True,
    ).count() > 0
    result["path_calculation"]["decision_form_visible"] = page.get_by_text(
        "이 결과로 안건 만들기", exact=True,
    ).count() > 0
    _close_dialog(page)

    # 4단계: 핵심 여정은 구형 기준선 입력 폼이 아니라 실제 Decision Center로 열려야 한다.
    _open_menu(page, "의사결정 안건")
    page.get_by_role("heading", name="의사결정 센터", exact=True).wait_for(timeout=15_000)
    page.screenshot(path=out / f"03-decision-center-{key}.png", full_page=False)
    result["decision"] = _dialog_metrics(page)
    result["decision"]["legacy_baseline_form_visible"] = page.get_by_role("dialog").get_by_text(
        "기준선 스냅샷 ID", exact=True,
    ).count() > 0
    _close_dialog(page)

    # 5단계: 브리핑은 조회 실패/권한 제외를 0건이나 문제 없음으로 접지 않아야 한다.
    _open_menu(page, "경영 브리핑")
    page.get_by_text("전사 브리핑", exact=True).first.wait_for(timeout=15_000)
    page.wait_for_timeout(1_000)
    page.screenshot(path=out / f"04-management-briefing-{key}.png", full_page=False)
    result["briefing"] = _dialog_metrics(page)
    result["briefing"]["load_failure_as_clear"] = (
        "브리핑을 가져오지 못했습니다" in result["briefing"]["text"]
        and "주의 필요 없음" in result["briefing"]["text"]
    )
    result["briefing"]["ambiguous_attention_clear"] = any(
        phrase in result["briefing"]["text"]
        for phrase in ("주의 없음", "주의 필요 없음")
    )
    _close_dialog(page)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", type=_local_url, default="http://127.0.0.1:5174")
    ap.add_argument("--out", type=Path, default=Path("output/uiux-audit/closed-loop-current"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "front": args.front, "user": DEMO_ADMIN, "screens": {},
        "console_errors": [], "network_failures": [],
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        for width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.on("console", lambda msg: report["console_errors"].append(msg.text)
                    if msg.type == "error" else None)
            page.on("requestfailed", lambda req: report["network_failures"].append({
                "url": req.url, "reason": req.failure or "unknown",
            }))
            page.goto(args.front, wait_until="networkidle")
            key = f"{width}x{height}"
            report["screens"][key] = _audit_once(page, args.out, key)
            context.close()
        browser.close()

    failures: list[str] = []
    for size, screens in report["screens"].items():
        for name, metrics in screens.items():
            if not metrics["within_viewport"]:
                failures.append(f"{size} {name}: 대화상자가 화면을 벗어남")
            if metrics["horizontal_overflow"]:
                failures.append(f"{size} {name}: 가로 넘침")
        if screens["approval"]["selected_capabilities"]:
            failures.append(f"{size}: 사람이 고르지 않은 계산 능력이 선택됨")
        if screens["path_calculation"]["calculated_numbers_visible"]:
            failures.append(f"{size}: 미승인 계산이 숫자를 표시함")
        if screens["path_calculation"]["decision_form_visible"]:
            failures.append(f"{size}: 미완료 계산 옆에 안건 생성 폼이 표시됨")
        if screens["decision"]["legacy_baseline_form_visible"]:
            failures.append(f"{size}: 핵심 여정이 구형 기준선 입력 폼으로 열림")
        if screens["briefing"]["load_failure_as_clear"]:
            failures.append(f"{size}: 브리핑 조회 실패를 주의 없음으로 표시함")
        if screens["briefing"]["ambiguous_attention_clear"]:
            failures.append(f"{size}: 먼저 볼 항목이 있는데 포괄적인 '주의 없음'을 표시함")
    if report["console_errors"]:
        failures.append(f"브라우저 콘솔 오류 {len(report['console_errors'])}건")
    if report["network_failures"]:
        failures.append(f"네트워크 실패 {len(report['network_failures'])}건")

    report["status"] = "FAIL" if failures else "PASS"
    report["failures"] = failures
    target = args.out / "report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "failures": failures,
                      "report": str(target)}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
