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

Open **http://127.0.0.1:8791**. Select a camera, draw and name floor polygons, save, analyze, and inspect the overlays and partial-dwell table. Activity suggestions require user confirmation. FFmpeg must be on PATH for H264 browser-compatible overlays. The footage acquisition script currently uses Windows curl.exe.

The setup helper acquires the official pretrained YOLO11n asset through Ultralytics and official CAVIAR videos/labels. Dataset provenance and hashes are retained in [the manifest](datasets/caviar/manifest.json). The existing evaluated baseline's SHA256 is recorded in [selection.json](experiments/deadline/selection.json).

## What is included

- **prototype/**: local FastAPI setup/dashboard, polygon validation, detection/tracking engine and latest-frame live buffer.
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
