"""Acquire small official CAVIAR shopping-centre clips, preserving provenance."""
import concurrent.futures
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin
import requests
import cv2

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'datasets' / 'caviar'
SOURCE = 'https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/'
SPLITS = {'EnterExitCrossingPaths1': 'train', 'TwoEnterShop1': 'train',
          'OneLeaveShop1': 'val', 'EnterExitCrossingPaths2': 'test',
          'OneShopOneWait2': 'test'}

def fetch(url, path):
    fetched_from=url
    if not path.exists():
        tmp = path.with_suffix(path.suffix + '.part')
        candidates=[url,url.replace('https://homepages.inf.ed.ac.uk/rbf/',
                                   'https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/')]
        for candidate in candidates:
            result=subprocess.run(['curl.exe', '-f', '-L', '-sS', '--retry', '2', '--retry-all-errors', '--http1.1',
                        '--connect-timeout', '10', '--max-time', '60',
                        candidate, '-o', str(tmp)],capture_output=True)
            if result.returncode==0:
                fetched_from=candidate
                break
        else: raise RuntimeError(f'Download failed: {url}')
        tmp.replace(path)
    return {'url': url, 'fetched_from':fetched_from, 'path': str(path.relative_to(ROOT)),
            'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fetch(SOURCE, OUT / 'source.html')
    html = (OUT / 'source.html').read_text(encoding='utf-8')
    links = re.findall(r'href\s*=\s*[\"\x27]([^\"\x27]+)', html, re.I)
    records = []
    jobs = []
    for scenario, split in SPLITS.items():
        for view in ['cor', 'front']:
            name = scenario + view
            matching = [urljoin(SOURCE, x) for x in links if '/' + name + '/' in urljoin(SOURCE, x)]
            video = next(x for x in matching if x.endswith('.mpg'))
            xml = next(x for x in matching if x.endswith('.xml'))
            record = {'name': name, 'scenario': scenario, 'view': view, 'split': split,
                      'video': str((OUT / (name + '.mpg')).relative_to(ROOT)),
                      'xml': str((OUT / (name + '.xml')).relative_to(ROOT))}
            records.append(record)
            jobs.extend([(video, OUT / (name + '.mpg')), (xml, OUT / (name + '.xml'))])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(fetch,*job) for job in jobs]
        files=[]; errors=[]
        for f in concurrent.futures.as_completed(futures):
            try: files.append(f.result())
            except Exception as exc: errors.append(str(exc)); print(str(exc),flush=True)
    if errors: raise RuntimeError(errors)
    for r in records:
        cap = cv2.VideoCapture(str(ROOT / r['video']))
        if not cap.isOpened(): raise RuntimeError(r['video'])
        r.update(fps=cap.get(cv2.CAP_PROP_FPS), container_reported_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                 width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        ok, frame = cap.read()
        if ok: cv2.imwrite(str(OUT / (r['name'] + '.jpg')), frame)
        count=int(ok)
        while True:
            ok,_=cap.read()
            if not ok: break
            count+=1
        r['frames']=count
        cap.release()
    manifest = {'source': SOURCE, 'attribution': 'EC Funded CAVIAR project/IST 2001 37540',
                'source_terms': 'Source page states Creative Commons BY-SA; retain attribution and source terms.',
                'split_policy': 'Entire scenarios and both associated views stay in one split. Same site and actors may recur; this is scenario generalization, not unseen-site generalization.',
                'records': records, 'files': files}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(records, indent=2))

if __name__ == '__main__': main()
