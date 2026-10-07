from __future__ import annotations

"""Downstream bottleneck robustness + forecasting experiment on NVIDIA PhysicalAI 2026.

Uses the real/synthetic benchmark's globally consistent PERSON world trajectories from
Warehouse_000.  No video inference is claimed here: this isolates the analytics layer
after tracking/projection and asks whether bottleneck/flow signals survive controlled
observation errors.
"""

from collections import defaultdict, Counter
from pathlib import Path
import csv
import json
import math

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import precision_recall_curve, precision_recall_fscore_support, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
GT_PATH = ROOT / "samples" / "physicalai" / "Warehouse_000" / "ground_truth.json"
OUT = ROOT / "experiments" / "physicalai_bottleneck"
FPS = 30.0
STEP = 30  # 1 Hz analytics sampling
GRID_N = 5


def load_people():
    d = json.load(GT_PATH.open("r", encoding="utf-8"))
    frames = sorted(map(int, d.keys()))
    sampled = frames[::STEP]
    rows = []
    for f in sampled:
        for o in d[str(f)]:
            if o.get("object type") != "Person":
                continue
            x, y, z = map(float, o["3d location"][:3])
            rows.append((f, int(o["object id"]), x, y, z, tuple(sorted(o.get("2d bounding box visible", {}).keys()))))
    return sampled, rows


def section_index(x, y, bounds):
    xmin, xmax, ymin, ymax = bounds
    ix = int(np.clip((x - xmin) / max(1e-9, xmax - xmin) * GRID_N, 0, GRID_N - 1))
    iy = int(np.clip((y - ymin) / max(1e-9, ymax - ymin) * GRID_N, 0, GRID_N - 1))
    return iy * GRID_N + ix


def build_clean_state(sampled, rows):
    xs = [r[2] for r in rows]
    ys = [r[3] for r in rows]
    bounds = (min(xs), max(xs), min(ys), max(ys))
    by_frame = defaultdict(dict)
    for f, pid, x, y, z, cams in rows:
        by_frame[f][pid] = (x, y, section_index(x, y, bounds), cams)

    per_frame = {}
    previous = {}
    for f in sampled:
        cur = by_frame[f]
        occ = Counter()
        speeds = defaultdict(list)
        dirs = defaultdict(list)
        inflow = Counter()
        outflow = Counter()
        for pid, (x, y, sec, cams) in cur.items():
            occ[sec] += 1
            if pid in previous:
                px, py, psec = previous[pid]
                vx, vy = x - px, y - py  # one second between samples
                speeds[sec].append(float(math.hypot(vx, vy)))
                dirs[sec].append((vx, vy))
                if psec != sec:
                    outflow[psec] += 1
                    inflow[sec] += 1
            previous[pid] = (x, y, sec)
        state = {}
        for sec in range(GRID_N * GRID_N):
            arr = speeds.get(sec, [])
            med_speed = float(np.median(arr)) if arr else 0.0
            # Direction entropy over 8 bins.
            hist = np.zeros(8, dtype=float)
            for vx, vy in dirs.get(sec, []):
                if abs(vx) + abs(vy) < 1e-9:
                    continue
                ang = (math.atan2(vy, vx) + 2 * math.pi) % (2 * math.pi)
                hist[min(7, int(ang / (2 * math.pi) * 8))] += 1
            if hist.sum():
                p = hist / hist.sum()
                p = p[p > 0]
                entropy = float(-(p * np.log(p)).sum() / math.log(8))
            else:
                entropy = 0.0
            state[sec] = {
                "occupancy": int(occ[sec]),
                "median_speed": med_speed,
                "inflow": int(inflow[sec]),
                "outflow": int(outflow[sec]),
                "imbalance": float((inflow[sec] - outflow[sec]) / (inflow[sec] + outflow[sec] + 1.0)),
                "direction_entropy": entropy,
            }
        per_frame[f] = state
    return bounds, per_frame


