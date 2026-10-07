"""Freeze validation-based deployment choice and verify final artifacts."""
import hashlib,json,unittest,compileall
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(ROOT))
from scripts.deadline.validate_and_stress import ContractTests,audit_training
from prototype.core import validate_config
OUT=ROOT/'experiments'/'deadline'
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
runs=json.loads((OUT/'comparison.json').read_text())['runs']
ranked=sorted([(max(r['validation_sweep'],key=lambda s:s['f1']),r['tag']) for r in runs],key=lambda x:-x[0]['f1'])
best,tag=ranked[0]
models={'baseline':'models/yolo11n.pt','reviewed':'experiments/deadline/training/reviewed/weights/best.pt','pseudo':'experiments/deadline/training/pseudo/weights/best.pt'}
params=json.loads((OUT/'zone_parameters.json').read_text())
config=json.loads((ROOT/'prototype/site.json').read_text())
config.update(model=models[tag],confidence=best['confidence'],cpu_threads=4,zone_persistence_s=.2)
validate_config(config)
(ROOT/'prototype/site.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
save('selection.json',{'date':'2026-10-07','criterion':'Maximum detection F1 on validation clips; test results are reported separately and do not choose the default.',
 'selected':tag,'model':models[tag],'model_sha256':hashlib.sha256((ROOT/models[tag]).read_bytes()).hexdigest(),
 'confidence':best['confidence'],'zone_persistence_s':.2,'zone_boundary_margin_normalized':.008,
 'candidates':[{'tag':t,'best_val_f1':r['f1'],'confidence':r['confidence']} for r,t in ranked],
 'limitations':'One small same-site validation scenario; near tie with reviewed model is not statistically conclusive. Site-specific camera holdout required.'})
suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
save('contract_tests.json',{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)})
assert result.wasSuccessful()
audit_training()
assert compileall.compile_dir(ROOT/'prototype',quiet=1)
assert compileall.compile_dir(ROOT/'scripts'/'deadline',quiet=1)
parsed=[]
for path in OUT.glob('*.json'):
    json.loads(path.read_text(encoding='utf-8'));parsed.append(path.name)
save('final_validation.json',{'selected':tag,'val_f1':best['f1'],'tests':result.testsRun,'json_files_parsed':parsed,
 'prototype_and_scripts_compile':True,'config_validated':True})
print(json.dumps({'selected':tag,'confidence':best['confidence'],'val_f1':best['f1'],'tests':result.testsRun,'parsed_json':len(parsed)}))
