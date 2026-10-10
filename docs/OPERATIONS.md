# Operating Everseen

## Start and choose a store

On first run, Everseen writes `prototype/site_runtime.json` and `prototype/floor_layout_runtime.json` from compatible demo templates. Both are ignored by Git. The default works after running `python scripts/setup_demo.py --data` to acquire CAVIAR and YOLO weights. Operator changes never rewrite the tracked templates.

You can explicitly choose a source configuration:

```powershell
$env:EVERSEEN_CONFIG = 'prototype/site_cctv.json'   # optional: your own local, rights-cleared CCTV files
$env:EVERSEEN_LAYOUT = 'prototype/floor_layout.json'
.\.venv\Scripts\python.exe -m prototype.server
```

The optional `site_cctv.json` template references six CCTV video filenames. **These clips are not distributed with the final submission**, so bring properly licensed replacements or provide your own footage at those paths. For the original CAVIAR two-camera setup, use `prototype/site_caviar.json` and `prototype/floor_layout_caviar.json`. Never combine unrelated CCTV recordings into a supposedly synchronized customer journey.

## Camera setup

From **Camera library**, enter a name and a playable source (a project-local `.mp4`, directly accessible HTTP video, RTSP stream or webcam index such as `0`). Video-platform webpage links are *not* equivalent to direct stream URLs. You can configure many sources, but the CPU prototype allows four active camera inference sessions. For each source, preview a frame and draw normalized camera polygons using **Manage camera zones** on Overview. Choose a meaningful area role and review threshold.

In **Floor plan**, draw sections, arrange them edge-to-edge and link them to camera zones. A single zone must not stand for two sections. The bottom of the grid defaults to the entrance and the top to the back unless you mark explicit entrance and exit sections. The graph is a schematic representation, not a verified map of real walkable corridors.

### What managers should trust

Live counts are *detected people in a selected camera view*, never all unique shoppers. The section map uses the **maximum** across fresh mapped feeds rather than summing overlapping views. “Dwell” represents only observed tracked intervals, and red heat tiles indicate relatively high **camera-image-space exposure** under a fixed numerical scale. When frames are dropped, the UI reports coverage and observations may be understated. An unknown or stale section is not a confirmed empty area.

No model identifies whether someone is buying or browsing; check the video before changing checkout staffing or display locations. A redistribution suggestion requires an actual sustained review cue and a separate, adequately measured lower-activity section.

## Store assistant and WhatsApp

**Ask Everseen** answers from currently ingested measured values, with retrieval over the project documentation. The default is fully local and deterministic. It can optionally use an external or local language model **only to rephrase an already composed answer**; only enable a cloud provider when it is appropriate for store-data privacy. Browser speech input/output depends on browser support; install `requirements-assistant.txt` for optional transcription support. Optional environment settings include `ASSISTANT_BACKEND=none|auto|ollama|llamacpp|cloud` and `ASSISTANT_CLOUD_API_KEY` (never commit keys).

**Manager briefings** build a ready-to-send summary, maintain a local recipient list, and produce an official `wa.me` link. WhatsApp cannot confirm delivery via these links; managers manually send the message. The app never silently pushes WhatsApp messages to an outside number. Recipient phone numbers and delivery history stay in ignored local files.

## Data provenance and licensing

- **CAVIAR**: [official University of Edinburgh / CAVIAR archive](https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA1/). Attribution: *EC Funded CAVIAR project / IST 2001 37540*. Respect the archive's applicable CC BY-SA terms. Acquired by `scripts/setup_demo.py --data`.
- **CUHK Mall / MERL Shopping**: optional research-only footage; not commercially redistributable. See dataset source pages referenced in `prototype/demo_catalog.json` and use only where permissions allow.
- **Operator CCTV**: people and premises are sensitive. Only ingest video you are authorized to process; avoid including customer footage in public submissions. The team's six optional local CCTV examples have unverified reuse terms and are excluded from this Git tree.
- **Detector**: YOLO11n weights are acquired through the official Ultralytics workflow and retain their own applicable license.

The selected baseline's experimental metrics are recorded in `experiments/deadline/selection.json`; see `docs/TECHNICAL.md` for details. All clip buffers, saved events, screenshots, logs and downloaded weights remain outside tracked source files.
