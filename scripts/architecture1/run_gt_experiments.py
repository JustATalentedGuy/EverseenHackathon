from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from citic_common import (  # noqa: E402
    Observation,
    Tracklet,
    UnionFind,
    apply_section_hysteresis,
    assign_gt_sections,
    assign_section,
    build_owner_observations,
    build_tracklets,
    choose_section_owners,
    estimate_section_camera_coverage,
    load_cameras,
    load_gt,
    load_rooms,
    precision_recall_f1,
    room_adjacency,
    safe_mean,
    shortest_hops,
    transition_events_from_tracklets,
)


FPS = 25.0


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def section_events(labels, frames):
    if not labels:
        return []
    events = []
    prev = labels[0]
    for label, frame in zip(labels[1:], frames[1:]):
        if label != prev:
            events.append((prev, label, frame))
            prev = label
    return events


def match_transition_events(gt_events, pred_events, tolerance_frames=12):
    used = set()
    tp = 0
    errors = []
    for ga, gb, gf in gt_events:
        best = None
        for j, (pa, pb, pf) in enumerate(pred_events):
            if j in used or pa != ga or pb != gb:
                continue
            err = abs(pf - gf)
            if err <= tolerance_frames and (best is None or err < best[0]):
                best = (err, j)
        if best is not None:
            used.add(best[1])
            tp += 1
            errors.append(best[0] / FPS)
    fp = len(pred_events) - len(used)
    fn = len(gt_events) - tp
    return tp, fp, fn, errors


def count_boundary_churn(labels, frames, max_seconds=0.6):
    events = section_events(labels, frames)
    max_frames = round(max_seconds * FPS)
    churn = 0
    for i in range(len(events) - 1):
        a, b, f1 = events[i]
        b2, a2, f2 = events[i + 1]
        if a == a2 and b == b2 and f2 - f1 <= max_frames:
            churn += 1
    return churn


def dwell_counts(labels, fps=FPS):
    c = Counter(labels)
    return {k: v / fps for k, v in c.items()}


def run_section_mapping(all_gt, rooms, seed):
    rows = []
    sigma_values = [0.0, 0.05, 0.10, 0.25, 0.50]
    persist_frames = [1, 3, 6, 12]
    for sigma in sigma_values:
        for persist in persist_frames:
            total_frames = correct = 0
            tp = fp = fn = 0
            transition_errors = []
            dwell_errors = []
            churn = 0
            gt_transition_total = 0
            pred_transition_total = 0
            rng = random.Random(seed + int(sigma * 1000) * 101 + persist * 17)
            for capture, observations in all_gt.items():
                by_id = defaultdict(list)
                for o in observations:
                    by_id[o.gt_id].append(o)
                for gt_id, seq in by_id.items():
                    seq.sort(key=lambda o: o.frame)
                    frames = [o.frame for o in seq]
                    gt_labels = [o.gt_section for o in seq]
                    raw = []
                    for o in seq:
                        nx = o.x + rng.gauss(0.0, sigma)
                        ny = o.y + rng.gauss(0.0, sigma)
                        raw.append(assign_section((nx, ny), rooms, None))
                    pred = apply_section_hysteresis(raw, persist)
                    total_frames += len(seq)
                    correct += sum(a == b for a, b in zip(gt_labels, pred))
                    ge = section_events(gt_labels, frames)
                    pe = section_events(pred, frames)
                    mtp, mfp, mfn, errs = match_transition_events(ge, pe)
                    tp += mtp
                    fp += mfp
                    fn += mfn
                    transition_errors.extend(errs)
                    gt_transition_total += len(ge)
                    pred_transition_total += len(pe)
                    churn += count_boundary_churn(pred, frames)
                    gd = dwell_counts(gt_labels)
                    pd = dwell_counts(pred)
                    for section in set(gd) | set(pd):
                        dwell_errors.append(abs(gd.get(section, 0.0) - pd.get(section, 0.0)))
            p, r, f1 = precision_recall_f1(tp, fp, fn)
            rows.append(
                {
                    "noise_sigma_m": sigma,
                    "hysteresis_frames": persist,
                    "hysteresis_seconds": persist / FPS,
                    "frame_section_accuracy": correct / max(total_frames, 1),
                    "transition_precision": p,
                    "transition_recall": r,
                    "transition_f1": f1,
                    "transition_timing_mae_s": safe_mean(transition_errors),
                    "dwell_mae_s_per_person_section": safe_mean(dwell_errors),
                    "boundary_churn_events": churn,
                    "gt_transition_events": gt_transition_total,
                    "pred_transition_events": pred_transition_total,
                }
            )
    return rows


