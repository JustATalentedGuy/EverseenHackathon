"""Local camera-zone setup and replay dashboard. Bind loopback only."""
import json
from pathlib import Path
import threading
import time
import cv2
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,Response
from .core import validate_config,propose_zones
from .run import run
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'prototype'/'site.json'
app=FastAPI(title='Everseen setup')
lock=threading.Lock(); job={'status':'idle'}

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
def index(): return FileResponse(ROOT/'prototype'/'index.html')

@app.get('/api/config')
def get_config(): return load()

@app.put('/api/config')
def put_config(config:dict):
    try:
        for cam in config.get('cameras',[]):
            src=cam.get('source','')
            if not src.startswith(('rtsp://','http://','https://')):
                path=(ROOT/src).resolve()
                if not path.is_relative_to(ROOT) or not path.is_file(): raise ValueError('Choose a video inside Everseen')
        validate_config(config)
    except (ValueError,KeyError,TypeError) as exc: raise HTTPException(422,str(exc))
    with lock:
        if job['status']=='running': raise HTTPException(409,'Wait for analysis to finish before editing zones')
        versions=ROOT/'prototype'/'config_versions'; versions.mkdir(exist_ok=True)
        (versions/f'{time.time_ns()}.json').write_text(CONFIG.read_text(),encoding='utf-8')
        tmp=CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(config,indent=2),encoding='utf-8'); tmp.replace(CONFIG)
    return {'saved':True,'camera_count':len(config['cameras'])}

@app.get('/api/frame/{camera_id}')
def frame(camera_id:str):
    c=next((c for c in load()['cameras'] if c['id']==camera_id),None)
    if c is None: raise HTTPException(404,'Unknown camera')
    src=c['source']; path=src if src.startswith(('rtsp://','http://','https://')) else str(ROOT/src)
    cap=cv2.VideoCapture(path); ok,img=cap.read(); cap.release()
    if not ok: raise HTTPException(422,'Cannot read camera')
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

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8791)
