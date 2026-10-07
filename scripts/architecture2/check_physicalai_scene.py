from __future__ import annotations

import argparse, json
from collections import Counter
from pathlib import Path
import ijson
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / 'samples' / 'physicalai' / 'Warehouse_000'
OUT = ROOT / 'experiments' / 'architecture2' / 'physicalai_scene_check.json'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--frames', type=int, default=100); args = ap.parse_args()
    calibration = json.loads((SCENE/'calibration.json').read_text(encoding='utf-8'))
    cameras = [s for s in calibration['sensors'] if s.get('type') == 'camera']
    by_id = {s['id']: s for s in cameras}
    required = ['intrinsicMatrix','extrinsicMatrix','cameraMatrix','homography','coordinates','scaleFactor','translationToGlobalCoordinates']
    missing = {f:[c['id'] for c in cameras if not c.get(f)] for f in required}
    conds, roundtrips = {}, {}
    pixels = np.array([[960.,900.],[960.,540.],[300.,900.],[1600.,900.]])
    for c in cameras:
        H=np.asarray(c['homography'],float); Hi=np.linalg.inv(H); conds[c['id']]=float(np.linalg.cond(H)); back=[]
        for uv in pixels:
            q=Hi@np.array([uv[0],uv[1],1.]); q=q[:2]/q[2]; p=H@np.array([q[0],q[1],1.]); back.append(p[:2]/p[2])
        roundtrips[c['id']]=float(np.max(np.linalg.norm(np.asarray(back)-pixels,axis=1)))
    types=Counter(); ids=set(); vis_counts=[]; naive=[]; frames=0; person_records=0
    with (SCENE/'ground_truth.json').open('rb') as h:
        for _, objects in ijson.kvitems(h,''):
            frames += 1
            for o in objects:
                types[o.get('object type','unknown')] += 1
                if o.get('object type') != 'Person': continue
                person_records += 1; ids.add(int(o['object id'])); visible=o.get('2d bounding box visible',{}); vis_counts.append(len(visible))
                gt=np.array([float(o['3d location'][0]),float(o['3d location'][1])])
                for cid,b in visible.items():
                    if cid not in by_id: continue
                    Hi=np.linalg.inv(np.asarray(by_id[cid]['homography'],float)); uv=np.array([(float(b[0])+float(b[2]))*.5,float(b[3]),1.]); q=Hi@uv; q=q[:2]/q[2]; naive.append(float(np.linalg.norm(q-gt)))
            if frames >= args.frames: break
    report={
      'dataset':'NVIDIA PhysicalAI Smart Spaces 2026 Warehouse_000',
      'experiment_class':'released synthetic scene metadata + ground truth; metadata validation only',
      'files':{'calibration_json_bytes':(SCENE/'calibration.json').stat().st_size,'map_png_bytes':(SCENE/'map.png').stat().st_size,'ground_truth_json_bytes_observed':(SCENE/'ground_truth.json').stat().st_size},
      'camera_count':len(cameras),'required_metadata_missing':missing,
      'homography_condition_number':{'min':float(min(conds.values())),'median':float(np.median(list(conds.values()))),'max':float(max(conds.values()))},
      'max_numeric_homography_roundtrip_error_px':float(max(roundtrips.values())),
      'sampled_frames':frames,'object_type_records':dict(types),'person_frame_records':person_records,'unique_person_ids':len(ids),
      'person_visible_camera_count':{'mean':float(np.mean(vis_counts)),'median':float(np.median(vis_counts)),'max':int(max(vis_counts)),'fraction_multi_camera':float(np.mean(np.asarray(vis_counts)>=2))},
      'naive_inverse_homography_vs_3d_location':{'n_visible_boxes':len(naive),'median_numeric_distance':float(np.median(naive)),'p90_numeric_distance':float(np.percentile(naive,90)),'interpretation':'Large mismatch: inverse-homography output and 3d location are not directly comparable without the released scene/global coordinate transform. Do not report this number as metre projection error.'},
      'blocker':'Need authoritative PhysicalAI coordinate-transform convention linking homography/map coordinates to the ground-truth 3d location frame before quantitative image-to-world accuracy is claimed.'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))

if __name__=='__main__': main()
