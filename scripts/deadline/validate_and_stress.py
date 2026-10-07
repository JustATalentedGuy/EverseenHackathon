"""Validate contracts and test zone stability, proposals and active review selection."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import unittest
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from prototype.core import Analytics,ZoneState,assign_zone,fit_calibration,match_boxes,propose_zones,conservative_zone_total,validate_polygon,world_point
from prototype.run import fuse_floor
from prototype.streams import LatestFrame
from scripts.deadline.experiment import OUT,DATA,save,zones,manifest,gt_frames,STEP

class ContractTests(unittest.TestCase):
    def test_live_buffer_keeps_only_latest_frame(self):
        class Capture:
            def __init__(self):self.n=0
            def read(self):
                self.n+=1
                return (self.n<=100,self.n)
            def release(self):pass
        reader=LatestFrame(Capture());reader.thread.join(timeout=1)
        item=reader.take();self.assertEqual(item[1],100);self.assertIsNone(reader.take());reader.close()
    def test_polygons_reject_crossing_and_degenerate(self):
        for p in [[[0,0],[1,1],[0,1],[1,0]],[[0,0],[0.5,0.5],[1,1]]]:
            with self.assertRaises(ValueError):validate_polygon(p)
    def test_ambiguous_overlap_abstains(self):
        z={'id':'a','polygon':[[0,0],[1,0],[1,1],[0,1]]}
        self.assertIsNone(assign_zone([.5,.5],[z,{**z,'id':'b'}]))
    def test_no_fabricated_gap_dwell(self):
        # Observed time is never accumulated through a visibility gap.
        a=Analytics([{'id':'a','polygon':[[0,0],[1,0],[1,1],[0,1]]}],persistence_s=0)
        for t in [0,.2,.4,10,10.2]:a.update(1,t,[.5,.5])
        self.assertAlmostEqual(a.observed_dwell[1,'a'],.6)
    def test_persistence_does_not_hide_ambiguous_overlap(self):
        a={'id':'a','polygon':[[0,0],[.7,0],[.7,1],[0,1]]}
        b={'id':'b','polygon':[[.3,0],[1,0],[1,1],[.3,1]]}
        state=ZoneState([a,b],0)
        self.assertEqual(state.update(1,0,[.1,.5]),'a')
        self.assertIsNone(state.update(1,.2,[.5,.5]))
    def test_malformed_calibration_rejected(self):
        with self.assertRaises(ValueError):fit_calibration({'image_points':[[0,0]]*4,'world_points':[[0,0]]*4})
    def test_independent_floor_check(self):
        p=[[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.3,.4],[.6,.7]]
        w=(np.array(p)*[10,5]).tolist()
        c=fit_calibration({'image_points':p,'world_points':w})
        np.testing.assert_allclose(world_point([.5,.5],c),[5,2.5],atol=1e-5)
        self.assertIsNone(world_point([.99,.5],c))
        w[-1][0]+=1
        with self.assertRaises(ValueError):fit_calibration({'image_points':p,'world_points':w})
    def test_duplicate_count_interval_and_owner_loss(self):
        r=conservative_zone_total({'a':3,'b':4});self.assertEqual((r['lower_bound'],r['upper_bound']),(4,7))
        self.assertIsNone(conservative_zone_total({'a':3},'b')['value'])
    def test_fusion_does_not_chain_or_merge_same_camera(self):
        obs=[{'camera':str(i),'track_id':i,'world':[i*.4,0],'time':0,'confidence':1-i*.1} for i in range(3)]
        self.assertEqual(len(fuse_floor(obs,.5)),2)
        self.assertEqual(len(fuse_floor([obs[0],{**obs[1],'camera':'0'}],.5)),2)
        self.assertEqual(len(fuse_floor([obs[0],{**obs[1],'time':1}],.5)),2)
    def test_admissible_box_assignment(self):
        gt=[[0,0,10,10],[20,0,30,10]];pred=[[0,0,10,10],[20,0,30,10]]
        self.assertEqual(len(match_boxes(gt,pred)),2)

def event_list(sequence):
    events=[];last=None
    for t,z in sequence:
        if z!=last and last is not None and z is not None: events.append((t,last,z))
        last=z
    return events

def event_score(truth,pred,tolerance=1):
    taken=set();tp=0
    for t,a,b in pred:
        choices=[(abs(t-q),i) for i,(q,c,d) in enumerate(truth) if i not in taken and (a,b)==(c,d) and abs(t-q)<=tolerance]
        if choices: taken.add(min(choices)[1]);tp+=1
    return tp,len(pred)-tp,len(truth)-tp

def stress():
    cached=json.loads((OUT/'baseline_predictions.json').read_text())['rows']
    test=[r for r in cached if r['split']=='test']; train=[r for r in cached if r['split']=='train']
    paths=defaultdict(list)
    for r in test:
        for g in r['gt']:paths[(r['name'],g['id'])].append((r['time'],np.array(g['foot'])/[r['width'],r['height']],r['view']))
    results=[]
    for sigma in [.002,.01,.03]:
        for persistence in [0,.2,.4,.8]:
            seed_rows=[]
            for seed in range(30):
                rng=np.random.default_rng(seed);correct=total=tp=fp=fn=0;dwell=[]
                for key,path in paths.items():
                    zz=zones(path[0][2]); state=ZoneState(zz,persistence,0 if persistence==0 else .008)
                    expected=[]; predicted=[]; eg=Counter();pg=Counter()
                    for t,p,view in path:
                        truth=assign_zone(p,zz); guess=state.update(key,t,p+rng.normal(0,sigma,2))
                        expected.append((t,truth));predicted.append((t,guess));correct+=int(truth==guess);total+=1
                        eg[truth]+=.2;pg[guess]+=.2
                    a,b,c=event_score(event_list(expected),event_list(predicted));tp+=a;fp+=b;fn+=c
                    dwell.extend(abs(eg[z['id']]-pg[z['id']]) for z in zz)
                seed_rows.append({'accuracy':correct/max(1,total),'transition_f1':2*tp/max(1,2*tp+fp+fn),
                                  'false_transition_events':fp,'dwell_mae_s':float(np.mean(dwell))})
            results.append({'sigma_normalized':sigma,'persistence_s':persistence,'seeds':30,
                            **{k:float(np.mean([r[k] for r in seed_rows])) for k in seed_rows[0]},
                            'transition_f1_std':float(np.std([r['transition_f1'] for r in seed_rows]))})
    save(OUT/'zone_stress.json',{'scope':'Controlled point perturbations on real held-out annotated trajectories; not detector/video robustness.', 'runs':results})
    proposal=[]
    for view in ['cor','front']:
        points=[]
        for r in train:
            if r['view']==view:points.extend([(b[0]+b[2])/2/r['width'],b[3]/r['height']] for b in r['detections'] if b[4]>=.25)
        proposals=propose_zones(points); num=den=0
        for r in test:
            if r['view']==view:
                for g in r['gt']:
                    pt=np.array(g['foot'])/[r['width'],r['height']]; den+=1
                    num+=int(any(assign_zone(pt,[z]) is not None for z in proposals))
        area=sum(abs(np.cross(np.array(z['polygon'])[1]-np.array(z['polygon'])[0],np.array(z['polygon'])[3]-np.array(z['polygon'])[0])) for z in proposals)
        proposal.append({'view':view,'proposals':proposals,'test_gt_point_coverage':num/max(1,den),'image_area_fraction':float(area),
                         'scope':'Train predictions only; measures activity coverage, not department or floor-mask correctness.'})
    save(OUT/'zone_proposals.json',proposal)
    queue=json.loads((OUT/'review_queue.json').read_text());lookup={(r['name'],r['frame']):r for r in train}
    def errors(rows):
        scores=[]
        for r in rows:
            det=[b for b in r['detections'] if b[4]>=.25]; pairs=match_boxes([g['box'] for g in r['gt']],[b[:4] for b in det])
            scores.append(len(det)+len(r['gt'])-2*len(pairs))
        return float(np.mean(scores))
    selected=[lookup[r['name'],r['frame']] for r in queue]
    random_scores=[errors([train[i] for i in np.random.default_rng(s).choice(len(train),len(selected),replace=False)]) for s in range(30)]
    save(OUT/'review_selection.json',{'budget':len(selected),'selected_mean_fp_plus_fn':errors(selected),
        'random_mean_fp_plus_fn':float(np.mean(random_scores)),'random_std':float(np.std(random_scores)),
        'scope':'Training-pool annotation triage; demonstrates error concentration, not training improvement or human time savings.'})
    print('stress complete',flush=True)

def audit_training():
    path=OUT/'training_manifest.json';m=json.loads(path.read_text());known={(r['name'],r['frame']) for r in m['frames']}
    records={r['name']:r for r in manifest()}
    for split in ['train','val']:
        for ip in (DATA/'yolo_reviewed'/'images'/split).glob('*.jpg'):
            name,f=ip.stem.rsplit('_',1);f=int(f)
            assert records[name]['split']==split and split!='test'
            if (name,f) not in known:
                m['frames'].append({'name':name,'split':split,'frame':f,'image':str(ip.relative_to(ROOT)),
                                    'label_source':'official human CAVIAR XML','note':'Additional early preparation sample retained'})
    m['counts']=dict(Counter(r['split'] for r in m['frames']));save(path,m)
    assert len({r['scenario'] for r in manifest() if r['split']=='train'}&{r['scenario'] for r in manifest() if r['split']=='test'})==0
    print('training audit',m['counts'],flush=True)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    save(OUT/'contract_tests.json',{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)})
    if not result.wasSuccessful():sys.exit(1)
    audit_training()
    if (OUT/'review_queue.json').exists():stress()
