"""Exercise live API + real model on the first configured demo camera.

Usage: .venv/Scripts/python.exe scripts/smoke_unified.py --seconds 10
Does not edit the site configuration or require a running HTTP server.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from prototype.server import app, live, load


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seconds', type=float, default=10)
    args = p.parse_args()
    camera_id = load()['cameras'][0]['id']
    client = TestClient(app)
    first = client.post(f'/api/live/start/{camera_id}')
    if first.status_code != 200:
        raise RuntimeError(f'Start API failed: {first.status_code}, {first.text}')
    try:
        time.sleep(args.seconds)
        status = next(c for c in client.get('/api/live/status').json()['cameras'] if c['id'] == camera_id)
        heat = client.get(f'/api/live/heat/{camera_id}.jpg')
        record = client.get(f'/api/live/events/{camera_id}')
        report = client.get(f'/api/live/report/{camera_id}.csv')
        result = {'camera': camera_id, 'status': status['status'], 'frames': status['frames'],
                  'heat_http': heat.status_code, 'heat_bytes': len(heat.content),
                  'events_http': record.status_code, 'event_lines': len(record.text.splitlines()),
                  'csv_http': report.status_code, 'csv_rows': len(report.text.splitlines()),
                  'elapsed_seconds': args.seconds,
                  'stats': status['zones'], 'output': status['output']}
        print(json.dumps(result, indent=2))
        if status['frames'] <= 0 or any(r.status_code != 200 for r in (heat, record, report)):
            raise AssertionError('Model, source, event, CSV or heatmap integration did not produce output')
    finally:
        live.stop(camera_id)
        summary = live.get(camera_id).output / 'summary.json'
        if not summary.is_file(): raise AssertionError('Stopped session summary was not persisted')


if __name__ == '__main__':
    main()
