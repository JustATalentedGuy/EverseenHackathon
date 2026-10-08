"""End-to-end browser check for the unified dashboard.

Requires the local server on port 8791 and Playwright/Chrome (research extras).
Temporarily adds one test zone, starts real inference, takes screenshots,
then restores the original configuration in a finally block.
"""
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8791'
OUT = ROOT / 'runs' / 'ui_checks'
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    saved = page.request.get(BASE + '/api/config').json()
    try:
        response = page.goto(BASE, wait_until='networkidle')
        assert response.status == 200
        expect(page.locator('#camera option')).to_have_count(len(saved['cameras']))
        page.locator('#snapshot').click()
        page.wait_for_function('document.querySelector("#feed").naturalWidth > 0', timeout=30000)
        page.locator('#zoneName').fill('Temporary browser test zone')
        page.locator('#mark').click()
        rect = page.locator('#canvas').bounding_box()
        for x, y in [(0.35, .45),(.65, .45),(.65,.72),(.35,.72)]:
            page.mouse.click(rect['x'] + x*rect['width'], rect['y'] + y*rect['height'])
        page.locator('#finish').click()
        expect(page.locator('#zones')).to_contain_text('Temporary browser test zone', timeout=15000)
        page.locator('#start').click()
        page.wait_for_function('document.querySelector("#statePill").textContent === "live"', timeout=45000)
        page.wait_for_function('Number(document.querySelector("#frameInfo").textContent.match(/\\d+/)?.[0] || 0) > 0',
                               timeout=50000)
        expect(page.locator('#csv')).to_be_visible()
        page.screenshot(path=str(OUT / 'unified_dashboard_desktop.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT / 'unified_dashboard_mobile.png'), full_page=True)
        page.locator('#stop').click()
        expect(page.locator('#statePill')).to_contain_text('stopped', timeout=15000)
        assert not errors, errors
        print('Unified dashboard browser check passed. Screenshots in', OUT)
    finally:
        page.request.put(BASE + '/api/config', data=saved)
        browser.close()
