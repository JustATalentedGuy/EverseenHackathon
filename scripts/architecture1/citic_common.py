from __future__ import annotations

import csv
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Point = Tuple[float, float]


@dataclass
class Observation:
    capture: int
    frame: int
    gt_id: int
    x: float
    y: float
    gt_section: str = "UNKNOWN"
    noisy_section: str = "UNKNOWN"
    camera: Optional[str] = None


@dataclass
class Tracklet:
    uid: str
    capture: int
    camera: str
    gt_id: int
    observations: List[Observation]
    parent_uid: Optional[str] = None
    split_index: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def start_frame(self) -> int:
        return self.observations[0].frame

    @property
    def end_frame(self) -> int:
        return self.observations[-1].frame

    @property
    def start_xy(self) -> Point:
        o = self.observations[0]
        return o.x, o.y

    @property
    def end_xy(self) -> Point:
        o = self.observations[-1]
        return o.x, o.y

    @property
    def start_section(self) -> str:
        return self.observations[0].noisy_section or self.observations[0].gt_section

    @property
    def end_section(self) -> str:
        return self.observations[-1].noisy_section or self.observations[-1].gt_section


class UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {x: x for x in items}
        self.rank = {x: 0 for x in items}

    def find(self, x: str) -> str:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_rooms(dataset_root: Path) -> Tuple[dict, dict]:
    data = load_json(dataset_root / "map_config" / "room_map.json")
    rooms = {}
    meta = {}
    for item in data["room_map"]:
        if "name" in item:
            rooms[item["name"]] = {
                "rect": tuple(tuple(float(v) for v in p) for p in item["rect"]),
                "doors": [tuple(float(v) for v in p) for p in item.get("doors", [])],
            }
        else:
            meta.update(item)
    return rooms, meta


def load_cameras(dataset_root: Path) -> Dict[str, dict]:
    cameras = {}
    for path in sorted((dataset_root / "map_config").glob("Node*.json")):
        data = load_json(path)
        cameras[data["name"]] = data
    return cameras


def load_gt(dataset_root: Path, capture: int) -> List[Observation]:
    path = dataset_root / f"capture{capture}_gt.mot.txt"
    observations: List[Observation] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            observations.append(
                Observation(
                    capture=capture,
                    frame=int(row[0]),
                    gt_id=int(row[1]),
                    x=float(row[7]),
                    y=float(row[8]),
                )
            )
    observations.sort(key=lambda o: (o.frame, o.gt_id))
    return observations


