"""Render actual home components with isolated layout fixtures; never log in or call the API.

Build: node frontend/scripts/build-enterprise-layout-fixture.mjs
Run: venv/Scripts/python.exe scripts/check_enterprise_responsive.py
Uses an in-memory HTTP response route; no service/listener or production session is needed.
"""
from pathlib import Path
import json

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'tmp/home-responsive-layout'
SHOTS = BUILD / 'screenshots'


def serve(route):
    from urllib.parse import urlparse, unquote
    import mimetypes
    url = urlparse(route.request.url)
    if url.hostname != 'layout.test':
        route.abort()
        return
    rel = unquote(url.path).lstrip('/')
    base = ROOT / 'frontend/public' if rel.startswith(('brand/', 'fonts/')) else BUILD
    file = (base / rel).resolve()
    if file.is_relative_to(base.resolve()) and file.is_file():
        route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
    else:
        route.fulfill(status=404, body='Fixture resource not found')


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(reduced_motion='reduce')
        context.route('**/*', serve)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width, height in [(1920, 1080), (1536, 864), (1440, 770), (1366, 768), (1280, 720), (1280, 600), (1152, 648), (1024, 768), (800, 700), (390, 844)]:
            for variant in ['', '?long&many']:
                page.set_viewport_size({'width': width, 'height': height})
                page.goto('http://layout.test/tests/enterprise-layout.fixture.html' + variant)
                page.wait_for_selector('.process')
                page.wait_for_function("document.querySelectorAll('.decision').length === 16")
                page.evaluate('document.fonts.ready')
                metrics = page.evaluate('''() => {
                    const rect = s => document.querySelector(s).getBoundingClientRect();
                    const doc = document.documentElement;
                    const overlay = rect('.overlay-strip'), focus = rect('.focus-panel');
                    const queue = rect('.queue'), tools = rect('.rail-tools');
                    const body = rect('.atlas-body'), input = rect('.atlas-input');
                    const slots = [...document.querySelectorAll('.overlay-slot')];
                    const nodes = [...document.querySelectorAll('.process')];
                    const aligned = slots.every((e, i) => Math.abs(e.getBoundingClientRect().x - nodes[i].getBoundingClientRect().x) < 1);
                    return { width: innerWidth, height: innerHeight, docWidth: doc.scrollWidth,
                        docHeight: doc.scrollHeight, gap: focus.top - overlay.bottom,
                        toolsBottom: tools.bottom, inputBottom: input.bottom,
                        queueClear: queue.bottom <= tools.top + 1,
                        inputClear: body.bottom <= input.top + 1, aligned,
                        focusInside: rect('.focus-copy').right <= focus.right + 1,
                        mapScrollable: document.querySelector('.thread-map-scroll').scrollWidth > document.querySelector('.thread-map-scroll').clientWidth,
                    };
                }''')
                assert metrics['docWidth'] <= width + 1, metrics
                assert metrics['gap'] >= 12, metrics
                assert metrics['queueClear'] and metrics['inputClear'] and metrics['aligned'] and metrics['focusInside'], metrics
                if width > 1100:
                    assert metrics['docHeight'] <= height + 1, metrics
                    assert metrics['toolsBottom'] <= height and metrics['inputBottom'] <= height, metrics
                if variant and width <= 1536:
                    assert metrics['mapScrollable'], metrics
                if not variant and width in (1920, 1440, 1280, 390):
                    page.screenshot(path=str(SHOTS / f'home-{width}x{height}.png'), full_page=True)
                # Long focus text must not consume its action row; button stays clickable.
                page.locator('.focus-actions button').last.click()
                page.locator('.process').first.click()
                assert page.locator('.focus-content h3').inner_text() == '원료조달'
                page.locator('.view-switch button').first.click()
                assert page.locator('.overlay-item.data').first.get_attribute('aria-hidden') == 'true'
                page.locator('#atlas-q').fill('레이아웃 입력 확인')
                page.locator('.canvas').evaluate('(el) => el.scrollTop = 0')
                page.locator('.thread-map-scroll').evaluate('(el) => el.scrollLeft = 0')
                page.locator('.atlas-body').evaluate('(el) => el.scrollTop = 0')
                page.evaluate('window.scrollTo(0,0)')
                results.append({**metrics, 'long': bool(variant)})
        assert not errors, errors
        context.close()
        browser.close()
    (BUILD / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} responsive layout cases passed; fixture only, no authentication/API/DB calls.')


if __name__ == '__main__':
    main()
