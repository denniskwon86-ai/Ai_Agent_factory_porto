"""화면을 실제 이미지로 캡처한다 — Browser 패널이 안 보일 때의 대책.

`computer{screenshot}` 은 Browser 패널이 화면에 표시돼 있지 않으면
"the Browser pane is not displayed, so the page is not compositing frames" 로 실패한다.
프레임을 합성하는 주체가 패널이기 때문이며, 패널을 열지 않고 우회할 수 없다.

그래서 **합성 주체를 바꾼다.** 이미 설치된 Chrome 을 playwright 로 헤드리스로 띄우면
패널과 무관하게 프레임을 만들 수 있다. `channel="chrome"` 이라 브라우저를 새로 내려받지 않는다.

사용:
    venv/Scripts/python.exe scripts/capture_screens.py                 # 전체
    venv/Scripts/python.exe scripts/capture_screens.py --only 기준정보  # 하나만
    venv/Scripts/python.exe scripts/capture_screens.py --out <디렉터리>

전제: 프론트(5173)와 백엔드(8080)가 이미 떠 있어야 한다. 이 스크립트는 서버를 띄우지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FRONT = "http://localhost:5173"

# 승인된 예시 계정만 쓴다 — 임의 계정을 만들지 않는다.
ADMIN = "hikwon@lsmnm.com"
NORMAL = "hikwon_16@lsmnm.com"
ANON = ""

VIEWPORTS = [(1280, 720), (1440, 900)]

# (파일이름표, 사용자, 경로)
# 경로는 `>` 로 나눈다. 첫 조각은 전체 메뉴에서 여는 화면, 그 뒤는 모달 안 좌측 레일 항목.
# 의사결정 센터·대내외 발간은 독립 화면이 아니라 협업 모달의 탭이므로 반드시 두 단계다.
SHOTS = [
    ("런처-미이관", ADMIN, ""),          # 대비용 — 아직 다크로 남아 있는 화면
    ("기준정보-관리자", ADMIN, "기준정보 마스터"),
    ("기준정보-일반", NORMAL, "기준정보 마스터"),
    ("기준정보-익명", ANON, "기준정보 마스터"),
    ("지식허브-관리자", ADMIN, "지식 허브"),
    ("협업-관리자", ADMIN, "협업"),
    ("의사결정-관리자", ADMIN, "협업>의사결정 센터"),
    ("발간-관리자", ADMIN, "협업>대내외 발간"),
]


def switch_user(page: Page, uid: str) -> None:
    """상단 바의 활동 사용자 선택을 바꾼다. 값이 없으면 익명."""
    sel = page.locator("select").first
    sel.select_option(value=uid)
    page.wait_for_timeout(1200)


def close_dialogs(page: Page) -> None:
    for _ in range(3):
        btn = page.locator('[role="dialog"] button', has_text="닫기")
        if btn.count() == 0:
            break
        btn.first.click()
        page.wait_for_timeout(300)


def open_panel(page: Page, path: str) -> tuple[bool, str]:
    """경로를 따라 화면을 연다. (성공여부, 실패이유) 를 돌려준다.

    ⚠️ 모달이 열려 있으면 `#root[inert]` 때문에 뒤의 전체 메뉴가 눌리지 않는다.
       그래서 반드시 먼저 닫고, 닫혔는지 확인한 다음 메뉴를 연다. 이걸 확인하지 않으면
       직전 화면이 그대로 찍혀서 «캡처 성공» 으로 착각한다(실제로 그렇게 틀렸다).
    """
    close_dialogs(page)
    if not path:                         # 빈 경로 = 아무것도 열지 않은 런처 자체
        return page.locator('[role="dialog"]').count() == 0, "모달이 남아 있다"

    first, *tabs = [s.strip() for s in path.split(">")]
    if page.locator('[role="dialog"]').count():
        return False, "직전 모달이 닫히지 않았다"

    menu = page.locator("button", has_text="전체 메뉴")
    if menu.count():
        menu.first.click()
        page.wait_for_timeout(500)
    target = page.locator("button", has_text=first)
    if target.count() == 0:
        return False, f"전체 메뉴에 «{first}» 가 없다"
    target.first.click()
    page.wait_for_timeout(2500)          # 실데이터 로딩까지 기다린다
    dlg = page.locator('[role="dialog"]')
    if dlg.count() == 0:
        return False, f"«{first}» 를 눌렀지만 모달이 열리지 않았다"

    for tab in tabs:                     # 모달 안 좌측 레일로 이동
        item = dlg.locator("button", has_text=tab)
        if item.count() == 0:
            return False, f"모달 안에 «{tab}» 항목이 없다"
        item.first.click()
        page.wait_for_timeout(2000)
        head = dlg.locator(".hub-bar, .afs-dialog-bar").first.inner_text()
        if tab.split()[0] not in head.replace(" ", ""):
            # 제목이 안 바뀌었으면 탭 전환이 안 된 것이다 — 찍어도 다른 화면이다
            return False, f"«{tab}» 를 눌렀는데 제목이 «{head[:20]}» 그대로다"
    return True, ""


def measure(page: Page) -> dict:
    """캡처와 같은 시점의 사실을 함께 남긴다 — 이미지와 수치가 어긋나지 않게."""
    return page.evaluate("""() => {
      const dlg = document.querySelector('[role="dialog"]');
      const g = el => el ? getComputedStyle(el) : null;
      const layout = dlg && dlg.querySelector('.hub-layout');
      const card = dlg && dlg.querySelector('.hub-card, .afs-card, .panel');
      const doc = document.documentElement;
      let small = [];
      (dlg || doc).querySelectorAll('*').forEach(e => {
        const t = (e.textContent || '').trim();
        if (!t || e.children.length) return;
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (/^[A-Z0-9 ·—–_./]{1,24}$/.test(t)) return;
        const fs = parseFloat(getComputedStyle(e).fontSize);
        if (fs < 12) small.push(fs + 'px:' + t.slice(0, 14));
      });
      return {
        모달: !!dlg,
        열구성: layout ? g(layout).gridTemplateColumns : null,
        셸배경: layout ? g(layout).backgroundColor : null,
        카드배경: card ? g(card).backgroundColor : null,
        본문색: dlg ? g(dlg).color : null,
        글꼴: dlg ? g(dlg).fontFamily.slice(0, 28) : null,
        Jarvis: !!(dlg && dlg.querySelector('.hub-jarvis, .jarvis-rail')),
        문서넘침: doc.scrollWidth - doc.clientWidth,
        작은글자: small.slice(0, 5),
      };
    }""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/uiux/screenshots")
    ap.add_argument("--only", default=None, help="이름표에 이 문자열이 든 항목만")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = [s for s in SHOTS if not args.only or args.only in s[0]]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for w, h in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": w, "height": h},
                                      device_scale_factor=1)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            # ⚠️ `networkidle` 은 쓰지 않는다 — 앱이 상태를 계속 폴링해서 idle 이 오지 않는다.
            page.goto(FRONT, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("select", timeout=30_000)   # 상단 바가 붙을 때까지
            page.wait_for_timeout(2500)                        # 첫 데이터 로딩

            for tag, uid, label in shots:
                try:
                    switch_user(page, uid)
                    opened, why = open_panel(page, label)
                    m = measure(page)
                    path = out / f"{tag}_{w}x{h}.png"
                    page.screenshot(path=str(path))
                    flag = "" if opened else f"  ⚠️ 이 이미지는 이 화면이 아니다 — {why}"
                    print(f"[{w}x{h}] {tag:18s} → {path}{flag}")
                    print(f"          {m}")
                except Exception as e:                       # 한 화면 실패가 전체를 죽이지 않게
                    print(f"[{w}x{h}] {tag:18s} ✗ 실패: {type(e).__name__}: {e}")
            if errors:
                print(f"[{w}x{h}] 콘솔 오류 {len(errors)}건: {errors[:3]}")
            ctx.close()
        browser.close()
    print(f"\n캡처 위치: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
