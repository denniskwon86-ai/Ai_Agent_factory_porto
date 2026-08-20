"""★★★ [시연 ②칸] Javis 상담을 **실제로 눌러** 본다.

⚠️⚠️ **이 스크립트는 LLM 을 부른다.** 이 저장소의 다른 동선 스크립트는 전부 LLM 0콜이다 —
  여기만 다르다. 돌리기 전에 승인을 확인할 것(최초 승인: Supervisor, 2026-08-20).

## 무엇을 보는가

로드맵 §3 의 2번 칸 질문을 그대로 던지고 **넷**을 본다:

    ① 답이 오는가 — 엔진 실패가 «성공» 으로 나가지 않는가
    ② UI 설계서 §7.2 의 **여섯 머리말**이 다 있는가
    ③ 그 머리말이 **화면 요소로 파싱**되는가(평문 덩어리로 떨어지면 목적이 사라진다)
    ④ 「부족하거나 확인하지 못한 데이터」 절이 **강조**되는가

★★★ ④ 가 핵심이다. 모르는 것을 아는 것처럼 말하는 답변은 그럴듯할수록 위험하고,
  이 저장소가 화면 전체에서 «조회 실패 ≠ 0건» 으로 지켜 온 규칙이 비서 답변에서만
  무너지면 아무 의미가 없다.

## 이 스크립트가 실제로 잡은 것 (2026-08-20)

· 엔진이 LLM 실패를 삼켜 **HTTP 200 «success»** 로 나가고 있었다
· 머리말 파서가 본문을 한 글자 앞에서 잘라 「가:」「각:」 같은 조각이 붙었다
· 모델이 `**핵심 답변:**` 처럼 굵게 보내면 파서가 통째로 실패했다
· 비서가 우리 준비도를 **하나도 모른 채** 「확인할 수 없습니다」만 답했다

전제: 프런트(5173)·백엔드가 떠 있고, 백엔드 환경에 LLM 키가 있어야 한다.
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

#: 로드맵 §3 의 2번 칸이 정한 질문.
QUESTION = "원료 도입계획을 관리하려면 무엇이 필요한가?"

#: ★★★ UI 설계서 §7.2 가 정한 **여섯 머리말**. 이것이 없으면 답은 그럴듯하지만
#:   검증할 수 없다 — 특히 ④ 가 없으면 비서는 모르는 것도 아는 것처럼 말한다.
HEADS = ("핵심 답변", "왜 그렇게 판단했는가", "근거와 기준시각",
         "부족하거나 확인하지 못한 데이터", "선택 가능한 다음 행동",
         "실행 시 영향과 승인 필요 여부")


def run(page) -> int:
    logs = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:140]}"))

    close_dialogs(page)
    #: ⚠️ 경영홈의 Javis 입력칸은 placeholder 가 「예: 이 앱은 어떤 자료를…」다.
    #:   「질문」이라는 낱말로 찾으면 못 찾는다(실제로 못 찾았다).
    box = page.locator("textarea").first
    if box.count() == 0:
        print("✗ Javis 입력칸을 찾지 못했다")
        return 1
    box.fill(QUESTION)
    send = page.locator("button", has_text="보내기").first
    if send.count() == 0:
        print("✗ 「보내기」가 없다")
        return 1
    send.click()

    #: ⚠️ LLM 응답은 느리다. 넉넉히 기다리되 **무한정은 아니다** — 안 오면 안 온 것이다.
    reply = ""
    for _ in range(40):
        page.wait_for_timeout(3000)
        body = page.inner_text("body")
        if any(h in body for h in HEADS) or "받지 못했습니다" in body:
            reply = body
            break
    if not reply:
        print("✗ 2분 안에 답이 오지 않았다")
        for line in logs[-10:]:
            print("   ", line)
        return 1

    if OUT is not None:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT / "자비스_상담.png"), full_page=True)

    if "받지 못했습니다" in reply:
        print("✗ 비서 응답 실패:")
        for line in reply.splitlines():
            if "받지 못했" in line:
                print("   ", line.strip()[:160])
        return 1

    got = [h for h in HEADS if h in reply]
    print(f"· 답변 도착 — 여섯 머리말 중 {len(got)}개 확인")
    for h in HEADS:
        print(f"   {'●' if h in reply else '✗'} {h}")

    #: ★★★ **④ 가 가장 중요하다.** 「부족하거나 확인하지 못한 데이터」를 적지 않으면
    #:   비서는 모르는 것도 아는 것처럼 말하고, 이 저장소가 화면 전체에서 지켜 온
    #:   «조회 실패 ≠ 0건» 규칙이 비서 답변에서만 무너진다.
    if "부족하거나 확인하지 못한 데이터" not in reply:
        print("✗ ④ 「부족하거나 확인하지 못한 데이터」가 없다 — 모르는 것을 안다고 말할 자리다")
        return 1

    #: ★★★ 머리말이 **화면 요소로 파싱됐는지** 본다. 평문 덩어리로 떨어지면 ④ 를
    #:   강조하는 이 화면의 목적이 사라진다(모델이 `**굵게**` 로 보내면 그렇게 된다).
    secs = page.locator(".jarvis-answer section")
    print(f"· 파싱된 절 {secs.count()}개")
    if secs.count() < 4:
        print("✗ 답이 평문으로 떨어졌다 — 머리말 파서가 모델 출력 형식을 못 읽는다")
        return 1
    gap = page.locator(".jarvis-answer section.gap")
    if gap.count() == 0:
        print("✗ ④ 「부족하거나 확인하지 못한 데이터」 절이 강조되지 않았다")
        return 1

    #: 답 본문을 조금 보여 준다(사람이 읽고 판단할 수 있게).
    print("\n=== 답변(일부) ===")
    started = False
    shown = 0
    for line in reply.splitlines():
        t = line.strip()
        if t.startswith("핵심 답변"):
            started = True
        if started and t:
            print("   ", t[:130])
            shown += 1
            if shown >= 22:
                break
    return 0 if len(got) >= 4 else 1


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
