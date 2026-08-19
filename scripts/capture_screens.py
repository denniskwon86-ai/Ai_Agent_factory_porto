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
DEFAULT_PASSWORD = "pass:"

VIEWPORTS = [(1280, 720), (1440, 900)]

# (파일이름표, 사용자, 경로)
# 경로는 `>` 로 나눈다. 첫 조각은 전체 메뉴에서 여는 화면, 그 뒤는 모달 안 좌측 레일 항목.
# 의사결정 센터·대내외 발간은 독립 화면이 아니라 협업 모달의 탭이므로 반드시 두 단계다.
SHOTS = [
    ("로그인-미인증", ANON, ""),
    ("경영홈-관리자", ADMIN, ""),
    #: [Wave H] 업무 데이터 준비 — 파일럿 동선 2~4칸
    ("업무데이터준비-관리자", ADMIN, "업무 데이터 준비"),
    ("시나리오-관리자", ADMIN, "시나리오 시뮬레이션"),
    ("의사결정안건-관리자", ADMIN, "의사결정 안건"),
    ("기준정보-관리자", ADMIN, "기준정보 마스터"),
    ("기준정보-일반", NORMAL, "기준정보 마스터"),
    ("지식허브-관리자", ADMIN, "지식 허브"),
    ("협업-관리자", ADMIN, "협업"),
    ("의사결정-관리자", ADMIN, "협업>의사결정 센터"),
    ("발간-관리자", ADMIN, "협업>대내외 발간"),
    # 이관 3/10 — 권한 세 갈래를 모두 본다. 개정 권한은 관리자에게만 있어야 한다.
    ("업무표준-관리자", ADMIN, "업무표준"),
    ("업무표준-일반", NORMAL, "업무표준"),
    ("업무표준-지침", ADMIN, "업무표준>업무지침"),
    # `#…` = 작업면 목록에서 실제 항목을 고른다. 선택 없는 빈 화면만 찍지 않는다.
    ("업무표준-규정상세", ADMIN, "업무표준>#품질 검증"),
    ("업무표준-연혁", ADMIN, "업무표준>#품질 검증>개정 연혁"),
    ("업무표준-고지문", ADMIN, "업무표준>#품질 검증>에이전트 고지문"),
    # 이관 4/10 — 조직·권한. 명부는 개인정보이므로 권한 세 갈래를 모두 본다.
    ("조직권한-관리자", ADMIN, "조직·권한"),
    ("조직권한-일반", NORMAL, "조직·권한"),
    ("조직권한-부서상세", ADMIN, "조직·권한>#마케팅"),
    ("조직권한-사용자", ADMIN, "조직·권한>사용자"),
    ("조직권한-내권한", NORMAL, "조직·권한>내 권한"),
    # 이관 5/10 — 거버넌스. «0건»과 «못 봤다»의 구분이 이 화면의 전부이므로 권한 세 갈래를 본다.
    ("거버넌스-관리자", ADMIN, "거버넌스"),
    ("거버넌스-일반", NORMAL, "거버넌스"),
    ("거버넌스-계약", ADMIN, "거버넌스>데이터 계약"),
    ("거버넌스-외부지표", ADMIN, "거버넌스>외부지표 준비도"),
    ("거버넌스-보정", ADMIN, "거버넌스>보정 목록"),
    # 이관 6/10 — 에이전트 통제소. 구성 변경은 관리자만이어야 한다.
    ("에이전트-관리자", ADMIN, "에이전트 통제소"),
    ("에이전트-일반", NORMAL, "에이전트 통제소"),
    ("에이전트-상세", ADMIN, "에이전트 통제소>#RFP 분석가"),
    ("에이전트-흐름", ADMIN, "에이전트 통제소>실행 흐름"),
    ("에이전트-템플릿", ADMIN, "에이전트 통제소>워크플로우 템플릿"),
    # 이관 8/10 — 스킬 개선안. 승인은 에이전트 행동 규칙을 영구히 바꾸므로 권한을 본다.
    ("스킬개선안-관리자", ADMIN, "스킬 진화"),
    ("스킬개선안-일반", NORMAL, "스킬 진화"),
    # 이관 9/10 — 전사 브리핑. 요약 화면이 다른 통제를 우회하지 않는지 본다.
    ("브리핑-관리자", ADMIN, "전사 브리핑"),
    ("브리핑-일반", NORMAL, "전사 브리핑"),
    ("브리핑-데이터상태", ADMIN, "전사 브리핑>데이터 상태"),
    ("브리핑-비용", ADMIN, "전사 브리핑>비용"),
    ("브리핑-일반-데이터상태", NORMAL, "전사 브리핑>데이터 상태"),
]


