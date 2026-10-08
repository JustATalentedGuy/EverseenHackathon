"""Local camera-zone setup and replay dashboard. Bind loopback only."""
import json
from pathlib import Path
import csv
import io
import re
import threading
import time
import cv2
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,Response,StreamingResponse
from .core import validate_config,propose_zones
from .run import run
from .sources import resolve_source
from .live import LiveManager
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'prototype'/'site.json'
DEMO_CATALOG=ROOT/'prototype'/'demo_catalog.json'
app=FastAPI(title='Everseen setup')
lock=threading.Lock(); job={'status':'idle'}
live=LiveManager(ROOT)

@app.middleware('http')
async def local_only(request:Request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ['127.0.0.1','localhost','testserver']: return Response('Local setup only',403)
    origin=request.headers.get('origin')
    if request.method not in ['GET','HEAD'] and origin and origin != 'http://'+request.headers.get('host',''):
        return Response('Origin not allowed',403)
    return await call_next(request)

def load(): return json.loads(CONFIG.read_text(encoding='utf-8'))

@app.get('/')
def index(): return FileResponse(ROOT/'prototype'/'dashboard.html')

@app.get('/setup')
def setup(): return FileResponse(ROOT/'prototype'/'index.html')

@app.get('/api/config')
def get_config(): return load()

def persist(config):
    """Validate and atomically save a site configuration, retaining prior versions."""
    try:
        for cam in config.get('cameras',[]):
            resolve_source(cam.get('source',''),ROOT)
        validate_config(config)
    except (ValueError,KeyError,TypeError) as exc: raise HTTPException(422,str(exc))
    with lock:
        if job['status']=='running': raise HTTPException(409,'Wait for analysis to finish before editing zones')
        versions=ROOT/'prototype'/'config_versions'; versions.mkdir(exist_ok=True)
        (versions/f'{time.time_ns()}.json').write_text(CONFIG.read_text(encoding='utf-8'),encoding='utf-8')
        tmp=CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(config,indent=2),encoding='utf-8'); tmp.replace(CONFIG)
    # Running cameras hold a snapshot; prevent stale zones and misleading stats.
    live.stop_all()
    return {'saved':True,'camera_count':len(config['cameras']), 'live_restarted':False}

@app.put('/api/config')
def put_config(config:dict):
    return persist(config)

def list_demo_catalog():
    """Only advertise playback-ready, audited videos as one-click camera sources."""
    records=json.loads(DEMO_CATALOG.read_text(encoding='utf-8'))
    validation_path=ROOT/'runs'/'retail_demo_validation.json'
    audits=json.loads(validation_path.read_text(encoding='utf-8')) if validation_path.exists() else {}
    for item in records:
        path=ROOT/item['source']
        audit=audits.get(item['validation_key'],{})
        valid=(path.is_file() and path.stat().st_size>4096 and
               path.stat().st_size==audit.get('file_bytes') and
               audit.get('status')=='tested' and audit.get('path')==item['source'] and
               audit.get('samples_decoded',0)>=8 and audit.get('nonempty_sample_fraction',0)>0)
        item['available']=bool(valid)
        item['state']='validated' if valid else ('needs_validation' if path.is_file() else 'not_downloaded')
        item['measurements']={key:audit[key] for key in
                ('resolution','estimated_duration_s','samples_decoded','mean_predicted_persons',
                 'max_predicted_persons','nonempty_sample_fraction') if key in audit} if valid else {}
    return records

@app.get('/api/demo/catalog')
def demo_catalog(): return {'videos':list_demo_catalog(),
                            'note':'Predictions are unlabelled model outputs, not validated accuracy; downloaded videos remain local.'}

@app.post('/api/demo/activate/{demo_id}')
def activate_demo(demo_id:str):
    item=next((i for i in list_demo_catalog() if i['id']==demo_id),None)
    if item is None:raise HTTPException(404,'Unknown demo video')
    if not item['available']:raise HTTPException(422,'Footage must first be downloaded, decoded and validated locally.')
    config=load()
    old=next((c for c in config['cameras'] if c.get('demo_catalog_id')==demo_id),None)
    if old:return {'id':old['id'],'already_added':True}
    if len(config['cameras'])>=8:raise HTTPException(422,'Maximum eight configured cameras. Remove an unused one first.')
    try:
        source,_=resolve_source(item['source'],ROOT)
        import hashlib
        digest=hashlib.sha256()
        with Path(source).open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):
                digest.update(block)
        audit_path=ROOT/'runs'/'retail_demo_validation.json'
        audit=json.loads(audit_path.read_text(encoding='utf-8'))[item['validation_key']]
        if digest.hexdigest()!=audit['sha256']:
            raise ValueError('Video changed after validation; run scripts/test_retail_demo.py again.')
        cap=cv2.VideoCapture(source)
        ok,_=cap.read()
        cap.release()
        if not ok:raise ValueError('The selected video cannot decode a frame. Re-run demo validation.')
    except ValueError as exc:raise HTTPException(422,str(exc))
    cid='demo_'+demo_id
    config['cameras'].append({'id':cid,'name':item['title'],'source':item['source'],
                              'sync_verified':False,'demo_catalog_id':demo_id,'zones':[]})
    persist(config)
    return {'id':cid,'added':True,'note':'Preview video and draw your own floor zones; no unverified area boundaries are supplied.'}

