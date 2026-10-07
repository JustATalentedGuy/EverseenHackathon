from pathlib import Path
from collections import defaultdict
import json
import time

import cv2
import numpy as np
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "samples" / "epfl_lab" / "cam0.avi"
CALIB = ROOT / "references" / "epfl_multicam_pipeline" / "data" / "floor_plan" / "calibration-4p.txt"
OUT = ROOT / "experiments" / "tracker_benchmark_epfl_cam0.json"
VIS_DIR = ROOT / "experiments" / "tracker_videos"


def parse_homography(path: Path, wanted="cam0"):
    lines = path.read_text().splitlines()
    current = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("# Camera"):
            current = f"cam{s.split()[-1]}"
        elif s == "# Ground plane homography" and current == wanted:
            return np.asarray(
                [[float(v) for v in lines[i+j].split()] for j in (1,2,3)],
                dtype=np.float32,
            )
    raise RuntimeError(f"No homography for {wanted}")


def project_foot(H, xyxy):
    x1, y1, x2, y2 = map(float, xyxy)
    foot = np.asarray([[[0.5 * (x1 + x2), y2]]], dtype=np.float32)
    p = cv2.perspectiveTransform(foot, H)[0,0]
    return [float(p[0]), float(p[1])]


def run_tracker(tracker_name: str, max_frames=180, imgsz=480):
    # A fresh model instance is important because tracker state is persistent.
    weights = ROOT / "models" / "yolo11n.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    if not weights.exists():
        # Ultralytics accepts a model name and downloads once; afterwards copy is avoided.
        model = YOLO("yolo11n.pt")
        src = Path("yolo11n.pt")
        if src.exists():
            src.replace(weights)
        else:
            # Recent Ultralytics may cache elsewhere; model itself is already usable.
            weights = "yolo11n.pt"
    else:
        model = YOLO(str(weights))
    if isinstance(weights, Path) and weights.exists() and 'model' not in locals():
        model = YOLO(str(weights))

    H = parse_homography(CALIB)
    cap = cv2.VideoCapture(str(VIDEO))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {VIDEO}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    VIS_DIR.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(VIS_DIR / f"cam0_{tracker_name.split('.')[0]}.mp4"),
        cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
    )

    seen_frames = defaultdict(list)
    ground_paths = defaultdict(list)
    dets_per_frame = []
    ids_per_frame = []
    confs = []
    start = time.perf_counter()
    fi = 0
    while fi < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        result = model.track(
            frame,
            persist=True,
            tracker=tracker_name,
            classes=[0],
            conf=0.25,
            iou=0.5,
            imgsz=imgsz,
            device="cpu",
            verbose=False,
        )[0]
        boxes = result.boxes
        frame_ids = []
        if boxes is not None and len(boxes):
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else np.full(len(boxes), -1)
            confs.extend(map(float, conf))
            for box, tid in zip(xyxy, ids):
                if tid < 0:
                    continue
                tid = int(tid)
                frame_ids.append(tid)
                seen_frames[tid].append(fi)
                ground_paths[tid].append([fi, *project_foot(H, box)])
        dets_per_frame.append(int(len(boxes)) if boxes is not None else 0)
        ids_per_frame.append(len(frame_ids))
        writer.write(result.plot())
        fi += 1

    elapsed = time.perf_counter() - start
    writer.release()
    cap.release()

    def gaps(frames):
        return sum(1 for a,b in zip(frames, frames[1:]) if b-a > 1)

    track_stats = {}
    for tid, frames in seen_frames.items():
        track_stats[str(tid)] = {
            "observed_frames": len(frames),
            "first_frame": min(frames),
            "last_frame": max(frames),
            "span_frames": max(frames)-min(frames)+1,
            "internal_gaps": gaps(frames),
            "coverage_in_span": len(frames)/(max(frames)-min(frames)+1),
            "first_ground_point": ground_paths[tid][0][1:],
            "last_ground_point": ground_paths[tid][-1][1:],
        }

    long_tracks = [v for v in track_stats.values() if v["observed_frames"] >= 20]
    return {
        "tracker": tracker_name,
        "frames_processed": fi,
        "input_fps": fps,
        "runtime_seconds": elapsed,
        "processing_fps_cpu": fi/elapsed if elapsed else None,
        "mean_person_detections_per_frame": float(np.mean(dets_per_frame)) if dets_per_frame else 0,
        "mean_tracked_ids_per_frame": float(np.mean(ids_per_frame)) if ids_per_frame else 0,
        "mean_detection_confidence": float(np.mean(confs)) if confs else None,
        "unique_local_track_ids": len(track_stats),
        "tracks_ge_20_frames": len(long_tracks),
        "mean_coverage_long_tracks": float(np.mean([x["coverage_in_span"] for x in long_tracks])) if long_tracks else None,
        "total_internal_gaps_long_tracks": int(sum(x["internal_gaps"] for x in long_tracks)),
        "track_stats": track_stats,
        "note": "Without frame-level person-ID ground truth this measures track continuity/stability, not true IDF1/HOTA.",
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "video": str(VIDEO),
        "assumptions": {
            "person_localization_point": "bounding-box bottom-center (approximate floor contact)",
            "floor_mapping": "provided EPFL ground-plane homography",
            "model": "YOLO11n pretrained COCO, person class only",
        },
        "runs": []
    }
    for tracker in ("bytetrack.yaml", "botsort.yaml"):
        print(f"Running {tracker}...")
        report["runs"].append(run_tracker(tracker))
        OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps([{k:v for k,v in r.items() if k != "track_stats"} for r in report["runs"]], indent=2))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
