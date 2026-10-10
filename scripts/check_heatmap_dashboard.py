"""Non-mutating browser test for the new foot-presence heatmap.

Uses an independently started localhost server (default 8893). Never edits
prototype/site.json or creates/removes zones. Stops its own live camera.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('EVERSEEN_HEATMAP_BASE','http://127.0.0.1:8893')
OUT=ROOT/'runs'/'heatmap_ui_checks'
OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    config=page.request.get(BASE+'/api/config').json()
    camera=config['cameras'][0]['id']
    result={}
    try:
        response=page.goto(BASE,wait_until='networkidle')
        assert response.status==200
        expect(page.locator('#heatWindow')).to_have_value('120')
        expect(page.locator('#heatBrief')).to_contain_text('Start monitoring')
        page.locator('#start').click()
        page.wait_for_function('Number(document.querySelector("#frameInfo").textContent.match(/\\d+/)?.[0]||0)>=8',timeout=60000)
        page.wait_for_function('document.querySelector("#heatBrief").textContent.includes("person-seconds")',timeout=20000)
        page.wait_for_function('document.querySelector("#heat").naturalWidth>0',timeout=20000)
        meta=page.request.get(BASE+'/api/live/heat/'+camera+'/summary?window_s=120').json()
        assert meta['window_s']==120 and meta['elapsed_s']>0
        assert meta['grid_columns']==16 and meta['grid_rows']==9
        assert meta['person_seconds']>=0 and 0<=meta['coverage_fraction']<=1
        result['initial']=meta
        page.locator('#heatWindow').select_option('30')
        expect(page.locator('#heat')).to_have_attribute('src',__import__('re').compile('window_s=30'),timeout=15000)
        page.locator('#heatWindow').select_option('300')
        expect(page.locator('#heat')).to_have_attribute('src',__import__('re').compile('window_s=300'),timeout=15000)
        page.locator('#heatWindow').select_option('120')
        page.screenshot(path=str(OUT/'foot_presence_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'foot_presence_mobile.png'),full_page=True)
        assert not errors,errors
        result['camera']=camera
        result['screenshots']='desktop and mobile'
        result['window_switching']='30, 120 and 300 seconds passed'
        print('HEATMAP DASHBOARD PASS',json.dumps(result),flush=True)
    finally:
        try:
            page.request.post(BASE+'/api/live/stop/'+camera,timeout=10000)
        except Exception as cleanup_error:
            print('Warning: live test camera could not be stopped:',cleanup_error,flush=True)
        browser.close()
    (OUT/'check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
