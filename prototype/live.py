"""On-demand camera monitoring built on the evaluated local detection/zone core.

Unlike completed visits or arrivals, all dwell and entries are *observations*.
Each camera has one latest-frame slot; slow CPU inference never queues old frames.
"""
from collections import Counter, defaultdict, deque
import importlib.util
import json
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker

from .core import Analytics, validate_config
from .insights import make_recommendation, sustained_pressure
from .sources import resolve_source

INFERENCE_LOCK = threading.Lock()  # CPU inference across camera workers
MODEL_CACHE = {}  # protected by INFERENCE_LOCK: avoids loading the same weights per camera
WINDOW_S = 300


def select_live_model(site, root):
    """Use validated CPU ONNX export when installed; retain PyTorch fallback.

    The ONNX parity evidence is limited to 16 validation images, not a full rerun.
    """
    explicit = site.get('live_model')
    if explicit and explicit != 'auto':
        chosen = Path(explicit)
    else:
        chosen = Path(site.get('model', 'models/yolo11n.pt'))
        candidate = Path('models/yolo11n.onnx')
        if (site.get('device','cpu') == 'cpu'
                and chosen.as_posix().endswith('models/yolo11n.pt')
                and (Path(root)/candidate).is_file()
                and importlib.util.find_spec('onnxruntime') is not None):
            chosen = candidate
    return chosen if chosen.is_absolute() else (Path(root)/chosen)


def new_tracker(confidence, fps):
    return BYTETracker(SimpleNamespace(
        track_high_thresh=confidence, track_low_thresh=0.05,
        new_track_thresh=confidence, track_buffer=max(1, round(fps)),
        match_thresh=0.8, fuse_score=True,
    ))


def summarize_window(samples, now, window_s=WINDOW_S):
    """Finite sliding-window occupancy statistics; no claim of unique shoppers."""
    fresh = [r for r in samples if 0 <= now - r['time'] <= window_s]
    if not fresh:
        return {'p90': 0, 'mean': 0, 'samples': 0}
    counts = [r['count'] for r in fresh]
    return {'p90': round(float(np.percentile(counts, 90)), 1),
            'mean': round(float(np.mean(counts)), 2), 'samples': len(counts)}


