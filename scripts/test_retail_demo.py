"""Audit demo candidate video decode and sampled person detections without GT claims.

The audit counts model predictions, NOT true positives or accuracy metrics.
Outputs are local ignored JSON; candidates remain unverified until this runs.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'runs' / 'retail_demo_validation.json'
CANDIDATES = {
    'caviar_walkby': 'datasets/caviar/WalkByShop1cor.mpg',
    'caviar_assistant': 'datasets/caviar/ShopAssistant1front.mpg',
    'caviar_entry': 'datasets/caviar/TwoEnterShop3front.mpg',
    'merl_shelf': 'samples/retail_demo/merl_shelf_browse.mp4',
    'mall_crowd': 'samples/retail_demo/mall_crowd.mp4',
    'teammate_store': '.cache/teammate-EverseenML/store.mp4',
    'caviar_existing_busy': 'datasets/caviar/OneShopOneWait2cor.mpg',
    'caviar_existing_entry': 'datasets/caviar/TwoEnterShop1front.mpg',
}


def evaluate(path, model):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError('OpenCV cannot open video')
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width < 150 or height < 100:
            raise ValueError('Video is too short or low-resolution')
        predictions=[];sample_errors=0; frame_signatures=[]
        raw_frames=[]
        decoded=0
        if path.suffix.lower()=='.mpg':
            # CAVIAR MPEG metadata is known to report a handful of frames despite
            # containing >1,000 sequentially decodable frames; never seek on MPEG.
            while True:
                ok,frame=cap.read()
                if not ok:break
                if decoded%75==0 and len(raw_frames)<24:raw_frames.append(frame.copy())
                decoded+=1
            raw_frames=raw_frames[::max(1,round(len(raw_frames)/12))][:12]
        else:
            if count < 20:
                raise ValueError('Video too short')
            indices=sorted(set(int(i) for i in np.linspace(0,max(0,count-2),12)))
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES,index)
                ok,frame=cap.read()
                if not ok:
                    sample_errors+=1
                    continue
                raw_frames.append(frame)
            decoded=count
        for frame in raw_frames:
            frame_signatures.append(hashlib.sha256(frame.tobytes()).hexdigest()[:12])
            r=model.predict(frame,imgsz=416,classes=[0],conf=0.35,verbose=False,device='cpu')[0]
            predictions.append(int(len(r.boxes)))
        if len(predictions) < 8:
            raise ValueError('Could not decode enough sample frames')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1048576),b''):
                digest.update(chunk)
        return {'path': str(path.relative_to(ROOT)).replace('\\','/'),
                'file_bytes':path.stat().st_size,'sha256':digest.hexdigest(),
                'resolution':f'{width}x{height}', 'fps':round(fps,3),
                'metadata_frames':count,'decoded_frames':decoded,
                'estimated_duration_s':round(decoded/fps,1),
                'samples_decoded':len(predictions), 'seek_errors':sample_errors,
                'mean_predicted_persons':round(float(np.mean(predictions)),2),
                'nonempty_sample_fraction':round(float(np.mean(np.array(predictions)>0)),2),
                'max_predicted_persons':max(predictions), 'distinct_frames':len(set(frame_signatures)),
                'model_used':'YOLO11n ONNX selected export, conf 0.35, sampled predictions only',
                'finding':'person detections present' if any(predictions) else 'no person detections',
                'status':'tested'}
    finally:
        cap.release()


def main():
    model_path = ROOT / 'models/yolo11n.onnx'
    if not model_path.exists():
        model_path = ROOT / 'models/yolo11n.pt'
    model = YOLO(str(model_path))
    results={}
    for name,source in CANDIDATES.items():
        path=ROOT/source
        if not path.exists():
            results[name]={'status':'missing', 'path':source}
            continue
        try:
            results[name]=evaluate(path,model)
            print(name,results[name],flush=True)
        except Exception as exc:
            results[name]={'status':'failed','path':source,'error':str(exc)}
            print(name,'FAILED',exc,flush=True)
    RESULTS.parent.mkdir(parents=True,exist_ok=True)
    RESULTS.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('Saved',RESULTS,flush=True)


if __name__ == '__main__':
    main()
