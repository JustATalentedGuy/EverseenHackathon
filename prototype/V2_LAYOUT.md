# Everseen 2.0 — Operator-defined spatial topology and multi-camera analytics

## Run and navigate

```powershell
cd C:\Coding\ML\Everseen
.\.venv\Scripts\python.exe -m prototype.server
```

Open `http://127.0.0.1:8791/layout` or use the **Layout Design & Topology** tab in Live Operations. The original Live Operations page is still `/`, including its per-camera monitoring, foot-presence heatmap and **Whole-store section analytics** table at the bottom. The original offline/replay editor remains `/setup`.

The UI is offline-capable vanilla JavaScript/CSS: no CDN, GPU, Three.js or seaborn Python runtime is required. Its rotatable 3D rendering uses browser perspective, translucent layered tiles, and miniature stylized 3D human icons. The heat colors are **inspired by seaborn's rocket palette**, but represent actual section counts (not a seaborn statistical KDE or physical surface).

## Set up a layout

1. **Add section** to create a rectangular grid cell group. Drag a section to move it. Use the small striped grip in its bottom-right corner to **resize** it. The schematic has **12 columns × 8 rows**, with edge snapping and no overlapping sections. Add up to 120 sections. Alternatively choose **Create example layout** as an explicitly conceptual starting point.
2. Select a box, edit its name, role and coordinates. **Entrance** starts a topology route, **Exit** ends one, and aisle/display/checkout/other describe the operator's intended use. If no explicit entrances/exits exist, tiles touching the **bottom** and **top** grid boundaries respectively are assumed to be the start/end, and the UI flags those assumptions.
3. Under **Camera mapping**, check each camera *zone* that actually observes the section. Set up camera polygons in Live Operations first. You can map multiple camera zones from multiple configured feeds to the **same section**, but one camera zone cannot be assigned to two different sections. Source cameras need not run simultaneously.
4. Choose **Save floor plan** to persist it to `prototype/floor_layout.json`. This is **independent** of `site.json`, so editing the schematic never rewrites the camera configurations. A stale camera-zone mapping is flagged and removed from the draft on next load, but is not silently saved. **Discard changes** restores the saved arrangement.
5. Start the relevant camera feeds from **Live Operations**; return to the layout screen. Metrics and 3D figures update automatically. Drag the 3D view to orbit, use the mouse wheel to zoom and **Reset angle** to restore the isometric view.

## How the internal graph works

Each section is an internal node. Two rectangles are adjacent if **one full/partial edge has positive overlap**; touching diagonally at a corner is not traversable. An undirected adjacency list records these touching relationships. Directed traversal favors **toward the top/back**, allowing a step if the next box's center lies at or above the current box's center. Horizontal steps at the same height are permitted both ways. The backend uses breadth-first search to find a schematic path from each entrance to the first exit. It counts how many such routes include a given intermediate section and surfaces connectivity assumptions and disconnected boxes as *warnings*. The topology graph is **not** drawn over the floor visualization and does not infer actual routes through walls, doors, or shelves. The user must verify passability.

Implementation: `prototype/topology.py`: `validate_layout`, `neighbors`, `build_topology`.

## Camera-zone aggregation

At each metrics refresh, the backend joins operator-authored section mappings with `/api/live/status`. It discards **stale** camera observations. For a physical section covered by multiple active feeds:

`section.current_observed_count = max(fresh_mapped_zone_occupancies)`

The **maximum**, not the sum, is intentional: overlapping camera views may observe the same person, and cameras may be unsynchronized. Without verified camera calibration and identity association, the total number of **distinct** people is not established.

- **P90 and mean occupancy:** the maximum of valid mapped-zone rolling five-minute statistics. This is a conservative display heuristic, not an exact fused distribution.
- **Partial visible dwell, observed track IDs:** use the data from the single mapped camera with the highest current occupancy, never sum track identities between cameras. This can switch supporting cameras between updates; do not interpret it as completed dwell of a person across cameras.
- **Mapped / active feeds:** the number of defined camera-zone mappings and the subset with fresh observations. No data shows `—`, never a misleading zero.
- **Overall observed section sum:** shown *only as a sum of section observations with an explicit non-unique warning*. It cannot be called unique mall footfall; schematic sections and camera fields of view may overlap.
- **Real-time capacity:** 128 configured camera sources maximum in this local prototype; at most **four** concurrent CPU inference streams due to the existing hardware-oriented workload cap. You can still register/match many cameras and monitor them in groups. Large deployments need scalable processing and per-site validation.

Implementation: `prototype/topology.py`: `aggregate`, `full_report`, plus `GET /api/layout/analytics` in `prototype/server.py`.

## Bottleneck and low-activity suggestions

A **review cue**, not a proven bottleneck, is available only after an existing camera-zone algorithm has detected **sustained above-threshold occupancy** across consecutive samples and the camera is fresh. The graph/insight layer uses those existing cues; it does not invent measured queues or customer intent.

A possible **underused destination** must have fresh, *observing-quality* camera data, at least 10 occupancy samples, at least 20 seconds of camera session, **zero observed people now**, five-minute mean occupancy at most 0.5, and no active review cue. A mapped but disconnected, stale, or unseen area is **not** called a dead zone.

Candidates must be **graph-connected** to the stressed section, and neither an entrance/exit nor a checkout counter is automatically proposed as a movable alternative. The nearest destination in graph-edge hops is considered first. The suggestion is limited to a cautious experiment: assess whether a **movable display or activity** could be *trialled* in the quieter area after reviewing accessibility and paths. No automated store-floor relocation happens. The UI explicitly warns that the analysis cannot prove that rearrangement will improve sales or reduce queue times.

When a supported destination is unavailable, the suggestion is an **inspection** of staffing, clearance and occlusion instead of an unjustified swap. Disconnected layout nodes are flagged. These are **heuristics**, not trained or independently benchmarked topology-optimization models.

Implementation: `prototype/topology.py`: `insights`, with the sustained occupancy rules in `prototype/insights.py`.

## API

| Method / endpoint | Purpose |
|---|---|
| `GET /layout` | Interactive designer + rotatable 3D store scene |
| `GET /static/layout.js` | Local browser controller (no remote scripts) |
| `GET /api/layout` | Read the persistent schematic |
| `PUT /api/layout` | Validate unique boxes/zone mappings and atomically save |
| `GET /api/layout/analytics` | Cross-camera section metrics, internal topology and guarded suggestions |

On saved layout failures (out-of-grid, overlapping rectangles, invalid camera-zone IDs, duplicate mappings), the API returns HTTP 422 and **does not overwrite** the existing layout.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_topology tests.test_heatmap tests.test_unified_prototype scripts.deadline.validate_and_stress.ContractTests -v
.\.venv\Scripts\python.exe scripts/check_layout_v2.py
```

The browser test requires a temporary local server on port 8895 and Chrome/Playwright; it saves and **restores** the prior layout in a `finally` block, and does not modify `prototype/site.json`. It tests drag, creation, editing, camera mappings, topology, save/reload, 3D rotation, whole-store analytics, and real video-to-3D figure integration. Screenshots go to ignored `runs/layout_v2_checks/`.

## Scientific and product limitations

Schematic rectangular tiles have no metric scale or guaranteed correspondence to floor measurements. The graph does not know where actual doors, corridors, obstructions or one-way routes are unless represented by the operator. 3D people are **illustrative icons proportional to observed camera counts**, not 3D human reconstructions or calibrated live positional estimates. Section-level color is not person density per square metre. A lack of camera evidence is *unknown*, not low demand. Camera-zone links require explicit operator confirmation. Topology suggestions require field validation before consequential operational decisions.