def close_dialogs(page: Page) -> None:
    for _ in range(3):
        btn = page.locator('[role="dialog"] button', has_text="닫기")
        if btn.count() == 0:
            break
        btn.first.click()
        page.wait_for_timeout(300)


def login_as(page: Page, uid: str) -> None:
    """현재 세션을 끝내고 지정 계정으로 로그인한다. 값이 없으면 로그인 화면에 머문다.

    2026-08-09 이후 사용자 전환 셀렉트는 제거됐고 로그인 세션이 제품의 유일한 진입점이다.
    캡처가 옛 전환기를 찾으면 화면 구현은 정상이어도 30초 뒤 실패하므로 실제 인증 계약을 따른다.
    미인증 사용자는 업무 화면을 볼 수 없으므로 권한별 패널 캡처가 아니라 로그인 화면 1장만 남긴다.
    """
    close_dialogs(page)
    logout = page.get_by_role("button", name="로그아웃")
    if logout.count():
        logout.first.click()
        page.get_by_role("button", name="로그인").wait_for(timeout=15_000)
    if not uid:
        return
    page.get_by_label("아이디").fill(uid)
    page.get_by_label("비밀번호").fill(DEFAULT_PASSWORD)
    page.get_by_role("button", name="로그인").click()
    page.get_by_role("button", name="로그아웃").wait_for(timeout=20_000)
    page.wait_for_timeout(1500)


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
        # `#텍스트` 는 **작업면 목록에서 항목을 고른다**는 뜻이다.
        # ⚠️ 선택이 없는 빈 화면만 찍으면 «실데이터가 어떻게 보이는가»를 한 번도 확인하지 못한다
        #   (교차검토 지적: 비어 있는 상태만으로 화면 검증을 끝내면 안 된다).
        if tab.startswith("#"):
            want = tab[1:].strip()
            row = dlg.locator(".hub-main button", has_text=want)
            if row.count() == 0:
                return False, f"작업면 목록에 «{want}» 가 없다"
            row.first.click()
            page.wait_for_timeout(2200)
            continue
        item = dlg.locator(".module-menu button", has_text=tab)
        if item.count() == 0:
            return False, f"모달 안에 «{tab}» 항목이 없다"
        item.first.click()
        page.wait_for_timeout(2000)
        # ⚠️ 상단 바 제목으로 판정하지 않는다. 허브마다 바가 모듈 이름을 고정으로 쓰기도 하고
        #   활성 화면을 따라가기도 한다 — 바를 기준으로 삼으면 «전환은 됐는데 실패» 로 잘못 잡힌다
        #   (업무표준 화면에서 실제로 그랬다). **탭이 선택됐다**는 사실 자체를 본다.
        active = dlg.locator('.module-menu button.active, .module-menu [aria-selected="true"]')
        got = active.first.inner_text().replace("\n", " ") if active.count() else "(없음)"
        if tab.replace(" ", "") not in got.replace(" ", ""):
            return False, f"«{tab}» 를 눌렀는데 활성 항목이 «{got[:24]}» 다"
    return True, ""