@app.post('/api/cameras')
def add_camera(camera:dict):
    name=str(camera.get('name','')).strip()[:80]
    source=str(camera.get('source','')).strip()
    if not name: raise HTTPException(422,'Camera name is required')
    config=load()
    if len(config['cameras']) >= 8: raise HTTPException(422,'Maximum eight configured cameras')
    stem=re.sub(r'[^a-z0-9_-]+','_',name.lower()).strip('_')[:32] or 'camera'
    taken={c['id'] for c in config['cameras']}
    cid=stem; counter=2
    while cid in taken:
        cid=f'{stem}_{counter}';counter+=1
    config['cameras'].append({'id':cid,'name':name,'source':source,'sync_verified':False,'zones':[]})
    persist(config)
    return {'id':cid,'name':name}

@app.delete('/api/cameras/{camera_id}')
def remove_camera(camera_id:str):
    config=load()
    if len(config['cameras']) <= 1: raise HTTPException(422,'Keep at least one camera')
    if camera_id not in [c['id'] for c in config['cameras']]: raise HTTPException(404,'Unknown camera')
    config['cameras']=[c for c in config['cameras'] if c['id']!=camera_id]
    config['zone_owners']={k:v for k,v in config.get('zone_owners',{}).items() if v!=camera_id}
    persist(config)
    return {'removed':camera_id}

@app.get('/api/frame/{camera_id}')
def frame(camera_id:str):
    c=next((c for c in load()['cameras'] if c['id']==camera_id),None)
    if c is None: raise HTTPException(404,'Unknown camera')
    try: path,_=resolve_source(c['source'],ROOT)
    except ValueError as exc: raise HTTPException(422,str(exc))
    cap=cv2.VideoCapture(path)
    opened=cap.isOpened()
    ok,img=cap.read() if opened else (False,None)
    cap.release()
    if not ok:
        raise HTTPException(422,'Source could not decode a video frame. Use a playable direct HTTP/RTSP video URL, check credentials/codecs, and for MP4-over-HTTP use a fast-start file or a range-capable server.')
    ok,enc=cv2.imencode('.jpg',img)
    return Response(enc.tobytes(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})

@app.get('/api/proposals/{camera_id}')
def proposals(camera_id:str):
    # Prefer observations from this installed camera. Training footage proposals are research-only.
    events=ROOT/'experiments'/'deadline'/'demo'/'events.jsonl'; points=[]
    summary=ROOT/'experiments'/'deadline'/'demo'/'summary.json'
    current=next((c for c in load()['cameras'] if c['id']==camera_id),None)
    prior=json.loads(summary.read_text()).get('config_snapshot',{}) if summary.exists() else {}
    installed=next((c for c in prior.get('cameras',[]) if c['id']==camera_id),None)
    if not current or not installed or current['source']!=installed['source']:
        return {'proposals':[],'observations':0,'note':'Analyze this camera source before suggesting regions.'}
    if events.exists():
        for line in events.read_text().splitlines():
            try: r=json.loads(line)
            except json.JSONDecodeError: continue
            if r.get('kind')=='camera_sample' and r.get('camera')==camera_id:
                points.extend(x['point'] for x in r['observations'] if not x['truncated'])
    return {'proposals':propose_zones(points),'observations':len(points),'note':'Activity regions need your confirmation and naming.'}

@app.post('/api/run')
def start():
    with lock:
        if job['status']=='running': raise HTTPException(409,'Analysis is already running')
        job.clear(); job.update(status='running',started=time.time())
    def work():
        try:
            run(CONFIG,ROOT/'experiments'/'deadline'/'demo',30)
            job.update(status='complete',finished=time.time())
        except Exception as exc: job.update(status='failed',error=str(exc))
    threading.Thread(target=work,daemon=True).start()
    return job

