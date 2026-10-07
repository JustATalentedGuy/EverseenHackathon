from pathlib import Path
from collections import defaultdict
import csv
import json
import time

import cv2
import motmetrics as mm
import numpy as np
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "samples" / "mot17" / "MOT17-11-raw.mp4"
GT = ROOT / "samples" / "mot17" / "labels" / "train" / "MOT17-11-DPM" / "gt" / "gt.txt"
OUT = ROOT / "experiments" / "mot17_11_tracker_eval.json"
PRED_DIR = ROOT / "experiments" / "mot17_predictions"
MODEL = ROOT / "models" / "yolo11n.pt"


def load_gt():
    """MOT17: keep marked pedestrian class=1; ignore distractor classes here."""
    by_frame = defaultdict(list)
    with GT.open(newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            frame = int(float(row[0]))
            oid = int(float(row[1]))
            x, y, w, h = map(float, row[2:6])
            mark = int(float(row[6]))
            cls = int(float(row[7])) if len(row) > 7 else 1
            vis = float(row[8]) if len(row) > 8 else 1.0
            if mark == 1 and cls == 1:
                by_frame[frame].append((oid, [x, y, w, h], vis))
    return by_frame


def ensure_model():
    if MODEL.exists():
        return YOLO(str(MODEL))
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    p = ROOT / "yolo11n.pt"
    model = YOLO(str(p if p.exists() else "yolo11n.pt"))
    if p.exists() and not MODEL.exists():
        p.replace(MODEL)
    return model


def run(tracker_yaml, conf=0.20, imgsz=640):
    model = ensure_model()
    cap = cv2.VideoCapture(str(VIDEO))
    if not cap.isOpened():
        raise RuntimeError(VIDEO)
    fps_in = cap.get(cv2.CAP_PROP_FPS)
    n_expected = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    gt = load_gt()
    acc = mm.MOTAccumulator(auto_id=True)
    rows = []
    frame = 0
    detections = 0
    tracked_boxes = 0
    t0 = time.perf_counter()

    while True:
        ok, img = cap.read()
        if not ok:
            break
        frame += 1
        result = model.track(
            img,
            persist=True,
            tracker=tracker_yaml,
            classes=[0],
            conf=conf,
            iou=0.5,
            imgsz=imgsz,
            device="cpu",
            verbose=False,
        )[0]

        pred_ids, pred_tlwh = [], []
        boxes = result.boxes
        if boxes is not None:
            detections += len(boxes)
            xyxy = boxes.xyxy.cpu().numpy() if len(boxes) else np.empty((0,4))
            tids = boxes.id.cpu().numpy().astype(int) if len(boxes) and boxes.id is not None else np.full(len(xyxy), -1)
            confs = boxes.conf.cpu().numpy() if len(boxes) else np.empty((0,))
            for b, tid, score in zip(xyxy, tids, confs):
                if tid < 0:
                    continue
                x1,y1,x2,y2 = map(float,b)
                tlwh = [x1,y1,x2-x1,y2-y1]
                pred_ids.append(int(tid))
                pred_tlwh.append(tlwh)
                tracked_boxes += 1
                rows.append([frame,int(tid),x1,y1,x2-x1,y2-y1,float(score),-1,-1,-1])

        g = gt.get(frame, [])
        gt_ids = [x[0] for x in g]
        gt_boxes = [x[1] for x in g]
        dists = mm.distances.iou_matrix(gt_boxes, pred_tlwh, max_iou=0.5)
        acc.update(gt_ids, pred_ids, dists)

    elapsed = time.perf_counter()-t0
    cap.release()

    metrics = [
        "num_frames","num_objects","mota","motp","idf1","idp","idr",
        "num_matches","num_switches","num_false_positives","num_misses",
        "mostly_tracked","partially_tracked","mostly_lost","num_fragmentations"
    ]
    mh = mm.metrics.create()
    summary = mh.compute(acc, metrics=metrics, name=tracker_yaml).iloc[0].to_dict()
    clean = {}
    for k,v in summary.items():
        if isinstance(v, (np.integer, int)):
            clean[k] = int(v)
        elif isinstance(v, (np.floating, float)):
            clean[k] = None if not np.isfinite(v) else float(v)
        else:
            clean[k] = v

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    pred_path = PRED_DIR / f"MOT17-11-{tracker_yaml.split('.')[0]}.txt"
    with pred_path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)

    return {
        "tracker": tracker_yaml,
        "detector": "YOLO11n COCO pretrained / person class",
        "confidence_threshold": conf,
        "imgsz": imgsz,
        "frames_read": frame,
        "expected_frames": n_expected,
        "input_fps": fps_in,
        "runtime_seconds_cpu": elapsed,
        "processing_fps_cpu": frame/elapsed if elapsed else None,
        "raw_detection_count": detections,
        "tracked_box_count": tracked_boxes,
        "motmetrics": clean,
        "prediction_file": str(pred_path),
        "evaluation_note": (
            "MOTChallenge-style comparison using class=1 marked pedestrian GT and IoU>=0.5. "
            "This is not claimed as an official MOTChallenge leaderboard score because the official evaluator's ignore-region handling may differ."
        ),
    }


def main():
    report = {
        "dataset": "MOT17-11 (busy shopping mall, moving camera)",
        "video": str(VIDEO),
        "gt": str(GT),
        "runs": [],
    }
    for tracker in ("bytetrack.yaml", "botsort.yaml"):
        print(f"Evaluating {tracker}...")
        report["runs"].append(run(tracker))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2))
        print(json.dumps(report["runs"][-1], indent=2))
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
