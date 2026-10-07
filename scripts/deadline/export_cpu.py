"""Export the selected detector and check CPU prediction equivalence on validation frames."""
import json
import time
from pathlib import Path
import sys
import cv2
import numpy as np
import torch
from ultralytics import YOLO
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from prototype.core import match_boxes
from scripts.deadline.experiment import OUT,save
torch.set_num_threads(4)
model=YOLO(str(ROOT/'models'/'yolo11n.pt'))
previous=OUT/'cpu_export_validation.json'
if previous.exists():
    save(OUT/'cpu_export_original_rect_mismatch.json',json.loads(previous.read_text()))
onnx_path=model.export(format='onnx',imgsz=416,opset=17,simplify=False,dynamic=False,device='cpu',half=False)
other=YOLO(str(onnx_path),task='detect')
images=sorted((ROOT/'datasets'/'caviar'/'yolo_reviewed'/'images'/'val').glob('*.jpg'))[::3]
records=[];durations={'torch':[],'onnx':[]};total=0;matched=0;maxdiff=0
for ip in images:
    img=cv2.imread(str(ip)); outputs={}
    for name,m in [('torch',model),('onnx',other)]:
        start=time.perf_counter();r=m.predict(img,classes=[0],imgsz=416,rect=False,conf=.35,verbose=False,device='cpu')[0]
        elapsed=time.perf_counter()-start
        outputs[name]=r.boxes.data.cpu().numpy()
        durations[name].append(elapsed)
    a,b=outputs['torch'],outputs['onnx'];pairs=match_boxes(a[:,:4],b[:,:4],.95)
    total+=len(a);matched+=len(pairs)
    for i,j in pairs:maxdiff=max(maxdiff,float(np.max(np.abs(a[i,:4]-b[j,:4]))))
    records.append({'image':str(ip.relative_to(ROOT)),'torch_count':len(a),'onnx_count':len(b),'iou95_matches':len(pairs)})
save(OUT/'cpu_export_validation.json',{'model':str(onnx_path),'validation_images':len(images),
     'matched_fraction_at_iou95':matched/max(1,total),'max_matched_box_difference_px':maxdiff,
     'torch_median_sample_s_excluding_warmup':float(np.median(durations['torch'][1:])),
     'onnx_median_sample_s_excluding_warmup':float(np.median(durations['onnx'][1:])),
     'records':records,'input_policy':'Both engines use identical square letterboxing with rect=False. The main PyTorch video experiment uses automatic rectangular letterboxing.',
     'note':'Small sequential CPU validation benchmark; concurrent experiments and camera decode are not represented. Export is a candidate, not the assessed deployment default.'})
print('CPU export validation complete')
