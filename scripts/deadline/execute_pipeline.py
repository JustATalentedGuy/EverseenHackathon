"""Record real child exit codes and logs, avoiding PowerShell stderr-warning exits."""
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments'/'deadline'
commands=[
 ['scripts/deadline/experiment.py','infer','--tag','reviewed','--model','experiments/deadline/training/reviewed/weights/best.pt','--splits','val','test'],
 ['scripts/deadline/experiment.py','train','--labels','pseudo','--epochs','6'],
 ['scripts/deadline/experiment.py','infer','--tag','pseudo','--model','experiments/deadline/training/pseudo/weights/best.pt','--splits','val','test'],
 ['scripts/deadline/experiment.py','evaluate']]
statuses=[]
for i,cmd in enumerate(commands):
    log=OUT/f'pipeline_{i}.log';started=time.time();print('starting',i,' '.join(cmd),flush=True)
    with log.open('w',encoding='utf-8') as f:r=subprocess.run([sys.executable,*cmd],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    statuses.append({'command':cmd,'exit_code':r.returncode,'seconds':time.time()-started,'log':str(log.relative_to(ROOT))})
    (OUT/'pipeline_status.json').write_text(json.dumps(statuses,indent=2))
    print('finished',i,r.returncode,flush=True)
    if r.returncode:sys.exit(r.returncode)
