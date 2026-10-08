"""Verify final UI-triggered analysis, playback and configuration invalidation."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments'/'deadline'
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1280,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    url='http://127.0.0.1:8791'
    try:
        page.goto(url+'/setup',wait_until='networkidle')
        saved=page.request.get(url+'/api/config').json()
        assert saved['confidence']==.35 and saved['zone_persistence_s']==.2
        page.locator('#run').click()
        expect(page.locator('#status')).to_have_text('Running')
        expect(page.locator('#samples')).to_have_text('194',timeout=180000)
        expect(page.locator('video')).to_have_count(2)
        page.wait_for_function('[...document.querySelectorAll("video")].every(v=>v.readyState>=2 && v.videoWidth>0)')
        page.locator('video').first.evaluate('(v)=>v.play()')
        page.wait_for_function('document.querySelector("video").currentTime > 0.1')
        page.locator('video').first.evaluate('(v)=>v.pause()')
        result=page.request.get(url+'/api/results').json()
        assert result['config_snapshot']==saved
        event_rows=[json.loads(x) for x in (OUT/'demo'/'events.jsonl').read_text().splitlines()]
        assert all(not r.get('fused_floor') for r in event_rows)
        proposals=page.request.get(url+'/api/proposals/corridor').json()
        assert proposals['observations']>0
        page.screenshot(path=str(OUT/'replay_dashboard.png'),full_page=True)
        changed=json.loads(json.dumps(saved));changed['confidence']=.36
        assert page.request.put(url+'/api/config',data=changed).status==200
        assert page.request.get(url+'/api/results').json().get('stale')
        assert page.request.get(url+'/api/overlay/corridor').status==409
        changed['cameras'][0]['source']='datasets/caviar/OneLeaveShop1cor.mpg'
        assert page.request.put(url+'/api/config',data=changed).status==200
        assert page.request.get(url+'/api/proposals/corridor').json()['observations']==0
        assert page.request.put(url+'/api/config',data=saved).status==200
        assert page.request.get(url+'/api/results').json()['ready']
        assert not errors,errors
    finally:
        if 'saved' in locals():page.request.put(url+'/api/config',data=saved)
        b.close()
LATEST=ROOT/'runs'/'ui_checks'/'replay_validation_latest.json';LATEST.parent.mkdir(parents=True,exist_ok=True)
LATEST.write_text(json.dumps({'camera_samples':194,'videos_loaded':2,
 'playback_verified':True,'ui_triggered_final_config_analysis':True,'stale_results_blocked':True,
 'changed_source_proposals_blocked':True,'unsynchronized_floor_fusion_disabled':True,'page_errors':errors,
 'wall_seconds':result['wall_seconds']},indent=2))
print(json.dumps({'replay_validation':'passed','wall_seconds':result['wall_seconds'],'camera_samples':194}))
