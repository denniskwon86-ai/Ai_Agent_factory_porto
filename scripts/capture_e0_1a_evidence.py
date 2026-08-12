"""[E0-1A] Preview 샌드박스가 **외부 호스트 없이** 동작한다는 것을 화면으로 남긴다.

## 무엇을 증명하는가

Preview 의 CSP 에서 `cdn.tailwindcss.com` · `unpkg.com` 을 지웠다(E0-1A). 그 상태에서
  ① 생성된 앱이 **여전히 정상 렌더**되는가 — 격리가 제품을 죽이지 않았는가
  ② 외부 `<script src>` 가 **정말 막히는가**
를 한 번에 본다.

⚠️⚠️ **②는 대조군 없이는 무의미하다.** 네트워크가 없어도 「차단됨」이 나온다. 그래서 같은
  샌드박스를 CSP 만 빼고 한 번 더 돌린다(`?nocsp=1`). 그쪽이 「로드됨」이어야 비로소
  «CSP 가 막았다» 고 말할 수 있다 — 2026-08-09 에 이것을 안 하고 「내 탓이 아니다」라고
  결론지었다가 217건을 남의 탓으로 돌릴 뻔했다.

## 왜 playwright 인가

`computer{screenshot}` 은 Browser 패널이 표시돼 있지 않으면
"the Browser pane is not displayed" 로 실패한다. 프레임을 합성하는 주체가 패널이기
때문이다. 그래서 **합성 주체를 바꾼다** — `scripts/capture_screens.py` 와 같은 방법이다.

## 사용

    venv/Scripts/python.exe scripts/capture_e0_1a_evidence.py [출력디렉터리]

전제: 프론트(5175 · frontend-verify)와 백엔드(8080)가 이미 떠 있어야 한다.
⚠️ 탐침 HTML 은 이 스크립트가 `frontend/public/` 에 **만들었다가 반드시 지운다.**
  거기 남겨 두면 배포물에 실려 나간다.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FRONT = "http://localhost:5175"
BACK = "http://127.0.0.1:8080"
USER = "hikwon@lsmnm.com"          # 승인된 예시 계정만 쓴다
#: A-1 완주 프로젝트 — `frontend_code_summary` 14KB 가 실제로 들어 있다.
PROJECT = "test_a1_unitconv"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/uiux/screenshots")
#: 탐침은 프론트가 서빙해야 하므로 public/ 에 둔다. **끝나면 지운다**(아래 finally).
PROBE_PATH = Path("frontend/public/__e0_probe.html")
PROBE_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>E0-1A 벤더 탐침</title></head>
<body style="font-family:sans-serif;padding:16px;margin:0">
<h1 style="font-size:15px;margin:0 0 8px">E0-1A — Preview 샌드박스 벤더/CSP 탐침</h1>
<pre id="out" style="background:#f1f5f9;padding:12px;white-space:pre-wrap;font-size:13px;margin:0 0 8px">측정 중…</pre>
<div id="host" style="border:1px solid #cbd5e1;height:120px"></div>
<script>
(async function () {
  var out = document.getElementById('out');
  var S = '<scr' + 'ipt>', E = '</scr' + 'ipt>';
  var noCsp = /[?&]nocsp=1/.test(location.search);
  try {
    var files = ['/preview-vendor/tailwind.js', '/preview-vendor/runtime.js', '/preview-vendor/babel.js'];
    var texts = await Promise.all(files.map(function (f) {
      return fetch(f).then(function (r) {
        if (!r.ok) throw new Error(f + ' → HTTP ' + r.status);
        return r.text();
      });
    }));
    var sizes = texts.map(function (t, i) { return files[i].split('/').pop() + ' ' + Math.round(t.length / 1024) + 'KB'; });
    var vendor = texts.map(function (t) { return S + t.replace(/<\/(script)/gi, '<\\/$1') + E; }).join('\n');

    // 제품 템플릿과 **같은 CSP**. 호스트가 하나도 없다.
    var csp = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline';"
            + " img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none';"
            + " object-src 'none'; frame-src 'none'; base-uri 'none';";

    var body = S + [
      '(function(){',
      '  var r = {react:0,reactDom:0,babel:0,lucide:0,jsx:"",tailwind:0,svg:0,ext:"대기"};',
      '  var sent = false;',
      '  function send(){ if(sent) return; sent = true; parent.postMessage({probe:r}, "*"); }',
      '  try {',
      '    r.react    = typeof React !== "undefined" && typeof React.createElement === "function" ? 1 : 0;',
      '    r.reactDom = typeof ReactDOM !== "undefined" && typeof ReactDOM.createRoot === "function" ? 1 : 0;',
      '    r.babel    = typeof Babel !== "undefined" ? 1 : 0;',
      '    r.lucide   = (typeof lucide !== "undefined" && lucide.Check) ? 1 : 0;',
      '    var jsxSrc = "function App(){ return <div className=\\"p-4 text-2xl font-bold\\">JSX 컴파일됨 <Check size={18} /></div>; }";',
      '    var compiled = Babel.transform(jsxSrc, {presets:["react"]}).code;',
      '    var fn = new Function("React","Check", compiled + "; return App;");',
      '    ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(fn(React, lucide.Check)));',
      '  } catch(e) { r.jsx = "ERR " + e.message; send(); return; }',
      '  setTimeout(function(){',
      '    try {',
      '      var el = document.querySelector("#root div");',
      '      r.jsx = el ? (el.textContent || "").trim() : "(렌더 안 됨)";',
      '      var cs = el ? getComputedStyle(el) : null;',
      '      r.tailwind = (cs && cs.fontWeight === "700") ? 1 : 0;',
      '      r.svg = document.querySelectorAll("#root svg").length;',
      '    } catch(e) { r.jsx = "ERR2 " + e.message; }',
      '    var s = document.createElement("script");',
      '    s.onload  = function(){ r.ext = "로드됨"; send(); };',
      '    s.onerror = function(){ r.ext = "차단됨"; send(); };',
      '    s.src = "https://unpkg.com/react@18/umd/react.production.min.js";',
      '    document.head.appendChild(s);',
      '    setTimeout(send, 4000);',
      '  }, 700);',
      '})();'
    ].join('\n') + E;

    var doc = '<!DOCTYPE html><html><head><meta charset="utf-8">'
            + (noCsp ? '' : '<meta http-equiv="Content-Security-Policy" content="' + csp + '">')
            + vendor + '</head><body><div id="root"></div>' + body + '</body></html>';

    var f = document.createElement('iframe');
    f.setAttribute('sandbox', 'allow-scripts');
    f.style.cssText = 'width:100%;height:100%;border:0';
    window.addEventListener('message', function (ev) {
      if (!ev.data || !ev.data.probe) return;
      var r = ev.data.probe;
      out.textContent = [
        (noCsp ? '■ 대조군 — CSP 를 뺀 같은 샌드박스' : '■ 제품과 같은 CSP (호스트 0개)'),
        '벤더(우리 출처에서 읽음): ' + sizes.join(' · '),
        'React ' + (r.react ? 'OK' : '없음')
          + '   ReactDOM ' + (r.reactDom ? 'OK(createRoot)' : '없음')
          + '   Babel ' + (r.babel ? 'OK' : '없음')
          + '   lucide-react ' + (r.lucide ? 'OK' : '없음'),
        'JSX 컴파일·렌더 결과 : ' + r.jsx,
        'lucide 아이콘 SVG    : ' + r.svg + '개',
        'Tailwind font-bold   : ' + (r.tailwind ? '적용됨' : '안 먹음'),
        '',
        '외부 <script src> (unpkg.com) : ' + r.ext
          + (noCsp ? '   ← 대조군이므로 「로드됨」이어야 한다'
                   : '   ← 「차단됨」이어야 한다')
      ].join('\n');
    });
    document.getElementById('host').appendChild(f);
    f.srcdoc = doc;
  } catch (e) {
    out.textContent = '탐침 실패: ' + e.message;
  }
})();
</script>
</body>
</html>
"""


