"""로컬 LAXS 핵심 화면을 합성 계정으로 캡처하고 기본 UI 불변식을 검사한다.

읽기 전용 감사 전용이다. 로그인 세션 외 제품 데이터를 만들거나 수정하지 않는다.
localhost/127.0.0.1 이외 주소는 거부한다. 수동 기능 확인·통합 시연은 제품 서버가 보는
단일 사전검증 정본 `data/`를 사용한다. 자동 회귀만 실행별 임시 사본을 사용한다.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


DEMO_USER = "runner@afs.invalid"
# core/auth.py 의 현재 공통 초기 비밀번호. 데모 계정은 별도 비밀을 만들지 않는다.
DEMO_PASSWORD = "pass1"
VIEWPORTS = ((1440, 900), (1280, 720))


def _local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost", "127.0.0.1"
    }:
        raise argparse.ArgumentTypeError("로컬 UI 감사는 localhost/127.0.0.1 만 허용합니다.")
    return value.rstrip("/")


def _metrics(page: Page) -> dict:
    return page.evaluate("""() => {
      const doc = document.documentElement;
      const visible = [...document.querySelectorAll('body *')].filter((el) => {
        const s = getComputedStyle(el); const r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      });
      const tiny = visible.filter((el) => {
        const px = parseFloat(getComputedStyle(el).fontSize || '0');
        return px > 0 && px < 12 && (el.textContent || '').trim();
      }).slice(0, 20).map((el) => (el.textContent || '').trim().slice(0, 80));
      const dlg = document.querySelector('[role="dialog"]');
      const bar = dlg && dlg.querySelector('.afs-dialog-bar');
      const barRect = bar && bar.getBoundingClientRect();
      const diagInput = document.querySelector('input[aria-label="패키지 적용 식별자"]');
      const diagDetails = diagInput && diagInput.closest('details');
      const businessKitGroups = [...document.querySelectorAll('details[data-business-kit]')];
      return {
        viewport: {width: innerWidth, height: innerHeight},
        document: {clientWidth: doc.clientWidth, scrollWidth: doc.scrollWidth,
                   clientHeight: doc.clientHeight, scrollHeight: doc.scrollHeight},
        horizontal_overflow: doc.scrollWidth > doc.clientWidth + 1,
        tiny_text: tiny,
        real_account_visible: document.body.innerText.includes('@lsmnm.com'),
        placeholder_name_visible: document.body.innerText.includes('Jarvis'),
        permission_excluded_visible: document.body.innerText.includes('권한 범위에서 제외'),
        dialogs: document.querySelectorAll('[role="dialog"]').length,
        dialog_bar_visible: !dlg || (!!barRect && barRect.top >= 0 && barRect.bottom <= innerHeight),
        technical_instance_input_visible: !!diagInput && (!diagDetails || diagDetails.open)
          && getComputedStyle(diagInput).visibility !== 'hidden',
        ready_package_visible: document.body.innerText.includes('AFS 데모소재그룹')
          && document.body.innerText.includes('시연 가능'),
        ready_package_business_kit_count_visible: document.body.innerText.includes('업무키트 8'),
        preparing_package_visible: document.body.innerText.includes('AFS 배터리케미컬')
          && document.body.innerText.includes('준비 중'),
        legacy_profile_visible_as_package: document.body.innerText.includes('원료 구매·도입 경영 키트'),
        business_kit_group_count: businessKitGroups.length,
        business_kit_ids: businessKitGroups.map((el) => el.dataset.businessKit),
        business_kit_expanded_count: businessKitGroups.filter((el) => el.open).length,
      };
    }""")


def _login(page: Page) -> None:
    page.get_by_label("아이디").fill(DEMO_USER)
    page.get_by_label("비밀번호").fill(DEMO_PASSWORD)
    page.get_by_role("button", name="로그인").click()
    page.get_by_role("button", name="로그아웃").wait_for(timeout=20_000)
    page.wait_for_timeout(1_000)


def _open_data_prep(page: Page) -> None:
    page.get_by_role("button", name="전체 메뉴").click()
    # 메뉴 버튼의 접근 가능한 이름에는 상태/설명이 함께 붙을 수 있다. 표시 문구를 기준으로 찾되
    # 첫 번째가 아닌 패널 안 실제 항목을 누른다.
    page.locator('[role="menu"] button', has_text="업무 데이터 준비").first.click()
    page.get_by_role("dialog").wait_for(timeout=15_000)
    page.get_by_text("사용 가능한 샘플 기업 패키지", exact=True).wait_for(timeout=15_000)
    page.wait_for_timeout(1_000)


def _open_applied_package(page: Page) -> None:
    page.get_by_role("button", name=re.compile("첫 수직 시연")).click()
    page.get_by_text("업무기능별 준비도", exact=True).wait_for(timeout=15_000)
    page.wait_for_timeout(1_000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", type=_local_url, default="http://127.0.0.1:5173")
    ap.add_argument("--out", type=Path, default=Path("output/uiux-audit/current"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report: dict = {"front": args.front, "user": DEMO_USER, "screens": {},
                    "console_errors": [], "network_failures": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        for width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.on("console", lambda msg: report["console_errors"].append(msg.text)
                    if msg.type == "error" else None)
            page.on("requestfailed", lambda req: report["network_failures"].append({
                "url": req.url, "reason": req.failure or "unknown"}))
            page.goto(args.front, wait_until="networkidle")

            key = f"{width}x{height}"
            page.screenshot(path=args.out / f"01-login-{key}.png", full_page=False)
            login_metrics = _metrics(page)
            _login(page)
            page.screenshot(path=args.out / f"02-home-{key}.png", full_page=False)
            home_metrics = _metrics(page)
            _open_data_prep(page)
            page.screenshot(path=args.out / f"03-data-prep-{key}.png", full_page=False)
            prep_metrics = _metrics(page)
            _open_applied_package(page)
            page.screenshot(path=args.out / f"04-readiness-{key}.png", full_page=False)
            readiness_metrics = _metrics(page)
            report["screens"][key] = {
                "login": login_metrics, "home": home_metrics, "data_prep": prep_metrics,
                "readiness": readiness_metrics}
            context.close()
        browser.close()

    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = []
    for size, screens in report["screens"].items():
        if screens["login"]["horizontal_overflow"]:
            failed.append(f"{size}: 로그인 가로 넘침")
        if screens["login"]["real_account_visible"]:
            failed.append(f"{size}: 로그인 실존 계정 노출")
        if screens["data_prep"]["real_account_visible"]:
            failed.append(f"{size}: 데이터 준비 실존 계정 노출")
        if screens["home"]["placeholder_name_visible"]:
            failed.append(f"{size}: AI 비서 가칭 노출")
        if not screens["home"]["permission_excluded_visible"]:
            failed.append(f"{size}: 권한 밖 Trust 상태 안내 누락")
        if not screens["data_prep"]["dialog_bar_visible"]:
            failed.append(f"{size}: 작업공간 상단 바 가림")
        if screens["data_prep"]["technical_instance_input_visible"]:
            failed.append(f"{size}: 기술 식별자 기본 노출")
        if not screens["data_prep"]["ready_package_visible"]:
            failed.append(f"{size}: 시연 가능 패키지 누락")
        if not screens["data_prep"]["ready_package_business_kit_count_visible"]:
            failed.append(f"{size}: 시연 패키지의 업무키트 8종 모수 누락")
        if not screens["data_prep"]["preparing_package_visible"]:
            failed.append(f"{size}: 준비 중 패키지 누락")
        if screens["data_prep"]["legacy_profile_visible_as_package"]:
            failed.append(f"{size}: 옛 축약 정의가 샘플 패키지로 노출")
        expected_kits = ["FOUNDATION"] + [f"BK-{n:02d}" for n in range(1, 9)]
        if screens["readiness"]["business_kit_ids"] != expected_kits:
            failed.append(f"{size}: 업무키트 8종+기반팩 분류 불일치")
        if screens["readiness"]["business_kit_expanded_count"] != 0:
            failed.append(f"{size}: 세부 데이터 계약이 기본으로 과다 노출")
    if report["network_failures"]:
        failed.append(f"네트워크 실패 {len(report['network_failures'])}건")
    if report["console_errors"]:
        failed.append(f"브라우저 콘솔 오류 {len(report['console_errors'])}건")
    print(json.dumps({"status": "FAIL" if failed else "PASS", "failures": failed,
                      "report": str(args.out / "report.json")}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