def clone_obs(o: Observation) -> Observation:
    return Observation(
        capture=o.capture,
        frame=o.frame,
        gt_id=o.gt_id,
        x=o.x,
        y=o.y,
        gt_section=o.gt_section,
        noisy_section=o.gt_section,
        camera=o.camera,
    )


def inject_fragmentation(base_tracklets, cuts_per_minute, dropout_frames, seed):
    rng = random.Random(seed)
    fragments = []
    min_piece = 12
    counter = 0
    cut_prob = cuts_per_minute / (FPS * 60.0)
    for base in base_tracklets:
        obs = [clone_obs(o) for o in base.observations]
        n = len(obs)
        if n < 2 * min_piece + dropout_frames + 1 or cuts_per_minute <= 0:
            counter += 1
            fragments.append(
                Tracklet(f"F{counter}", base.capture, base.camera, base.gt_id, obs, parent_uid=base.uid, split_index=0)
            )
            continue
        candidate_cuts = []
        last = min_piece
        for i in range(min_piece, n - min_piece):
            if i - last < min_piece + dropout_frames:
                continue
            if rng.random() < cut_prob:
                candidate_cuts.append(i)
                last = i
        starts = [0]
        pieces = []
        for cut in candidate_cuts:
            left_end = max(starts[-1], cut - dropout_frames // 2)
            if left_end - starts[-1] >= min_piece:
                pieces.append((starts[-1], left_end))
                starts[-1] = min(n, cut + (dropout_frames - dropout_frames // 2))
        if n - starts[-1] >= min_piece:
            pieces.append((starts[-1], n))
        if not pieces:
            pieces = [(0, n)]
        for split_index, (s, e) in enumerate(pieces):
            piece = obs[s:e]
            if not piece:
                continue
            counter += 1
            fragments.append(
                Tracklet(
                    f"F{counter}",
                    base.capture,
                    base.camera,
                    base.gt_id,
                    piece,
                    parent_uid=base.uid,
                    split_index=split_index,
                )
            )
    return fragments


def true_consecutive_links(tracklets, same_camera=None, max_gap_frames=None):
    by_gt = defaultdict(list)
    for t in tracklets:
        by_gt[(t.capture, t.gt_id)].append(t)
    links = set()
    for seq in by_gt.values():
        seq.sort(key=lambda t: (t.start_frame, t.end_frame, t.uid))
        for a, b in zip(seq, seq[1:]):
            if same_camera is True and a.camera != b.camera:
                continue
            if same_camera is False and a.camera == b.camera:
                continue
            gap = b.start_frame - a.end_frame - 1
            if gap < 0:
                continue
            if max_gap_frames is not None and gap > max_gap_frames:
                continue
            links.add((a.uid, b.uid))
    return links


def local_candidates(tracklets, adj, max_gap_s=1.5, max_speed=3.0):
    max_gap_frames = round(max_gap_s * FPS)
    candidates = []
    by_cam = defaultdict(list)
    for t in tracklets:
        by_cam[(t.capture, t.camera)].append(t)
    for seq in by_cam.values():
        seq.sort(key=lambda t: t.start_frame)
        for i, a in enumerate(seq):
            for b in seq[i + 1 :]:
                gap = b.start_frame - a.end_frame - 1
                if gap < 0:
                    continue
                if gap > max_gap_frames:
                    break
                hops = shortest_hops(adj, a.end_section, b.start_section)
                if hops is None or hops > 1:
                    continue
                dt = max((b.start_frame - a.end_frame) / FPS, 1.0 / FPS)
                speed = math.dist(a.end_xy, b.start_xy) / dt
                if speed > max_speed:
                    continue
                score = 0.45 * (gap / max_gap_frames) + 0.45 * (speed / max_speed) + 0.10 * hops
                candidates.append((score, a.uid, b.uid))
    return candidates


def greedy_links(candidates, threshold):
    accepted = set()
    used_out = set()
    used_in = set()
    for score, a, b in sorted(candidates):
        if score > threshold or a in used_out or b in used_in:
            continue
        accepted.add((a, b))
        used_out.add(a)
        used_in.add(b)
    return accepted


def eval_links(pred, truth):
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    p, r, f1 = precision_recall_f1(tp, fp, fn)
    return {
        "tp": tp,
        "fp_false_merges": fp,
        "fn_false_splits": fn,
        "precision": p,
        "recall": r,
        "f1": f1,
        "false_merge_rate": 1.0 - p,
        "false_split_rate": 1.0 - r,
    }


def run_fragmentation(base_by_capture, adj, seed):
    rows = []
    thresholds = [0.20, 0.35, 0.50, 0.65, 0.80, 1.00]
    for rate in [2.0, 5.0, 10.0, 15.0]:
        all_fragments = []
        for cap, base in base_by_capture.items():
            all_fragments.extend(inject_fragmentation(base, rate, 6, seed + cap * 1009 + int(rate * 10)))
        truth = true_consecutive_links(all_fragments, same_camera=True, max_gap_frames=round(1.5 * FPS))
        candidates = local_candidates(all_fragments, adj)
        for threshold in thresholds:
            pred = greedy_links(candidates, threshold)
            metrics = eval_links(pred, truth)
            rows.append(
                {
                    "cuts_per_minute": rate,
                    "dropout_frames_per_cut": 6,
                    "score_threshold": threshold,
                    "base_tracklets": sum(len(v) for v in base_by_capture.values()),
                    "fragmented_tracklets": len(all_fragments),
                    "candidate_links": len(candidates),
                    "true_repair_links": len(truth),
                    "accepted_links": len(pred),
                    **metrics,
                }
            )
    return rows


def section_camera_sets(coverage, min_fraction=0.02):
    return {
        section: {cam for cam, frac in fractions.items() if frac >= min_fraction}
        for section, fractions in coverage.items()
    }


def camera_topology(section_sets, adj):
    cams = sorted({cam for v in section_sets.values() for cam in v})
    allowed = set()
    for a in cams:
        a_secs = [s for s, cs in section_sets.items() if a in cs]
        for b in cams:
            if a == b:
                continue
            b_secs = [s for s, cs in section_sets.items() if b in cs]
            min_h = None
            for sa in a_secs:
                for sb in b_secs:
                    h = shortest_hops(adj, sa, sb)
                    if h is not None and (min_h is None or h < min_h):
                        min_h = h
            if min_h is not None and min_h <= 2:
                allowed.add((a, b))
    return allowed


def learn_time_priors(base_by_capture, exclude_capture):
    values = defaultdict(list)
    global_values = []
    for cap, ts in base_by_capture.items():
        if cap == exclude_capture:
            continue
        for e in transition_events_from_tracklets(ts, FPS):
            values[(e["from_camera"], e["to_camera"])].append(e["gap_seconds"])
            global_values.append(e["gap_seconds"])

    def median(xs):
        xs = sorted(xs)
        if not xs:
            return 0.0
        n = len(xs)
        return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])

    global_med = median(global_values)
    global_mad = median([abs(x - global_med) for x in global_values]) if global_values else 1.0
    priors = {}
    for key, xs in values.items():
        med = median(xs)
        mad = median([abs(x - med) for x in xs])
        priors[key] = (med, max(mad, 0.15), len(xs))
    return priors, (global_med, max(global_mad, 0.25), len(global_values))


def handoff_candidates(tracklets, strategy, allowed_cam_pairs, adj, priors, global_prior, max_gap_s=12.0):
    max_gap_frames = round(max_gap_s * FPS)
    candidates = []
    seq = sorted(tracklets, key=lambda t: (t.start_frame, t.end_frame, t.uid))
    for i, a in enumerate(seq):
        for b in seq[i + 1 :]:
            if a.capture != b.capture or a.camera == b.camera:
                continue
            gap = b.start_frame - a.end_frame - 1
            if gap < 0:
                continue
            if gap > max_gap_frames:
                if b.start_frame > a.end_frame + max_gap_frames + 1:
                    break
                continue
            gap_s = gap / FPS
            if strategy == "time_only":
                score = gap_s / max_gap_s
            else:
                if (a.camera, b.camera) not in allowed_cam_pairs:
                    continue
                hops = shortest_hops(adj, a.end_section, b.start_section)
                if hops is None or hops > 4:
                    continue
                med, mad, _ = priors.get((a.camera, b.camera), global_prior)
                time_dev = abs(gap_s - med) / (3.0 * mad + 0.5)
                score = 0.80 * time_dev + 0.20 * (hops / 4.0)
            candidates.append((score, a.uid, b.uid))
    return candidates


def run_handoffs(base_by_capture, coverage, adj):
    rows = []
    allowed = camera_topology(section_camera_sets(coverage), adj)
    thresholds = [0.10, 0.20, 0.35, 0.50, 0.70, 1.00]
    for strategy in ["time_only", "topology_time"]:
        for threshold in thresholds:
            agg = Counter()
            candidate_total = truth_total = accepted_total = 0
            for test_cap in sorted(base_by_capture):
                test = base_by_capture[test_cap]
                truth = true_consecutive_links(test, same_camera=False, max_gap_frames=round(12 * FPS))
                priors, gp = learn_time_priors(base_by_capture, test_cap)
                cand = handoff_candidates(test, strategy, allowed, adj, priors, gp)
                pred = greedy_links(cand, threshold)
                m = eval_links(pred, truth)
                for key in ["tp", "fp_false_merges", "fn_false_splits"]:
                    agg[key] += m[key]
                candidate_total += len(cand)
                truth_total += len(truth)
                accepted_total += len(pred)
            p, r, f1 = precision_recall_f1(agg["tp"], agg["fp_false_merges"], agg["fn_false_splits"])
            rows.append(
                {
                    "strategy": strategy,
                    "score_threshold": threshold,
                    "candidate_links": candidate_total,
                    "true_handoffs": truth_total,
                    "accepted_links": accepted_total,
                    "tp": agg["tp"],
                    "fp_false_merges": agg["fp_false_merges"],
                    "fn_false_splits": agg["fn_false_splits"],
                    "precision": p,
                    "recall": r,
                    "f1": f1,
                    "false_merge_rate": 1.0 - p,
                    "false_split_rate": 1.0 - r,
                }
            )
    return rows, sorted([list(x) for x in allowed])


def uf_from_links(tracklets, links):
    uf = UnionFind([t.uid for t in tracklets])
    for a, b in links:
        uf.union(a, b)
    return uf


def collapse_tracklets(tracklets, uf, prefix="L"):
    groups = defaultdict(list)
    for t in tracklets:
        groups[uf.find(t.uid)].append(t)
    collapsed = []
    for idx, members in enumerate(groups.values(), 1):
        obs = []
        gt_counts = Counter()
        for t in members:
            obs.extend(t.observations)
            gt_counts[t.gt_id] += len(t.observations)
        obs.sort(key=lambda o: (o.frame, o.gt_id))
        # Deduplicate repeated observations if a component ever contains the
        # same GT point through a pathological link.
        dedup = []
        seen = set()
        for o in obs:
            key = (o.frame, o.gt_id, o.camera)
            if key not in seen:
                seen.add(key)
                dedup.append(o)
        gt_id = gt_counts.most_common(1)[0][0]
        camera_counts = Counter(t.camera for t in members)
        camera = camera_counts.most_common(1)[0][0]
        collapsed.append(
            Tracklet(
                uid=f"{prefix}{idx}",
                capture=members[0].capture,
                camera=camera,
                gt_id=gt_id,
                observations=dedup,
                parent_uid=None,
                split_index=0,
                metadata={"member_uids": [t.uid for t in members], "gt_ids": sorted(gt_counts)},
            )
        )
    return collapsed


def observations_by_cluster(tracklets, uf):
    out = []
    for t in tracklets:
        cid = uf.find(t.uid)
        for o in t.observations:
            out.append((cid, o))
    return out


def greedy_cluster_gt_assignment(cluster_obs):
    overlap = Counter((cid, o.gt_id) for cid, o in cluster_obs)
    pairs = sorted(((n, cid, gt) for (cid, gt), n in overlap.items()), reverse=True)
    assigned_c = set()
    assigned_g = set()
    mapping = {}
    for n, cid, gt in pairs:
        if cid in assigned_c or gt in assigned_g:
            continue
        mapping[cid] = gt
        assigned_c.add(cid)
        assigned_g.add(gt)
    return mapping


def analytics_metrics(base_obs, fragment_tracklets, uf):
    gt_occ = Counter()
    gt_dwell = Counter()
    gt_by_id = defaultdict(list)
    for o in base_obs:
        gt_occ[(o.frame, o.gt_section)].add(o.gt_id) if False else None
        gt_by_id[o.gt_id].append(o)
    # Counter cannot hold sets; rebuild with defaultdict.
    gt_occ_s = defaultdict(set)
    for o in base_obs:
        gt_occ_s[(o.frame, o.gt_section)].add(o.gt_id)
        gt_dwell[(o.gt_id, o.gt_section)] += 1

    cluster_obs = observations_by_cluster(fragment_tracklets, uf)
    pred_occ_s = defaultdict(set)
    for cid, o in cluster_obs:
        pred_occ_s[(o.frame, o.gt_section)].add(cid)
    keys = set(gt_occ_s) | set(pred_occ_s)
    occ_errors = [abs(len(gt_occ_s.get(k, set())) - len(pred_occ_s.get(k, set()))) for k in keys]
    occupancy_mae = safe_mean(occ_errors)

    mapping = greedy_cluster_gt_assignment(cluster_obs)
    pred_dwell = Counter()
    for cid, o in cluster_obs:
        if cid in mapping:
            pred_dwell[(mapping[cid], o.gt_section)] += 1
    dwell_keys = set(gt_dwell) | set(pred_dwell)
    dwell_errors = [abs(gt_dwell.get(k, 0) - pred_dwell.get(k, 0)) / FPS for k in dwell_keys]

    def flows_from_gt():
        c = Counter()
        for seq in gt_by_id.values():
            seq.sort(key=lambda o: o.frame)
            prev = None
            for o in seq:
                if prev is not None and o.frame - prev.frame <= 2 and o.gt_section != prev.gt_section:
                    c[(prev.gt_section, o.gt_section)] += 1
                prev = o
        return c

    def flows_from_pred():
        by_c = defaultdict(list)
        for cid, o in cluster_obs:
            by_c[cid].append(o)
        c = Counter()
        for seq in by_c.values():
            seq.sort(key=lambda o: o.frame)
            prev = None
            for o in seq:
                if prev is not None and o.frame - prev.frame <= 2 and o.gt_section != prev.gt_section:
                    c[(prev.gt_section, o.gt_section)] += 1
                prev = o
        return c

    gf, pf = flows_from_gt(), flows_from_pred()
    flow_keys = set(gf) | set(pf)
    flow_abs_error = sum(abs(gf.get(k, 0) - pf.get(k, 0)) for k in flow_keys)
    gt_flow_total = sum(gf.values())
    return {
        "occupancy_mae_people": occupancy_mae,
        "dwell_mae_s_per_person_section": safe_mean(dwell_errors),
        "flow_absolute_count_error": flow_abs_error,
        "flow_relative_absolute_error": flow_abs_error / gt_flow_total if gt_flow_total else 0.0,
        "gt_flow_events": gt_flow_total,
        "pred_clusters": len({uf.find(t.uid) for t in fragment_tracklets}),
        "gt_people": len({o.gt_id for o in base_obs}),
        "observed_point_recall": len(cluster_obs) / max(len(base_obs), 1),
    }


def run_analytics_robustness(base_by_capture, owner_obs_by_capture, adj, coverage, fragmentation_rows, handoff_rows, seed):
    # Use objectively best F1 thresholds from the earlier sweeps; record them so the
    # report does not pretend they were pre-specified deployment thresholds.
    frag_candidates = [r for r in fragmentation_rows if r["cuts_per_minute"] == 10.0]
    local_best = max(frag_candidates, key=lambda r: (r["f1"], -r["false_merge_rate"]))
    hand_candidates = [r for r in handoff_rows if r["strategy"] == "topology_time"]
    hand_best = max(hand_candidates, key=lambda r: (r["f1"], -r["false_merge_rate"]))
    allowed = camera_topology(section_camera_sets(coverage), adj)
    rows = []
    for cap in sorted(base_by_capture):
        fragments = inject_fragmentation(base_by_capture[cap], 10.0, 6, seed + cap * 7919)
        lc = local_candidates(fragments, adj)
        local_links = greedy_links(lc, local_best["score_threshold"])

        local_uf = uf_from_links(fragments, local_links)
        repaired_tracklets = collapse_tracklets(fragments, local_uf, prefix=f"C{cap}_L")

        priors, gp = learn_time_priors(base_by_capture, cap)
        hc = handoff_candidates(repaired_tracklets, "topology_time", allowed, adj, priors, gp)
        hand_links = greedy_links(hc, hand_best["score_threshold"])

        raw_uf = uf_from_links(fragments, set())
        m = analytics_metrics(owner_obs_by_capture[cap], fragments, raw_uf)
        rows.append({"capture": cap, "stage": "fragmented_raw", "fragmentation_cuts_per_minute": 10.0,
                     "local_threshold": local_best["score_threshold"], "handoff_threshold": hand_best["score_threshold"],
                     "local_links_used": 0, "handoff_links_used": 0, **m})

        m = analytics_metrics(owner_obs_by_capture[cap], fragments, local_uf)
        rows.append({"capture": cap, "stage": "after_local_repair", "fragmentation_cuts_per_minute": 10.0,
                     "local_threshold": local_best["score_threshold"], "handoff_threshold": hand_best["score_threshold"],
                     "local_links_used": len(local_links), "handoff_links_used": 0, **m})

        global_uf = uf_from_links(repaired_tracklets, hand_links)
        m = analytics_metrics(owner_obs_by_capture[cap], repaired_tracklets, global_uf)
        rows.append({"capture": cap, "stage": "after_local_plus_handoff", "fragmentation_cuts_per_minute": 10.0,
                     "local_threshold": local_best["score_threshold"], "handoff_threshold": hand_best["score_threshold"],
                     "local_links_used": len(local_links), "handoff_links_used": len(hand_links), **m})
    return rows, local_best, hand_best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261004)
    args = parser.parse_args()

    rooms, room_meta = load_rooms(args.dataset_root)
    cameras = load_cameras(args.dataset_root)
    adjacency = room_adjacency(rooms)
    coverage = estimate_section_camera_coverage(rooms, cameras, grid=40)
    owners = choose_section_owners(coverage)

    all_gt = {}
    owner_obs_by_capture = {}
    base_by_capture = {}
    for capture in (1, 2, 3):
        obs = load_gt(args.dataset_root, capture)
        assign_gt_sections(obs, rooms)
        for o in obs:
            o.noisy_section = o.gt_section
        all_gt[capture] = obs
        owner_obs = build_owner_observations(obs, cameras, owners, coverage)
        owner_obs_by_capture[capture] = owner_obs
        base_by_capture[capture] = build_tracklets(owner_obs)

    dataset_summary = {
        "dataset": "CITIC-MTMC",
        "fps": FPS,
        "captures": {},
        "sections": sorted(rooms),
        "room_adjacency": {k: sorted(v) for k, v in adjacency.items()},
        "section_camera_coverage_fraction": coverage,
        "section_owner_camera": owners,
        "cameras": sorted(cameras),
        "entry_points": room_meta.get("entry_points", []),
        "exit_points": room_meta.get("exit_points", []),
    }
    for cap in (1, 2, 3):
        obs = all_gt[cap]
        visible = owner_obs_by_capture[cap]
        ts = base_by_capture[cap]
        dataset_summary["captures"][str(cap)] = {
            "gt_rows": len(obs),
            "gt_people": len({o.gt_id for o in obs}),
            "frame_min": min(o.frame for o in obs),
            "frame_max": max(o.frame for o in obs),
            "gt_duration_s": (max(o.frame for o in obs) - min(o.frame for o in obs) + 1) / FPS,
            "section_counts": dict(Counter(o.gt_section for o in obs)),
            "owner_visible_rows": len(visible),
            "owner_visible_fraction": len(visible) / len(obs),
            "base_tracklets": len(ts),
            "natural_cross_camera_handoffs": len(transition_events_from_tracklets(ts, FPS)),
        }

    section_rows = run_section_mapping(all_gt, rooms, args.seed)
    frag_rows = run_fragmentation(base_by_capture, adjacency, args.seed)
    handoff_rows, allowed_pairs = run_handoffs(base_by_capture, coverage, adjacency)
    analytics_rows, local_best, hand_best = run_analytics_robustness(
        base_by_capture, owner_obs_by_capture, adjacency, coverage, frag_rows, handoff_rows, args.seed
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "dataset_summary.json", dataset_summary)
    write_csv(args.output_dir / "section_hysteresis.csv", section_rows)
    write_csv(args.output_dir / "fragmentation_repair.csv", frag_rows)
    write_csv(args.output_dir / "handoff_tradeoff.csv", handoff_rows)
    write_csv(args.output_dir / "analytics_robustness.csv", analytics_rows)

    summary = {
        "seed": args.seed,
        "dataset": "CITIC-MTMC",
        "data_mode": "official world-GT + room graph + camera visibility/calibration; no detector output in these experiments",
        "section_mapping_best_by_noise": {},
        "fragmentation_best_by_rate": {},
        "handoff_best_by_strategy": {},
        "analytics": analytics_rows,
        "camera_topology_allowed_pairs": allowed_pairs,
        "selected_local_threshold_for_analytics": local_best,
        "selected_handoff_threshold_for_analytics": hand_best,
    }
    for sigma in sorted({r["noise_sigma_m"] for r in section_rows}):
        subset = [r for r in section_rows if r["noise_sigma_m"] == sigma]
        summary["section_mapping_best_by_noise"][str(sigma)] = max(
            subset, key=lambda r: (r["transition_f1"], r["frame_section_accuracy"], -r["boundary_churn_events"])
        )
    for rate in sorted({r["cuts_per_minute"] for r in frag_rows}):
        subset = [r for r in frag_rows if r["cuts_per_minute"] == rate]
        summary["fragmentation_best_by_rate"][str(rate)] = max(
            subset, key=lambda r: (r["f1"], -r["false_merge_rate"])
        )
    for strategy in sorted({r["strategy"] for r in handoff_rows}):
        subset = [r for r in handoff_rows if r["strategy"] == strategy]
        summary["handoff_best_by_strategy"][strategy] = max(
            subset, key=lambda r: (r["f1"], -r["false_merge_rate"])
        )
    write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
