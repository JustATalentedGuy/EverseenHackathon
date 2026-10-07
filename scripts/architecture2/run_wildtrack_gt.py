"""Architecture 2 experiments on a tiny official WILDTRACK GT/calibration subset.

Experiments are GT-derived: no RGB images are required. We use the real
WILDTRACK per-view boxes, person IDs, position IDs and camera calibration.
Additional calibration, timestamp, detection and dropout errors are simulated
explicitly and are always reported as perturbations of that real annotation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "samples" / "wildtrack_subset"
OUT = ROOT / "experiments" / "architecture2"
CAMERAS = ["CVLab1", "CVLab2", "CVLab3", "CVLab4", "IDIAP1", "IDIAP2", "IDIAP3"]
IMAGE_W, IMAGE_H = 1920, 1080
GRID_W, GRID_H = 480, 1440
GRID_STEP_CM = 2.5
GRID_ORIGIN_CM = (-300.0, -900.0)
ANNOTATION_DT_S = 0.5  # released frames 0,5,10,... from a 10 FPS synchronized stream
SECTION_N = 4
FUSION_THRESHOLD_CM = 75.0


@dataclass
class Camera:
    name: str
    K: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray
    H_world_to_image: np.ndarray


def load_matrix(path: Path, name: str) -> np.ndarray:
    fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    try:
        matrix = fs.getNode(name).mat()
    finally:
        fs.release()
    if matrix is None:
        raise RuntimeError(f"{path}: missing matrix {name}")
    return np.asarray(matrix, dtype=np.float64)


def load_cameras() -> list[Camera]:
    cameras = []
    for name in CAMERAS:
        K = load_matrix(
            DATA / "calibrations" / "intrinsic_zero" / f"intr_{name}.xml",
            "camera_matrix",
        )
        root = ET.parse(
            DATA / "calibrations" / "extrinsic" / f"extr_{name}.xml"
        ).getroot()
        rvec = np.fromstring(root.find("rvec").text.strip(), dtype=np.float64, sep=" ")
        tvec = np.fromstring(root.find("tvec").text.strip(), dtype=np.float64, sep=" ")
        R, _ = cv2.Rodrigues(rvec)
        H = K @ np.column_stack([R[:, 0], R[:, 1], tvec.reshape(3)])
        H /= H[2, 2]
        cameras.append(Camera(name, K, rvec, tvec, H))
    return cameras


def position_id_to_world_cm(position_id: int) -> np.ndarray:
    return np.array(
        [
            GRID_ORIGIN_CM[0] + GRID_STEP_CM * (position_id % GRID_W),
            GRID_ORIGIN_CM[1] + GRID_STEP_CM * (position_id // GRID_W),
        ],
        dtype=np.float64,
    )


def project_image_to_world(H_world_to_image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    Hinv = np.linalg.inv(H_world_to_image)
    p = Hinv @ np.array([float(uv[0]), float(uv[1]), 1.0])
    return p[:2] / p[2]


def section_of(world_xy: np.ndarray) -> int:
    x, y = map(float, world_xy)
    x0, y0 = GRID_ORIGIN_CM
    width = GRID_W * GRID_STEP_CM
    height = GRID_H * GRID_STEP_CM
    sx = int(np.clip(math.floor((x - x0) / width * SECTION_N), 0, SECTION_N - 1))
    sy = int(np.clip(math.floor((y - y0) / height * SECTION_N), 0, SECTION_N - 1))
    return sy * SECTION_N + sx


def load_frames(limit: int | None = None) -> list[dict]:
    files = sorted((DATA / "annotations_positions").glob("*.json"))
    if limit:
        files = files[:limit]
    frames = []
    for seq_idx, path in enumerate(files):
        people = {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        for person in raw:
            pid = int(person["personID"])
            views = {}
            for view in person["views"]:
                if int(view["xmax"]) < 0:
                    continue
                views[int(view["viewNum"])] = {
                    "xmin": float(view["xmin"]),
                    "ymin": float(view["ymin"]),
                    "xmax": float(view["xmax"]),
                    "ymax": float(view["ymax"]),
                }
            people[pid] = {
                "world_gt": position_id_to_world_cm(int(person["positionID"])),
                "views": views,
            }
        frames.append(
            {
                "seq_idx": seq_idx,
                "source_frame_number": int(path.stem),
                "time_s": seq_idx * ANNOTATION_DT_S,
                "people": people,
            }
        )
    return frames


def perturb_homography(
    H: np.ndarray, sigma_px: float, rng: np.random.Generator
) -> np.ndarray:
    if sigma_px <= 0:
        return H.copy()
    image_anchors = np.array(
        [
            [0.15 * IMAGE_W, 0.45 * IMAGE_H],
            [0.50 * IMAGE_W, 0.45 * IMAGE_H],
            [0.85 * IMAGE_W, 0.45 * IMAGE_H],
            [0.15 * IMAGE_W, 0.65 * IMAGE_H],
            [0.50 * IMAGE_W, 0.65 * IMAGE_H],
            [0.85 * IMAGE_W, 0.65 * IMAGE_H],
            [0.15 * IMAGE_W, 0.88 * IMAGE_H],
            [0.50 * IMAGE_W, 0.88 * IMAGE_H],
            [0.85 * IMAGE_W, 0.88 * IMAGE_H],
        ],
        dtype=np.float64,
    )
    world = np.array([project_image_to_world(H, p) for p in image_anchors])
    noisy_image = image_anchors + rng.normal(0.0, sigma_px, image_anchors.shape)
    H_fit, _ = cv2.findHomography(world.astype(np.float64), noisy_image.astype(np.float64), 0)
    if H_fit is None:
        raise RuntimeError("homography perturbation fit failed")
    return H_fit / H_fit[2, 2]


def make_observations(
    frames: list[dict],
    cameras: list[Camera],
    *,
    detection_sigma_px: float,
    calibration_sigma_px: float,
    timestamp_sigma_s: float,
    miss_rate: float,
    seed: int,
) -> tuple[list[list[dict]], dict[str, int]]:
    rng = np.random.default_rng(seed)
    Hs = [
        perturb_homography(c.H_world_to_image, calibration_sigma_px, rng)
        for c in cameras
    ]
    # One fixed clock offset per camera models imperfect stream synchronization.
    sigma_frames = timestamp_sigma_s / ANNOTATION_DT_S
    offsets = np.rint(rng.normal(0.0, sigma_frames, len(cameras))).astype(int)
    by_base_frame: list[list[dict]] = []

    for base_idx in range(len(frames)):
        frame_obs = []
        for view_idx, camera in enumerate(cameras):
            source_idx = base_idx + int(offsets[view_idx])
            if not (0 <= source_idx < len(frames)):
                continue
            source = frames[source_idx]
            base_people = frames[base_idx]["people"]
            for pid, person in source["people"].items():
                bbox = person["views"].get(view_idx)
                if bbox is None or rng.random() < miss_rate:
                    continue
                uv = np.array(
                    [(bbox["xmin"] + bbox["xmax"]) * 0.5, bbox["ymax"]],
                    dtype=np.float64,
                )
                if detection_sigma_px > 0:
                    uv += rng.normal(0.0, detection_sigma_px, 2)
                world_est = project_image_to_world(Hs[view_idx], uv)
                obs = {
                    "base_frame": base_idx,
                    "source_frame": source_idx,
                    "camera_idx": view_idx,
                    "camera": camera.name,
                    "person_id": pid,
                    "uv": uv,
                    "world_est": world_est,
                    "source_world_gt": person["world_gt"],
                    "base_world_gt": (
                        base_people[pid]["world_gt"] if pid in base_people else None
                    ),
                }
                frame_obs.append(obs)
        by_base_frame.append(frame_obs)
    return by_base_frame, {cameras[i].name: int(offsets[i]) for i in range(len(cameras))}


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def projection_metrics(by_frame: list[list[dict]]) -> dict:
    errors = []
    correct = 0
    n = 0
    per_camera = defaultdict(list)
    for observations in by_frame:
        for obs in observations:
            err = float(np.linalg.norm(obs["world_est"] - obs["source_world_gt"]))
            errors.append(err)
            per_camera[obs["camera"]].append(err)
            correct += section_of(obs["world_est"]) == section_of(obs["source_world_gt"])
            n += 1
    return {
        "n_observations": n,
        "median_error_cm": percentile(errors, 50),
        "p90_error_cm": percentile(errors, 90),
        "mean_error_cm": float(np.mean(errors)) if errors else None,
        "section_accuracy": correct / n if n else None,
        "per_camera": {
            cam: {
                "n": len(vals),
                "median_error_cm": percentile(vals, 50),
                "p90_error_cm": percentile(vals, 90),
            }
            for cam, vals in sorted(per_camera.items())
        },
    }


def overlap_agreement(by_frame: list[list[dict]]) -> dict:
    distances = []
    for observations in by_frame:
        by_person = defaultdict(list)
        for obs in observations:
            by_person[obs["person_id"]].append(obs)
        for person_obs in by_person.values():
            for i in range(len(person_obs)):
                for j in range(i + 1, len(person_obs)):
                    if person_obs[i]["camera_idx"] == person_obs[j]["camera_idx"]:
                        continue
                    distances.append(
                        float(
                            np.linalg.norm(
                                person_obs[i]["world_est"] - person_obs[j]["world_est"]
                            )
                        )
                    )
    return {
        "n_same_person_cross_camera_pairs": len(distances),
        "median_disagreement_cm": percentile(distances, 50),
        "p90_disagreement_cm": percentile(distances, 90),
        "fraction_within_50cm": (
            float(np.mean(np.array(distances) <= 50.0)) if distances else None
        ),
        "fraction_within_100cm": (
            float(np.mean(np.array(distances) <= 100.0)) if distances else None
        ),
    }


def cluster_frame(observations: list[dict], threshold_cm: float) -> list[list[int]]:
    n = len(observations)
    parent = list(range(n))
    members = [{i} for i in range(n)]
    cameras = [{observations[i]["camera_idx"]} for i in range(n)]

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if observations[i]["camera_idx"] == observations[j]["camera_idx"]:
                continue
            d = float(
                np.linalg.norm(observations[i]["world_est"] - observations[j]["world_est"])
            )
            if d <= threshold_cm:
                edges.append((d, i, j))
    edges.sort(key=lambda x: x[0])

    # Single-link geometry clustering with an important physical constraint:
    # one fused person cannot contain two simultaneous observations from the
    # same camera. This prevents transitive chains from swallowing neighbours.
    for _, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj or cameras[ri] & cameras[rj]:
            continue
        if len(members[ri]) < len(members[rj]):
            ri, rj = rj, ri
        parent[rj] = ri
        members[ri] |= members[rj]
        cameras[ri] |= cameras[rj]
        members[rj].clear()
        cameras[rj].clear()

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    return list(clusters.values())


def fusion_metrics(by_frame: list[list[dict]], threshold_cm: float) -> dict:
    tp = fp = fn = 0
    wrong_clusters = 0
    merged_clusters = 0
    duplicate_before = 0
    duplicate_after = 0
    fused_position_errors = []

    for observations in by_frame:
        if not observations:
            continue
        clusters = cluster_frame(observations, threshold_cm)
        cluster_of = {}
        for ci, cluster in enumerate(clusters):
            ids = {observations[i]["person_id"] for i in cluster}
            if len(cluster) > 1:
                merged_clusters += 1
                if len(ids) > 1:
                    wrong_clusters += 1
            for i in cluster:
                cluster_of[i] = ci
            # Base-time position error is where timestamp offsets matter.
            if len(ids) == 1:
                pid = next(iter(ids))
                base_gts = [
                    observations[i]["base_world_gt"]
                    for i in cluster
                    if observations[i]["base_world_gt"] is not None
                ]
                if base_gts:
                    estimate = np.mean(
                        [observations[i]["world_est"] for i in cluster], axis=0
                    )
                    target = np.mean(base_gts, axis=0)
                    fused_position_errors.append(float(np.linalg.norm(estimate - target)))

        by_pid = defaultdict(list)
        for i, obs in enumerate(observations):
            by_pid[obs["person_id"]].append(i)
        duplicate_before += sum(max(0, len(v) - 1) for v in by_pid.values())
        for indices in by_pid.values():
            n_clusters = len({cluster_of[i] for i in indices})
            duplicate_after += max(0, n_clusters - 1)

        for i in range(len(observations)):
            for j in range(i + 1, len(observations)):
                if observations[i]["camera_idx"] == observations[j]["camera_idx"]:
                    continue
                truth = observations[i]["person_id"] == observations[j]["person_id"]
                pred = cluster_of[i] == cluster_of[j]
                if truth and pred:
                    tp += 1
                elif not truth and pred:
                    fp += 1
                elif truth and not pred:
                    fn += 1

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold_cm": threshold_cm,
        "pair_precision": precision,
        "pair_recall": recall,
        "pair_f1": f1,
        "pair_tp": tp,
        "pair_fp": fp,
        "pair_fn": fn,
        "wrong_merge_cluster_rate": (
            wrong_clusters / merged_clusters if merged_clusters else 0.0
        ),
        "merged_clusters": merged_clusters,
        "duplicate_excess_before": duplicate_before,
        "duplicate_excess_after": duplicate_after,
        "duplicate_excess_removed_fraction": (
            1.0 - duplicate_after / duplicate_before if duplicate_before else 1.0
        ),
        "fused_position_median_error_cm": percentile(fused_position_errors, 50),
        "fused_position_p90_error_cm": percentile(fused_position_errors, 90),
    }


def person_estimates(by_frame: list[list[dict]]) -> dict[int, dict[int, np.ndarray]]:
    out: dict[int, dict[int, np.ndarray]] = defaultdict(dict)
    for frame_idx, observations in enumerate(by_frame):
        by_pid = defaultdict(list)
        for obs in observations:
            by_pid[obs["person_id"]].append(obs["world_est"])
        for pid, points in by_pid.items():
            # Oracle grouping is used only for downstream degradation analysis.
            out[pid][frame_idx] = np.median(np.asarray(points), axis=0)
    return out


def stitching_metrics(by_frame: list[list[dict]]) -> dict:
    estimates = person_estimates(by_frame)
    fragments = []
    frag_len = 4

    for pid, trajectory in estimates.items():
        frames = sorted(trajectory)
        runs = []
        run = []
        for frame in frames:
            if run and frame != run[-1] + 1:
                if run:
                    runs.append(run)
                run = []
            run.append(frame)
        if run:
            runs.append(run)
        for run in runs:
            for start in range(0, len(run) - frag_len + 1, frag_len):
                block = run[start : start + frag_len]
                if len(block) == frag_len:
                    fragments.append(
                        {
                            "uid": len(fragments),
                            "pid": pid,
                            "start": block[0],
                            "end": block[-1],
                            "points": [trajectory[t] for t in block],
                        }
                    )

    starts = defaultdict(list)
    by_pid = defaultdict(list)
    for frag in fragments:
        starts[frag["start"]].append(frag)
        by_pid[frag["pid"]].append(frag)
    for pid in by_pid:
        by_pid[pid].sort(key=lambda f: f["start"])

    links = []
    for pid, frags in by_pid.items():
        for a, b in zip(frags, frags[1:]):
            if 1 <= b["start"] - a["end"] <= 3:
                links.append((a, b))

    correct_geometry = 0
    correct_velocity = 0
    correct_time_only = 0
    evaluated = 0
    for a, true_b in links:
        candidates = []
        for start in range(a["end"] + 1, a["end"] + 4):
            candidates.extend(starts.get(start, []))
        candidates = [c for c in candidates if c["uid"] != a["uid"]]
        if not candidates or true_b not in candidates:
            continue
        evaluated += 1

        min_gap = min(c["start"] - a["end"] for c in candidates)
        time_candidates = sorted(
            [c for c in candidates if c["start"] - a["end"] == min_gap],
            key=lambda c: c["uid"],
        )
        correct_time_only += time_candidates[0]["pid"] == a["pid"]

        last = np.asarray(a["points"][-1])
        geom_choice = min(
            candidates,
            key=lambda c: float(np.linalg.norm(last - np.asarray(c["points"][0]))),
        )
        correct_geometry += geom_choice["pid"] == a["pid"]

        velocity = np.asarray(a["points"][-1]) - np.asarray(a["points"][-2])
        vel_choice = min(
            candidates,
            key=lambda c: float(
                np.linalg.norm(
                    (last + velocity * (c["start"] - a["end"]))
                    - np.asarray(c["points"][0])
                )
            ),
        )
        correct_velocity += vel_choice["pid"] == a["pid"]

    return {
        "experiment_type": "GT-derived simulated fragmentation over projected person-level world estimates",
        "fragment_length_frames": frag_len,
        "eligible_links": evaluated,
        "time_only_top1_accuracy": correct_time_only / evaluated if evaluated else None,
        "geometry_nearest_top1_accuracy": (
            correct_geometry / evaluated if evaluated else None
        ),
        "geometry_velocity_top1_accuracy": (
            correct_velocity / evaluated if evaluated else None
        ),
    }


def flow_residual_metrics(
    frames: list[dict], by_frame: list[list[dict]], window: int = 20
) -> dict:
    window = min(window, len(frames))
    counts = Counter()
    for frame in frames[:window]:
        counts.update(frame["people"].keys())
    stable_ids = {pid for pid, count in counts.items() if count == window}
    estimates = person_estimates(by_frame)

    occupancy = []
    observed_sections = []
    for t in range(window):
        sections = {}
        for pid in stable_ids:
            p = estimates.get(pid, {}).get(t)
            if p is not None:
                sections[pid] = section_of(p)
        observed_sections.append(sections)
        c = np.zeros(SECTION_N * SECTION_N, dtype=np.int64)
        for s in sections.values():
            c[s] += 1
        occupancy.append(c)

    residuals = []
    for t in range(1, window):
        inflow = np.zeros(SECTION_N * SECTION_N, dtype=np.int64)
        outflow = np.zeros(SECTION_N * SECTION_N, dtype=np.int64)
        common = set(observed_sections[t - 1]) & set(observed_sections[t])
        for pid in common:
            a = observed_sections[t - 1][pid]
            b = observed_sections[t][pid]
            if a != b:
                outflow[a] += 1
                inflow[b] += 1
        residual = occupancy[t] - occupancy[t - 1] - inflow + outflow
        residuals.extend(np.abs(residual).tolist())

    denom = sum(int(x.sum()) for x in occupancy[1:])
    total_abs = float(np.sum(residuals))
    return {
        "experiment_type": "closed-cohort flow-conservation diagnostic on GT-stable IDs",
        "window_frames": window,
        "stable_gt_ids": len(stable_ids),
        "mean_abs_residual_people_per_section_step": (
            float(np.mean(residuals)) if residuals else None
        ),
        "total_abs_residual": total_abs,
        "normalized_abs_residual_per_observed_person": (
            total_abs / denom if denom else None
        ),
    }


def flatten_metrics(
    scenario: dict,
    seed: int,
    projection: dict,
    overlap: dict,
    fusion: dict,
    stitching: dict,
    flow: dict,
    offsets: dict[str, int],
) -> dict:
    return {
        **scenario,
        "seed": seed,
        "actual_camera_offset_frames_json": json.dumps(offsets, sort_keys=True),
        "n_observations": projection["n_observations"],
        "projection_median_error_cm": projection["median_error_cm"],
        "projection_p90_error_cm": projection["p90_error_cm"],
        "section_accuracy": projection["section_accuracy"],
        "overlap_pairs": overlap["n_same_person_cross_camera_pairs"],
        "overlap_median_disagreement_cm": overlap["median_disagreement_cm"],
        "overlap_p90_disagreement_cm": overlap["p90_disagreement_cm"],
        "overlap_fraction_within_50cm": overlap["fraction_within_50cm"],
        "fusion_pair_precision": fusion["pair_precision"],
        "fusion_pair_recall": fusion["pair_recall"],
        "fusion_pair_f1": fusion["pair_f1"],
        "fusion_wrong_merge_cluster_rate": fusion["wrong_merge_cluster_rate"],
        "fusion_duplicate_removed_fraction": fusion[
            "duplicate_excess_removed_fraction"
        ],
        "fusion_position_median_error_cm": fusion[
            "fused_position_median_error_cm"
        ],
        "stitch_geometry_nearest_accuracy": stitching[
            "geometry_nearest_top1_accuracy"
        ],
        "stitch_geometry_velocity_accuracy": stitching[
            "geometry_velocity_top1_accuracy"
        ],
        "stitch_time_only_accuracy": stitching["time_only_top1_accuracy"],
        "flow_normalized_abs_residual": flow[
            "normalized_abs_residual_per_observed_person"
        ],
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cameras = load_cameras()
    frames = load_frames(args.frames)

    scenarios = [
        dict(
            scenario="clean",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="detection_2px",
            detection_sigma_px=2.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="detection_5px",
            detection_sigma_px=5.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="detection_10px",
            detection_sigma_px=10.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="calibration_0p5px",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.5,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="calibration_1px",
            detection_sigma_px=0.0,
            calibration_sigma_px=1.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="calibration_2px",
            detection_sigma_px=0.0,
            calibration_sigma_px=2.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="calibration_4px",
            detection_sigma_px=0.0,
            calibration_sigma_px=4.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="timestamp_0p5s",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.5,
            miss_rate=0.0,
        ),
        dict(
            scenario="timestamp_1s",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=1.0,
            miss_rate=0.0,
        ),
        dict(
            scenario="miss_5pct",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.05,
        ),
        dict(
            scenario="miss_10pct",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.10,
        ),
        dict(
            scenario="miss_20pct",
            detection_sigma_px=0.0,
            calibration_sigma_px=0.0,
            timestamp_sigma_s=0.0,
            miss_rate=0.20,
        ),
        dict(
            scenario="combined_mild",
            detection_sigma_px=2.0,
            calibration_sigma_px=1.0,
            timestamp_sigma_s=0.5,
            miss_rate=0.05,
        ),
        dict(
            scenario="combined_severe",
            detection_sigma_px=5.0,
            calibration_sigma_px=2.0,
            timestamp_sigma_s=1.0,
            miss_rate=0.10,
        ),
    ]

    rows = []
    detailed_clean = None
    threshold_rows = []
    for scenario in scenarios:
        for seed in range(args.seeds):
            by_frame, offsets = make_observations(
                frames,
                cameras,
                detection_sigma_px=scenario["detection_sigma_px"],
                calibration_sigma_px=scenario["calibration_sigma_px"],
                timestamp_sigma_s=scenario["timestamp_sigma_s"],
                miss_rate=scenario["miss_rate"],
                seed=20261004 + seed,
            )
            proj = projection_metrics(by_frame)
            overlap = overlap_agreement(by_frame)
            fusion = fusion_metrics(by_frame, FUSION_THRESHOLD_CM)
            stitching = stitching_metrics(by_frame)
            flow = flow_residual_metrics(frames, by_frame)
            rows.append(
                flatten_metrics(
                    scenario, seed, proj, overlap, fusion, stitching, flow, offsets
                )
            )
            if scenario["scenario"] == "clean" and seed == 0:
                detailed_clean = {
                    "projection": proj,
                    "overlap_agreement": overlap,
                    "fusion": fusion,
                    "stitching": stitching,
                    "flow_conservation": flow,
                }
                for threshold in (25.0, 50.0, 75.0, 100.0, 150.0):
                    threshold_rows.append(fusion_metrics(by_frame, threshold))

    write_csv(OUT / "wildtrack_noise_sweep.csv", rows)
    write_csv(OUT / "wildtrack_fusion_threshold_sweep.csv", threshold_rows)
    write_csv(
        OUT / "wildtrack_projection_by_camera.csv",
        [
            {"camera": camera, **metrics}
            for camera, metrics in detailed_clean["projection"]["per_camera"].items()
        ],
    )

    aggregate = {}
    for scenario in scenarios:
        name = scenario["scenario"]
        subset = [r for r in rows if r["scenario"] == name]
        aggregate[name] = {}
        numeric_keys = [
            k
            for k, value in subset[0].items()
            if isinstance(value, (int, float)) and k != "seed"
        ]
        for key in numeric_keys:
            vals = [float(r[key]) for r in subset if r[key] is not None]
            if vals:
                aggregate[name][key] = {
                    "mean": float(np.mean(vals)),
                    "std": float(np.std(vals)),
                }

    report = {
        "dataset": "WILDTRACK",
        "experiment_class": "real dataset calibration + real GT annotations; perturbations are simulated",
        "subset": {
            "annotation_frames": len(frames),
            "time_span_seconds_at_2fps": (len(frames) - 1) * ANNOTATION_DT_S,
            "cameras": CAMERAS,
            "rgb_downloaded": False,
            "manifest": str(DATA / "subset_manifest.json"),
        },
        "coordinate_system": {
            "unit": "centimeters",
            "origin_cm": GRID_ORIGIN_CM,
            "grid_step_cm": GRID_STEP_CM,
            "grid_shape": [GRID_W, GRID_H],
            "sections": f"{SECTION_N}x{SECTION_N} equal grid over WILDTRACK ground extent",
        },
        "fusion_threshold_cm": FUSION_THRESHOLD_CM,
        "clean_detailed": detailed_clean,
        "scenario_aggregate": aggregate,
        "notes": [
            "Projection uses bbox bottom-center as an approximate foot contact point.",
            "Timestamp perturbation is quantized to the released 2 FPS annotation interval.",
            "Stitching is a controlled GT-derived fragmentation experiment over projected trajectories.",
            "Flow residual uses a closed cohort of IDs present throughout the first 20-frame window.",
        ],
    }
    (OUT / "wildtrack_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["clean_detailed"], indent=2))
    print(f"saved outputs under {OUT}")


if __name__ == "__main__":
    main()
