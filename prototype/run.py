"""Offline or RTSP camera analytics; config edited by prototype/server.py.
python -m prototype.run --config prototype/site.json --output experiments/demo
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import time
import shutil
import subprocess
from types import SimpleNamespace
import cv2
import numpy as np
import torch
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from .core import Analytics,validate_config,world_point,projection_sigma,conservative_zone_total
from .streams import LatestFrame

def fuse_floor(observations,radius_m=0.45):
    """Greedy nearest cluster requiring pairwise compatibility, one observation/camera.
    Caller must supply synchronized, checked floor points. No blind-gap ID inference.
    """
    groups=[]
    for o in sorted(observations,key=lambda x:-x.get('confidence',0)):
        if o.get('position_sigma_m',0)>0.25: continue
        candidates=[]
        for i,g in enumerate(groups):
            if any(x['camera']==o['camera'] for x in g): continue
            if any(abs(x['time']-o['time'])>0.15 for x in g): continue
            distances=[np.linalg.norm(np.array(o['world'])-x['world']) for x in g]
            if max(distances)<radius_m: candidates.append((max(distances),i))
        if candidates: groups[min(candidates)[1]].append(o)
        else: groups.append([o])
    return [{'world':np.mean([x['world'] for x in g],axis=0).tolist(),
             'members':[f'{x["camera"]}:{x["track_id"]}' for x in g],
             'time':float(np.mean([x['time'] for x in g]))} for g in groups]

def run(config_path,output,max_seconds=None):
    config_path=Path(config_path).resolve(); root=Path(__file__).resolve().parents[1]
    config=validate_config(json.loads(config_path.read_text(encoding='utf-8')))
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    model_path=Path(config.get('model','models/yolo11n.pt'))
    if not model_path.is_absolute(): model_path=root/model_path
    model=YOLO(str(model_path)); cams=[]
    torch.set_num_threads(int(config.get('cpu_threads',4)))
    hz=float(config.get('sample_hz',5)); confidence=float(config.get('confidence',0.25))
    if not 0<hz<=30: raise ValueError('sample_hz must be >0 and <=30')
    for c in config['cameras']:
        src=c['source']; live=src.startswith(('rtsp://','http://','https://'))
        if not live and not Path(src).is_absolute(): src=str(root/src)
        cap=cv2.VideoCapture(src)
        if not cap.isOpened(): raise RuntimeError(f'Cannot open camera {c["id"]}')
        fps=cap.get(cv2.CAP_PROP_FPS) or 25; dt=max(1,round(fps/hz))/fps
        tracker=BYTETracker(SimpleNamespace(track_high_thresh=confidence,track_low_thresh=0.05,
                new_track_thresh=confidence,track_buffer=max(1,round(1/dt)),match_thresh=0.8,fuse_score=True))
        cams.append({'c':c,'cap':cap,'fps':fps,'step':max(1,round(fps/hz)),'frame':0,'live':live,
                     'clock':time.monotonic(),'tracker':tracker,'analytics':Analytics(c['zones'],persistence_s=float(config.get('zone_persistence_s',.2)),max_gap_s=dt*1.6),
                     'previous':{},'slow_since':{},'writer':None,'done':False,
                     'reader':LatestFrame(cap) if live else None,'last_emit':-float('inf')})
    events=(output/'events.jsonl').open('w',encoding='utf-8'); processed=0; started=time.perf_counter()
    try:
        while not all(cam['done'] for cam in cams):
            pass_processed=processed
            floor=[]; zone_counts=defaultdict(dict); times=[]
            for cam in cams:
                if cam['done']: continue
                c=cam['c']; selected=None
                captured=None
                if cam['live']:
                    item=cam['reader'].take()
                    if item is None:
                        if cam['reader'].done:cam['done']=True
                        continue
                    f,frame,captured=item
                    if captured-cam['last_emit']<1/hz:continue
                    cam['last_emit']=captured;selected=(f,frame)
                else:
                    # Sequential decode avoids incorrect MPEG frame-count/seek metadata.
                    for _ in range(cam['step']):
                        ok,frame=cam['cap'].read()
                        if not ok: cam['done']=True; break
                        f=cam['frame']; cam['frame']+=1
                        if f%cam['step']==0: selected=(f,frame)
                if selected is None: continue
                f,frame=selected; h,w=frame.shape[:2]
                t=(captured-cam['clock'] if cam['live'] else f/cam['fps'])+float(c.get('time_offset_s',0))
                if max_seconds is not None and t>max_seconds: cam['done']=True; continue
                times.append(t)
                r=model.predict(frame,imgsz=int(config.get('imgsz',416)),classes=[0],conf=0.05,verbose=False,device=config.get('device','cpu'))[0]
                tracks=cam['tracker'].update(r.boxes.cpu().numpy()); counts=Counter(); slow=Counter(); observed=[]
                for tr in tracks:
                    tid=int(tr[4]); x1,y1,x2,y2=tr[:4]; pt=[float((x1+x2)/2/w),float(y2/h)]
                    truncated=y2>=h-2 or y1<=1
                    z=cam['analytics'].update(tid,t,pt) if not truncated else None
                    if z is not None: counts[z]+=1
                    wp=world_point(pt,c.get('calibration')) if not truncated else None
                    sigma=projection_sigma(pt,c['calibration'],(h,w)) if wp is not None else None
                    speed=None; speed_unit=None
                    old=cam['previous'].get(tid)
                    if old and 0<t-old['time']<=cam['analytics'].max_gap:
                        if wp is not None and old['world'] is not None:
                            speed=float(np.linalg.norm(np.array(wp)-old['world'])/(t-old['time'])); speed_unit='m/s'
                        else:
                            # Body-height normalization attenuates perspective; never label this m/s.
                            speed=float(np.linalg.norm(np.array(pt)-old['point'])/max((y2-y1)/h,0.03)/(t-old['time'])); speed_unit='body heights/s'
                        if speed<float(config.get('slow_metric_mps',0.2) if speed_unit=='m/s' else config.get('slow_body_heights_ps',0.1)) and z: slow[z]+=1
                    cam['previous'][tid]={'point':pt,'world':wp,'time':t}
                    o={'camera':c['id'],'track_id':tid,'time':t,'point':pt,'world':wp,'zone':z,
                       'confidence':float(tr[5]),'speed':speed,'speed_unit':speed_unit,'truncated':bool(truncated),
                       'position_sigma_m':sigma}
                    observed.append(o)
                    if wp is not None and c.get('sync_verified',False): floor.append(o)
                    cv2.rectangle(frame,(int(x1),int(y1)),(int(x2),int(y2)),(64,225,169),1)
                    cv2.putText(frame,f'{tid} {z or "unknown"}',(int(x1),max(12,int(y1))),cv2.FONT_HERSHEY_SIMPLEX,0.35,(64,225,169),1)
                risks=[]
                for z in c['zones']:
                    name=z['id']; n=counts[name]; fraction=slow[name]/max(1,n)
                    active=n>=int(z.get('crowd_threshold',4)) and fraction>=float(z.get('slow_fraction',0.6))
                    key=name
                    if active: cam['slow_since'].setdefault(key,t)
                    else: cam['slow_since'].pop(key,None)
                    if active and t-cam['slow_since'][key]>=float(z.get('persistence_s',5)):
                        risks.append({'zone':name,'type':'crowding with slow movement','people':n,'slow_fraction':fraction,
                                      'message':'Inspect this region; browsing and waiting may also explain slow movement.'})
                    zone_counts[z.get('semantic_id',name)][c['id']]=n
                    pts=np.array(z['polygon'])*[w,h]; cv2.polylines(frame,[pts.astype(np.int32)],True,(240,180,60),1)
                if cam['writer'] is None:
                    cam['writer']=cv2.VideoWriter(str(output/(c['id']+'_overlay.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),cam['fps']/cam['step'],(w,h))
                cam['writer'].write(frame)
                events.write(json.dumps({'kind':'camera_sample','camera':c['id'],'time':t,'observations':observed,
                         'counts':dict(counts),'risks':risks,'health':{'truncated':sum(o['truncated'] for o in observed),
                         'geometry_enabled':bool(c.get('calibration')),'sync_verified':bool(c.get('sync_verified'))}},allow_nan=False)+'\n')
                processed+=1
            if times:
                owners=config.get('zone_owners',{})
                aligned=max(times)-min(times)<=0.25
                totals={z:conservative_zone_total(cc,owners.get(z)) for z,cc in zone_counts.items()} if aligned else {}
                events.write(json.dumps({'kind':'scene_sample','time':max(times),'zone_totals':totals,
                                         'sample_times_aligned':aligned,'fused_floor':fuse_floor(floor) if aligned else []},allow_nan=False)+'\n')
            if processed==pass_processed:time.sleep(.01)
    finally:
        events.close()
        for cam in cams:
            if cam['reader']:cam['reader'].close()
            else:cam['cap'].release()
            if cam['writer']: cam['writer'].release()
    ffmpeg=shutil.which('ffmpeg')
    if ffmpeg:
        for cam in cams:
            path=output/(cam['c']['id']+'_overlay.mp4');encoded=path.with_name(path.stem+'_browser.mp4')
            if not path.exists():continue
            subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(path),'-c:v','libx264','-pix_fmt','yuv420p',
                            '-preset','fast','-movflags','+faststart',str(encoded)],check=True)
            encoded.replace(path)
    summary={'config':str(config_path),'camera_samples':processed,'wall_seconds':time.perf_counter()-started,
             'config_snapshot':json.loads(config_path.read_text(encoding='utf-8')),
             'cameras':{cam['c']['id']:cam['analytics'].snapshot() for cam in cams},
             'scope':'Local observed dwell; geometry fusion only with checked calibration + user-verified synchronization. No unvalidated blind-gap global identities.'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'camera_samples':processed,'wall_seconds':summary['wall_seconds'],'output':str(output)},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',default='prototype/site.json'); p.add_argument('--output',default='experiments/deadline/demo')
    p.add_argument('--seconds',type=float); a=p.parse_args(); run(a.config,a.output,a.seconds)