@app.get('/api/status')
def status(): return job

@app.get('/api/results')
def results():
    out=ROOT/'experiments'/'deadline'/'demo'/'summary.json'
    if not out.exists(): return {'ready':False}
    result=json.loads(out.read_text())
    if result.get('config_snapshot')!=load(): return {'ready':False,'stale':True,'note':'Setup changed; analyze again.'}
    return {'ready':True,**result}

@app.get('/api/overlay/{camera_id}')
def overlay(camera_id:str):
    if not results().get('ready'): raise HTTPException(409,'Setup changed; analyze again')
    if camera_id not in [c['id'] for c in load()['cameras']]: raise HTTPException(404)
    f=ROOT/'experiments'/'deadline'/'demo'/(camera_id+'_overlay.mp4')
    if not f.exists(): raise HTTPException(404,'Run analysis first')
    return FileResponse(f,media_type='video/mp4')

@app.get('/api/live/status')
def live_status(): return live.stats()

@app.post('/api/live/start/{camera_id}')
def live_start(camera_id:str):
    try: return live.start(camera_id,load())
    except KeyError: raise HTTPException(404,'Unknown camera')
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))

@app.post('/api/live/stop/{camera_id}')
def live_stop(camera_id:str):
    try: return live.stop(camera_id)
    except KeyError: raise HTTPException(404,'Camera is not active')

@app.get('/api/live/video/{camera_id}')
def live_video(camera_id:str):
    cam=live.get(camera_id)
    if cam is None: raise HTTPException(404,'Start camera first')
    def frames():
        last=0
        while not cam.stop_event.is_set():
            with cam.lock:
                seq,jpg=cam.jpg_seq,cam.jpeg
            if jpg and seq!=last:
                last=seq
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+jpg+b'\r\n'
            time.sleep(.1)
    return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame',
                             headers={'Cache-Control':'no-store'})

@app.get('/api/live/heat/{camera_id}.jpg')
def live_heat(camera_id:str):
    cam=live.get(camera_id)
    if cam is None: raise HTTPException(404,'Start camera first')
    jpg=cam.heatmap_jpeg()
    if jpg is None: return Response(status_code=204)
    return Response(jpg,media_type='image/jpeg',headers={'Cache-Control':'no-store'})

@app.get('/api/live/events/{camera_id}')
def live_events(camera_id:str):
    cam=live.get(camera_id)
    if cam is None or not cam.events_path.exists(): raise HTTPException(404,'No observations yet')
    # A growing log must not use FileResponse's size-based Content-Length:
    # concurrent writes can otherwise abort downloads with a length mismatch.
    path=cam.events_path
    upper_bound=path.stat().st_size
    def snapshot():
        remaining=upper_bound
        with path.open('rb') as stream:
            while remaining:
                chunk=stream.read(min(65536,remaining))
                if not chunk:break
                remaining-=len(chunk)
                yield chunk
    return StreamingResponse(snapshot(),media_type='application/x-ndjson',
                             headers={'Content-Disposition':f'attachment; filename="{camera_id}_observations.jsonl"',
                                      'Cache-Control':'no-store'})

@app.get('/api/live/report/{camera_id}.csv')
def live_report(camera_id:str):
    cam=live.get(camera_id)
    if cam is None: raise HTTPException(404,'Start camera first')
    data=cam.stats()
    file=io.StringIO(newline=''); writer=csv.writer(file)
    writer.writerow(['camera','zone','current_observed_occupancy','peak_observed_occupancy',
                     'p90_occupancy_5m','observed_track_entries_not_people',
                     'mean_partial_visible_dwell_seconds','partial_track_zone_segments',
                     'zone_role','review_threshold_people','measurement_state','age_of_last_sample_seconds',
                     'measured_fps_30s','target_hz'])
    for z in data['zones']:
        # Avoid spreadsheet formula interpretation of operator-authored labels.
        label=z['label']
        if label and label[0] in '=+-@': label="'"+label
        writer.writerow([camera_id,label,z['occupancy'],z['peak'],z['p90_occupancy_5m'],
                         z['observed_track_entries'],z['partial_dwell_mean_s'],z['partial_dwell_tracks'],
                         z['role'],z['crowd_threshold'],data['measurement']['state'],
                         data['measurement']['age_s'],data['measurement']['observed_fps_30s'],
                         data['measurement']['target_hz']])
    return Response(file.getvalue(),media_type='text/csv',headers={
        'Content-Disposition':f'attachment; filename="{camera_id}_observed_zones.csv"'})

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8791)
