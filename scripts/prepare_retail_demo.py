"""Download research-licensed retail demo footage to ignored *local* paths.

The repo stores only provenance/metadata, never these third-party video bytes.
Usage: python scripts/prepare_retail_demo.py [--only merl caviar mall]
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'retail_video_downloads'
SAMPLES = ROOT / 'samples' / 'retail_demo'
CAVIAR = ROOT / 'datasets' / 'caviar'
FILES = {
    'merl': ('https://huggingface.co/datasets/Voxel51/MERL_Shopping_Dataset/resolve/main/data/10_1_crop.mp4?download=true',
             SAMPLES / 'merl_shelf_browse.mp4', 65_000_000),
    'walk': ('https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA2/WalkByShop1cor/WalkByShop1cor.mpg',
             CAVIAR / 'WalkByShop1cor.mpg', 35_000_000),
    'assistant': ('https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA2/ShopAssistant1front/ShopAssistant1front.mpg',
                  CAVIAR / 'ShopAssistant1front.mpg', 35_000_000),
    'entry': ('https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA2/TwoEnterShop3front/TwoEnterShop3front.mpg',
              CAVIAR / 'TwoEnterShop3front.mpg', 30_000_000),
    'mall': ('https://staff.ie.cuhk.edu.hk/~ccloy/files/datasets/mall_dataset.zip',
             CACHE / 'mall_dataset.zip', 110_000_000),
}


def download(url, destination, max_bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 4096:
        print('Already present:', destination, flush=True)
        return
    temp = destination.with_suffix(destination.suffix + '.part')
    size = 0
    with requests.get(url, stream=True, timeout=(15, 90), headers={'User-Agent': 'Everseen-Educational-Demo/1.0'}) as response:
        response.raise_for_status()
        with temp.open('wb') as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f'File exceeds {max_bytes} byte demo limit')
                out.write(chunk)
                if size % (16 * 1024 * 1024) < len(chunk):
                    print(f'  {destination.name}: {size / 1048576:.0f} MiB', flush=True)
    if size < 4096:
        raise ValueError(f'Likely failed download: {destination}')
    temp.replace(destination)


def extract_mall(max_frames=420):
    archive = CACHE / 'mall_dataset.zip'
    if not archive.exists():
        raise FileNotFoundError(archive)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    output = SAMPLES / 'mall_crowd.mp4'
    if output.exists() and output.stat().st_size > 30000:
        print('Already present:', output, flush=True)
        return
    with zipfile.ZipFile(archive) as z:
        files = [x for x in z.namelist() if x.lower().endswith(('.jpg', '.jpeg', '.png'))
                 and not x.startswith('__MACOSX')]
        # Ignore bundled examples/visualizations: choose the largest contiguous frame directory.
        from collections import Counter
        counts = Counter(Path(x).parent.as_posix() for x in files)
        if not counts:
            raise ValueError(f'No image frames in {archive}')
        folder, total = counts.most_common(1)[0]
        frames = sorted(x for x in files if Path(x).parent.as_posix() == folder)
        print('Mall archive folder:', folder, 'frames:', len(frames), 'all folders:', counts.most_common(5), flush=True)
        if len(frames) < 60:
            raise ValueError('Not enough chronological mall frames')
        # The Mall benchmark is sampled below 2 Hz. Do not fabricate 25-Hz real-time trajectories.
        # Create a 2 FPS demo, with a warning in the catalog about nonuniform sample timestamps.
        selected = frames[:max_frames]
        first = cv2.imdecode(__import__('numpy').frombuffer(z.read(selected[0]), dtype='uint8'), cv2.IMREAD_COLOR)
        if first is None:
            raise ValueError('Cannot decode first Mall JPEG')
        h, w = first.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(output), fourcc, 2.0, (w, h))
        if not writer.isOpened():
            raise RuntimeError('Cannot open Mall MP4 writer')
        written = 0
        try:
            for filename in selected:
                array = __import__('numpy').frombuffer(z.read(filename), dtype='uint8')
                frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                if frame.shape[:2] != (h, w):
                    frame = cv2.resize(frame, (w, h))
                writer.write(frame)
                written += 1
        finally:
            writer.release()
        print('Wrote Mall sampled-frame sequence', written, 'frames,', w, 'x', h, 'at 2 FPS', flush=True)
    if written < 60:
        output.unlink(missing_ok=True)
        raise ValueError('Too few readable frames in output')


def fingerprint(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='*', choices=list(FILES), default=list(FILES))
    args = parser.parse_args()
    for name in args.only:
        url, dest, limit = FILES[name]
        print('Downloading', name, url, flush=True)
        download(url, dest, limit)
    if 'mall' in args.only:
        extract_mall()
    print('Download phase done; use scripts/test_retail_demo.py for actual decode and detection validation.', flush=True)
