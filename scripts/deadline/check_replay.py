import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments'/'deadline'
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1280,'height':1100})
    page.goto('http://127.0.0.1:8791/',wait_until='networkidle')
    expect(page.locator('#samples')).to_have_text('194')
    expect(page.locator('video')).to_have_count(2)
    page.wait_for_function('[...document.querySelectorAll("video")].every(v=>v.readyState>=2 && v.videoWidth>0)')
    for i in range(2):
        page.locator('video').nth(i).evaluate('(v)=>v.play()')
        page.wait_for_function('(i)=>document.querySelectorAll("video")[i].currentTime > 0.5',arg=i)
        page.locator('video').nth(i).evaluate('(v)=>v.pause()')
    expect(page.locator('#results table')).to_have_count(1)
    expect(page.locator('#results')).to_contain_text('partial')
    page.screenshot(path=str(OUT/'replay_dashboard.png'),full_page=True)
    b.close()
path=OUT/'replay_validation.json';record=json.loads(path.read_text()) if path.exists() else {}
record.update(camera_samples=194,videos_loaded=2,playback_verified=True,both_videos_playback_verified=True,operator_dwell_table_verified=True)
path.write_text(json.dumps(record,indent=2))
print('replay validated')
