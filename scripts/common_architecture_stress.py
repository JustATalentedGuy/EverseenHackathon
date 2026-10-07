from __future__ import annotations

"""Common controlled MTMC stress benchmark for the three Everseen architectures.

This benchmark uses REAL CITIC-MTMC ground-truth walking trajectories and the REAL
camera visibility polygons / room map, then injects controlled observation errors.
It is intentionally not presented as a video-ReID benchmark: appearance embeddings
are synthetic so that ambiguity can be varied reproducibly.  The goal is to compare
the association logic of Architecture 1/2/3 on identical tracklets.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import csv
import json
import math
import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import networkx as nx
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CITIC = ROOT / "references" / "citic-mtmc"
OUTDIR = ROOT / "experiments" / "common_architecture_stress"

FPS = 25.0
STRIDE = 5  # 5 Hz samples; enough for section/association experiments.
V_MAX = 2.2  # m/s plausibility envelope for ordinary indoor walking.


@dataclass
class Obs:
    gt_id: str
    t_true: float
    t_obs: float
    x_true: float
    y_true: float
    x_obs: float
    y_obs: float
    camera: str
    section_true: str
    section_obs: str


@dataclass
class Tracklet:
    idx: int
    gt_id: str
    camera: str
    obs: List[Obs]
    embedding: np.ndarray
    corrupted_embedding: bool
    quality: float

    @property
    def start(self) -> float:
        return self.obs[0].t_obs

    @property
    def end(self) -> float:
        return self.obs[-1].t_obs

    @property
    def start_pos(self) -> np.ndarray:
        return np.array([self.obs[0].x_obs, self.obs[0].y_obs], dtype=float)

    @property
    def end_pos(self) -> np.ndarray:
        return np.array([self.obs[-1].x_obs, self.obs[-1].y_obs], dtype=float)

    @property
    def start_section(self) -> str:
        return self.obs[0].section_obs

    @property
    def end_section(self) -> str:
        return self.obs[-1].section_obs

    @property
    def duration(self) -> float:
        if len(self.obs) <= 1:
            return 1.0 / (FPS / STRIDE)
        return max(1.0 / (FPS / STRIDE), self.obs[-1].t_obs - self.obs[0].t_obs)

    @property
    def velocity(self) -> np.ndarray:
        dt = self.end - self.start
        if dt < 0.4:
            return np.zeros(2)
        # Robust enough for this controlled benchmark: use first/last quartile points.
        a = self.obs[max(0, len(self.obs) // 4)]
        b = self.obs[min(len(self.obs) - 1, 3 * len(self.obs) // 4)]
        dt2 = max(1e-6, b.t_obs - a.t_obs)
        return np.array([b.x_obs - a.x_obs, b.y_obs - a.y_obs]) / dt2


def point_in_poly(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)):
            x_inter = (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
            if x < x_inter:
                inside = not inside
        j = i
    return inside


def load_site():
    room = json.loads((CITIC / "map_config" / "room_map.json").read_text())
    sections = []
    doors_by_section = {}
    for item in room["room_map"]:
        if "name" not in item:
            continue
        sections.append((item["name"], item["rect"]))
        doors_by_section[item["name"]] = [tuple(map(float, d)) for d in item.get("doors", [])]

    # Door coordinates encode room adjacency directly.
    adjacency = defaultdict(set)
    names = [x[0] for x in sections]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            da = doors_by_section.get(a, [])
            db = doors_by_section.get(b, [])
            if any(np.linalg.norm(np.array(x) - np.array(y)) < 0.05 for x in da for y in db):
                adjacency[a].add(b)
                adjacency[b].add(a)

    cameras = {}
    for p in sorted((CITIC / "map_config").glob("Node*.json")):
        d = json.loads(p.read_text())
        cameras[d["name"]] = {
            "position": tuple(map(float, d["position"][:2])),
            "visibility_polygon": d["visibility_polygon"],
        }
    return sections, dict(adjacency), cameras


SECTIONS, SECTION_ADJ, CAMERAS = load_site()


def section_of(x: float, y: float) -> str:
    # Rectangles are axis-aligned; order in room_map is intentional.
    for name, rect in SECTIONS:
        (x1, y1), (x2, y2) = rect
        lo_x, hi_x = sorted((float(x1), float(x2)))
        lo_y, hi_y = sorted((float(y1), float(y2)))
        if lo_x - 1e-9 <= x <= hi_x + 1e-9 and lo_y - 1e-9 <= y <= hi_y + 1e-9:
            return name
    return "UNKNOWN"


def visible_cameras(x: float, y: float) -> List[str]:
    return [name for name, c in CAMERAS.items() if point_in_poly(x, y, c["visibility_polygon"])]


def load_real_trajectories() -> Dict[str, List[Tuple[float, float, float]]]:
    """Return six real CITIC trajectories, time-aligned to create controlled concurrency."""
    trajs: Dict[str, List[Tuple[float, float, float]]] = {}
    # Offsets create simultaneous visitors while keeping every spatial path real.
    offsets = [0.0, 5.0, 10.0, 2.5, 7.5, 12.5]
    k = 0
    for cap in (1, 2, 3):
        a = np.loadtxt(CITIC / f"capture{cap}_gt.mot.txt", delimiter=",")
        for pid in sorted(set(a[:, 1].astype(int))):
            r = a[a[:, 1].astype(int) == pid]
            r = r[::STRIDE]
            t0 = float(r[0, 0])
            gid = f"c{cap}_p{pid}"
            trajs[gid] = [
                ((float(row[0]) - t0) / FPS + offsets[k], float(row[7]), float(row[8]))
                for row in r
            ]
            k += 1
    return trajs


REAL_TRAJS = load_real_trajectories()


def choose_camera_sequence(points: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float, Optional[str], str]]:
    """Choose one authoritative camera per world point, with sticky overlap ownership.

    This produces a deduplicated observation stream for the common handoff benchmark.
    Architecture-2 overlap fusion is evaluated separately in its dedicated experiment.
    """
    out = []
    prev: Optional[str] = None
    for t, x, y in points:
        cams = visible_cameras(x, y)
        if prev in cams:
            cam = prev
        elif cams:
            cam = min(
                cams,
                key=lambda c: np.linalg.norm(np.array(CAMERAS[c]["position"]) - np.array([x, y])),
            )
        else:
            cam = None
        out.append((t, x, y, cam, section_of(x, y)))
        prev = cam
    return out


CLEAN_SEQS = {gid: choose_camera_sequence(p) for gid, p in REAL_TRAJS.items()}


def derive_camera_priors():
    """Derive site-level camera adjacency and broad transition-time priors.

    This stands in for the camera topology / travel-time metadata expected in a real
    deployment.  It is learned from all six real paths but contains no appearance data.
    """
    gaps = defaultdict(list)
    for seq in CLEAN_SEQS.values():
        last_cam = None
        last_t = None
        for t, x, y, cam, sec in seq:
            if cam is None:
                continue
            if last_cam is not None and cam != last_cam:
                gaps[(last_cam, cam)].append(max(0.0, t - float(last_t)))
            last_cam, last_t = cam, t
    priors = {}
    for pair, vals in gaps.items():
        arr = np.asarray(vals)
        priors[pair] = {
            "median": float(np.median(arr)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(max(5.0, np.percentile(arr, 95) + 8.0)),
        }
    return priors


CAMERA_PRIORS = derive_camera_priors()


SCENARIOS = {
    "clean": dict(frag_prob=0.002, miss_prob=0.005, pos_sigma=0.05, clock_sigma=0.02,
                  app_sigma=0.10, app_corrupt=0.00, tracklet_drop=0.00),
    "moderate": dict(frag_prob=0.012, miss_prob=0.020, pos_sigma=0.20, clock_sigma=0.15,
                     app_sigma=0.25, app_corrupt=0.08, tracklet_drop=0.02),
    "appearance_hard": dict(frag_prob=0.015, miss_prob=0.020, pos_sigma=0.10, clock_sigma=0.05,
                            app_sigma=0.55, app_corrupt=0.25, tracklet_drop=0.02),
    "geometry_hard": dict(frag_prob=0.015, miss_prob=0.020, pos_sigma=0.60, clock_sigma=0.45,
                          app_sigma=0.20, app_corrupt=0.05, tracklet_drop=0.03),
    "severe": dict(frag_prob=0.030, miss_prob=0.060, pos_sigma=0.45, clock_sigma=0.50,
                   app_sigma=0.45, app_corrupt=0.20, tracklet_drop=0.08),
}


def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / max(1e-12, n)


def make_latents(rng: np.random.Generator, dim=32) -> Dict[str, np.ndarray]:
    ids = sorted(REAL_TRAJS)
    z = {gid: unit(rng.normal(size=dim)) for gid in ids}
    # Create realistic hard appearance pairs (similar clothing/body appearance).
    for a, b in ((ids[0], ids[1]), (ids[2], ids[3])):
        z[b] = unit(0.88 * z[a] + 0.48 * unit(rng.normal(size=dim)))
    return z


def simulate_tracklets(seed: int, cfg: dict) -> List[Tracklet]:
    rng = np.random.default_rng(seed)
    latents = make_latents(rng)
    cam_offset = {c: float(rng.normal(0.0, cfg["clock_sigma"])) for c in CAMERAS}
    built: List[Tracklet] = []
    next_idx = 0

    for gid, seq in CLEAN_SEQS.items():
        cur: List[Obs] = []
        cur_cam: Optional[str] = None
        last_kept_t: Optional[float] = None

        def flush():
            nonlocal cur, cur_cam, next_idx
            if len(cur) < 2:
                cur = []
                return
            if rng.random() < cfg["tracklet_drop"]:
                cur = []
                return
            emb = unit(latents[gid] + rng.normal(0.0, cfg["app_sigma"], size=latents[gid].shape))
            corrupt = rng.random() < cfg["app_corrupt"]
            if corrupt:
                other = rng.choice([x for x in latents if x != gid])
                emb = unit(0.75 * latents[other] + 0.25 * emb)
            quality = float(np.clip(len(cur) / 15.0, 0.1, 1.0))
            built.append(Tracklet(next_idx, gid, str(cur_cam), cur, emb, bool(corrupt), quality))
            next_idx += 1
            cur = []

        for t, x, y, cam, sec_true in seq:
            if cam is None:
                flush()
                cur_cam = None
                last_kept_t = None
                continue
            if rng.random() < cfg["miss_prob"]:
                continue
            # Random local tracker restart / fragmentation.
            forced_cut = rng.random() < cfg["frag_prob"]
            if cur and (cam != cur_cam or forced_cut or (last_kept_t is not None and t - last_kept_t > 0.65)):
                flush()
            if not cur:
                cur_cam = cam
            xn = float(x + rng.normal(0.0, cfg["pos_sigma"]))
            yn = float(y + rng.normal(0.0, cfg["pos_sigma"]))
            tobs = float(t + cam_offset[cam] + rng.normal(0.0, cfg["clock_sigma"] * 0.08))
            cur.append(Obs(gid, t, tobs, x, y, xn, yn, cam, sec_true, section_of(xn, yn)))
            last_kept_t = t
        flush()

    # Sorting gives deterministic online order independent of GT identity.
    built.sort(key=lambda tr: (tr.start, tr.camera, tr.idx))
    for i, tr in enumerate(built):
        tr.idx = i
    return built


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(1.0 - np.clip(float(np.dot(unit(a), unit(b))), -1.0, 1.0))


def sections_compatible(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if b in SECTION_ADJ.get(a, set()):
        return 0.25
    if "UNKNOWN" in (a, b):
        return 0.55
    return 1.0


def candidate_allowed(a: Tracklet, b: Tracklet) -> bool:
    if b.start <= a.end - 0.7:
        return False
    gap = b.start - a.end
    if a.camera == b.camera:
        return -0.7 <= gap <= 4.5
    prior = CAMERA_PRIORS.get((a.camera, b.camera))
    if prior is None:
        return False
    return -0.7 <= gap <= max(6.0, prior["max"])


def time_cost(a: Tracklet, b: Tracklet) -> float:
    gap = max(0.0, b.start - a.end)
    if a.camera == b.camera:
        return min(1.0, gap / 4.0)
    p = CAMERA_PRIORS.get((a.camera, b.camera), {"median": 2.0, "max": 10.0})
    return min(1.0, abs(gap - p["median"]) / max(2.0, p["max"]))


def world_cost(a: Tracklet, b: Tracklet) -> float:
    gap = max(0.0, b.start - a.end)
    d_endpoint = float(np.linalg.norm(b.start_pos - a.end_pos))
    pred = a.end_pos + a.velocity * gap
    d_pred = float(np.linalg.norm(b.start_pos - pred))
    d = min(d_endpoint, d_pred)
    physically_reachable = max(0.8, V_MAX * gap + 0.8)
    return min(1.5, d / physically_reachable)


def cost_arch1(a: Tracklet, b: Tracklet, use_app=True) -> float:
    tc = time_cost(a, b)
    sc = sections_compatible(a.end_section, b.start_section)
    base = 0.52 * tc + 0.48 * sc
    if not use_app:
        return base
    ac = min(1.2, cosine_distance(a.embedding, b.embedding))
    # Appearance is conditional and not allowed to overwhelm impossible topology.
    return 0.48 * base + 0.52 * ac


def cost_arch2(a: Tracklet, b: Tracklet, use_app=True) -> float:
    tc = time_cost(a, b)
    sc = sections_compatible(a.end_section, b.start_section)
    wc = world_cost(a, b)
    base = 0.20 * tc + 0.18 * sc + 0.62 * wc
    if not use_app:
        return base
    ac = min(1.2, cosine_distance(a.embedding, b.embedding))
    return 0.68 * base + 0.32 * ac


def greedy_associate(tracklets: List[Tracklet], arch: int) -> List[Tuple[int, int, float]]:
    chains: List[List[int]] = []
    selected: List[Tuple[int, int, float]] = []
    threshold = 0.57 if arch == 1 else 0.53
    unique_base_gate = 0.46 if arch == 1 else 0.40
    cost_fn = cost_arch1 if arch == 1 else cost_arch2

    for j, cur in enumerate(tracklets):
        cands = []
        for ci, chain in enumerate(chains):
            prev = tracklets[chain[-1]]
            if candidate_allowed(prev, cur):
                base = cost_fn(prev, cur, use_app=False)
                cands.append((ci, chain[-1], base))

        if not cands:
            chains.append([j])
            continue

        scored = []
        for ci, pi, base in cands:
            prev = tracklets[pi]
            # Conditional ReID: do not spend/trust appearance if geometry/topology already unique.
            use_app = not (len(cands) == 1 and base < unique_base_gate)
            scored.append((cost_fn(prev, cur, use_app=use_app), ci, pi))
        scored.sort()
        best, ci, pi = scored[0]
        margin = (scored[1][0] - best) if len(scored) > 1 else 1.0
        if best <= threshold and (margin >= 0.025 or best < threshold * 0.72):
            chains[ci].append(j)
            selected.append((pi, j, float(best)))
        else:
            chains.append([j])
    return selected


def global_graph_associate(tracklets: List[Tracklet]) -> List[Tuple[int, int, float]]:
    """Global path-cover style association using maximum-weight bipartite matching.

    Left/right copies let a tracklet have at most one successor and one predecessor,
    while still allowing it to sit in the middle of a trajectory chain.
    """
    g = nx.Graph()
    unmatched_cost = 0.50
    edge_cost = {}
    candidate_costs_out = defaultdict(list)
    candidate_costs_in = defaultdict(list)
    for i, a in enumerate(tracklets):
        g.add_node(("L", i), bipartite=0)
        g.add_node(("R", i), bipartite=1)
        for j in range(i + 1, len(tracklets)):
            b = tracklets[j]
            if b.start - a.end > 35.0:
                break
            if not candidate_allowed(a, b):
                continue
            c = cost_arch2(a, b, use_app=True)
            # Extra quality penalty discourages weak fragments from hijacking a chain.
            c += 0.035 * (2.0 - a.quality - b.quality)
            candidate_costs_out[i].append(c)
            candidate_costs_in[j].append(c)
            if c < unmatched_cost:
                w = unmatched_cost - c
                g.add_edge(("L", i), ("R", j), weight=float(w))
                edge_cost[(i, j)] = float(c)

    raw = nx.max_weight_matching(g, maxcardinality=False, weight="weight")
    selected = []
    for u, v in raw:
        if u[0] == "R":
            u, v = v, u
        if u[0] != "L" or v[0] != "R":
            continue
        i, j = int(u[1]), int(v[1])
        c = edge_cost[(i, j)]

        # Conservative ambiguity gate: keep false merges low.  Global competition is
        # allowed to resolve some close cases, but truly flat candidate sets are split.
        outs = sorted(candidate_costs_out.get(i, []))
        ins = sorted(candidate_costs_in.get(j, []))
        out_margin = (outs[1] - outs[0]) if len(outs) > 1 else 1.0
        in_margin = (ins[1] - ins[0]) if len(ins) > 1 else 1.0
        if c <= 0.48 and (min(out_margin, in_margin) >= 0.012 or c < 0.34):
            selected.append((i, j, c))
    return selected


def union_labels(n: int, links: List[Tuple[int, int, float]]) -> List[int]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for a, b, _ in links:
        union(a, b)
    roots = {}
    labels = []
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        labels.append(roots[r])
    return labels


def bcubed(tracklets: List[Tracklet], labels: List[int]) -> Tuple[float, float, float]:
    pred_members = defaultdict(list)
    true_members = defaultdict(list)
    for i, (tr, lab) in enumerate(zip(tracklets, labels)):
        pred_members[lab].append(i)
        true_members[tr.gt_id].append(i)
    ps, rs = [], []
    for i, (tr, lab) in enumerate(zip(tracklets, labels)):
        pset = set(pred_members[lab])
        tset = set(true_members[tr.gt_id])
        inter = len(pset & tset)
        ps.append(inter / len(pset))
        rs.append(inter / len(tset))
    p = float(np.mean(ps)) if ps else 0.0
    r = float(np.mean(rs)) if rs else 0.0
    f = 2 * p * r / max(1e-12, p + r)
    return p, r, f


def dwell_by_section_obs(obs: Iterable[Obs], observed: bool) -> Dict[str, float]:
    d = defaultdict(float)
    dt = STRIDE / FPS
    for o in obs:
        s = o.section_obs if observed else o.section_true
        d[s] += dt
    return d


def evaluate(tracklets: List[Tracklet], links: List[Tuple[int, int, float]]) -> dict:
    labels = union_labels(len(tracklets), links)
    p, r, f = bcubed(tracklets, labels)
    pred_clusters = defaultdict(list)
    gt_tracklets = defaultdict(list)
    for i, (tr, lab) in enumerate(zip(tracklets, labels)):
        pred_clusters[lab].append(i)
        gt_tracklets[tr.gt_id].append(i)

    false_merge_clusters = sum(len({tracklets[i].gt_id for i in inds}) > 1 for inds in pred_clusters.values())
    splits = 0
    for gid, inds in gt_tracklets.items():
        splits += max(0, len({labels[i] for i in inds}) - 1)

    # Consecutive true tracklet links are the handoff/fragment-repair opportunities.
    true_edges = set()
    for gid, inds in gt_tracklets.items():
        inds = sorted(inds, key=lambda i: tracklets[i].start)
        true_edges.update(zip(inds[:-1], inds[1:]))
    selected_pairs = {(a, b) for a, b, _ in links}
    selected_same = {(a, b) for a, b, _ in links if tracklets[a].gt_id == tracklets[b].gt_id}
    link_precision = len(selected_same) / max(1, len(selected_pairs))
    link_recall = len(selected_pairs & true_edges) / max(1, len(true_edges))

    # Dwell reconstruction: map each GT visitor to the predicted cluster containing the
    # largest amount of that visitor's observed time.  Merges add contamination; splits
    # lose portions of dwell.  This is intentionally strict but application-relevant.
    dt = STRIDE / FPS
    dwell_errors = []
    completeness = []
    for gid, inds in gt_tracklets.items():
        true_obs = [o for i in inds for o in tracklets[i].obs]
        true_d = dwell_by_section_obs(true_obs, observed=False)
        by_cluster = defaultdict(float)
        for i in inds:
            by_cluster[labels[i]] += len(tracklets[i].obs) * dt
        best_lab = max(by_cluster, key=by_cluster.get)
        pred_obs = [o for i in pred_clusters[best_lab] for o in tracklets[i].obs]
        pred_d = dwell_by_section_obs(pred_obs, observed=True)
        keys = set(true_d) | set(pred_d)
        dwell_errors.append(sum(abs(pred_d.get(k, 0.0) - true_d.get(k, 0.0)) for k in keys))
        total_true = sum(len(tracklets[i].obs) * dt for i in inds)
        completeness.append(by_cluster[best_lab] / max(1e-9, total_true))

    visitor_error = abs(len(pred_clusters) - len(gt_tracklets)) / max(1, len(gt_tracklets))
    return {
        "n_tracklets": len(tracklets),
        "n_true_visitors": len(gt_tracklets),
        "n_predicted_global_ids": len(pred_clusters),
        "bcubed_precision": p,
        "bcubed_recall": r,
        "bcubed_f1": f,
        "link_precision": link_precision,
        "link_recall_consecutive": link_recall,
        "false_merge_clusters": false_merge_clusters,
        "split_excess_clusters": splits,
        "visitor_count_relative_error": visitor_error,
        "mean_dwell_l1_error_seconds": float(np.mean(dwell_errors)) if dwell_errors else 0.0,
        "median_dwell_l1_error_seconds": float(np.median(dwell_errors)) if dwell_errors else 0.0,
        "mean_trajectory_completeness": float(np.mean(completeness)) if completeness else 0.0,
    }


def raw_baseline(tracklets: List[Tracklet]) -> dict:
    return evaluate(tracklets, [])


def occupancy_section_error(tracklets: List[Tracklet]) -> dict:
    """Identity-independent section occupancy error from misses + projection noise.

    Fragmentation does not affect this quantity; this demonstrates why congestion metrics
    should not unnecessarily depend on global identity continuity.
    """
    dt = STRIDE / FPS
    pred = defaultdict(float)
    true = defaultdict(float)
    # Simulated observed samples (after misses/drop) vs those same samples' true sections.
    # This isolates projection/section error from identity stitching.
    for tr in tracklets:
        for o in tr.obs:
            bucket = round(o.t_true / dt)
            pred[(bucket, o.section_obs)] += 1.0
            true[(bucket, o.section_true)] += 1.0
    keys = set(pred) | set(true)
    if not keys:
        return {"section_occupancy_mae_per_bucket": 0.0, "section_assignment_error_rate": 0.0}
    mae = float(np.mean([abs(pred.get(k, 0.0) - true.get(k, 0.0)) for k in keys]))
    n = sum(len(tr.obs) for tr in tracklets)
    wrong = sum(o.section_obs != o.section_true for tr in tracklets for o in tr.obs)
    return {
        "section_occupancy_mae_per_bucket": mae,
        "section_assignment_error_rate": wrong / max(1, n),
    }


def run_one(seed: int, scenario: str) -> dict:
    cfg = SCENARIOS[scenario]
    tr = simulate_tracklets(seed, cfg)
    result = {
        "seed": seed,
        "scenario": scenario,
        "input": {
            "n_tracklets": len(tr),
            "mean_tracklets_per_person": len(tr) / max(1, len(set(x.gt_id for x in tr))),
            "corrupted_embedding_fraction": float(np.mean([x.corrupted_embedding for x in tr])) if tr else 0.0,
            **occupancy_section_error(tr),
        },
        "raw_unstitched": raw_baseline(tr),
        "architecture_1_section_first": evaluate(tr, greedy_associate(tr, 1)),
        "architecture_2_geometry_first": evaluate(tr, greedy_associate(tr, 2)),
        "architecture_3_global_graph": evaluate(tr, global_graph_associate(tr)),
    }
    return result


def aggregate(rows: List[dict]) -> dict:
    methods = ["raw_unstitched", "architecture_1_section_first", "architecture_2_geometry_first", "architecture_3_global_graph"]
    out = {}
    for scenario in SCENARIOS:
        rr = [x for x in rows if x["scenario"] == scenario]
        out[scenario] = {"n_runs": len(rr), "input": {}}
        for k in rr[0]["input"]:
            vals = np.asarray([x["input"][k] for x in rr], dtype=float)
            out[scenario]["input"][k] = {"mean": float(vals.mean()), "std": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0}
        for method in methods:
            out[scenario][method] = {}
            for k in rr[0][method]:
                vals = np.asarray([x[method][k] for x in rr], dtype=float)
                out[scenario][method][k] = {"mean": float(vals.mean()), "std": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0}
    return out


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # 30 Monte-Carlo seeds per scenario is enough for stable comparisons while remaining fast.
    rows = [run_one(seed, scenario) for scenario in SCENARIOS for seed in range(30)]
    agg = aggregate(rows)

    (OUTDIR / "per_run.json").write_text(json.dumps(rows, indent=2))
    (OUTDIR / "summary.json").write_text(json.dumps(agg, indent=2))
    (OUTDIR / "site_priors.json").write_text(json.dumps({
        "camera_priors": {f"{a}->{b}": v for (a, b), v in CAMERA_PRIORS.items()},
        "section_adjacency": {k: sorted(v) for k, v in SECTION_ADJ.items()},
        "real_trajectory_ids": sorted(REAL_TRAJS),
        "note": "Real CITIC world paths + real camera visibility/topology; injected observation and appearance noise.",
    }, indent=2))

    with (OUTDIR / "summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "method", "metric", "mean", "std"])
        for scenario, block in agg.items():
            for method, metrics in block.items():
                if method in ("n_runs", "input"):
                    continue
                for metric, stat in metrics.items():
                    w.writerow([scenario, method, metric, stat["mean"], stat["std"]])

    # Human-readable compact output for command-line QA.
    for scenario in SCENARIOS:
        print(f"\n[{scenario}]")
        print("input tracklets/person:", round(agg[scenario]["input"]["mean_tracklets_per_person"]["mean"], 2))
        for method in ("raw_unstitched", "architecture_1_section_first", "architecture_2_geometry_first", "architecture_3_global_graph"):
            m = agg[scenario][method]
            print(
                method,
                "B3F1=", round(m["bcubed_f1"]["mean"], 3),
                "linkP=", round(m["link_precision"]["mean"], 3),
                "linkR=", round(m["link_recall_consecutive"]["mean"], 3),
                "merges=", round(m["false_merge_clusters"]["mean"], 2),
                "splits=", round(m["split_excess_clusters"]["mean"], 2),
                "dwellL1=", round(m["mean_dwell_l1_error_seconds"]["mean"], 2),
            )
    print(f"\nSaved to {OUTDIR}")


if __name__ == "__main__":
    main()
