"""Open the dashboard in a real browser, start a camera, and check the feed actually renders.

HTTP 200 on the MJPEG endpoint does not prove the browser decoded a frame, so this asserts
on the rendered element (naturalWidth/naturalHeight) and captures a screenshot.
"""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8791/'
CAM = sys.argv[2] if len(sys.argv) > 2 else 'mall_atrium'
SHOT = sys.argv[3] if len(sys.argv) > 3 else '/tmp/dash.png'

with sync_playwright() as p:
    browser = p.chromium.launch(args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1500, 'height': 1150})
    errors = []
    page.on('console', lambda m: errors.append(f'{m.type}: {m.text}') if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

    page.goto(URL, wait_until='networkidle')
    page.wait_for_timeout(2500)

    cameras = page.eval_on_selector_all('#camera option', 'els => els.map(e => e.textContent)')
    print('camera dropdown:', cameras)

    page.select_option('#camera', CAM)
    page.wait_for_timeout(600)
    print('selected:', page.input_value('#camera'))

    page.click('#start')
    print('clicked start, waiting for frames…')
    page.wait_for_timeout(14000)

    state = page.evaluate("""() => {
        const img = document.getElementById('feed');
        const ph  = document.getElementById('placeholder');
        return {src: (img.getAttribute('src')||'').slice(0,60),
                naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight,
                complete: img.complete,
                placeholderHidden: ph.hidden,
                status: (document.getElementById('status')||{}).textContent};
    }""")
    print('feed element:', state)
    page.screenshot(path=SHOT, full_page=True)
    print('screenshot ->', SHOT)
    if errors:
        print('console errors:')
        for e in errors[:8]:
            print('  ', e)
    else:
        print('console errors: none')
    browser.close()