def mint_token() -> str:
    """세션을 API 로 발급받는다 — 폼에 비밀번호를 타이핑하지 않는다."""
    req = urllib.request.Request(
        f"{BACK}/api/v1/auth/login",
        data=json.dumps({"user_id": USER, "password": "pass:"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode())
    return str((d.get("data") or d).get("token") or "")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    PROBE_PATH.write_text(PROBE_HTML, encoding="utf-8")
    try:
        return _run()
    finally:
        #: ⚠️ 예외가 나도 지운다. 남으면 `npm run build` 가 배포물에 넣는다.
        PROBE_PATH.unlink(missing_ok=True)


def _run() -> int:
    token = mint_token()
    if not token:
        print("로그인 실패 — 세션을 못 받았습니다."); return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        #: 문서가 뜨기 **전에** 토큰을 심는다. 뜬 뒤에 심으면 첫 렌더가 로그인 화면이 된다.
        ctx.add_init_script(
            f"try{{localStorage.setItem('factory.sessionToken','{token}');"
            f"localStorage.removeItem('factory.actingUser');}}catch(e){{}}")
        page = ctx.new_page()
        #: ⚠️ `networkidle` 을 쓰지 않는다 — 앱이 계속 폴링해서 idle 이 오지 않는다.
        page.goto(FRONT, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)

        # ── Software Factory 로 들어가 프로젝트를 연다 ────────────────────────
        page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')]
            .find(e => /전체 메뉴/.test(e.textContent||'')); if (b) b.click();
        }""")
        page.wait_for_timeout(600)
        page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')]
            .find(e => /업무 SW 만들기/.test(e.textContent||'')); if (b) b.click();
        }""")
        page.wait_for_timeout(2000)
        #: ⚠️ **코드가 있는 프로젝트를 골라야 한다.** 목록 첫 항목(demo-todo-app)은
        #   `frontend_code_summary` 가 없어 샌드박스가 「렌더링 대기 중」에서 멈춘다 —
        #   그 화면을 증거라고 올리면 «미리보기가 깨졌다» 로 읽힌다(실제로 한 번 그랬다).
        page.fill('input[placeholder="이름·ID 로 찾기"]', PROJECT)
        page.wait_for_timeout(1200)
        page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')]
            .find(e => (e.textContent||'').trim() === '열기'); if (b) b.click();
        }""")
        page.wait_for_timeout(2500)

        # 실시간 샌드박스 탭을 확실히 활성화
        page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')]
            .find(e => /실시간 샌드박스/.test(e.textContent||'')); if (b) b.click();
        }""")
        #: 벤더 4MB 인라인 + Babel 컴파일 + 렌더까지 넉넉히 기다린다.
        page.wait_for_selector('iframe[title="AI Factory Preview Sandbox"]', timeout=30_000)
        page.wait_for_timeout(9000)

        # ── 증거 ① 계측값 ────────────────────────────────────────────────────
        page.wait_for_timeout(4000)
        facts = page.evaluate("""() => {
          const f = document.querySelector('iframe[title="AI Factory Preview Sandbox"]');
          const d = f ? (f.srcdoc || '') : '';
          const csp = (d.match(/Content-Security-Policy" content="([^"]*)"/)||[])[1] || '(없음)';
          return {
            srcdocKB: Math.round(d.length/1024),
            scriptSrcTags: (d.match(/<script[^>]*\\ssrc=/gi)||[]).length,
            cdnOutsideComments: (d.replace(/<!--[\\s\\S]*?-->/g,'')
                                  .match(/https?:\\/\\/(unpkg\\.com|cdn\\.tailwindcss\\.com|cdn\\.jsdelivr\\.net)/g)||[]).length,
            csp
          };
        }""")
        print("── srcDoc 계측 ──")
        for k, v in facts.items():
            print(f"  {k}: {v}")

        # ── 증거 ② 화면 ──────────────────────────────────────────────────────
        page.screenshot(path=str(OUT / "e0_1a_preview_sandbox_1440x900.png"))
        el = page.query_selector('iframe[title="AI Factory Preview Sandbox"]')
        if el:
            el.screenshot(path=str(OUT / "e0_1a_preview_sandbox_iframe.png"))

        # ── 증거 ③ 대조군 탐침(CSP 켬 / 뺌) ─────────────────────────────────
        for suffix, url in (("csp_on", "/__e0_probe.html"), ("csp_off", "/__e0_probe.html?nocsp=1")):
            page.goto(FRONT + url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_function(
                    "() => !/측정 중/.test(document.getElementById('out').textContent)",
                    timeout=30_000)
            except Exception:
                pass
            page.wait_for_timeout(500)
            print(f"── 탐침 {suffix} ──")
            print(page.inner_text("#out"))
            page.screenshot(path=str(OUT / f"e0_1a_probe_{suffix}.png"), full_page=True)

        ctx.close(); browser.close()

    print(f"\n캡처 위치: {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