class LiveCamera:
    def __init__(self, camera, site, root):
        self.camera = camera
        self.site = site
        self.root = Path(root)
        self.source, self.is_stream = resolve_source(camera['source'], root)
        self.id = camera['id']
        self.model_path = select_live_model(site, root)
        self.status = 'starting'
        self.error = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.seq = 0
        self.latest = None
        self.jpeg = None
        self.jpg_seq = 0
        self.heat = np.zeros((180, 320), np.float32)
        self.analytics = Analytics(camera.get('zones', []),
                                  persistence_s=float(site.get('zone_persistence_s', 0.2)),
                                  max_gap_s=max(0.45, 1.6 / float(site.get('sample_hz', 5))))
        self.previous = {}
        self.track_epoch = 0
        self.seen_entries = defaultdict(set)
        self.peak = Counter()
        self.counts = Counter()
        self.samples = defaultdict(lambda: deque(maxlen=2400))
        self.processed_times = deque(maxlen=256)
        self.last_processed_at = None
        self.capture_age_at_result_s = None
        self.last_track_count = 0
        self.last_truncated_count = 0
        self.frames = 0
        self.started_wall = time.time()
        self.started = time.monotonic()
        self.last_observation = None
        self.current_risks = []
        self.output = self.root / 'runs' / 'live' / f'{self.id}_{int(self.started_wall)}'
        self.output.mkdir(parents=True, exist_ok=True)
        self.events_path = self.output / 'observations.jsonl'
        self.reader = threading.Thread(target=self._read, daemon=True, name=f'camera-read-{self.id}')
        self.worker = threading.Thread(target=self._infer, daemon=True, name=f'camera-infer-{self.id}')
        self.reader.start()
        self.worker.start()

    def _read(self):
        retries = 0
        while not self.stop_event.is_set():
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                cap.release()
                retries += 1
                with self.lock:
                    self.status = 'reconnecting' if self.is_stream else 'failed'
                    self.error = 'Unable to open source'
                if not self.is_stream:
                    break
                self.stop_event.wait(min(2 * retries, 10))
                continue
            retries = 0
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = fps if math.isfinite(fps) and 1 <= fps <= 120 else 25
            next_frame_at = time.monotonic()
            with self.lock:
                self.status = 'connecting'
                self.error = None
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] > 1280:
                    width = 1280
                    frame = cv2.resize(frame, (width, round(frame.shape[0] * width / frame.shape[1])))
                now = time.monotonic()
                with self.lock:
                    self.seq += 1
                    self.latest = (self.seq, now, frame)
                    self.status = 'live'
                # Replayed clips respect their original frame rate. Streams do not sleep.
                if not self.is_stream:
                    next_frame_at = max(next_frame_at + 1 / fps, now)
                    self.stop_event.wait(max(0, next_frame_at - time.monotonic()))
            cap.release()
            if not self.is_stream:
                with self.lock:
                    if not self.stop_event.is_set(): self.status = 'ended'
                break
            with self.lock:
                if not self.stop_event.is_set(): self.status = 'reconnecting'
            self.stop_event.wait(2)

    def _infer(self):
        try:
            with INFERENCE_LOCK:
                torch.set_num_threads(int(self.site.get('cpu_threads', 4)))
                key=str(self.model_path.resolve())
                if key not in MODEL_CACHE:
                    MODEL_CACHE[key]=YOLO(key)
                model=MODEL_CACHE[key]
            hz = float(self.site.get('sample_hz', 5))
            confidence = float(self.site.get('confidence', 0.35))
            tracker = new_tracker(confidence, hz)
            last_seq, last_sample = -1, -1e9
            previous_capture = None
            with self.events_path.open('a', encoding='utf-8', buffering=1) as out:
                while not self.stop_event.is_set():
                    with self.lock:
                        item = self.latest
                        source_status = self.status
                    if item is None or item[0] == last_seq or item[1] - last_sample < 1 / hz:
                        if source_status in ('ended', 'failed') and (item is None or item[0] == last_seq):
                            break
                        self.stop_event.wait(0.025)
                        continue
                    seq, taken_at, frame = item
                    last_seq, last_sample = seq, taken_at
                    # Never implicitly continue track identities across decoder outages.
                    if previous_capture is not None and taken_at-previous_capture > max(2.0, 3/hz):
                        tracker = new_tracker(confidence, hz)
                        self.track_epoch += 1
                        self.previous.clear()
                    previous_capture = taken_at
                    with INFERENCE_LOCK:
                        prediction = model.predict(frame, imgsz=int(self.site.get('imgsz', 416)),
                                                   classes=[0], conf=0.05, verbose=False,
                                                   device=self.site.get('device', 'cpu'))[0]
                    tracks = tracker.update(prediction.boxes.cpu().numpy())
                    with self.lock:
                        self._step(frame, tracks, taken_at - self.started, out)
                        self.last_processed_at = time.monotonic()
                        self.capture_age_at_result_s = max(0, self.last_processed_at - taken_at)
                        self.processed_times.append(self.last_processed_at)
        except Exception as exc:
            self.stop_event.set()  # failed inference must not leave a decoder running forever
            with self.lock:
                self.status = 'failed'
                self.error = f'{type(exc).__name__}: {exc}'

    def _step(self, frame, tracks, t, out):
        h, w = frame.shape[:2]
        counts, speeds, observations = Counter(), defaultdict(list), []
        self.last_track_count = len(tracks)
        self.last_truncated_count = 0
        for track in tracks:
            tid = self.track_epoch * 1_000_000 + int(track[4])
            x1, y1, x2, y2 = (float(v) for v in track[:4])
            point = [max(0, min(1, (x1 + x2) / (2*w))), max(0, min(1, y2 / h))]
            truncated = y1 <= 1 or y2 >= h - 2
            self.last_truncated_count += int(truncated)
            zone = self.analytics.update(tid, t, point) if not truncated else None
            speed = None
            old = self.previous.get(tid)
            if old and 0 < t - old[0] <= self.analytics.max_gap:
                speed = float(np.linalg.norm(np.array(point) - old[1]) /
                              max((y2 - y1)/h, .03) / (t - old[0]))
            self.previous[tid] = (t, point)
            if zone:
                counts[zone] += 1
                self.seen_entries[zone].add(tid)
                if speed is not None:
                    speeds[zone].append(speed)
            if not truncated:
                hx, hy = min(319, int(point[0]*320)), min(179, int(point[1]*180))
                self.heat[hy, hx] += 1
            observations.append({'track_id': tid, 'point': point, 'zone': zone,
                                 'truncated': bool(truncated), 'speed_body_heights_s': speed})
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (93, 219, 155), 2)
            cv2.putText(frame, f'#{tid} {zone or "unassigned"}',
                        (max(0, int(x1)), max(14, int(y1) - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (93, 219, 155), 1)
        self.heat *= .996
        risks = []
        now = time.monotonic()
        for zone in self.camera.get('zones', []):
            name = zone['id']
            count = counts[name]
            self.peak[name] = max(self.peak[name], count)
            slow_fraction = (sum(s < float(self.site.get('slow_body_heights_ps', .1)) for s in speeds[name])
                             / len(speeds[name])) if speeds[name] else None
            self.samples[name].append({'time': now, 'count': count,
                                       'slow_fraction': slow_fraction})
            pts = (np.array(zone['polygon']) * [w, h]).astype(np.int32)
            cv2.polylines(frame, [pts], True, (230, 189, 84), 2)
            cv2.putText(frame, f'{zone.get("label", name)}: {count}',
                        tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, .53, (230, 189, 84), 2)
            window = summarize_window(self.samples[name], now)
            evidence = sustained_pressure(self.samples[name],
                         threshold=int(zone.get('crowd_threshold', 4)),
                         persistence_s=float(zone.get('persistence_s', 5)),
                         max_gap_s=max(3, 2.5 / float(self.site.get('sample_hz',5))))
            suggestion = make_recommendation(zone, evidence)
            if suggestion is not None:
                risks.append(suggestion)
        self.counts = counts
        ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        record = {'camera': self.id, 'time_s': round(t, 3), 'counts': dict(counts),
                  'observations': observations, 'inspection_cues': risks}
        out.write(json.dumps(record, allow_nan=False) + '\n')
        self.current_risks = risks
        self.last_observation = round(t, 2)
        self.frames += 1
        if ok:
            self.jpeg = jpg.tobytes()
            self.jpg_seq += 1

    def stats(self):
        with self.lock:
            now = time.monotonic()
            age = round(now - self.last_processed_at, 1) if self.last_processed_at else None
            stale_after = max(4, 3/float(self.site.get('sample_hz',5)))
            fresh = age is not None and age <= stale_after and self.status == 'live'
            recent = [t for t in self.processed_times if now-t <= 30]
            measured_fps = round(len(recent)/max(1.0, min(30,now-self.started)), 2)
            configured_hz = float(self.site.get('sample_hz', 5))
            throughput_ratio = measured_fps/configured_hz
            reliability = ('no_data' if age is None else
                           'stale' if not fresh else
                           'warming' if len(self.processed_times) < 6 or now-self.started < 8 else
                           'limited' if throughput_ratio < .5 else 'observing')
            dwell = defaultdict(list)
            for item in self.analytics.snapshot()['observed_dwell']:
                dwell[item['zone']].append(item['seconds'])
            zones = []
            for z in self.camera.get('zones', []):
                name = z['id']
                window = summarize_window(list(self.samples[name]), now)
                partial = dwell[name]
                zones.append({'id': name, 'label': z.get('label', name),
                              'role': z.get('role','other'),
                              'crowd_threshold': int(z.get('crowd_threshold',4)),
                              'occupancy': self.counts[name] if fresh else None,
                              'peak': self.peak[name],
                              'observed_track_entries': len(self.seen_entries[name]),
                              'partial_dwell_mean_s': round(float(np.mean(partial)), 1) if partial else 0,
                              'partial_dwell_tracks': len(partial), 'p90_occupancy_5m': window['p90'],
                              'mean_occupancy_5m': window['mean'], 'samples_5m': window['samples']})
            return {'id': self.id, 'name': self.camera.get('name', self.id),
                    'status': self.status, 'error': self.error, 'frames': self.frames,
                    'elapsed_s': round(now - self.started, 1), 'last_observation_s': self.last_observation,
                    'zones': zones,
                    'inspection_cues': list(self.current_risks) if fresh and reliability == 'observing' else [],
                    'measurement': {'state': reliability, 'fresh': fresh,
                                    'age_s': age, 'observed_fps_30s': measured_fps,
                                    'target_hz': configured_hz, 'capture_lag_s': round(self.capture_age_at_result_s, 2)
                                    if self.capture_age_at_result_s is not None else None,
                                    'backend': self.model_path.suffix.lower().lstrip('.'),
                                    'tracked_boxes_last_sample': self.last_track_count,
                                    'truncated_boxes_last_sample': self.last_truncated_count,
                                    'note': 'Warm-up: too few samples to evaluate rate. Limited: below half the target sampling rate; counts may miss activity.'},
                    'output': str(self.output.relative_to(self.root)).replace('\\', '/'),
                    'scope': 'Observed camera-local tracks and partial visible dwell only'}

    def heatmap_jpeg(self):
        with self.lock:
            item = self.latest
            heat = self.heat.copy()
        if item is None:
            return None
        frame = item[2]
        blurred = cv2.GaussianBlur(heat, (0, 0), 4)
        strength = blurred.max()
        heat8 = (255 * blurred / strength).astype(np.uint8) if strength > 0 else np.zeros_like(blurred, np.uint8)
        heat8 = cv2.resize(heat8, (frame.shape[1], frame.shape[0]))
        tinted = cv2.addWeighted(frame, .53, cv2.applyColorMap(heat8, cv2.COLORMAP_JET), .47, 0)
        masked = np.where((heat8 > 16)[..., None], tinted, frame)
        ok, buffer = cv2.imencode('.jpg', masked)
        return buffer.tobytes() if ok else None

    def stop(self):
        self.stop_event.set()
        self.reader.join(timeout=2)
        self.worker.join(timeout=3)
        with self.lock:
            if self.status not in ('failed', 'ended'): self.status = 'stopped'
        (self.output / 'summary.json').write_text(json.dumps(self.stats(), indent=2), encoding='utf-8')


class LiveManager:
    def __init__(self, root):
        self.root = Path(root)
        self.cameras = {}
        self.lock = threading.Lock()

    def start(self, camera_id, site):
        validate_config(site)
        camera = next((c for c in site['cameras'] if c['id'] == camera_id), None)
        if camera is None:
            raise KeyError('Unknown camera')
        with self.lock:
            existing = self.cameras.get(camera_id)
            if existing and existing.status not in ('stopped', 'failed', 'ended'):
                return existing.stats()
            if existing:
                # Do not retain an orphaned decoder when retrying failed streams.
                existing.stop()
            if len([c for c in self.cameras.values() if c.status not in ('stopped', 'failed', 'ended')]) >= 4:
                raise ValueError('Maximum four live cameras in this demo')
            cam = LiveCamera(camera, site, self.root)
            self.cameras[camera_id] = cam
            return cam.stats()

    def stop(self, camera_id):
        with self.lock:
            cam = self.cameras.get(camera_id)
        if cam is None:
            raise KeyError('Unknown live camera')
        cam.stop()
        return cam.stats()

    def stop_all(self):
        with self.lock:
            cameras = list(self.cameras.values())
            self.cameras.clear()  # config updates invalidate prior session metrics
        for cam in cameras:
            cam.stop()

    def get(self, camera_id):
        with self.lock:
            return self.cameras.get(camera_id)

    def stats(self):
        with self.lock:
            cams = list(self.cameras.values())
        return {'cameras': [c.stats() for c in cams],
                'note': 'Track entries are not unique visitors. Dwell covers observed intervals, not completed visits.'}