def measure(page: Page) -> dict:
    """캡처와 같은 시점의 사실을 함께 남긴다 — 이미지와 수치가 어긋나지 않게.

    ★★ 여기서 재는 항목은 **재승인 기준**(2026-08-04 지침)과 1:1 로 붙어 있다.
      이전에는 «넘침 0 · 12px 미만 0» 만 재서 전부 통과했는데, 사람이 이미지를 보자마자
      결함 6건이 나왔다. 측정이 통과하는데 제품이 아니면 그건 **재는 항목이 틀린 것**이다.
      그래서 지적받은 결함을 각각 기계가 재는 항목으로 바꿨다."""
    return page.evaluate("""() => {
      const dlg = document.querySelector('[role="dialog"]');
      const g = el => el ? getComputedStyle(el) : null;
      const layout = dlg && dlg.querySelector('.hub-layout');
      const card = dlg && dlg.querySelector('.panel');
      const doc = document.documentElement;
      const root = dlg || doc;

      // ① 레일 아이콘 중복 — 같은 모양이 두 번 나오면 아이콘이 구별에 쓸모가 없다.
      const icons = [...root.querySelectorAll('.module-menu [data-icon]')]
        .map(e => e.getAttribute('data-icon'));
      const dupIcons = [...new Set(icons.filter((v, i) => icons.indexOf(v) !== i))];
      // 아이콘이 aria 로 읽히면 스크린리더가 두 번 말한다.
      const iconsExposed = [...root.querySelectorAll('.module-menu [data-icon]')]
        .filter(e => e.getAttribute('aria-hidden') !== 'true').length;
      // 버튼이 전체 기능명을 말하는가.
      const railButtonsWithoutLabel = [...root.querySelectorAll('.module-menu button')]
        .filter(b => !(b.getAttribute('aria-label') || '').trim()).length;

      // ② 마지막 메뉴 항목 잘림 — 잘렸는데 스크롤바도 없으면 «끝»과 구분되지 않는다.
      const menu = root.querySelector('.module-menu');
      let railCut = null;
      if (menu) {
        const items = [...menu.querySelectorAll('button')];
        const mr = menu.getBoundingClientRect();
        const vis = b => {
          const r = b.getBoundingClientRect();
          return r.top >= mr.top - 1 && r.bottom <= mr.bottom + 1;
        };
        const half = b => {   // 일부만 보이는 항목 = 잘린 항목
          const r = b.getBoundingClientRect();
          return !vis(b) && r.bottom > mr.top && r.top < mr.bottom;
        };
        const active = items.find(b => b.classList.contains('active'));
        const barPx = menu.offsetWidth - menu.clientWidth;   // 실제로 자리를 차지한 스크롤바
        railCut = {
          항목수: items.length,
          온전히보임: items.filter(vis).length,
          잘린항목: items.filter(half).length,
          // ★ 지금 보고 있는 화면이 메뉴에 안 보이면 사용자는 자기 위치를 알 수 없다.
          활성항목보임: active ? vis(active) : null,
          스크롤가능: menu.scrollHeight > menu.clientHeight + 1,
          스크롤바폭: barPx,
        };
      }

      // ②-2 하단 안내 카드도 잘릴 수 있다. 잘렸으면 스크롤바가 보여야 한다.
      const card2 = root.querySelector('.inheritance-card');
      const cardCut = card2 ? {
        넘침: card2.scrollHeight > card2.clientHeight + 1,
        스크롤바폭: card2.offsetWidth - card2.clientWidth,
      } : null;

      // ③ 한 글자 고아 줄바꿈 — 마지막 줄에 글자가 하나만 남은 문단을 **글자 단위로** 찾는다.
      //    («다», «요», «됨» 같은 것. 종전 측정은 이걸 전혀 보지 않았다.)
      const orphans = [];
      root.querySelectorAll('p, small, b, dd, li, span').forEach(e => {
        if (e.children.length) return;
        const txt = (e.textContent || '').trim();
        if (txt.length < 8 || !/[가-힣]/.test(txt)) return;
        const node = e.firstChild;
        if (!node || node.nodeType !== 3) return;
        const rng = document.createRange();
        const tops = [];
        for (let i = 0; i < node.length; i++) {
          rng.setStart(node, i); rng.setEnd(node, i + 1);
          const r = rng.getBoundingClientRect();
          if (r.width === 0 && r.height === 0) continue;
          tops.push(Math.round(r.top));
        }
        if (!tops.length) return;
        const lastTop = tops[tops.length - 1];
        const lastLine = tops.filter(t => Math.abs(t - lastTop) <= 2).length;
        // 줄이 둘 이상인데 마지막 줄이 한 글자면 고아다(공백 제외 기준).
        const lineCount = new Set(tops).size;
        if (lineCount > 1 && lastLine === 1) orphans.push(txt.slice(0, 22));
      });

      // ④ Jarvis 죽은 공간 — 로그 안 내용이 끝난 뒤 남는 빈 높이.
      const log = root.querySelector('.jarvis-log');
      let jarvisDead = null;
      if (log) {
        const lr = log.getBoundingClientRect();
        const kids = [...log.children];
        const bottom = kids.length ? kids[kids.length - 1].getBoundingClientRect().bottom : lr.top;
        jarvisDead = Math.max(0, Math.round(lr.bottom - bottom));
      }

      // ④-2 Jarvis 근거 목록 잘림 — «무엇에 근거해 답했나»가 잘리면 답을 검증할 수 없다.
      //     레일 메뉴·안내 카드와 같은 유형의 결함이라 같은 방식으로 검사한다.
      const ev = root.querySelector('.jarvis-evidence');
      const evCut = ev ? {
        높이: Math.round(ev.clientHeight), 내용: Math.round(ev.scrollHeight),
        잘림: ev.scrollHeight > ev.clientHeight + 1,
        스크롤바폭: ev.offsetWidth - ev.clientWidth,
      } : null;

      // ⑤ 상단 바 노출 — 전체화면 작업공간이므로 뒤가 비쳐서는 안 된다.
      let barLeak = null;
      if (dlg) {
        const r = dlg.getBoundingClientRect();
        barLeak = {
          위: Math.round(r.top), 아래: Math.round(innerHeight - r.bottom),
          왼: Math.round(r.left), 오른: Math.round(innerWidth - r.right),
        };
      }

      // ⑥ 배너의 «0건/0개» 오해 표현.
      const banners = [...root.querySelectorAll('.afs-banner')].map(b => b.innerText.trim());
      const zeroTalk = banners.filter(t => /(^|[^0-9])0\\s*(건|개)/.test(t));

      // ⑦ 내부 식별자 노출 — `knowledge/packs` 처럼 «영문/영문» 슬러그가 사용자에게 보이면
      //    뜻이 없다. 제목·문맥 자리에서만 검사한다(코드·type_id 는 실제 식별자이므로 정상).
      const slugSpots = [...root.querySelectorAll(
        '.jarvis-context h3, .jarvis-zero-ctx dd, .screen-head h2, .module-intro h1')];
      const slugLeaks = slugSpots
        .map(e => (e.textContent || '').trim())
        .filter(t => /^[a-z0-9_]+\\/[a-z0-9_]+$/.test(t));

      // 12px 미만 본문(영문 kicker·코드는 제외).
      let small = [];
      root.querySelectorAll('*').forEach(e => {
        const t = (e.textContent || '').trim();
        if (!t || e.children.length) return;
        // ⚠️ 라이브러리가 넣는 **저작자 표시**는 우리 본문이 아니다(ReactFlow 어트리뷰션).
        //   숨기는 것은 라이선스 조건에 걸리므로 지우지 않고 검사에서 제외한다.
        if (e.closest('.react-flow__attribution')) return;
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (/^[A-Z0-9 ·—–_./]{1,24}$/.test(t)) return;
        if (parseFloat(getComputedStyle(e).fontSize) < 12) small.push(t.slice(0, 14));
      });

      return {
        모달: !!dlg,
        열구성: layout ? g(layout).gridTemplateColumns : null,
        셸배경: layout ? g(layout).backgroundColor : null,
        카드배경: card ? g(card).backgroundColor : null,
        본문색: dlg ? g(dlg).color : null,
        글꼴: dlg ? g(dlg).fontFamily.slice(0, 18) : null,
        Jarvis: !!(dlg && dlg.querySelector('.jarvis-rail')),
        문서넘침: doc.scrollWidth - doc.clientWidth,
        작은글자: small.slice(0, 4),
        아이콘: icons,
        아이콘중복: dupIcons,
        아이콘노출: iconsExposed,
        라벨없는버튼: railButtonsWithoutLabel,
        레일잘림: railCut,
        안내카드: cardCut,
        고아줄바꿈: orphans.slice(0, 6),
        Jarvis빈공간: jarvisDead,
        Jarvis근거: evCut,
        모달바깥여백: barLeak,
        배너: banners.map(t => t.slice(0, 46)),
        영건표현: zeroTalk.map(t => t.slice(0, 40)),
        슬러그노출: slugLeaks,
      };
    }""")