def add_baselines(sampled, state):
    # Per-section robust baselines from the whole clean sequence.
    by_sec = defaultdict(lambda: defaultdict(list))
    for f in sampled:
        for sec, s in state[f].items():
            for k in ("occupancy", "median_speed", "inflow", "outflow"):
                by_sec[sec][k].append(float(s[k]))

    baselines = {}
    for sec in range(GRID_N * GRID_N):
        o = np.asarray(by_sec[sec]["occupancy"])
        v = np.asarray(by_sec[sec]["median_speed"])
        positive_v = v[v > 0]
        baselines[sec] = {
            "occ_med": float(np.median(o)),
            "occ_p80": float(np.percentile(o, 80)),
            "occ_p90": float(np.percentile(o, 90)),
            "free_speed": float(np.percentile(positive_v, 70)) if len(positive_v) else 0.0,
            "slow_p30": float(np.percentile(positive_v, 30)) if len(positive_v) else 0.0,
        }

    # Define an interpretable clean congestion proxy and severity score.
    labels = {}
    severity = {}
    for f in sampled:
        labels[f] = {}
        severity[f] = {}
        for sec, s in state[f].items():
            b = baselines[sec]
            if b["occ_p80"] <= 0:
                labels[f][sec] = 0
                severity[f][sec] = 0.0
                continue
            occ_excess = np.clip((s["occupancy"] - b["occ_med"]) / max(1.0, b["occ_p90"] - b["occ_med"]), 0, 2)
            speed_loss = 0.0 if b["free_speed"] <= 1e-9 else np.clip((b["free_speed"] - s["median_speed"]) / b["free_speed"], 0, 1)
            accumulation = max(0.0, s["imbalance"])
            ent = s["direction_entropy"]
            score = float(np.clip(0.45 * min(1.0, occ_excess) + 0.30 * speed_loss + 0.15 * accumulation + 0.10 * ent, 0, 1))
            severity[f][sec] = score
            labels[f][sec] = int(s["occupancy"] >= b["occ_p80"] and speed_loss >= 0.25 and score >= 0.55)

    # Temporal persistence: require >=2 of current/adjacent three seconds.
    frame_to_i = {f: i for i, f in enumerate(sampled)}
    persistent = {f: {} for f in sampled}
    for f in sampled:
        i = frame_to_i[f]
        for sec in range(GRID_N * GRID_N):
            vals = []
            for j in range(max(0, i - 1), min(len(sampled), i + 2)):
                vals.append(labels[sampled[j]][sec])
            persistent[f][sec] = int(sum(vals) >= 2)
    return baselines, persistent, severity


def simulate_noisy_rows(rows, bounds, seed, miss=0.0, pos_sigma=0.0, duplicate=0.0, id_switch=0.0):
    rng = np.random.default_rng(seed)
    ids = sorted(set(r[1] for r in rows))
    out = []
    for f, pid, x, y, z, cams in rows:
        if rng.random() < miss:
            continue
        observed_pid = pid
        if rng.random() < id_switch:
            observed_pid = int(rng.choice([i for i in ids if i != pid]))
        xn = float(x + rng.normal(0, pos_sigma))
        yn = float(y + rng.normal(0, pos_sigma))
        out.append((f, observed_pid, xn, yn, z, cams, pid))
        if rng.random() < duplicate:
            # Simulates overlap double counting / duplicate global tracks.
            out.append((f, int(100000 + pid * 100 + rng.integers(0, 100)), xn + rng.normal(0, pos_sigma * 0.3 + 0.02), yn + rng.normal(0, pos_sigma * 0.3 + 0.02), z, cams, pid))
    return out


def build_noisy_state(sampled, noisy_rows, bounds, geometry_dedup=False):
    by_frame = defaultdict(list)
    for row in noisy_rows:
        by_frame[row[0]].append(row)

    previous = {}
    per_frame = {}
    for f in sampled:
        raw = by_frame[f]
        if geometry_dedup:
            # Conservative world-space non-max suppression: collapse observations within 0.45m.
            kept = []
            for r in sorted(raw, key=lambda x: x[1]):
                x, y = r[2], r[3]
                if any(math.hypot(x - q[2], y - q[3]) < 0.45 for q in kept):
                    continue
                kept.append(r)
            raw = kept

        occ = Counter()
        speeds = defaultdict(list)
        dirs = defaultdict(list)
        inflow = Counter(); outflow = Counter()
        for _, pid, x, y, z, cams, true_pid in raw:
            sec = section_index(x, y, bounds)
            occ[sec] += 1
            if pid in previous:
                px, py, psec = previous[pid]
                vx, vy = x - px, y - py
                speeds[sec].append(float(math.hypot(vx, vy)))
                dirs[sec].append((vx, vy))
                if psec != sec:
                    outflow[psec] += 1; inflow[sec] += 1
            previous[pid] = (x, y, sec)
        state = {}
        for sec in range(GRID_N * GRID_N):
            arr = speeds.get(sec, [])
            med_speed = float(np.median(arr)) if arr else 0.0
            hist = np.zeros(8, dtype=float)
            for vx, vy in dirs.get(sec, []):
                if abs(vx) + abs(vy) < 1e-9: continue
                ang = (math.atan2(vy, vx) + 2 * math.pi) % (2 * math.pi)
                hist[min(7, int(ang / (2 * math.pi) * 8))] += 1
            if hist.sum():
                p = hist / hist.sum(); p = p[p > 0]
                entropy = float(-(p * np.log(p)).sum() / math.log(8))
            else: entropy = 0.0
            state[sec] = {
                "occupancy": int(occ[sec]), "median_speed": med_speed,
                "inflow": int(inflow[sec]), "outflow": int(outflow[sec]),
                "imbalance": float((inflow[sec] - outflow[sec]) / (inflow[sec] + outflow[sec] + 1.0)),
                "direction_entropy": entropy,
            }
        per_frame[f] = state
    return per_frame


