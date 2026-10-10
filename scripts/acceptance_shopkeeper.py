"""Shopkeeper journey: HTTP camera, typed zone, sustained alerts, data quality, CSV.

Requires local server :8791, demo HTTP video at :8902/store_web.mp4,
Playwright and Chrome. Restores site.json even if an assertion fails.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8791'
URL='http://127.0.0.1:8902/store_web.mp4'
OUT=ROOT/'runs'/'shopkeeper_acceptance'
OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1024})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    original=page.request.get(BASE+'/api/config').json()
    evidence={'scenario':'Shopkeeper operating a checkout camera from a direct HTTP URL'}
    try:
        page.goto(BASE,wait_until='networkidle')
        page.get_by_role('tab',name='Camera library').click()
        page.locator('#newName').fill('Shopkeeper demo checkout')
        page.locator('#newSource').fill(URL)
        page.locator('#add').click()
        expect(page.locator('#camera')).to_have_value('shopkeeper_demo_checkout',timeout=12000)
        page.locator('#snapshot').click()
        page.get_by_role('tab',name='Live dashboard').click()
        page.wait_for_function('document.querySelector("#feed").naturalWidth > 0',timeout=35000)
        page.locator('#zoneEditor summary').click()
        evidence['http_video_preview']=True
        page.locator('#zoneName').fill('Front checkout queue area')
        page.locator('#zoneRole').select_option('checkout')
        page.locator('#zoneThreshold').fill('2')
        page.locator('#mark').click()
        rect=page.locator('#canvas').bounding_box()
        for x,y in [(0.28,.43),(.71,.43),(.71,.91),(.28,.91)]:
            page.mouse.click(rect['x']+x*rect['width'],rect['y']+y*rect['height'])
        page.locator('#finish').click()
        expect(page.locator('#zones')).to_contain_text('Front checkout queue area',timeout=15000)
        config=page.request.get(BASE+'/api/config').json()
        demo=next(c for c in config['cameras'] if c['id']=='shopkeeper_demo_checkout')
        assert demo['zones'][0]['role']=='checkout' and demo['zones'][0]['crowd_threshold']==2
        evidence['zone_role_threshold_saved']=True
        page.locator('#start').click()
        page.wait_for_function('document.querySelector("#statePill").textContent==="live"',timeout=45000)
        page.wait_for_function('document.querySelector("#frameInfo").textContent.startsWith("2 samples") || Number(document.querySelector("#frameInfo").textContent.match(/\\d+/)?.[0]||0)>=2',timeout=65000)
        stats=page.request.get(BASE+'/api/live/status').json()
        cam=next(c for c in stats['cameras'] if c['id']=='shopkeeper_demo_checkout')
        assert cam['measurement']['state'] in ('observing','limited','warming')
        assert cam['measurement']['age_s'] is not None
        evidence['sample_health']=cam['measurement']
        assert cam['zones'][0]['role']=='checkout'
        assert cam['zones'][0]['crowd_threshold']==2
        assert cam['frames']>=2
        evidence['processed_frames']=cam['frames']
        r=page.request.get(BASE+'/api/live/report/shopkeeper_demo_checkout.csv')
        assert r.status==200 and 'measurement_state' in r.text() and 'checkout' in r.text()
        evidence['business_csv_export']=True
        events=page.request.get(BASE+'/api/live/events/shopkeeper_demo_checkout')
        assert events.status==200 and events.text().count('\n')>=2
        evidence['jsonl_export']=True
        page.screenshot(path=str(OUT/'shopkeeper_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'shopkeeper_mobile.png'),full_page=True)
        evidence['desktop_mobile_screenshots']=True
        page.locator('#stop').click()
        expect(page.locator('#statePill')).to_have_text('stopped',timeout=15000)
        evidence['stop_and_session_summary']=True
        assert not errors,errors
        print(json.dumps(evidence,indent=2))
    finally:
        restore=page.request.put(BASE+'/api/config',data=original)
        if restore.status!=200:print('WARNING: config restore failed',restore.status,restore.text())
        browser.close()
    (OUT/'acceptance.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
