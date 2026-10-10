"""Submission-level Chrome acceptance for store overview, assistant and floor plan.

Never edits the camera/floor config or sends WhatsApp messages. The demo server
must be running (default http://127.0.0.1:8897). Chrome/Playwright are required.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('EVERSEEN_TEST_URL', 'http://127.0.0.1:8897')
OUT = ROOT / 'runs' / 'final_acceptance'
OUT.mkdir(parents=True, exist_ok=True)
results = []

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        headless=True,
    )
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))
    camera_id = None
    try:
        response = page.goto(BASE, wait_until='domcontentloaded')
        assert response.status == 200
        expect(page.get_by_role('heading', name='Know your store at a glance.')).to_be_visible()
        expect(page.locator('#monitorCard')).to_be_visible()
        expect(page.locator('#heatCard')).to_be_visible()
        expect(page.locator('#overall-layout')).to_be_visible()
        expect(page.locator('#zoneEditor')).not_to_have_attribute('open', '')
        results.append('concise Overview dashboard and collapsed advanced editing')

        cfg = page.request.get(BASE + '/api/config').json()
        layout = page.request.get(BASE + '/api/layout').json()
        assert cfg['cameras'] and layout['sections']
        report = page.request.get(BASE + '/api/layout/analytics').json()
        assert report['overall']['sections'] == len(layout['sections'])
        assert report['overall']['cameras_configured'] == len(cfg['cameras'])
        assert all(s['count'] is None for s in report['sections'])
        results.append('matching first-run cameras, floor plan and honest offline metrics')

        page.locator('#agentLauncher').click()
        expect(page.locator('#agentDrawer')).to_be_visible()
        page.locator('#askInput').fill('What is visible dwell time?')
        page.locator('#askSend').click()
        expect(page.locator('#askReply')).not_to_contain_text('Checking the current observations', timeout=20000)
        assert len(page.locator('#askReply').inner_text()) > 18
        results.append('Store assistant answers operator question without model setup')

        page.locator('[data-agent-view="briefing"]').click()
        expect(page.locator('#briefCard')).to_be_visible()
        expect(page.locator('#assistantCard')).to_be_hidden()
        assert page.request.get(BASE + '/api/assistant/briefing').status == 200
        assert page.request.get(BASE + '/api/briefing/config').status == 200
        results.append('briefing tab and WhatsApp manual-handoff API')
        page.locator('#agentClose').click()
        expect(page.locator('#agentDrawer')).to_be_hidden()

        page.get_by_role('tab', name='Camera library').click()
        expect(page.locator('#libraryCard')).to_be_visible()
        expect(page.locator('#sourceCard')).to_be_visible()
        expect(page.locator('#monitorCard')).to_be_hidden()
        page.get_by_role('tab', name='Live dashboard').click()
        results.append('camera library, manual source input, and tab switching')

        camera_id = next((c['id'] for c in cfg['cameras'] if c.get('zones')), cfg['cameras'][0]['id'])
        page.locator('#camera').select_option(camera_id)
        page.locator('#start').click()
        page.wait_for_function(r'Number(document.querySelector("#frameInfo").textContent.match(/\d+/)?.[0]||0)>=4', timeout=75000)
        page.wait_for_function('document.querySelector("#heatBrief").textContent.includes("person-seconds")', timeout=30000)
        live = page.request.get(BASE + '/api/live/status').json()
        cam = next(c for c in live['cameras'] if c['id'] == camera_id)
        assert cam['frames'] >= 4
        heat = page.request.get(BASE + '/api/live/heat/' + camera_id + '/summary?window_s=30')
        assert heat.status == 200 and 'person_seconds' in heat.json()
        assert page.request.get(BASE + '/api/live/report/' + camera_id + '.csv').status == 200
        results.append(f'actual YOLO video inference / heatmap / CSV export ({cam["frames"]} frames)')

        page.screenshot(path=str(OUT/'overview_desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(OUT/'overview_mobile.png'), full_page=True)
        page.goto(BASE + '/layout', wait_until='domcontentloaded')
        expect(page.locator('#editor .edit-tile')).to_have_count(len(layout['sections']))
        expect(page.locator('#orbitFloor')).to_be_visible()
        expect(page.locator('#overallRows')).to_be_visible()
        page.screenshot(path=str(OUT/'floorplan_mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.screenshot(path=str(OUT/'floorplan_desktop.png'), full_page=True)
        results.append('populated floor plan, rotatable 3D layout, and mobile/desktop rendering')
        assert not errors, errors
        print(json.dumps({'status': 'passed', 'checks': results, 'browser_errors': errors}, indent=2), flush=True)
    finally:
        if camera_id:
            try:
                page.request.post(BASE + '/api/live/stop/' + camera_id, timeout=20000)
            except Exception as exc:
                print('Live camera cleanup warning:', exc, flush=True)
        browser.close()

(OUT / 'result.json').write_text(json.dumps({'checks': results}, indent=2), encoding='utf-8')
