"""Create reproducible GT/detection overlays for independent visual inspection."""
import json
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments'/'deadline'
rows=json.loads((OUT/'baseline_predictions.json').read_text())['rows']
selected=[]
for name in sorted({r['name'] for r in rows if r['split']=='test'}):
    clip=[r for r in rows if r['name']==name]
    selected.extend(clip[i] for i in [0,len(clip)//2])
tiles=[]
for r in selected:
    cap=cv2.VideoCapture(str(ROOT/'datasets'/'caviar'/(r['name']+'.mpg')))
    for f in range(r['frame']+1):ok,img=cap.read()
    cap.release();assert ok
    for g in r['gt']:
        b=np.array(g['box']).astype(int);cv2.rectangle(img,tuple(b[:2]),tuple(b[2:]),(100,255,100),1)
        cv2.circle(img,tuple(np.array(g['foot']).astype(int)),2,(100,255,100),-1)
    for p in r['detections']:
        if p[4]<.35:continue
        b=np.array(p[:4]).astype(int);cv2.rectangle(img,tuple(b[:2]),tuple(b[2:]),(80,80,255),1)
    tile=np.zeros((324,384,3),np.uint8);tile[:288]=img
    cv2.putText(tile,r['name'],(5,303),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1)
    cv2.putText(tile,f'frame {r["frame"]}: GT green, prediction red',(5,318),cv2.FONT_HERSHEY_SIMPLEX,.32,(255,255,255),1)
    tiles.append(tile)
montage=np.concatenate([np.concatenate(tiles[i:i+2],axis=1) for i in range(0,len(tiles),2)],axis=0)
cv2.imwrite(str(OUT/'heldout_visual_audit.jpg'),montage)
print('saved heldout_visual_audit.jpg')
