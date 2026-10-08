# Everseen | Unified hackathon prototype

## Getting started

From **`C:\Coding\ML\Everseen`** on Windows with the existing Python virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m prototype.server
```

Open **http://127.0.0.1:8791/**. The app binds **127.0.0.1 only**. For a new machine, see the root [README](../README.md) for the required pretrained model and sample footage acquisition (`scripts/setup_demo.py --data`). No database, Node.js build, cloud account, or MediaMTX is required when analyzing a project-local video.

1. **Camera onboarding:** enter a name and source: `0` for a webcam, an `rtsp://...` camera URL, an `https://.../video.mp4` or HTTP MJPEG URL supported by OpenCV, or a relative existing project path such as `samples/epfl_lab/cam0.avi`. Click **Add camera source**. External URLs must actually be readable by OpenCV/FFmpeg; web pages like YouTube watch URLs are **not** direct video URLs.
2. **Site geometry:** choose the camera, click **Show original frame**, enter a section name, choose its **business type** (checkout / aisle / display / entrance / other) and the minimum **observed people** that should warrant review. Choose **Draw new zone**, click at least three floor-region corners, then **Finish zone**. For each saved zone, adjust its business type and review threshold using **Save limits**. Every save stops monitoring to avoid stale zone definitions.
3. **Monitor:** choose a camera, click **Start monitoring**, inspect annotated video, recent foot-point heatmap, selected-camera occupancy, partial visible dwell, and reasoned review recommendations. The measurement panel shows frame freshness, warm-up/limited throughput, target and observed FPS, and backend. Missing/stale current occupancy is shown as unavailable, not zero. The active CPU target is set in `prototype/site.json` (`sample_hz`, default 5). Restart or stop an individual camera without restarting the server.
4. **Reproducible replay:** use the **Replay & calibration** navigation or `/setup` for the original 30-second experiment workflow, audited polygon geometry, proposals, floor calibration, generated MP4 overlays, and exact recorded summaries.
5. **Export:** click **Export event log** in live operations for timestamped JSONL, or **Export zone report (.csv)** for a spreadsheet-ready, caveated per-zone summary. Session files live at `runs/live/<camera>_<start_time>/observations.jsonl` with `summary.json` saved when a session stops (all excluded from Git). Each observation row contains the camera, elapsed observed time, tracked foot points, zone counts and inspection cues. Offline results live in `experiments/deadline/demo`.

## What came from each codebase

| Capability | Local research repository (`JustATalentedGuy/EverseenHackathon`) | Teammate (`myselfGokul-1111/EverseenML`) | Unified decision |
|---|---|---|---|
| Person model | Evaluated YOLO11n and adapted alternatives on CAVIAR | YOLOv8s, no comparable evaluation supplied | **Use independently selected YOLO11n**; allow an operator to change model config, but avoid claiming unmeasured gains |
| Tracking | Explicit ByteTrack with zone persistence, occlusion-aware partial dwell | Ultralytics `track`, `persist=True` | **Retain research tracking/zone semantics**; never call track IDs unique shoppers |
| Floor geometry | Operator polygons, ambiguity checking, optional calibrated homography and sync guards | Camera-specific named sections | Keep checked geometry plus simple live editor |
| Input | Local files, RTSP/HTTP + latest-frame buffer in replay | Runtime camera add/remove, webcam, RTSP, local file looping | **On-demand camera add/remove, webcam and URL input**, latest-frame processing, finite clips end rather than silently looping and counting repeated tracks |
| Visuals | Offline annotated MP4, setup editor, partial-dwell table | Live MJPEG overlay, recent foot-point heatmap, rolling metrics | **Live MJPEG + heatmap + selected-camera KPI dashboard**, preserve original research replay page |
| Flags | Explicit crowd + slow-movement inspection cues; limitations documented | Relative speeds, dead zones, pass-through and causal bottleneck labels | Add **evidence-gated, role-specific review suggestions**, never unvalidated causal, sales or checkout-wait assertions |

The other repository was inspected at commit `ce392b9` on 8 October 2026. Its sample `store.mp4`, pretrained YOLOv8s weights, and `auto.key`/`auto.crt` files are **not** copied into this project or Git. This is a new integration implementation informed by the two systems, not a wholesale merge of unverified code/heuristics. Confirm third-party licenses and rights before publicly redistributing any team footage or artifacts.

## Data flow

```text
Video source ──► decode thread ──► latest-frame slot (no old-frame FIFO)
                                     │
                      sampled YOLO11n person inference
                                     │
                              ByteTrack (per camera)
                                     │
                    foot point + zone persistence filter
                      /               |                 \
              timestamped JSONL   observed metrics   annotated MJPEG
                                     |                 │
                           rolling occupancy         live dashboard
                           heatmap/inspection cues

Reproducible offline mode: same selected detector/tracker core ► MP4 overlay,
                        events.jsonl, summary.json, guarded floor fusion
```

