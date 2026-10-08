# Everseen Hackathon — Dwell-Time & Bottleneck Mapper

A local CCTV analytics prototype with operator-defined floor zones, person detection, camera-local tracking, observed occupancy, partial visible dwell, and optional checked floor geometry.

**Start with [the consolidated project documentation](research/EVERSEEN_FINAL_PROJECT_DOCUMENTATION.md)** for the progression, numerical architecture/training comparisons, and reasons behind the final choices. The [prototype guide](prototype/README.md) contains configuration and experiment commands.

## Quick start (Windows / Python 3.12)

```powershell
git clone https://github.com/JustATalentedGuy/EverseenHackathon.git
Set-Location EverseenHackathon
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup_demo.py --data
.\.venv\Scripts\python.exe -m prototype.server
```

Open **http://127.0.0.1:8791** for the integrated live operations dashboard. Add a local video, RTSP/HTTP(S) stream or webcam index, draw and save floor zones, then start live monitoring. Watch camera-local occupancy, annotated MJPEG, heatmaps, rolling occupancy, and partial visible dwell; export the JSONL observation log. Use **http://127.0.0.1:8791/setup** for the existing offline replay and calibration tools. FFmpeg must be on PATH for H264 browser-compatible *offline* overlays. The footage acquisition script currently uses Windows curl.exe.

See **[Unified prototype guide](prototype/INTEGRATION.md)** for the two-repository comparison, architecture, shopkeeper workflow, guarded recommendations, formulas, configuration, limitations and validation. In live mode, a locally available ONNX export may be selected automatically on CPU for better throughput; the evaluated PyTorch checkpoint remains the fallback. To enable that optional path on a new machine, install `requirements-accelerated.txt` and create/obtain the matching validated ONNX export. Do not treat small-sample ONNX parity as a new accuracy benchmark.

**Retail demo footage catalog:** Open the home dashboard to use **Curated demonstration footage**. Research-sourced clips are prepared and checked by `scripts/prepare_retail_demo.py` and `scripts/test_retail_demo.py`; source credits, reuse conditions, intended demonstrations, and limitations are in [prototype/DEMO_FOOTAGE.md](prototype/DEMO_FOOTAGE.md). Third-party video bytes and local validation runs remain excluded from Git.

The setup helper acquires the official pretrained YOLO11n asset through Ultralytics and official CAVIAR videos/labels. Dataset provenance and hashes are retained in [the manifest](datasets/caviar/manifest.json). The existing evaluated baseline's SHA256 is recorded in [selection.json](experiments/deadline/selection.json).

## What is included

- **prototype/**: integrated local FastAPI live operations dashboard, camera onboarding, on-demand MJPEG monitoring/heatmaps, offline setup/replay, validated zones and tracking, and bounded latest-frame input.
- **scripts/**: reproducible acquisition, architecture tests, detector adaptation and evaluation.
- **research/**: full research history and the single consolidated final document.
- **experiments/**: selected compact numerical evidence and training configuration/results.
- **datasets/**: dataset catalogs, acquisition plan and CAVIAR provenance only.

Downloaded footage/annotations, third-party repository checkouts, model weights, virtual environments, raw prediction caches, logs, configuration history and generated media stay outside Git.

## Findings and scope

Held-out CAVIAR detector F1 was **0.786 pretrained / 0.823 supervised adaptation / 0.747 uncorrected pseudo-label adaptation**. The pretrained model remains the default because it narrowly won validation; the supervised checkpoint remains a candidate. Human-label adaptation uses existing official annotations.

The demo camera views are not verified synchronous; floor fusion is disabled. Metric projection needs distributed fit anchors plus independent checks, and fusion additionally needs verified capture synchronization. Local track IDs do not establish full-store unique visitors or completed checkout waits.

This is an evaluated local replay prototype. Unseen-store accuracy, causal bottleneck identification, sustained RTSP throughput and two-camera 5 Hz real time are not established. Detailed metrics and limitations are in the consolidated documentation.

## Validation and experiments

Install the additional research/test dependencies when needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-research.txt
.\.venv\Scripts\python.exe -m unittest scripts.deadline.validate_and_stress.ContractTests -v
```

Ten contract tests passed in the recorded environment. Browser checks require Google Chrome at the supplied Windows path. Numerical evidence is committed; full experiment reruns require the corresponding external data. CAVIAR acquisition is provided; CITIC, WILDTRACK, PhysicalAI, MOT17 and EPFL data requirements and original download locations are documented in the research and scripts.

A fresh CAVIAR export selects 192 training images; the recorded 198-image pilot retained six earlier samples listed in training_manifest.json. The exact original pilot also requires those images/labels. Dataset data are not redistributed in this repository.

The evaluated environment already has these dependencies installed. The requirements files record direct package versions; they are not a complete dependency lockfile or a claim of fresh-environment installation validation.

## Attribution

CAVIAR footage and labels: **EC Funded CAVIAR project/IST 2001 37540**, [official archive](https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/). Follow the archive's attribution/share-alike terms when acquiring or sharing the data. Other datasets and pretrained model assets retain their respective licenses.