def predict_congestion(sampled, state, baselines):
    pred = {f:{} for f in sampled}
    score = {f:{} for f in sampled}
    for f in sampled:
        for sec, s in state[f].items():
            b = baselines[sec]
            if b["occ_p80"] <= 0:
                pred[f][sec] = 0; score[f][sec] = 0.0; continue
            occ_excess = np.clip((s["occupancy"] - b["occ_med"]) / max(1.0, b["occ_p90"] - b["occ_med"]), 0, 2)
            speed_loss = 0.0 if b["free_speed"] <= 1e-9 else np.clip((b["free_speed"] - s["median_speed"]) / b["free_speed"], 0, 1)
            c = float(np.clip(0.45*min(1,occ_excess)+0.30*speed_loss+0.15*max(0,s["imbalance"])+0.10*s["direction_entropy"],0,1))
            score[f][sec]=c
            pred[f][sec]=int(s["occupancy"] >= b["occ_p80"] and speed_loss >= 0.25 and c >= 0.55)
    # persistence
    p2={f:{} for f in sampled}
    for i,f in enumerate(sampled):
        for sec in range(GRID_N*GRID_N):
            vals=[pred[sampled[j]][sec] for j in range(max(0,i-1),min(len(sampled),i+2))]
            p2[f][sec]=int(sum(vals)>=2)
    return p2,score


def flatten_labels(sampled, labels):
    y=[]
    for f in sampled:
        for sec in range(GRID_N*GRID_N): y.append(labels[f][sec])
    return np.asarray(y,dtype=int)


def metric_state_error(sampled, clean, noisy):
    occ=[]; flow=[]; conservation=[]
    prev_occ_clean={}; prev_occ_noisy={}
    for f in sampled:
        for sec in range(GRID_N*GRID_N):
            c,n=clean[f][sec],noisy[f][sec]
            occ.append(abs(c["occupancy"]-n["occupancy"]))
            flow.append(abs((c["inflow"]+c["outflow"])-(n["inflow"]+n["outflow"])))
            if sec in prev_occ_noisy:
                delta=n["occupancy"]-prev_occ_noisy[sec]
                residual=delta-(n["inflow"]-n["outflow"])
                conservation.append(abs(residual))
            prev_occ_clean[sec]=c["occupancy"]; prev_occ_noisy[sec]=n["occupancy"]
    return {"occupancy_mae":float(np.mean(occ)),"boundary_flow_mae":float(np.mean(flow)),"mean_abs_conservation_residual":float(np.mean(conservation))}


