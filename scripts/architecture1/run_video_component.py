from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from citic_common import assign_gt_sections, assign_section, load_cameras, load_gt, load_rooms, point_in_polygon  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def invert_homography(h):
    return np.linalg.inv(np.asarray(h, dtype=np.float64))


def project_h(h, x, y):
    v = np.asarray([x, y, 1.0], dtype=np.float64)
    o = h @ v
    if abs(o[2]) < 1e-12:
        return None
    return float(o[0] / o[2]), float(o[1] / o[2])


def longest_positive_run(frames_with_people: set[int]) -> tuple[int, int]:
    if not frames_with_people:
        raise RuntimeError("No GT points fall inside the camera visibility polygon")
    values = sorted(frames_with_people)
    best = (values[0], values[0])
    start = prev = values[0]
    for f in values[1:]:
        if f == prev + 1:
            prev = f
        else:
            if prev - start > best[1] - best[0]:
                best = (start, prev)
            start = prev = f
    if prev - start > best[1] - best[0]:
        best = (start, prev)
    return best


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--capture", type=int, default=1)
    p.add_argument("--camera", default="Showroom")
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--conf", type=float, default=0.25)
    args = p.parse_args()

    rooms, _ = load_rooms(args.dataset_root)
    cameras = load_cameras(args.dataset_root)
    cam = cameras[args.camera]
    if "homography" not in cam.get("calibration", {}):
        raise RuntimeError(f"{args.camera} does not provide a direct homography; this script intentionally uses one that does")
    h_img_to_world = np.asarray(cam["calibration"]["homography"], dtype=np.float64)
    h_world_to_img = invert_homography(h_img_to_world)

    gt = load_gt(args.dataset_root, args.capture)
    assign_gt_sections(gt, rooms)
    gt_by_frame = defaultdict(list)
    visible_frames = set()
    for o in gt:
        if point_in_polygon((o.x, o.y), cam["visibility_polygon"]):
            gt_by_frame[o.frame].append(o)
            visible_frames.add(o.frame)

    run_start, run_end = longest_positive_run(visible_frames)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {args.video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    max_segment_frames = max(1, round(args.seconds * fps))
    # CITIC GT frame indices are 1-based. Pick the beginning of the longest GT-visible run.
    start_frame = max(1, run_start)
    end_frame = min(run_end, start_frame + max_segment_frames - 1, total_frames)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame - 1)

    model = YOLO(str(args.model))
    rows = []
    track_lengths = Counter()
    total_detections = 0
    total_inside_visibility = 0
    total_inside_section = 0
    count_errors = []
    exact_count = 0

    for frame_idx in range(start_frame, end_frame + 1):
        ok, frame = cap.read()
        if not ok:
            break
        results = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=args.conf,
            imgsz=640,
            verbose=False,
            device="cpu",
        )
        r = results[0]
        det_count = 0
        inside_visibility = 0
        inside_section = 0
        ids = []
        if r.boxes is not None and len(r.boxes):
            xyxy = r.boxes.xyxy.cpu().numpy()
            id_tensor = r.boxes.id
            track_ids = id_tensor.int().cpu().tolist() if id_tensor is not None else [None] * len(xyxy)
            for box, tid in zip(xyxy, track_ids):
                x1, y1, x2, y2 = [float(v) for v in box]
                u = 0.5 * (x1 + x2)
                v = y2
                world = project_h(h_img_to_world, u, v)
                det_count += 1
                if tid is not None:
                    ids.append(int(tid))
                    track_lengths[int(tid)] += 1
                if world is not None:
                    if point_in_polygon(world, cam["visibility_polygon"]):
                        inside_visibility += 1
                    if assign_section(world, rooms, None) == "SH":
                        inside_section += 1
        gt_count = len(gt_by_frame.get(frame_idx, []))
        err = abs(det_count - gt_count)
        count_errors.append(err)
        exact_count += int(det_count == gt_count)
        total_detections += det_count
        total_inside_visibility += inside_visibility
        total_inside_section += inside_section
        rows.append(
            {
                "frame": frame_idx,
                "gt_visible_people": gt_count,
                "detected_people": det_count,
                "absolute_count_error": err,
                "detections_projecting_inside_visibility": inside_visibility,
                "detections_projecting_inside_SH_section": inside_section,
                "active_track_ids": ";".join(str(x) for x in sorted(ids)),
            }
        )

    cap.release()
    processed = len(rows)
    mean_gt = sum(r["gt_visible_people"] for r in rows) / processed if processed else 0.0
    mean_det = sum(r["detected_people"] for r in rows) / processed if processed else 0.0
    track_lens = sorted(track_lengths.values())
    median_track_len = float(np.median(track_lens)) if track_lens else 0.0

    summary = {
        "dataset": "CITIC-MTMC",
        "capture": args.capture,
        "camera": args.camera,
        "video": str(args.video),
        "model": str(args.model),
        "tracker": "Ultralytics ByteTrack",
        "confidence_threshold": args.conf,
        "video_fps": fps,
        "video_frame_count": total_frames,
        "segment_start_frame_1_based": start_frame,
        "segment_end_frame_1_based": rows[-1]["frame"] if rows else start_frame - 1,
        "frames_processed": processed,
        "segment_seconds_processed": processed / fps if fps else 0.0,
        "gt_visible_run_available": [run_start, run_end],
        "mean_gt_visible_people_per_frame": mean_gt,
        "mean_detected_people_per_frame": mean_det,
        "person_count_mae_per_frame": sum(count_errors) / processed if processed else math.nan,
        "exact_person_count_frame_fraction": exact_count / processed if processed else math.nan,
        "detections_total": total_detections,
        "detections_projecting_inside_official_visibility_fraction": total_inside_visibility / total_detections if total_detections else math.nan,
        "detections_projecting_inside_showroom_section_fraction": total_inside_section / total_detections if total_detections else math.nan,
        "unique_bytetrack_ids": len(track_lengths),
        "median_track_length_frames": median_track_len,
        "note": "Count comparison uses official world GT filtered by the official Showroom visibility polygon. It is a real-video sanity component, not a full detector benchmark; GT supplies floor positions rather than image boxes.",
    }
    write_csv(args.output_dir / "video_showroom_frames.csv", rows)
    write_json(args.output_dir / "video_showroom_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