Configuration remains in `prototype/site.json` (backed up on every edit to `prototype/config_versions/`, Git-ignored). `confidence=0.35`, `imgsz=416`, `sample_hz=5`, `cpu_threads=4` and the `models/yolo11n.pt` baseline remain the *evaluated* defaults. Live mode automatically prefers the existing `models/yolo11n.onnx` *export of the same weights* for CPU **only when the export and onnxruntime are already installed**; otherwise it falls back to the PyTorch baseline. It is optional to override `live_model` explicitly in advanced JSON. Reported 16-image ONNX box parity and CPU speed are limited checks, **not** evidence that the complete live pipeline retains CAVIAR F1. Inference instances are reused per model across camera sessions under a CPU inference lock. If the user changes parameters or replaces the detector, historical F1 numbers are **not** transferable without evaluation. Live counters reflect processed frames and are affected by hardware and throughput. Live camera frames use local receipt timestamps, not synchronized camera acquisition times. Long stream gaps reset the local tracker epoch instead of assuming continuity.

The system is designed for **local hackathon demonstrations**. Camera URLs can contain credentials; keep them private in the local config and never upload this config with real secrets. A source must be an actual playable URL and OpenCV must have the required codecs. Stream reconnect is best effort; sustained camera uptime and real-time 5 Hz multicamera performance have not been established. Four concurrent live camera sessions are allowed in this demo; actual CPU capacity will often be lower. User-selected RTSP streams may require MediaMTX or your camera server, but MediaMTX is optional for local-file demos. For a teammate-source test on this computer, the local file `.cache/teammate-EverseenML/store.mp4` can be added manually; that untracked video does not ship with the project.

## Interpretation / scientific boundaries

- **Occupancy** = current reliable tracked persons whose feet are inside the zone in the processed frame. **The dashboard main occupancy KPI is the selected camera only**, never an unverified sum over different cameras. Stale/non-live values are shown as missing, not zero. Two unsynchronized cameras cannot establish a store-unique number.
- **P90 / mean occupancy** = 90th percentile / mean of observed zone counts in the last 300 seconds. Sampling is inference-driven, not unbiased under severe frame drops.
- **Track entries** = number of camera-local track IDs that have been seen in a zone *during the session*, not distinct people or entry events. Tracks may fragment.
- **Partial visible dwell** = sum of intervals between successive valid observations in the same zone. Unknown time, gaps and nonvisible sections are censored. Mean partial dwell is across observed `(track, zone)` pairs, not completed visit durations.
- **Heatmap** = exponentially decayed foot-point hits; supports visualization only, without metric area or traffic counts.
- **Review recommendation** = the same zone stays at/above its operator-selected observed-count threshold in **at least four contiguous samples over at least five seconds**, without a gap above 3 seconds (or the sample-rate-adjusted tolerance). Checkout/aisle/display/entrance labels determine **what to check**, not what was proven to happen. The recommendation includes the smallest observed count, duration, sample support, and cautious explanation. It is suppressed if stale, warming up or measured throughput is less than half the target. This is not a proven queue, causal bottleneck or purchase observation. Extremely slow or stopped cameras may omit important events.
- **Measurement health** = age since the last processed frame (stale after more than `max(4,3/sample_hz)` seconds or non-live status), recent processing FPS relative to target, model backend, last capture-to-result delay, and counts of truncated tracked boxes. The first six samples or eight seconds are treated as model warm-up. The measured 30-second FPS is a startup-inclusive diagnostic, not an inference-only benchmark.

Known recorded CAVIAR results: validation F1 `0.7365` (baseline), `0.7340` (reviewed), `0.5817` (pseudo); held-out test F1 `0.786`, `0.823`, `0.747` respectively. The baseline was chosen by *validation*, not test, and the small validation tie is inconclusive. See [selection evidence](../experiments/deadline/selection.json) and [complete research documentation](../research/EVERSEEN_FINAL_PROJECT_DOCUMENTATION.md). **No new model was trained** in the integration; current site performance and cross-repository detector performance have not been benchmarked comparably.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_unified_prototype scripts.deadline.validate_and_stress.ContractTests -v
.\.venv\Scripts\python.exe scripts/smoke_unified.py --seconds 10
.\.venv\Scripts\python.exe scripts/check_dashboard.py
```

The unit and API contracts cover source path safety, isolated camera CRUD, rolling stats, recommendation persistence, noncausal language, config validity, origin protection and the original geometry/tracking constraints. The smoke test runs the actual selected live detector on the first camera, validates JSONL/CSV/heatmap responses and session summary persistence. `scripts/acceptance_shopkeeper.py` adds an end-to-end HTTP-video journey with a separately running **local** HTTP service on port 8902; `scripts/check_dashboard.py`, `scripts/deadline/check_ui.py` and `check_final_replay.py` validate the live and offline browser workflows with Chrome. The results from earlier research remain unchanged.
