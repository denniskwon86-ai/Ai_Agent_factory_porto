"""★★★ [파일럿] 생성 앱을 **브라우저에서 실제로 열어** 데이터를 읽는지 본다.

## 왜 이 스크립트가 필요한가 (2026-08-19 실측)

카나리(`tests/test_end_to_end_canary.py`)는 HTTP 를 **직접** 부른다. 그런데 앱은
`postMessage` 브리지를 지나고, 그 브리지가 응답을 **허용목록으로 투영**한다. 그래서
서버가 200 을 주는데 앱은 빈 칸을 보는 상태가 존재하고 — 실제로 그랬다:

    파일 판 경로가 «평평한 행» 을 돌려주고 있었다 → 허용목록에 하나도 안 걸려 `{}`
    → 앱은 «3건» 을 받고 **모든 칸이 빈** 표를 그렸다. 아무 오류도 나지 않았다.

⚠️ 그리고 여기서 **파일럿 동선의 순서**가 드러난다:
    ① 조직 범위를 고르지 않으면 증명 발급이 409 다(「조직 미지정」이 실제로 막는다)
    ② 후보 앱은 실제 조직 문맥에서 **열 수 없다**(F-1: Preview 는 SYNTHETIC 전용)
       → 실제 문맥에서 보려면 **승격**해야 한다
    ③ 승격이 되어야 앱이 인증된 판을 읽는다

## 사용

    venv/Scripts/python.exe scripts/drive_generated_app.py [--shots <디렉터리>]

전제: 프런트(5173)·백엔드가 떠 있고, 프런트에 `VITE_AFS_HOST_RUNTIME=1` 이 있어야
한다(브리지 기본값은 «꺼짐» 이다). 데이터는 `scripts/pilot_demo_seed.py` 가 격리
워크트리에 심는다.

LLM 0콜.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

from scripts.capture_screens import ADMIN, FRONT, close_dialogs, login_as  # noqa: E402

#: 화면을 남길 곳. `--shots` 를 안 주면 아무것도 남기지 않는다.
OUT: Path | None = None


def _shot(page, name: str) -> None:
    if OUT is None:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / name), full_page=True)


def run(page) -> int:
    logs = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:160]}"))
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {str(e)[:160]}"))

    close_dialogs(page)

    #: ★★★ **조직 범위를 먼저 고른다.** 안 고르면 증명 발급이 409 로 막힌다 —
    #:   「조직 범위를 선택해야 앱이 데이터에 연결됩니다」. 화면 상단이 계속
    #:   「조직 미지정」이었는데, 그것이 실제로 막는 자리다.
    sw = page.locator("button", has_text="조직 전환").first
    if sw.count() == 0 or sw.is_disabled():
        print("✗ 「조직 전환」 을 쓸 수 없다 — 범위를 고를 방법이 없으면 앱을 못 연다")
        return 1
    sw.click()
    page.wait_for_timeout(1200)
    #: ⚠️ `.afs-scope` 는 화면에서 세 군데 쓰인다 — 클래스로 첫 것을 집으면 열림 단추
    #:   자신을 다시 누르게 된다(실제로 그랬다). **이름으로** 고른다.
    #: ★★★ **일하는 조직을 고른다.** 본사(공유서비스)는 공장의 «운영 상위» 가 아니므로
    #:   본사 문맥에서 공장 프로젝트를 열면 `SCOPE_OUTSIDE` 로 404 다 — 그리고 그것은
    #:   옳다(설계 §6.1: 권한 상속은 `OPERATING_PARENT` 만 따른다. 전사 집계 권한이
    #:   곧 모든 상세 데이터 권한이 되면 안 된다).
    #: ⚠️ 사용자에게는 「프로젝트를 찾을 수 없습니다」로만 보인다. 시연에서 문맥을
    #:   잘못 고르면 제품이 고장 난 것처럼 읽힌다 — 시연 대본에 넣을 것.
    opt = page.get_by_role("button", name="광양 1공장", exact=True).first
    if opt.count() == 0:
        print("✗ 고를 조직이 없다")
        return 1
    print(f"· 조직 «{opt.inner_text().strip()}» 선택")
    opt.click()
    page.wait_for_timeout(2500)

    #: ★★★ **후보 앱은 실제 조직 문맥에서 열 수 없다**(F-1) — Preview 는
    #:   `SYNTHETIC_TEST` 문맥에서만 돈다. 실제 문맥에서 보려면 **승격**해야 한다.
    #:   그것이 파일럿의 실제 이야기다: 데이터 준비 → 승격 → 앱이 돈다.
    close_dialogs(page)
    menu = page.locator("button", has_text="협업·의사결정·발간").first
    hub = page.locator("button", has_text="운영 승격").first
    if hub.count() == 0:
        #: 메뉴가 접혀 있으면 열고 다시 찾는다.
        m = page.locator("button", has_text="☰").first
        if m.count():
            m.click()
            page.wait_for_timeout(1200)
        hub = page.locator("button", has_text="운영 승격").first
    if hub.count() == 0:
        print("✗ 「운영 승격」 진입점을 찾지 못했다")
        return 1
    hub.click()
    page.wait_for_timeout(2500)
    dlg = page.locator('[role="dialog"]').last
    row = dlg.locator("button", has_text="원료 입고 현황 앱").first
    if row.count() == 0:
        #: ★ 이미 운영이면 후보 목록에 없다 — 그 자체가 승격이 끝났다는 뜻이다.
        if "올릴 후보 판이 없습니다" in dlg.inner_text():
            print("· 이미 운영 상태다(이전 실행에서 승격됨) — 승격 단계를 건너뛴다")
            close0 = dlg.locator("button", has_text="닫기").first
            if close0.count():
                close0.click()
            page.wait_for_timeout(1500)
            return _open_app(page, logs)
        print("✗ 승격 화면에 후보가 없다:", dlg.inner_text()[:200])
        return 1
    row.click()
    page.wait_for_timeout(2500)
    go = dlg.locator("button", has_text="운영으로 올리기").first
    if go.is_disabled():
        print("✗ 승격이 막혀 있다 — 화면이 말한 사유:")
        for line in dlg.inner_text().splitlines():
            t = line.strip()
            if t and ("없습니다" in t or "않았습니다" in t or "막힌" in t):
                print("   ", t[:130])
        _shot(page, "앱_00_승격막힘.png")
        return 1
    go.click()
    page.wait_for_timeout(5000)
    body = dlg.inner_text()
    if "운영으로 올렸습니다" not in body:
        print("✗ 승격이 끝나지 않았다:")
        for line in body.splitlines():
            t = line.strip()
            if t and ("못" in t or "없" in t):
                print("   ", t[:130])
        _shot(page, "앱_00_승격실패.png")
        return 1
    print("· 운영 승격 완료")
    for line in body.splitlines():
        if "지문" in line:
            print("   ", line.strip()[:120])
    #: ⚠️ Escape 만으로는 안 닫힐 수 있다 — 배경이 클릭을 가로채면 다음 단계가
    #:   통째로 멈춘다(실제로 그랬다). 「닫기」를 눌러 확실히 닫는다.
    close = dlg.locator("button", has_text="닫기").first
    if close.count():
        close.click()
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(2000)

    return _open_app(page, logs)


def _open_app(page, logs) -> int:
    """라이브러리에서 앱을 열어 **데이터를 읽는지** 본다."""
    #: 업무 만들기 목록면으로 간다.
    btn = page.locator("button", has_text="업무 SW 만들기").first
    if btn.count() == 0:
        print("✗ 「업무 SW 만들기」 진입점을 찾지 못했다")
        return 1
    btn.click()
    page.wait_for_timeout(3000)

    #: ★ 목록면은 탭으로 나뉜다 — 「Releases」를 눌러야 결과물이 보인다.
    tab = page.locator("button", has_text="Releases").first
    if tab.count() == 0:
        print("✗ Releases 탭이 없다")
        return 1
    tab.click()
    page.wait_for_timeout(2500)
    _shot(page, "앱_01_목록.png")

    body = page.inner_text("body")
    if "rel_pilot" not in body:
        print("✗ 목록에 rel_pilot 이 없다 — 라이브러리를 못 읽었다")
        for line in body.splitlines():
            if line.strip() and ("결과물" in line or "Release" in line or "없" in line):
                print("   ", line.strip()[:110])
        return 1

    #: 그 줄의 「열기」를 누른다.
    row = page.locator("div").filter(has_text="rel_pilot").last
    open_btn = row.locator("button", has_text="열기").first
    if open_btn.count() == 0:
        open_btn = page.locator("button", has_text="열기").first
    if open_btn.count() == 0:
        print("✗ 「열기」 단추가 없다")
        return 1
    open_btn.click()
    page.wait_for_timeout(6000)
    _shot(page, "앱_02_실행.png")

    #: ★★★ 앱은 **iframe 안**에서 돈다. 부모 본문만 보면 아무것도 못 본다.
    frames = [f for f in page.frames if f != page.main_frame]
    print(f"· iframe {len(frames)}개")
    found = False
    for f in frames:
        try:
            txt = f.locator("body").inner_text(timeout=3000)
        except Exception as e:
            print(f"  (프레임 읽기 실패: {str(e)[:60]})")
            continue
        if "원료 입고 현황" in txt or "afs-app" in txt or "읽은 행 수" in txt:
            found = True
            for line in txt.splitlines():
                if line.strip():
                    print("   ", line.strip()[:110])
            break
    if not found:
        print("✗ 앱 화면을 iframe 에서 찾지 못했다 — 콘솔:")
        for line in logs[-25:]:
            print("   ", line)
        return 1

    print("\n=== 콘솔 ===")
    for line in logs[-15:]:
        print("   ", line)
    return 0


def main() -> int:
    global OUT
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--shots", default="", help="화면을 남길 디렉터리(선택)")
    args = ap_.parse_args()
    OUT = Path(args.shots) if args.shots else None

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(FRONT, wait_until="domcontentloaded")
        login_as(page, ADMIN)
        code = run(page)
        b.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
