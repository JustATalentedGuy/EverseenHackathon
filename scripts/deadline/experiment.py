"""Scenario-separated detector adaptation, tracking, zones and proposal experiments.
Run from Everseen with its existing Python environment. No test labels enter training.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import cv2
import numpy as np
import torch
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from prototype.core import Analytics, ZoneState, assign_zone, match_boxes, propose_zones, select_review_frames
OUT=ROOT/'experiments'/'deadline'
DATA=ROOT/'datasets'/'caviar'
STEP=5

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')

def manifest(): return json.loads((DATA/'manifest.json').read_text())['records']

def gt_frames(record):
    frames={}
    root=ET.parse(ROOT/record['xml']).getroot()
    for f in root.findall('frame'):
        persons=[]
        for o in f.findall('./objectlist/object'):
            b=o.find('box')
            if b is None: continue
            x,y,w,h=[float(b.get(k)) for k in ['xc','yc','w','h']]
            if min(w,h)<=0: continue
            feet=[]
            for foot in o.findall('.//feet/*'):
                if foot.get('occluded')=='no' and foot.get('xc') is not None:
                    feet.append([float(foot.get('xc')),float(foot.get('yc'))])
            persons.append({'id':int(o.get('id')),'box':[max(0,x-w/2),max(0,y-h/2),min(record['width'],x+w/2),min(record['height'],y+h/2)],
                            'foot':np.mean(feet,axis=0).tolist() if feet else [x,min(record['height'],y+h/2)],
                            'has_annotated_foot':bool(feet)})
        frames[int(f.get('number'))]=persons
    return frames

def zones(view):
    # Explicitly illustrative image-floor regions, not supermarket department GT.
    if view=='cor':
        return [{'id':name,'polygon':[[a,0.32],[b,0.32],[b,1],[a,1]]} for name,a,b in [('left',0,0.35),('middle',0.35,0.65),('right',0.65,1)]]
    return [{'id':name,'polygon':[[0,a],[1,a],[1,b],[0,b]]} for name,a,b in [('far',0.25,0.48),('near',0.48,1)]]

def prepare():
    export=DATA/'yolo_reviewed'
    counts=Counter()
    exported=[]
    for r in manifest():
        if r['split']=='test': continue
        gt=gt_frames(r); cap=cv2.VideoCapture(str(ROOT/r['video']))
        # Spread labelled examples across entire train/val clips, not adjacent-frame split.
        selected=set((np.linspace(0,min(r['frames']-1,max(gt))//STEP,48 if r['split']=='train' else 24,dtype=int)*STEP).tolist())
        for f in range(max(selected)+1):
            ok,img=cap.read()
            if not ok: raise RuntimeError(f'Cannot decode {r["name"]}:{f}')
            if f not in selected: continue
            stem=f'{r["name"]}_{f:06d}'
            ip=export/'images'/r['split']/(stem+'.jpg'); lp=export/'labels'/r['split']/(stem+'.txt')
            ip.parent.mkdir(parents=True,exist_ok=True); lp.parent.mkdir(parents=True,exist_ok=True)
            cv2.imwrite(str(ip),img)
            labels=[]
            for p in gt.get(f,[]):
                x1,y1,x2,y2=p['box']; w=r['width']; h=r['height']
                labels.append(f'0 {(x1+x2)/2/w:.7f} {(y1+y2)/2/h:.7f} {(x2-x1)/w:.7f} {(y2-y1)/h:.7f}')
            lp.write_text('\n'.join(labels),encoding='utf-8'); counts[r['split']]+=1
            exported.append({'name':r['name'],'split':r['split'],'frame':f,'image':str(ip.relative_to(ROOT)), 'label_source':'official human CAVIAR XML'})
        cap.release()
    yaml=export/'data.yaml'
    yaml.write_text(f'path: {export.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: person\n',encoding='utf-8')
    save(OUT/'training_manifest.json',{'counts':dict(counts),'frames':exported,'test_exported':False})
    print(dict(counts),flush=True)

def infer(args):
    torch.set_num_threads(4)
    cache=OUT/f'{args.tag}_predictions.json'
    model=YOLO(str(args.model)); rows=[]; timings=[]
    for r in manifest():
        if r['split'] not in args.splits: continue
        gt=gt_frames(r); cap=cv2.VideoCapture(str(ROOT/r['video'])); f=0; start=time.perf_counter(); n=0
        while True:
            ok,img=cap.read()
            if not ok: break
            if f%STEP==0 and f in gt:
                result=model.predict(img,classes=[0],imgsz=416,conf=0.05,device='cpu',verbose=False)[0]
                det=result.boxes.data.cpu().numpy().tolist()
                row={'name':r['name'],'split':r['split'],'view':r['view'],'frame':f,'time':f/r['fps'],
                     'width':r['width'],'height':r['height'],'detections':det,'gt':gt[f]}
                rows.append(row); n+=1
            f+=1
        cap.release(); elapsed=time.perf_counter()-start
        timings.append({'clip':r['name'],'samples':n,'seconds':elapsed,'sample_fps':n/elapsed})
        save(cache,{'tag':args.tag,'weights':str(args.model),'weights_sha256':hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
                    'sample_stride':STEP,'imgsz':416,'rows':rows,'timings':timings})
        print(args.tag,r['name'],n,round(elapsed,1),flush=True)

def pseudo():
    import shutil
    reviewed=DATA/'yolo_reviewed'; target=DATA/'yolo_pseudo'
    cached=json.loads((OUT/'baseline_predictions.json').read_text())['rows']
    lookup={(r['name'],r['frame']):r for r in cached if r['split']=='train'}
    frames=json.loads((OUT/'training_manifest.json').read_text())['frames']
    quality={'tp':0,'fp':0,'fn':0,'frames':0}
    for r in frames:
        src=ROOT/r['image']; stem=src.stem; split=r['split']
        if split=='train' and (r['name'],r['frame']) not in lookup: continue
        ip=target/'images'/split/src.name; lp=target/'labels'/split/(stem+'.txt')
        ip.parent.mkdir(parents=True,exist_ok=True); lp.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,ip)
        if split=='val': shutil.copyfile(reviewed/'labels'/split/(stem+'.txt'),lp); continue
        row=lookup[r['name'],r['frame']]; det=[b for b in row['detections'] if b[4]>=0.6]
        pairs=match_boxes([x['box'] for x in row['gt']],[x[:4] for x in det])
        quality['tp']+=len(pairs); quality['fp']+=len(det)-len(pairs); quality['fn']+=len(row['gt'])-len(pairs); quality['frames']+=1
        labels=[]
        for x1,y1,x2,y2,conf,cls in det:
            w=row['width']; h=row['height']; labels.append(f'0 {(x1+x2)/2/w:.7f} {(y1+y2)/2/h:.7f} {(x2-x1)/w:.7f} {(y2-y1)/h:.7f}')
        lp.write_text('\n'.join(labels),encoding='utf-8')
    (target/'data.yaml').write_text(f'path: {target.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: person\n',encoding='utf-8')
    quality['precision']=quality['tp']/max(1,quality['tp']+quality['fp']); quality['recall']=quality['tp']/max(1,quality['tp']+quality['fn'])
    save(OUT/'pseudo_label_quality.json',quality)
    # Review selector sees only predictions. Official GT is used subsequently to assess its choice.
    active=select_review_frames([r for r in cached if r['split']=='train'],48)
    save(OUT/'review_queue.json',active)
    print(quality,flush=True)

def train(args):
    torch.set_num_threads(4)
    data=DATA/f'yolo_{args.labels}'/'data.yaml'
    model=YOLO(str(ROOT/'models'/'yolo11n.pt'))
    model.train(data=str(data),epochs=args.epochs,imgsz=416,batch=8,device='cpu',workers=0,
                freeze=10,seed=42,deterministic=True,patience=10,optimizer='AdamW',lr0=0.0005,
                mosaic=0,mixup=0,fliplr=0.5,translate=0.05,scale=0.15,plots=False,amp=False,
                project=str(OUT/'training'),name=args.labels,exist_ok=True,verbose=False)

def metrics(rows,conf):
    tp=fp=fn=0; mae=[]; exact=[]
    for r in rows:
        pred=[p for p in r['detections'] if p[4]>=conf]; gt=[p['box'] for p in r['gt']]
        pairs=match_boxes(gt,[p[:4] for p in pred])
        tp+=len(pairs); fp+=len(pred)-len(pairs); fn+=len(gt)-len(pairs)
        mae.append(abs(len(pred)-len(gt))); exact.append(int(len(pred)==len(gt)))
    return {'frames':len(rows),'tp':tp,'fp':fp,'fn':fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn),
            'f1':2*tp/max(1,2*tp+fp+fn),'count_mae':float(np.mean(mae)),'exact_count_fraction':float(np.mean(exact))}

def tracking_metrics(rows,conf):
    clips=defaultdict(list)
    for r in rows: clips[r['name']].append(r)
    outputs=[]; totalgt=totalpred=idtp=switches=0
    zone_correct=zone_total=centre_correct=annotated=annotated_correct=annotated_centre=0; occ_errors=[]; dwell_errors=[]
    parameter_path=OUT/'zone_parameters.json'
    parameters=json.loads(parameter_path.read_text()) if parameter_path.exists() else {'persistence_s':.2,'margin':.008}
    for name,clip in clips.items():
        sample_dt=float(np.mean(np.diff([r['time'] for r in clip]))) if len(clip)>1 else .2
        tracker=BYTETracker(SimpleNamespace(track_high_thresh=conf,track_low_thresh=0.05,
            new_track_thresh=conf,track_buffer=max(1,round(1/sample_dt)),match_thresh=0.8,fuse_score=True))
        counts=Counter(); last={}; gt_dwell=defaultdict(float); pred_dwell=defaultdict(float)
        zz=zones(clip[0]['view']); state=ZoneState(zz,parameters['persistence_s'],parameters['margin']); histories=defaultdict(list)
        for r in clip:
            det=np.asarray(r['detections'],np.float32).reshape(-1,6)
            tracks=tracker.update(Boxes(det,(r['height'],r['width'])))
            totalgt+=len(r['gt']); totalpred+=len(tracks)
            pairs=match_boxes([p['box'] for p in r['gt']],[p[:4] for p in tracks])
            gt_occ=Counter(); pr_occ=Counter()
            for g in r['gt']:
                point=np.array(g['foot'])/[r['width'],r['height']]; z=assign_zone(point,zz)
                gt_occ[z]+=1; gt_dwell[(g['id'],z)]+=sample_dt
            for tr in tracks:
                tid=int(tr[4]); pt=[(tr[0]+tr[2])/2/r['width'],tr[3]/r['height']]
                z=state.update(tid,r['time'],pt); pr_occ[z]+=1; pred_dwell[(tid,z)]+=sample_dt
                histories[tid].append([r['time'],*pt])
            for i,j in pairs:
                g=r['gt'][i]; tr=tracks[j]; tid=int(tr[4]); gid=g['id']; counts[(gid,tid)]+=1
                if gid in last and r['time']-last[gid][0]<=0.8 and tid!=last[gid][1]: switches+=1
                last[gid]=(r['time'],tid)
                expected=assign_zone(np.array(g['foot'])/[r['width'],r['height']],zz)
                foot=assign_zone([(tr[0]+tr[2])/2/r['width'],tr[3]/r['height']],zz)
                centre=assign_zone([(tr[0]+tr[2])/2/r['width'],(tr[1]+tr[3])/2/r['height']],zz)
                zone_correct+=int(expected==foot); centre_correct+=int(expected==centre); zone_total+=1; annotated+=int(g['has_annotated_foot'])
                if g['has_annotated_foot']:
                    annotated_correct+=int(expected==foot);annotated_centre+=int(expected==centre)
            for z in zz: occ_errors.append(abs(gt_occ[z['id']]-pr_occ[z['id']]))
            outputs.append({**{k:r[k] for k in ['name','frame','time','width','height','view']},'tracks':np.asarray(tracks).tolist()})
        gids=sorted({x[0] for x in counts}); tids=sorted({x[1] for x in counts})
        table=np.array([[counts[g,t] for t in tids] for g in gids])
        if table.size:
            aa,bb=linear_sum_assignment(-table); idtp+=sum(table[i,j] for i,j in zip(aa,bb))
            mapping={gids[i]:tids[j] for i,j in zip(aa,bb)}
            for (gid,z),seconds in gt_dwell.items():
                if z is not None: dwell_errors.append(abs(seconds-pred_dwell.get((mapping.get(gid),z),0)))
    return {'sampled_idf1_iou50':2*int(idtp)/max(1,totalgt+totalpred),'id_switches_matched_within_0_8s':switches,
            'matched_zone_accuracy_foot':zone_correct/max(1,zone_total),'matched_zone_accuracy_centre':centre_correct/max(1,zone_total),
            'zone_matched_observations':zone_total,'matched_with_human_feet':annotated,
            'human_feet_only_zone_accuracy_foot':annotated_correct/max(1,annotated),
            'human_feet_only_zone_accuracy_centre':annotated_centre/max(1,annotated),
            'zone_persistence_s':parameters['persistence_s'],
            'zone_occupancy_mae_people':float(np.mean(occ_errors)),
            'oracle_mapped_observed_zone_duration_mae_s':float(np.mean(dwell_errors)),
            'duration_note':'Duration uses sampled observed frames, illustrative zones and oracle identity mapping for evaluation. Not completed visit wait-time or official retail zone labels.'},outputs

def evaluate():
    summaries=[]
    for file in sorted(OUT.glob('*_predictions.json')):
        data=json.loads(file.read_text()); rows=data['rows']; val=[r for r in rows if r['split']=='val']; test=[r for r in rows if r['split']=='test']
        sweep=[{'confidence':c,**metrics(val,c)} for c in [0.15,0.25,0.35,0.5]]
        best=max(sweep,key=lambda x:x['f1']); conf=best['confidence']
        summary={'tag':data['tag'],'selected_confidence_on_val':conf,'validation_sweep':sweep,'test':metrics(test,conf),
                 'test_per_clip':{name:metrics([r for r in test if r['name']==name],conf) for name in sorted({r['name'] for r in test})},
                 'timings':data['timings']}
        tracking,outputs=tracking_metrics(test,conf); summary['tracking_and_zones']=tracking
        save(OUT/f'{data["tag"]}_test_tracks.json',outputs); summaries.append(summary)
        print(data['tag'],summary['test'],tracking,flush=True)
    save(OUT/'comparison.json',{'evidence_scope':'Real CAVIAR shopping-centre video, scenario holdout at same site; detector adaptation is a small pilot.', 'runs':summaries})
    flat=[]
    for s in summaries: flat.append({'tag':s['tag'],'confidence':s['selected_confidence_on_val'],**s['test'],**{k:v for k,v in s['tracking_and_zones'].items() if k!='duration_note'}})
    with (OUT/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0])); w.writeheader(); w.writerows(flat)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['prepare','infer','pseudo','train','evaluate'])
    p.add_argument('--model',type=Path,default=ROOT/'models'/'yolo11n.pt'); p.add_argument('--tag',default='baseline')
    p.add_argument('--labels',choices=['reviewed','pseudo'],default='reviewed'); p.add_argument('--epochs',type=int,default=6)
    p.add_argument('--splits',nargs='+',choices=['train','val','test'],default=['train','val','test'])
    a=p.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    {'prepare':prepare,'infer':lambda:infer(a),'pseudo':pseudo,'train':lambda:train(a),'evaluate':evaluate}[a.action]()
