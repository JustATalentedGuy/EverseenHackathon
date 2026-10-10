# Everseen deadline prototype

Implemented camera-zone setup, local video replay, and the unified live operations dashboard. See [INTEGRATION.md](INTEGRATION.md) for combined repository features, live video usage and the accuracy limitations. Research conclusion: ../research/FINAL_DEADLINE_DATA_AND_DEPLOYMENT_ARCHITECTURE.md.

The dashboard also ships a voice/text assistant over the live status and an hourly WhatsApp briefing, both read-only over the same metrics. See [ASSISTANT.md](ASSISTANT.md); they add no dependency and no server process unless you enable the optional local model.

## Launch

```powershell
Set-Location C:\Coding\ML\Everseen
.\.venv\Scripts\python.exe -m prototype.server
```

Open http://127.0.0.1:8791 for live operations, or http://127.0.0.1:8791/setup for this original setup/replay editor. The supplied environment already contains the dependencies. The loopback server may already be running; do not launch a second copy.

Choose a camera, click the visible floor to draw a polygon, name it, finish and save. Click Analyze 30 seconds. Inspect overlays and partial dwell. Suggestions use prior observations from the same installed source and require acceptance/naming. Save changes and analyze again. Old results become unavailable when setup changes.

## CCTV replay set

Six real retail CCTV clips are configured in `site_cctv.json` (mall atrium, pharmacy,
convenience, liquor aisle, produce, multi-aisle). Run them with
`python3 -m prototype.run --config prototype/site_cctv.json --output experiments/deadline/cctv --seconds 60`,
or serve them with `EVERSEEN_CONFIG=prototype/site_cctv.json python3 -m prototype.server`.
See [CCTV_DATASET.md](CCTV_DATASET.md) for zones, measured results and the limitations
these clips impose.

## Configuration and scope

site.json selects pretrained YOLO11n, confidence 0.35, 416 pixels, four CPU threads, 5 Hz replay and 0.2-second zone persistence. The two CAVIAR camera views are not verified synchronous; sync_verified=false is intentional.

Sources: project-local video paths, RTSP or HTTP video. Actual RTSP hardware, prolonged reconnects and two-camera real-time throughput have not been validated. Live input keeps a single latest frame instead of accumulating a growing inference queue. It uses local decode-receipt timestamps.

Advanced JSON supports additional cameras, zone priorities, semantic_id, zone_owners and checked calibration. A calibration uses >=6 normalized image_points/world_points correspondences in metres: four fit and at least two independent checks. Only points within the fit-anchor hull are projected. Floor fusion additionally requires genuine time synchronization.

Camera-scoped track IDs, observed counts and partial visible dwell are implemented. Full-store unique visitors, completed queue waits, causal bottleneck detection and forecasting are not validated. Slow/crowded regions are inspection cues. Uncalibrated speed uses body heights/s.

An owner camera resolves duplicate counting of a shared semantic region. Otherwise [max counts, sum counts] expresses duplicate uncertainty for observed detections, not a bound on all true people.

## CLI replay

```powershell
.\.venv\Scripts\python.exe -m prototype.run --config prototype/site.json --output experiments/deadline/demo --seconds 30
```

FFmpeg on PATH converts overlays to H264 for browser playback. Model defaults to models/yolo11n.pt. Adapted candidate: experiments/deadline/training/reviewed/weights/best.pt with confidence 0.15. It has stronger current test results but did not beat validation F1.

## Reproduce experiments

Run from the project root. Acquisition can reuse existing clips.

```powershell
.\.venv\Scripts\python.exe scripts/deadline/acquire_caviar.py
.\.venv\Scripts\python.exe scripts/deadline/experiment.py prepare
.\.venv\Scripts\python.exe scripts/deadline/experiment.py infer --tag baseline
.\.venv\Scripts\python.exe scripts/deadline/experiment.py pseudo
.\.venv\Scripts\python.exe scripts/deadline/experiment.py train --labels reviewed --epochs 6
.\.venv\Scripts\python.exe scripts/deadline/execute_pipeline.py
.\.venv\Scripts\python.exe scripts/deadline/tune_zone.py
.\.venv\Scripts\python.exe scripts/deadline/experiment.py evaluate
.\.venv\Scripts\python.exe scripts/deadline/validate_and_stress.py
.\.venv\Scripts\python.exe scripts/deadline/cadence.py
.\.venv\Scripts\python.exe scripts/deadline/export_cpu.py
.\.venv\Scripts\python.exe scripts/deadline/finalize.py
```

The exact existing pilot export contains 198 train/48 val images, including six retained early preparation samples audited in training_manifest.json. Fresh export alone normally selects 192 train/48 val frames; use the manifest/export images to reproduce the exact existing pilot. Do not delete retained data if reproducing its metrics.

With the server running:
```powershell
.\.venv\Scripts\python.exe scripts/deadline/check_ui.py
.\.venv\Scripts\python.exe scripts/deadline/check_final_replay.py
```

Browser checks require Google Chrome at the supplied Windows path and Playwright. Dependencies used: Python 3.12.4, torch 2.2.2 CPU, ultralytics 8.4.172, OpenCV 4.11.0.86, numpy 1.26.4, scipy 1.17.1, fastapi 0.141.1, uvicorn 0.52.0, onnx 1.17.0, onnxruntime 1.19.2, playwright 1.63.0. Complete training parameters are retained in training run args.yaml.

Raw results: experiments/deadline/comparison.json and .csv. selection.json records validation choice and model hash. zone_stress.json is a controlled point perturbation experiment, not an additional real video robustness benchmark.

## Data provenance

CAVIAR: https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/

Attribution: EC Funded CAVIAR project/IST 2001 37540. Retain archive Creative Commons attribution/share-alike terms when using footage/labels. Sources and hashes: datasets/caviar/manifest.json.

The code/evidence ZIP at experiments/deadline/everseen_deadline_prototype.zip excludes footage, detector weights and large raw prediction caches. Download sources using scripts/deadline/acquire_caviar.py, and keep models/yolo11n.pt from the existing project. All generated weights and large caches remain available in the project.
