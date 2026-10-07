"""Check tracking at reduced camera sampling rates using cached real detections."""
import json
from collections import defaultdict
import numpy as np
from experiment import OUT,save,metrics,tracking_metrics
data=json.loads((OUT/'baseline_predictions.json').read_text())
test=[r for r in data['rows'] if r['split']=='test']
clips=defaultdict(list)
for r in test:clips[r['name']].append(r)
results=[]
for hz in [5,2.5,2,1]:
    chosen=[]
    for name,rows in clips.items():
        last=-1
        for r in rows:
            bucket=round(r['time']*hz)
            if bucket>last:chosen.append(r);last=bucket
    tracking,_=tracking_metrics(chosen,.35)
    results.append({'requested_hz':hz,'sampled_frames':len(chosen),'detection':metrics(chosen,.35),'tracking':tracking})
save(OUT/'sampling_cadence.json',{'scope':'Cached-detection downsampling, no new inference. Reduced temporal coverage changes tracking.', 'runs':results})
print('cadence validation complete')
