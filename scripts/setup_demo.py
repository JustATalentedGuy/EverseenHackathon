"""Acquire the excluded pretrained model and optionally official demo footage."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
from ultralytics import YOLO

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',action='store_true',help='Also acquire official CAVIAR demo footage/labels')
    args=parser.parse_args()
    path=ROOT/'models'/'yolo11n.pt'
    path.parent.mkdir(parents=True,exist_ok=True)
    YOLO(str(path))  # Ultralytics acquires this named official asset when absent.
    print('Model:',path)
    print('SHA256:',hashlib.sha256(path.read_bytes()).hexdigest())
    if args.data:
        subprocess.run([sys.executable,str(ROOT/'scripts'/'deadline'/'acquire_caviar.py')],cwd=ROOT,check=True)
    else:
        print('For the supplied video demo, run again with --data. Acquisition uses curl.exe on Windows.')

if __name__=='__main__':
    main()
