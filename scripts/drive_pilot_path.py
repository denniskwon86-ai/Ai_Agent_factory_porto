"""★★★ [파일럿] 화면 동선을 **실제로 눌러** 끝까지 간다.

## 왜 이 스크립트가 필요한가 (2026-08-19 실측)

`capture_screens.py` 는 「화면이 뜬다」를 증명한다. 그런데 그날 나온 결함 넷은 전부
**뜬 뒤에** 있었다 — 인스턴스를 열려면 `ki_…` 를 타이핑해야 했고, 기준값 7개를
띄어쓰기로 순서대로 받았고, 위쪽 경고와 아래쪽 안건이 같은 판을 두고 서로 다른 답을
했다. 화면은 전부 「정상」으로 캡처됐다.

⚠️⚠️ 그리고 이 저장소의 프런트에는 **자동 시험이 하나도 없다**(vitest 미설치). 그래서
  화면 배선이 끊겨도 잡아 주는 것이 아무것도 없다. 이 스크립트가 그 자리를 임시로
  메운다 — 정식 프런트 시험 도구 도입은 UI 담당(Codex) 영역의 결정이다.

## 무엇을 확인하는가

    ① 기준선 고르개에 인스턴스가 뜨고, 인증된 판을 고를 수 있는가
    ② 기준값이 **인증된 판에서 뽑히는가**(그리고 나머지는 이름표 있는 칸으로 받는가)
    ③ 시뮬레이션이 숫자와 **지문**을 내는가
    ④ 안건이 만들어지고, 근거의 계보가 **사람이 읽는 이름**으로 나오는가

★ 「전부 초록」을 확인하는 스크립트가 아니다. 각 칸에서 **무엇이 없어서 멈췄는지**를
  말하는 것이 이 스크립트의 일이다.

사용:
    venv/Scripts/python.exe scripts/drive_pilot_path.py
    venv/Scripts/python.exe scripts/drive_pilot_path.py --shots <디렉터리>

전제: 프런트(5173)와 백엔드가 이미 떠 있고, 그 백엔드에 **인증된 판이 하나 이상**
있어야 한다(`scripts/pilot_demo_seed.py` 가 격리 워크트리에 심는다).

LLM 0콜.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from scripts.capture_screens import ADMIN, FRONT, login_as, open_panel  # noqa: E402

#: 기준값 — **시연용 숫자**다. ⚠️ 제품이 이 값을 갖고 있지 않다는 사실 자체가
#:   확인 대상이다. 지금은 사용자가 회사 실적에서 손으로 채워야 한다.
BASE = {"생산량": "1000", "기말재고": "200", "구매지급": "5000000",
        "기말현금": "30000000", "영업이익": "4000000", "전력비": "800000",
        "기간": "30"}
DRIVERS = {"환율": "10", "도입 지연": "5", "전력단가": "8"}

#: 이 문구가 남아 있으면 그 칸은 끝나지 않은 것이다.
#: ⚠️ **안내 문구를 여기 넣지 않는다.** 「…을 고르십시오」는 고르개가 늘 달고 있는
#:   안내라, 넣으면 성공한 실행도 실패로 읽힌다(첫 판에서 실제로 그랬다). 실패의
#:   증거는 **화면이 실패라고 말할 때만 쓰는 문구**여야 한다.
STUCK = ("불러오지 못했습니다", "만들지 못했습니다", "확인하지 못했습니다")


def _fill(dlg, values: dict, tag: str) -> bool:
    """이름표로 칸을 찾아 채운다. ★ 순서로 찾지 않는다 — 순서는 화면이 바뀌면 깨진다."""
    for name, v in values.items():
        lab = dlg.locator("label", has_text=name).first
        if lab.count() == 0:
            print(f"  ✗ {tag}: «{name}» 칸이 없다")
            return False
        lab.locator("input").first.fill(v)
    return True


def _shot(page: Page, shots: Path | None, name: str) -> None:
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shots / f"{name}.png"), full_page=True)


def _echo(body: str, keys: tuple[str, ...]) -> None:
    for line in body.splitlines():
        s = line.strip()
        if s and any(k in s for k in keys):
            print("   ", s[:120])


def run(page: Page, shots: Path | None) -> int:
    # ── ① 시나리오: 기준선 고르기 ───────────────────────────────────────
    ok, why = open_panel(page, "시나리오 시뮬레이션")
    if not ok:
        print(f"✗ ① 화면 열기 실패: {why}")
        return 1
    dlg = page.locator('[role="dialog"]').last

    inst = dlg.locator("button", has_text="파일럿 시연").first
    if inst.count() == 0:
        print("✗ ① 기준선 고르개에 인스턴스가 없다 — 여기서 사용자는 시작할 수 없다")
        _shot(page, shots, "동선_01_인스턴스없음")
        return 1
    inst.click()
    page.wait_for_timeout(1500)

    boxes = dlg.locator('input[type="checkbox"]')
    n = boxes.count()
    print(f"· ① 인증된 판 {n}건")
    if n == 0:
        print("✗ ① 고를 수 있는 인증된 판이 없다 — 동선이 여기서 끊긴다")
        _shot(page, shots, "동선_01_판없음")
        return 1
    boxes.first.check()
    page.wait_for_timeout(400)
    _shot(page, shots, "동선_01_기준선")

    # ── ② 기준값 — 먼저 «판에서 뽑기» 를 눌러 본다 ──────────────────────
    #: ★★★ 사람이 7칸을 손으로 채우는 것과, 인증된 판에서 뽑히는 것은 다른 제품이다.
    fill_btn = dlg.locator("button", has_text="고른 판에서 채우기").first
    if fill_btn.count() == 0:
        print("✗ ② 「고른 판에서 채우기」가 없다 — 있는 값을 사람에게 다시 묻고 있다")
        return 1
    fill_btn.click()
    page.wait_for_timeout(2500)
    picked = dlg.locator("text=판에서 뽑음").count()
    print(f"· ② 판에서 뽑힌 칸 {picked}개")
    if picked == 0:
        print("✗ ② 아무 칸도 뽑히지 않았다 — 화면이 말한 사유:")
        _echo(dlg.inner_text(), ("없습니다", "숫자가", "찾을 수", "다릅니다"))
        _shot(page, shots, "동선_02_유도실패")
        return 1
    _shot(page, shots, "동선_02_기준값유도")

    #: 나머지(재무 3칸 등)는 사람이 채운다 — 그 사실 자체가 이 화면의 답이다.
    if not (_fill(dlg, BASE, "②") and _fill(dlg, DRIVERS, "②")):
        return 1
    page.wait_for_timeout(300)

    # ── ③ 시뮬레이션 ────────────────────────────────────────────────────
    btn = dlg.locator("button", has_text="시뮬레이션 실행").first
    if btn.count() == 0:
        print("✗ ③ 실행 단추가 없다")
        return 1
    btn.click()
    page.wait_for_timeout(3000)
    _shot(page, shots, "동선_02_결과")

    body = dlg.inner_text()
    stuck = [w for w in STUCK if w in body]
    if stuck:
        print(f"✗ ③ 아직 못 넘어간 문구가 남아 있다: {stuck}")
        _echo(body, ("못", "지정", "실패", "없습니다"))
        return 1
    if "지문" not in body:
        #: ★★★ 지문이 없으면 그 숫자는 «무엇으로 만들었는지» 답할 수 없다.
        print("✗ ③ 결과에 지문이 없다 — 재현성을 주장할 수 없는 숫자다")
        return 1
    print("· ③ 시뮬레이션 실행됨")
    _echo(body, ("생산량", "기말현금", "영업이익", "지문"))

    # ── ④ 의사결정 안건 ─────────────────────────────────────────────────
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    ok, why = open_panel(page, "의사결정 안건")
    if not ok:
        print(f"✗ ④ 화면 열기 실패: {why}")
        return 1
    dlg = page.locator('[role="dialog"]').last

    for ph, v in (("안건 제목", "원료 도입 지연 대응"), ("실행 책임자", "구매팀장"),
                  ("기한", "2026-08-30")):
        f = dlg.locator(f'input[placeholder*="{ph}"]').first
        if f.count() == 0:
            print(f"✗ ④ «{ph}» 칸이 없다")
            return 1
        f.fill(v)

    inst = dlg.locator("button", has_text="파일럿 시연").first
    if inst.count() == 0:
        print("✗ ④ 기준선 고르개에 인스턴스가 없다")
        return 1
    inst.click()
    page.wait_for_timeout(1500)
    boxes = dlg.locator('input[type="checkbox"]')
    if boxes.count() == 0:
        print("✗ ④ 고를 수 있는 판이 없다")
        return 1
    boxes.first.check()
    page.wait_for_timeout(800)
    fill_btn = dlg.locator("button", has_text="고른 판에서 채우기").first
    if fill_btn.count() == 0:
        print("✗ ④ 「고른 판에서 채우기」가 없다")
        return 1
    fill_btn.click()
    page.wait_for_timeout(2500)
    if not (_fill(dlg, BASE, "④") and _fill(dlg, DRIVERS, "④")):
        return 1
    page.wait_for_timeout(400)

    btn = dlg.locator("button", has_text="안건 만들기").first
    if btn.is_disabled():
        print("✗ ④ 「안건 만들기」가 잠겨 있다 — 화면이 말한 사유:")
        _echo(dlg.inner_text(), ("필요합니다", "고르십시오", "채워"))
        _shot(page, shots, "동선_03_잠김")
        return 1
    btn.click()
    page.wait_for_timeout(3500)
    _shot(page, shots, "동선_04_안건")

    body = dlg.inner_text()
    if "만들지 못" in body:
        print("✗ ④ 안건을 만들지 못했다")
        _echo(body, ("못", "없습니다"))
        return 1

    #: ★★★ 계보가 계약키로 나오면 §12 위반이다 — 읽는 사람이 무엇인지 모른다.
    leaked = [k for k in ("purchase_orders", "material_arrivals", "production_plans",
                          "financials", "shipments", "products")
              if k in body]
    if leaked:
        print(f"✗ ④ 계약키가 사람에게 그대로 나갔다: {leaked}")
        return 1

    print("· ④ 안건 만들어짐")
    _echo(body, ("관점", "책임자", "기한", "근거"))
    print("\n=== 파일럿 동선 4칸 전부 통과 ===")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="", help="화면을 남길 디렉터리(선택)")
    args = ap.parse_args()
    shots = Path(args.shots) if args.shots else None

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(FRONT, wait_until="domcontentloaded")
        login_as(page, ADMIN)
        code = run(page, shots)
        b.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
