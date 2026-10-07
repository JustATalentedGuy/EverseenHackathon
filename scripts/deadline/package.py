"""Package reproducible code and compact evidence, without footage or model caches."""
import json,zipfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments'/'deadline'
files=[]
for folder in ['prototype','scripts/deadline']:
    files.extend(p for p in (ROOT/folder).iterdir() if p.is_file() and p.suffix in ['.py','.html','.json','.md'])
files.append(ROOT/'research'/'FINAL_DEADLINE_DATA_AND_DEPLOYMENT_ARCHITECTURE.md')
files.append(ROOT/'datasets'/'caviar'/'manifest.json')
for name in ['comparison.csv','comparison.json','selection.json','training_manifest.json','pseudo_label_quality.json',
             'review_selection.json','review_queue.json','zone_parameters.json','zone_stress.json','zone_proposals.json',
             'sampling_cadence.json','cpu_export_validation.json','contract_tests.json','final_validation.json',
             'ui_validation.json','replay_validation.json','pipeline_status.json','setup_desktop.png','setup_mobile.png',
             'replay_dashboard.png','heldout_visual_audit.jpg']:
    files.append(OUT/name)
for label in ['reviewed','pseudo']:
    folder=OUT/'training'/label
    for name in ['args.yaml','results.csv']:
        if (folder/name).exists():files.append(folder/name)
files.append(OUT/'demo'/'summary.json')
path=OUT/'everseen_deadline_prototype.zip'
with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(set(files)):
        assert f.is_file(),f
        z.write(f,f.relative_to(ROOT).as_posix())
with zipfile.ZipFile(path) as z:assert z.testzip() is None
result={'archive':str(path),'files':len(set(files)),'bytes':path.stat().st_size,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'zip_integrity':'passed',
        'exclusions':'Video footage, detector weights and large raw prediction caches remain in the project.'}
(OUT/'package_validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