# 재승인 기준(2026-08-04 지침) — 하나라도 어기면 «통과»라고 쓰지 않는다.
def gate_failures(m: dict) -> list[str]:
    out: list[str] = []
    if m.get("아이콘중복"):
        out.append(f"레일 아이콘 중복: {m['아이콘중복']}")
    if m.get("아이콘노출"):
        out.append(f"아이콘이 스크린리더에 읽힌다: {m['아이콘노출']}개")
    if m.get("라벨없는버튼"):
        out.append(f"aria-label 없는 레일 버튼 {m['라벨없는버튼']}개")
    cut = m.get("레일잘림") or {}
    if cut.get("활성항목보임") is False:
        out.append("지금 보고 있는 화면이 레일에서 보이지 않는다(활성 항목이 스크롤 밖)")
    if cut.get("잘린항목"):
        # 일부만 보이는 항목은 «끝»과 구분되지 않는다. 스크롤바가 있어도 잘림 자체를 허용하지 않는다.
        out.append(f"레일 항목 {cut['잘린항목']}개가 반쯤 잘려 보인다")
    if cut.get("스크롤가능") and int(cut.get("스크롤바폭") or 0) <= 0:
        out.append("레일이 스크롤되는데 스크롤바가 자리를 차지하지 않는다(항목이 더 있는지 알 수 없다)")
    card = m.get("안내카드") or {}
    if card.get("넘침") and int(card.get("스크롤바폭") or 0) <= 0:
        out.append("하단 안내 카드가 잘렸는데 스크롤바가 없다(다 읽은 줄 안다)")
    if m.get("고아줄바꿈"):
        out.append(f"한 글자 고아 줄바꿈: {m['고아줄바꿈']}")
    evc = m.get("Jarvis근거") or {}
    if evc.get("잘림") and int(evc.get("스크롤바폭") or 0) <= 0:
        out.append(f"Jarvis 근거가 잘렸는데 스크롤바가 없다({evc.get('높이')}/{evc.get('내용')}px)")
    dead = m.get("Jarvis빈공간")
    if isinstance(dead, int) and dead > 80:
        out.append(f"Jarvis 로그에 빈 공간 {dead}px")
    leak = m.get("모달바깥여백") or {}
    if any(int(v or 0) > 0 for v in leak.values()):
        out.append(f"모달 밖으로 배경이 비친다: {leak}")
    if m.get("영건표현"):
        out.append(f"배너에 «0건» 오해 표현: {m['영건표현']}")
    if m.get("슬러그노출"):
        out.append(f"내부 식별자가 제목·문맥에 노출: {m['슬러그노출']}")
    if m.get("문서넘침"):
        out.append(f"문서 가로 넘침 {m['문서넘침']}px")
    if m.get("작은글자"):
        out.append(f"12px 미만 본문: {m['작은글자']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/uiux/screenshots")
    ap.add_argument("--only", default=None, help="이름표에 이 문자열이 든 항목만")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = [s for s in SHOTS if not args.only or args.only in s[0]]

    verdicts: list[tuple[str, list[str]]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for w, h in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": w, "height": h},
                                      device_scale_factor=1)
            page = ctx.new_page()
            errors: list[str] = []
            # ⚠️ «403 Forbidden» 리소스 오류는 **통제가 작동한 흔적**이다(익명이 명부를 못 받는
            #   것이 정상이다). 그것까지 결함으로 세면 통제를 켤 때마다 게이트가 붉어지고,
            #   그러면 사람이 게이트를 무시하기 시작한다. 그 외 오류는 그대로 잡는다.
            def _console(m):
                if m.type != "error":
                    return
                if "403" in m.text and "Failed to load resource" in m.text:
                    return
                errors.append(m.text)
            page.on("console", _console)
            # 네이티브 alert/confirm 은 화면 전체를 막는다. 자동으로 닫되 결함으로 남긴다.
            page.on("dialog", lambda d: (errors.append(f"네이티브 대화상자: {d.message}"), d.dismiss()))
            # ⚠️ `networkidle` 은 쓰지 않는다 — 앱이 상태를 계속 폴링해서 idle 이 오지 않는다.
            page.goto(FRONT, wait_until="domcontentloaded", timeout=60_000)
            page.get_by_role("button", name="로그인").wait_for(timeout=30_000)

            for tag, uid, label in shots:
                try:
                    login_as(page, uid)
                    if uid:
                        opened, why = open_panel(page, label)
                    else:
                        opened = page.get_by_role("button", name="로그인").count() == 1
                        why = "" if opened else "미인증 로그인 화면이 아니다"
                    m = measure(page)
                    path = out / f"{tag}_{w}x{h}.png"
                    page.screenshot(path=str(path))
                    who = f"{tag} {w}x{h}"
                    if not opened:
                        verdicts.append((who, [f"이 이미지는 이 화면이 아니다 — {why}"]))
                        print(f"[{w}x{h}] {tag:18s} → {path}  ⚠️ {why}")
                        continue
                    bad = gate_failures(m) if label else []      # 런처는 이관 대상이 아니다
                    verdicts.append((who, bad))
                    print(f"[{w}x{h}] {tag:18s} → {path}  {'✗ ' + str(len(bad)) + '건' if bad else '✓'}")
                    print(f"          {m}")
                    for b in bad:
                        print(f"          ✗ {b}")
                except Exception as e:                       # 한 화면 실패가 전체를 죽이지 않게
                    verdicts.append((f"{tag} {w}x{h}", [f"{type(e).__name__}: {e}"]))
                    print(f"[{w}x{h}] {tag:18s} ✗ 실패: {type(e).__name__}: {e}")
            if errors:
                verdicts.append((f"콘솔 {w}x{h}", [f"콘솔 오류 {len(errors)}건: {errors[:2]}"]))
                print(f"[{w}x{h}] 콘솔 오류 {len(errors)}건: {errors[:3]}")
            ctx.close()
        browser.close()

    print(f"\n캡처 위치: {out.resolve()}")
    failed = [(w, b) for w, b in verdicts if b]
    if failed:
        print(f"\n=== 재승인 기준 미달 {len(failed)}건 ===")
        for who, bad in failed:
            for b in bad:
                print(f"  ✗ {who}: {b}")
        return 1
    print(f"\n=== 재승인 기준 전 항목 통과 ({len(verdicts)}개 화면) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
