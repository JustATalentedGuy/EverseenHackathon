"""Real browser acceptance: drag, resize, zone assignment, topology, 3D orbit.

Run an isolated prototype.server on :8895 beforehand. Never changes site.json;
stores the original floor layout and restores it in a finally block.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('EVERSEEN_TEST_URL','http://127.0.0.1:8895')
OUT=ROOT/'runs'/'layout_v2_checks';OUT.mkdir(parents=True,exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('dialog',lambda d:d.accept())
    previous=page.request.get(BASE+'/api/layout').json()
    config=page.request.get(BASE+'/api/config').json()
    source=next((c for c in config['cameras'] if c.get('zones')),None)
    assert source is not None,'Need at least one configured source zone'
    result={'browser':'Chrome','tests':[]}
    started_camera=None
    try:
        res=page.goto(BASE+'/layout',wait_until='networkidle');assert res.status==200
        expect(page.get_by_role('heading',name='Floor plan designer')).to_be_visible()
        expect(page.locator('#editor .edit-tile')).to_have_count(len(previous['sections']))
        page.locator('#starter').click()
        expect(page.locator('#editor .edit-tile')).to_have_count(7)
        result['tests'].append('example template generated with 7 tiles')
        editor=page.locator('#editor');rect=editor.bounding_box()
        before=page.locator('#editor .edit-tile[data-id="example_0"]').get_attribute('style')
        tile=page.locator('#editor .edit-tile[data-id="example_0"]')
        handle=tile.locator('.resize')
        start=handle.bounding_box()
        # Example entrance begins x4..8, y6..8. Resize can only extend right,
        # never below floor bound; verify cursor and event cause selected-state UI.
        page.mouse.click(rect['x']+rect['width']*.55,rect['y']+rect['height']*.83)
        expect(page.locator('#properties')).to_be_visible()
        page.locator('#sectionName').fill('Main Entrance')
        page.locator('#applyProperties').click()
        expect(page.locator('#editor .edit-tile[data-id="example_0"]')).to_contain_text('Main Entrance')
        result['tests'].append('select tile, edit name and section properties')
        # Drag the middle room to a free position is restricted by existing neighbors;
        # use an isolated tile test after adding an eighth small tile in a free cell.
        page.locator('#addSection').click()
        expect(page.locator('#editor .edit-tile')).to_have_count(8)
        moved=page.locator('#editor .edit-tile.selected')
        start=moved.bounding_box()
        page.mouse.move(start['x']+start['width']*.5,start['y']+start['height']*.5)
        page.mouse.down();page.mouse.move(start['x']+start['width']*.5+rect['width']/12,start['y']+start['height']*.5,steps=4);page.mouse.up()
        expect(page.locator('#sectionX')).to_have_value('1')
        moved=page.locator('#editor .edit-tile.selected .resize')
        corner=moved.bounding_box()
        page.mouse.move(corner['x']+corner['width']*.5,corner['y']+corner['height']*.5)
        page.mouse.down();page.mouse.move(corner['x']+corner['width']*.5+rect['width']/12,corner['y']+corner['height']*.5,steps=5);page.mouse.up()
        expect(page.locator('#sectionW')).to_have_value('3')
        result['tests'].append('drag and resize to snapped non-overlapping grid coordinates')
        # Remove the temporary extra tile before saving reference layout.
        page.locator('#deleteSection').click()
        expect(page.locator('#editor .edit-tile')).to_have_count(7)
        page.locator('#editor .edit-tile[data-id="example_1"]').click()
        zone_label=f'{source.get("name",source["id"])} · {source["zones"][0].get("label",source["zones"][0]["id"])}'
        page.locator('#zoneLinks .link-option').filter(has_text=zone_label).locator('input').check()
        result['tests'].append('map camera-zone reference to selected physical section')
        page.locator('#saveLayout').click()
        expect(page.locator('#dirty')).to_contain_text('All changes saved',timeout=15000)
        stored=page.request.get(BASE+'/api/layout').json()
        assert len(stored['sections'])==7
        assert stored['sections'][1]['links']==[{'camera_id':source['id'],'zone_id':source['zones'][0]['id']}]
        result['tests'].append('persistence and camera mapping API')
        metrics=page.request.get(BASE+'/api/layout/analytics').json()
        assert len(metrics['sections'])==7
        assert 'adjacency' in metrics['topology'] and metrics['topology']['routes']
        assert metrics['sections'][1]['count'] is None
        result['tests'].append('internal topology paths; no live camera means missing, not zero')
        stage=page.locator('#orbitStage');stage.scroll_into_view_if_needed();box=stage.bounding_box()
        initial=page.locator('#orbitFloor').get_attribute('style')
        page.mouse.move(box['x']+box['width']*.55,box['y']+box['height']*.46)
        page.mouse.down();page.mouse.move(box['x']+box['width']*.75,box['y']+box['height']*.52,steps=9);page.mouse.up()
        after=page.locator('#orbitFloor').get_attribute('style')
        assert after!=initial
        page.locator('#resetOrbit').click();assert page.locator('#orbitFloor').get_attribute('style')!=after
        result['tests'].append('3D scene interactive rotation and reset')
        expect(page.locator('#overallRows tr')).to_have_count(7)
        result['tests'].append('all-section analytics table at bottom')
        # A real live camera must feed the 3D figures and the bottom analytics.
        page.set_viewport_size({'width':1500,'height':1000})
        start=page.request.post(BASE+'/api/live/start/'+source['id'],timeout=15000)
        assert start.status==200,(start.status,start.text())
        started_camera=source['id']
        page.wait_for_function('document.querySelectorAll("#orbitFloor .person3d").length>0',timeout=60000)
        report=page.request.get(BASE+'/api/layout/analytics').json()
        active=next(x for x in report['sections'] if x['id']=='example_1')
        assert active['active_feeds']>=1 and active['count'] is not None
        result['tests'].append(f'real {source["id"]} camera detection feeds 3D people and section count')
        page.screenshot(path=str(OUT/'layout_live_people.png'),full_page=True)
        page.request.post(BASE+'/api/live/stop/'+source['id'],timeout=15000)
        started_camera=None
        # Presentation contract for topology suggestions: a synthetic API
        # fixture exercises the UI without forging any real camera claims.
        fake=report.copy()
        fake['sections']=copy_sections=json.loads(json.dumps(report['sections']))
        for s in copy_sections:
            if s['id']=='example_1':s.update(count=4,state='observing')
            if s['id']=='example_2':s.update(count=0,state='observing')
        fake['insights']=[{'kind':'redistribution_candidate','severity':'review',
            'section_id':'example_1','candidate_id':'example_2',
            'title':'Consider redistributing activity from North Aisle',
            'recommendation':'Inspect whether a movable display could be trialled in Central Display.',
            'evidence':'Simulated browser UI test: four observed in North Aisle and zero in Central Display.',
            'caveat':'Synthetic test data, not a verified live-store recommendation.'}]
        page.route('**/api/layout/analytics',lambda route:route.fulfill(status=200,
                   content_type='application/json',body=json.dumps(fake)))
        page.locator('#refresh').click()
        expect(page.locator('#insights')).to_contain_text('Consider redistributing activity',timeout=15000)
        page.screenshot(path=str(OUT/'layout_insight_simulated.png'),full_page=True)
        page.unroute('**/api/layout/analytics')
        result['tests'].append('right-hand topology recommendation cards and suggested target (simulated UI fixture)')
        page.screenshot(path=str(OUT/'layout_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'layout_mobile.png'),full_page=True)
        # Existing Live Operations tab retains its sections table.
        page.goto(BASE,wait_until='domcontentloaded')
        expect(page.locator('a[href="/layout"]').first).to_be_visible()
        expect(page.locator('#layoutOverall')).to_be_visible()
        result['tests'].append('existing live-operations tab links to floor plan and global metrics')
        assert not errors,errors
        print('LAYOUT V2 BROWSER PASSED',json.dumps(result,indent=2),flush=True)
    finally:
        if started_camera:
            try:page.request.post(BASE+'/api/live/stop/'+started_camera,timeout=15000)
            except Exception as exc:print('WARNING: live camera cleanup:',exc,flush=True)
        resp=page.request.put(BASE+'/api/layout',data=previous)
        if resp.status!=200:print('WARNING: Could not restore original layout',resp.status,resp.text())
        browser.close()
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
