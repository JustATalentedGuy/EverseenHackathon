"""Exercise the real local setup editor and save a screenshot."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments'/'deadline'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8791/setup',wait_until='networkidle')
    expect(page.locator('#camera option')).to_have_count(2)
    page.wait_for_function('img.complete && img.naturalWidth > 0')
    old=page.request.get('http://127.0.0.1:8791/api/config').json()
    canvas=page.locator('#canvas');bounds=canvas.bounding_box()
    for x,y in [(0.3,.65),(.45,.65),(.45,.8),(.3,.8)]:
        page.mouse.click(bounds['x']+bounds['width']*x,bounds['y']+bounds['height']*y)
    page.locator('#zoneName').fill('QA temporary region');page.locator('#finish').click()
    expect(page.locator('#zones')).to_contain_text('QA temporary region')
    page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('Setup saved.')
    actual=page.request.get('http://127.0.0.1:8791/api/config').json()
    assert len(actual['cameras'][0]['zones'])==len(old['cameras'][0]['zones'])+1
    bad=json.loads(json.dumps(actual));bad['cameras'][0]['zones'][-1]['polygon']=[[0,0],[1,1],[0,1],[1,0]]
    assert page.request.put('http://127.0.0.1:8791/api/config',data=bad).status==422
    assert page.request.put('http://127.0.0.1:8791/api/config',data=old).status==200
    page.reload(wait_until='networkidle');page.wait_for_function('img.complete && img.naturalWidth > 0')
    page.screenshot(path=str(OUT/'setup_desktop.png'),full_page=True)
    page.locator('#camera').select_option('1');page.wait_for_function('img.complete && img.naturalWidth > 0')
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'setup_mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
LATEST=ROOT/'runs'/'ui_checks'/'setup_validation_latest.json';LATEST.parent.mkdir(parents=True,exist_ok=True)
LATEST.write_text(json.dumps({'camera_options':2,'polygon_add_save_restore':True,
         'self_intersection_rejected':True,'page_errors':errors,'desktop_and_mobile_screenshots':True},indent=2))
print('UI validation passed')