def point_in_polygon(point: Point, polygon: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        on_seg = _point_on_segment(point, (xi, yi), (xj, yj), eps=1e-8)
        if on_seg:
            return True
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_on_segment(p: Point, a: Point, b: Point, eps: float = 1e-9) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -eps:
        return False
    sq = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= sq + eps


def rect_contains(point: Point, rect, eps: float = 1e-9) -> bool:
    (x0, y0), (x1, y1) = rect
    x, y = point
    return x0 - eps <= x <= x1 + eps and y0 - eps <= y <= y1 + eps


def rect_center(rect) -> Point:
    (x0, y0), (x1, y1) = rect
    return (0.5 * (x0 + x1), 0.5 * (y0 + y1))


def rect_area(rect) -> float:
    (x0, y0), (x1, y1) = rect
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def assign_section(point: Point, rooms: dict, previous: Optional[str] = None) -> str:
    candidates = [name for name, info in rooms.items() if rect_contains(point, info["rect"])]
    if not candidates:
        return "UNKNOWN"
    if previous in candidates:
        return previous
    if len(candidates) == 1:
        return candidates[0]
    # Door/boundary tie: choose the room whose center is closest. This affects only
    # exact boundary samples and is deterministic.
    x, y = point
    return min(
        candidates,
        key=lambda n: (math.dist((x, y), rect_center(rooms[n]["rect"])), rect_area(rooms[n]["rect"]), n),
    )


def assign_gt_sections(observations: List[Observation], rooms: dict) -> None:
    by_id = defaultdict(list)
    for o in observations:
        by_id[o.gt_id].append(o)
    for seq in by_id.values():
        seq.sort(key=lambda o: o.frame)
        for o in seq:
            # Ground truth uses the same deterministic geometric rule as the
            # stateless mapper. Hysteresis is evaluated separately; otherwise
            # zero-noise data would inherit state from the GT construction.
            o.gt_section = assign_section((o.x, o.y), rooms, None)


def room_adjacency(rooms: dict, tol: float = 1e-4) -> Dict[str, set]:
    adj = {name: set() for name in rooms}
    names = list(rooms)
    # Primary source: matching door coordinates.
    for i, a in enumerate(names):
        da = rooms[a].get("doors", [])
        for b in names[i + 1 :]:
            db = rooms[b].get("doors", [])
            shared = any(math.dist(x, y) <= tol for x in da for y in db)
            if shared:
                adj[a].add(b)
                adj[b].add(a)
    return adj


def shortest_hops(adj: Dict[str, set], start: str, end: str) -> Optional[int]:
    if start == end:
        return 0
    if start not in adj or end not in adj:
        return None
    q = deque([(start, 0)])
    seen = {start}
    while q:
        u, d = q.popleft()
        for v in adj[u]:
            if v == end:
                return d + 1
            if v not in seen:
                seen.add(v)
                q.append((v, d + 1))
    return None


def visible_cameras(point: Point, cameras: Dict[str, dict]) -> List[str]:
    return [
        name
        for name, info in cameras.items()
        if point_in_polygon(point, info.get("visibility_polygon", []))
    ]


def estimate_section_camera_coverage(rooms: dict, cameras: Dict[str, dict], grid: int = 30) -> dict:
    coverage = {}
    for section, info in rooms.items():
        (x0, y0), (x1, y1) = info["rect"]
        counts = {name: 0 for name in cameras}
        total = 0
        for ix in range(grid):
            x = x0 + (ix + 0.5) / grid * (x1 - x0)
            for iy in range(grid):
                y = y0 + (iy + 0.5) / grid * (y1 - y0)
                total += 1
                for cam in visible_cameras((x, y), cameras):
                    counts[cam] += 1
        coverage[section] = {name: counts[name] / max(total, 1) for name in cameras}
    return coverage


def choose_section_owners(coverage: dict, min_fraction: float = 0.02) -> Dict[str, Optional[str]]:
    owners = {}
    for section, fractions in coverage.items():
        if not fractions:
            owners[section] = None
            continue
        name, frac = max(fractions.items(), key=lambda kv: (kv[1], kv[0]))
        owners[section] = name if frac >= min_fraction else None
    return owners


def choose_camera_for_observation(o: Observation, cameras: dict, owners: dict, coverage: dict) -> Optional[str]:
    visible = visible_cameras((o.x, o.y), cameras)
    if not visible:
        return None
    preferred = owners.get(o.gt_section)
    if preferred in visible:
        return preferred
    # Fall back to the camera with highest section coverage. This keeps ownership
    # deterministic and avoids double counting overlapping cameras.
    return max(visible, key=lambda c: (coverage.get(o.gt_section, {}).get(c, 0.0), c))


def build_owner_observations(observations: List[Observation], cameras: dict, owners: dict, coverage: dict) -> List[Observation]:
    out = []
    for o in observations:
        o.camera = choose_camera_for_observation(o, cameras, owners, coverage)
        if o.camera is not None:
            out.append(o)
    return out


def build_tracklets(observations: List[Observation], max_frame_step: int = 1) -> List[Tracklet]:
    by_key = defaultdict(list)
    for o in observations:
        if o.camera is None:
            continue
        by_key[(o.capture, o.gt_id, o.camera)].append(o)
    tracklets = []
    counter = 0
    for (capture, gt_id, camera), seq in sorted(by_key.items()):
        seq.sort(key=lambda o: o.frame)
        current = []
        prev_frame = None
        for o in seq:
            if current and (o.frame - prev_frame > max_frame_step):
                counter += 1
                uid = f"C{capture}_{camera}_T{counter}"
                tracklets.append(Tracklet(uid, capture, camera, gt_id, current, parent_uid=uid))
                current = []
            current.append(o)
            prev_frame = o.frame
        if current:
            counter += 1
            uid = f"C{capture}_{camera}_T{counter}"
            tracklets.append(Tracklet(uid, capture, camera, gt_id, current, parent_uid=uid))
    return tracklets


def transition_events_from_tracklets(tracklets: Sequence[Tracklet], fps: float) -> List[dict]:
    by_gt = defaultdict(list)
    for t in tracklets:
        by_gt[(t.capture, t.gt_id)].append(t)
    events = []
    for (capture, gt_id), seq in by_gt.items():
        seq.sort(key=lambda t: (t.start_frame, t.end_frame, t.camera))
        for a, b in zip(seq, seq[1:]):
            if a.camera == b.camera:
                continue
            # Because owner assignment is unique per frame, overlap should not exist.
            gap_frames = b.start_frame - a.end_frame - 1
            if gap_frames < 0:
                continue
            events.append(
                {
                    "capture": capture,
                    "gt_id": gt_id,
                    "from_camera": a.camera,
                    "to_camera": b.camera,
                    "from_section": a.end_section,
                    "to_section": b.start_section,
                    "gap_frames": gap_frames,
                    "gap_seconds": gap_frames / fps,
                    "from_uid": a.uid,
                    "to_uid": b.uid,
                }
            )
    return events


def compress_sections(observations: Sequence[Observation], attr: str = "gt_section") -> List[Tuple[str, int, int]]:
    if not observations:
        return []
    seq = sorted(observations, key=lambda o: o.frame)
    out = []
    cur = getattr(seq[0], attr)
    start = seq[0].frame
    last = start
    for o in seq[1:]:
        label = getattr(o, attr)
        if label != cur:
            out.append((cur, start, last))
            cur = label
            start = o.frame
        last = o.frame
    out.append((cur, start, last))
    return out


def apply_section_hysteresis(labels: Sequence[str], min_persist_frames: int) -> List[str]:
    if not labels:
        return []
    committed = labels[0]
    candidate = None
    count = 0
    out = [committed]
    for label in labels[1:]:
        if label == committed:
            candidate = None
            count = 0
        elif label == candidate:
            count += 1
            if count >= min_persist_frames:
                committed = candidate
                candidate = None
                count = 0
        else:
            candidate = label
            count = 1
            if min_persist_frames <= 1:
                committed = candidate
                candidate = None
                count = 0
        out.append(committed)
    return out


def event_pairs(labels: Sequence[str]) -> List[Tuple[str, str]]:
    if not labels:
        return []
    pairs = []
    prev = labels[0]
    for label in labels[1:]:
        if label != prev:
            pairs.append((prev, label))
            prev = label
    return pairs


def precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def safe_mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
