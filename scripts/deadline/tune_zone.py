"""Select a temporal zone parameter using validation trajectories only."""
import json
from collections import defaultdict
import numpy as np
from validate_and_stress import event_list,event_score
from experiment import OUT,save,zones
from prototype.core import ZoneState,assign_zone
rows=[r for r in json.loads((OUT/'baseline_predictions.json').read_text())['rows'] if r['split']=='val']
paths=defaultdict(list)
for r in rows:
    for g in r['gt']:paths[(r['name'],g['id'])].append((r['time'],np.array(g['foot'])/[r['width'],r['height']],r['view']))
results=[]
for persistence in [0,.2,.4,.8]:
    scores=[]
    for seed in range(10):
        rng=np.random.default_rng(seed);tp=fp=fn=0
        for key,path in paths.items():
            zz=zones(path[0][2]);s=ZoneState(zz,persistence,0 if persistence==0 else .008)
            truth=[];pred=[]
            for t,pt,_ in path:
                truth.append((t,assign_zone(pt,zz)));pred.append((t,s.update(key,t,pt+rng.normal(0,.01,2))))
            a,b,c=event_score(event_list(truth),event_list(pred));tp+=a;fp+=b;fn+=c
        scores.append(2*tp/max(1,2*tp+fp+fn))
    results.append({'persistence_s':persistence,'validation_mean_transition_f1':float(np.mean(scores))})
best=max(results,key=lambda r:r['validation_mean_transition_f1'])
save(OUT/'zone_parameters.json',{'persistence_s':best['persistence_s'],'margin':.008 if best['persistence_s'] else 0,
     'selection_scope':'Validation GT trajectory perturbation only, sigma=.01 normalized, 10 seeds.', 'sweep':results})
print(best)