def forecasting_experiment(sampled, clean_state, clean_labels):
    # Architecture-3 style section-state predictor: predict congestion within next 10s.
    X=[]; y=[]; meta=[]
    horizon=10
    for i,f in enumerate(sampled[:-horizon]):
        for sec in range(GRID_N*GRID_N):
            s=clean_state[f][sec]
            prev=clean_state[sampled[max(0,i-3)]][sec]
            feat=[s["occupancy"],s["median_speed"],s["inflow"],s["outflow"],s["imbalance"],s["direction_entropy"],s["occupancy"]-prev["occupancy"]]
            target=max(clean_labels[sampled[j]][sec] for j in range(i+1,min(len(sampled),i+horizon+1)))
            X.append(feat); y.append(target); meta.append((i,sec))
    X=np.asarray(X,float); y=np.asarray(y,int)
    train_i=int(len(sampled)*0.55)
    val_i=int(len(sampled)*0.70)
    train=np.array([m[0] < train_i for m in meta])
    val=np.array([(m[0] >= train_i) and (m[0] < val_i) for m in meta])
    test=np.array([m[0] >= val_i for m in meta])
    model=GradientBoostingClassifier(random_state=0,n_estimators=80,max_depth=2,learning_rate=0.05)
    model.fit(X[train],y[train])
    val_prob=model.predict_proba(X[val])[:,1]
    vp,vr,vt=precision_recall_curve(y[val],val_prob)
    vf=2*vp*vr/np.maximum(1e-12,vp+vr)
    best=int(np.nanargmax(vf[:-1])) if len(vt) else 0
    threshold=float(vt[best]) if len(vt) else 0.5
    prob=model.predict_proba(X[test])[:,1]
    pred=(prob>=threshold).astype(int)
    p,r,f,_=precision_recall_fscore_support(y[test],pred,average='binary',zero_division=0)
    auc=roc_auc_score(y[test],prob) if len(np.unique(y[test]))>1 else float('nan')
    return {
        "validation_selected_threshold":threshold,
        "validation_best_f1":float(vf[best]) if len(vt) else 0.0,
        "test_samples":int(test.sum()),"positive_rate":float(y[test].mean()),
        "precision":float(p),"recall":float(r),"f1":float(f),"roc_auc":float(auc)
    }


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sampled,rows=load_people()
    bounds,clean=build_clean_state(sampled,rows)
    baselines,clean_labels,severity=add_baselines(sampled,clean)
    ytrue=flatten_labels(sampled,clean_labels)
    scenarios={
        "mild":dict(miss=0.03,pos_sigma=0.12,duplicate=0.01,id_switch=0.01),
        "moderate":dict(miss=0.08,pos_sigma=0.30,duplicate=0.04,id_switch=0.04),
        "severe":dict(miss=0.18,pos_sigma=0.65,duplicate=0.10,id_switch=0.10),
    }
    results={"dataset":{},"scenarios":{},"forecasting":None}
    results["dataset"]={
        "frames_sampled":len(sampled),"person_rows":len(rows),"unique_people":len(set(r[1] for r in rows)),
        "bounds":bounds,"grid_sections":GRID_N*GRID_N,"clean_congestion_positive_rate":float(ytrue.mean()),
    }
    for name,cfg in scenarios.items():
        rr=[]
        for seed in range(20):
            noisy_rows=simulate_noisy_rows(rows,bounds,seed,**cfg)
            # Section-first: hard sections, no global geometry duplicate fusion.
            a1=build_noisy_state(sampled,noisy_rows,bounds,geometry_dedup=False)
            # Geometry-first/global-graph analytics both benefit from world-space dedup;
            # identity differences are evaluated in the separate CITIC common benchmark.
            a2=build_noisy_state(sampled,noisy_rows,bounds,geometry_dedup=True)
            for label,state in (("architecture_1_section_first",a1),("architecture_2_geometry_first",a2),("architecture_3_global_graph",a2)):
                pred,_=predict_congestion(sampled,state,baselines)
                yp=flatten_labels(sampled,pred)
                p,r,f,_=precision_recall_fscore_support(ytrue,yp,average='binary',zero_division=0)
                block={"method":label,"precision":float(p),"recall":float(r),"f1":float(f),**metric_state_error(sampled,clean,state)}
                rr.append(block)
        agg={}
        for method in sorted(set(x["method"] for x in rr)):
            xs=[x for x in rr if x["method"]==method]; agg[method]={}
            for k in xs[0]:
                if k=="method": continue
                vals=np.asarray([x[k] for x in xs],float); agg[method][k]={"mean":float(vals.mean()),"std":float(vals.std(ddof=1))}
        results["scenarios"][name]=agg
    results["forecasting"]=forecasting_experiment(sampled,clean,clean_labels)
    (OUT/"results.json").write_text(json.dumps(results,indent=2))
    with (OUT/"results.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["scenario","method","metric","mean","std"])
        for sc,block in results["scenarios"].items():
            for m,metrics in block.items():
                for k,v in metrics.items(): w.writerow([sc,m,k,v["mean"],v["std"]])
    print(json.dumps(results,indent=2))


if __name__=="__main__":
    main()
