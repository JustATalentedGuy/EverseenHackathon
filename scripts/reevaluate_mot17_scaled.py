from pathlib import Path
from collections import defaultdict
import csv
import json

import motmetrics as mm
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GT = ROOT / 'samples' / 'mot17' / 'labels' / 'train' / 'MOT17-11-DPM' / 'gt' / 'gt.txt'
PRED_DIR = ROOT / 'experiments' / 'mot17_predictions'
OUT = ROOT / 'experiments' / 'mot17_11_tracker_eval_scaled.json'

ORIGINAL_W, ORIGINAL_H = 1920.0, 1080.0
PREVIEW_W, PREVIEW_H = 960.0, 540.0
SX, SY = ORIGINAL_W / PREVIEW_W, ORIGINAL_H / PREVIEW_H


def load_gt():
    by = defaultdict(list)
    with GT.open(newline='') as f:
        for r in csv.reader(f):
            if not r:
                continue
            frame = int(float(r[0])); oid = int(float(r[1]))
            x,y,w,h = map(float,r[2:6])
            mark = int(float(r[6])); cls = int(float(r[7]))
            if mark == 1 and cls == 1:
                by[frame].append((oid,[x,y,w,h]))
    return by


def load_pred(path):
    by = defaultdict(list)
    with path.open(newline='') as f:
        for r in csv.reader(f):
            if not r:
                continue
            frame = int(float(r[0])); tid=int(float(r[1]))
            x,y,w,h = map(float,r[2:6])
            by[frame].append((tid,[x*SX,y*SY,w*SX,h*SY]))
    return by


def eval_file(path):
    gt=load_gt(); pr=load_pred(path)
    acc=mm.MOTAccumulator(auto_id=True)
    for frame in range(1,901):
        g=gt.get(frame,[]); p=pr.get(frame,[])
        gids=[x[0] for x in g]; gboxes=[x[1] for x in g]
        pids=[x[0] for x in p]; pboxes=[x[1] for x in p]
        d=mm.distances.iou_matrix(gboxes,pboxes,max_iou=0.5)
        acc.update(gids,pids,d)
    metrics=['num_frames','num_objects','mota','motp','idf1','idp','idr','num_matches','num_switches','num_false_positives','num_misses','mostly_tracked','partially_tracked','mostly_lost','num_fragmentations']
    row=mm.metrics.create().compute(acc,metrics=metrics,name=path.stem).iloc[0].to_dict()
    clean={}
    for k,v in row.items():
        if isinstance(v,(np.integer,int)): clean[k]=int(v)
        elif isinstance(v,(np.floating,float)): clean[k]=None if not np.isfinite(v) else float(v)
        else: clean[k]=v
    return clean


def main():
    report={
        'annotation_resolution':[int(ORIGINAL_W),int(ORIGINAL_H)],
        'preview_video_resolution':[int(PREVIEW_W),int(PREVIEW_H)],
        'prediction_scale_to_annotation':[SX,SY],
        'note':'Predictions were generated on MOTChallenge preview MP4, which is exactly half the original annotation dimensions. Boxes are scaled by 2 before IoU evaluation.',
        'runs':{}
    }
    for name in ('bytetrack','botsort'):
        p=PRED_DIR/f'MOT17-11-{name}.txt'
        report['runs'][name]=eval_file(p)
    OUT.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    print('saved',OUT)

if __name__=='__main__':
    main()
