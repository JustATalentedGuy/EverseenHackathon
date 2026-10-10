"""Headless Chrome acceptance check for tested one-click retail demo videos.

Requires local FastAPI server :8791, Chrome and Playwright. Restores config.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs'/'retail_catalog_ui'
OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8791'

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('dialog',lambda d:d.accept())
    saved=page.request.get(BASE+'/api/config').json()
    report={}
    try:
        page.goto(BASE,wait_until='networkidle')
        page.get_by_role('tab',name='Camera library').click()
        catalog=page.request.get(BASE+'/api/demo/catalog').json()['videos']
        ready=[r for r in catalog if r['available']]
        assert len(ready)>=6,(len(ready),[x['state'] for x in catalog])
        expect(page.locator('#demoList .demo-item')).to_have_count(len(ready))
        report['total']=len(catalog)
        report['ready']=len(ready)
        for identifier in ['caviar_walkby','mall_crowd','merl_shelf']:
            item=next(x for x in catalog if x['id']==identifier)
            assert item['available']
            cid='demo_'+identifier
            page.locator('#demoList .demo-item').filter(has_text=item['title']).locator('button').click()
            expect(page.locator('#camera')).to_have_value(cid,timeout=30000)
            page.wait_for_function('document.querySelector("#feed").naturalWidth>0',timeout=30000)
            status=page.locator('#notice').inner_text()
            report[identifier]={'camera_id':cid,'preview':'passed','source':item['source']}
        # Perform live inference on one newly-downloaded research clip, not only preview.
        page.locator('#camera').select_option('demo_caviar_walkby')
        page.locator('#start').click()
        page.wait_for_function('Number(document.querySelector("#frameInfo").textContent.match(/\\d+/)?.[0]||0)>=2',timeout=50000)
        live=page.request.get(BASE+'/api/live/status').json()
        cam=next(c for c in live['cameras'] if c['id']=='demo_caviar_walkby')
        assert cam['frames']>=2 and cam['measurement']['backend'] in ('onnx','pt')
        report['live_inference']={'frames':cam['frames'],'backend':cam['measurement']['backend']}
        page.screenshot(path=str(OUT/'retail_catalog_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'retail_catalog_mobile.png'),full_page=True)
        assert not errors,errors
        print('CATALOG TEST PASSED',json.dumps(report),flush=True)
    finally:
        response=page.request.put(BASE+'/api/config',data=saved)
        if response.status!=200:raise AssertionError('Could not restore original site config')
        browser.close()
    (OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
