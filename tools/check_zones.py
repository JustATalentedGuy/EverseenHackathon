"""Draw a config's zones onto a frame from each camera's source. Verification aid, not part of the app."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'prototype' / (sys.argv[1] if len(sys.argv) > 1 else 'site_cctv.json')).read_text())
out = Path('/tmp/zonecheck'); out.mkdir(exist_ok=True)
try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit('Pillow required: pip install pillow')

for cam in config['cameras']:
    src = ROOT / cam['source']
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'csv=p=0', str(src)], capture_output=True, text=True).stdout.strip())
    frame = out / f"{cam['id']}.png"
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(dur * 0.55), '-i', str(src),
                    '-frames:v', '1', str(frame), '-y'], check=True)
    img = Image.open(frame).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for zone in cam['zones']:
        pts = [(x * w, y * h) for x, y in zone['polygon']]
        draw.polygon(pts, outline=(0, 255, 120), width=3)
        draw.text((pts[0][0] + 6, pts[0][1] + 4), zone['label'], fill=(0, 255, 120))
    img.save(out / f"{cam['id']}_zones.png")
    print('wrote', out / f"{cam['id']}_zones.png")