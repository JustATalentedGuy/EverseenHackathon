"""Camera-image exposure map with units instead of frame-count-based color.

Only consecutive sightings of the same tracked foot point contribute person-
seconds. Unsupported intervals and missing IDs are *not* guessed or filled.
Camera-image cells are NOT equal-area floor regions.
"""

from collections import deque

import cv2
import numpy as np


HEAT_WINDOWS = (30, 120, 300)


class PresenceHeatmap:
    COLUMNS = 16
    ROWS = 9
    MAX_GAP_S = 1.5

    def __init__(self):
        self.events = deque(maxlen=160_000)  # (start, end, cell_y, cell_x, stable_zone)
        self.intervals = deque(maxlen=10_000)  # supported frame-pair timing
        self.previous = {}
        self.previous_zones = {}
        self.previous_time = None
        self.first_time = None
        self.last_time = None
        self.last_frame = None

    def update(self, t, foot_points, frame, zones=None):
        """foot_points: {camera-local track ID: normalized, nontruncated foot (x,y)}.

        Frame and evidence are stored together so heat is never overlaid on a
        different (more recent, unanalyzed) camera frame.
        """
        zones = zones or {}
        if self.first_time is None:
            self.first_time = t
        if self.previous_time is not None:
            dt = t - self.previous_time
            if 0 < dt <= self.MAX_GAP_S:
                self.intervals.append((self.previous_time, t))
                for tid, point in foot_points.items():
                    prior = self.previous.get(tid)
                    if prior is None:
                        continue
                    x = float(np.clip((point[0] + prior[0]) / 2, 0, 1 - 1e-8))
                    y = float(np.clip((point[1] + prior[1]) / 2, 0, 1 - 1e-8))
                    zone = zones.get(tid) if zones.get(tid) == self.previous_zones.get(tid) else None
                    self.events.append((self.previous_time, t,
                                        int(y * self.ROWS), int(x * self.COLUMNS), zone))
        self.previous = dict(foot_points)
        self.previous_zones = dict(zones)
        self.previous_time = t
        self.last_time = t
        self.last_frame = frame.copy()
        self.prune(t)

    def prune(self, now):
        threshold = now - max(HEAT_WINDOWS)
        while self.events and self.events[0][1] < threshold:
            self.events.popleft()
        while self.intervals and self.intervals[0][1] < threshold:
            self.intervals.popleft()

    def snapshot(self, window_s):
        if window_s not in HEAT_WINDOWS:
            raise ValueError('Heatmap window must be 30, 120 or 300 seconds')
        values = np.zeros((self.ROWS, self.COLUMNS), dtype=np.float32)
        if self.last_time is None:
            return values, {'window_s':window_s, 'time_s':None,
                            'elapsed_s':0., 'supported_s':0.,
                            'coverage_fraction':0., 'person_seconds':0.,
                            'peak_observed_avg_people_per_tile':0.,
                            'grid_columns':self.COLUMNS,'grid_rows':self.ROWS,
                            'tracked_pairs':0,'zones_person_seconds':{}}
        start = max(self.first_time, self.last_time - window_s)
        elapsed = max(0., self.last_time - start)
        supported = sum(max(0., end - max(begin, start))
                        for begin, end in self.intervals if end > start)
        pairs = 0
        zone_times = {}
        for begin, end, y, x, zone in self.events:
            if end > start:
                contribution = end - max(begin, start)
                if contribution > 0:
                    values[y, x] += contribution
                    pairs += 1
                    if zone:
                        zone_times[zone] = zone_times.get(zone, 0.) + contribution
        # Use real elapsed time as denominator. Gaps remain unobserved rather
        # than inflating average presence by dividing by only supported time.
        average = values / elapsed if elapsed > 0 else values
        meta = {'window_s':window_s, 'time_s':round(self.last_time,2),
                'elapsed_s':round(elapsed,1), 'supported_s':round(supported,1),
                'coverage_fraction':round(min(1.,supported/elapsed),2) if elapsed else 0.,
                'person_seconds':round(float(values.sum()),1),
                'peak_observed_avg_people_per_tile':round(float(average.max()),2),
                'grid_columns':self.COLUMNS,'grid_rows':self.ROWS,
                'tracked_pairs':pairs,
                'zones_person_seconds':{z:round(v,1) for z,v in sorted(zone_times.items(),key=lambda z:-z[1])}}
        return average, meta

    def jpeg(self, window_s):
        if self.last_frame is None:
            return None
        average, _ = self.snapshot(window_s)
        frame = self.last_frame.copy()
        height, width = frame.shape[:2]
        # Fixed scale across cameras/time windows: <.25 blue, .25-.5 teal,
        # .5-1 amber, >=1 red, all in observed avg people per IMAGE tile.
        # Do not color cells with no observations.
        palette = [None, (226, 128, 68), (137, 191, 55),
                   (68, 183, 245), (65, 68, 237)]  # BGR
        thresholds = (0.015, 0.25, 0.5, 1.0)
        top = sorted(((float(average[y,x]), y, x)
                      for y in range(self.ROWS) for x in range(self.COLUMNS)), reverse=True)
        top_cells = {(y,x) for amount,y,x in top[:4] if amount >= 0.1}
        for y in range(self.ROWS):
            y0, y1 = round(y * height/self.ROWS), round((y+1)*height/self.ROWS)
            for x in range(self.COLUMNS):
                amount = float(average[y,x])
                if amount < thresholds[0]:
                    continue
                x0, x1 = round(x * width/self.COLUMNS), round((x+1)*width/self.COLUMNS)
                palette_index = 1 + int(amount >= thresholds[1]) + int(amount >= thresholds[2]) + int(amount >= thresholds[3])
                region = frame[y0:y1,x0:x1]
                region[:]=cv2.addWeighted(region, .5,
                          np.full_like(region,palette[palette_index]), .5,0)
                cv2.rectangle(frame,(x0,y0),(x1-1,y1-1),(245,245,245),1)
                if (y,x) in top_cells and x1-x0>=35 and y1-y0>=20:
                    label=f'{amount:.1f}'
                    cv2.putText(frame,label,(x0+3,y0+min(y1-y0-4,17)),
                                cv2.FONT_HERSHEY_SIMPLEX,.43,(8,18,23),2,cv2.LINE_AA)
                    cv2.putText(frame,label,(x0+3,y0+min(y1-y0-4,17)),
                                cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
        encoded, buffer = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,83])
        return buffer.tobytes() if encoded else None
