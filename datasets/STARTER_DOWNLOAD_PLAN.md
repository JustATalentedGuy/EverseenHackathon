# Starter Dataset Download Plan

Goal: assemble a **small, complementary test pack comfortably below 5 GB** that can exercise the first retail Dwell-Time & Bottleneck Mapper prototype without pulling any large benchmark archives.

No large dataset should be downloaded as part of this starter step.

## Recommended immediate pack

| Priority | Dataset / subset | Approx. download | Why it belongs in the starter pack | Requirements exercised | Access |
|---:|---|---:|---|---|---|
| 1 | **CAVIAR Lisbon shopping-centre: selected synchronized clip pairs + XML labels** | Small; individual clips are commonly ~2-21 MB each. Budget **<= 300 MB** for a representative subset. | Only surveyed dataset combining actual retail CCTV, 2D person annotations, simple behavioural/dwell scenarios, paired views and world-reference points for homography. | R1, R2, R3, R4 | Public; CC BY-SA |
| 2 | **ATC one-day pedestrian trajectory sample** | **~201 MB** | Gives clean trajectory ground truth in a real shopping centre, with metric coordinates and occupancy/floor map. Lets the analytics layer be tested independently of vision errors. | R3, R4 | Public for research |
| 3 | **EPFL-RLC full ZIP** | **~1.1 GB** | Provides three synchronized real indoor cameras, Tsai calibration, a shared 55x45 floor grid and projection data. Ideal for validating camera-to-floor mapping and multi-view occupancy. | R1, partial R2, R3, partial R4 | Public page; reuse terms should be verified |
| 4 | **CITIC-MTMC metadata first** | Budget **<= 100 MB** until archive sizes are checked | Strongest compact real indoor topology benchmark: floorplan, room/door graph, per-camera calibration, synchronization and world-position GT. Start with repository/metadata; add video later only if it fits. | R1-R4 metadata/GT; especially MTMC handoff | CC BY-NC-SA 4.0 |
| 5 | **NVIDIA PhysicalAI Smart Spaces 2025 metadata / one-scene manifest** | Budget **<= 250 MB** initially; no bulk videos | Best geometry metadata: synchronized cameras, homographies, intrinsic/extrinsic matrices, top-down maps and global 3D GT. 2025 explicitly includes retail/office/hospital/warehouse layouts. | R1-R4 | CC-BY-4.0; primarily synthetic |
| 6 | **MMPTRACK Retail metadata/access setup** | Budget **<= 50 MB** until retail-subset byte size is confirmed | Strongest real/staged retail MTMC dataset: six synchronized cameras, consistent IDs, calibration and world footpoints. Register/accept terms and inspect metadata first. | R1-R4 | Research-only agreement |
| 7 | **MALL-VLM devkit + annotations only** | Budget **<= 100 MB** initially; no bulk images/crops | Real operating-mall cross-camera appearance data with 22 cameras and cross-camera IDs. Use labels/devkit first; image sampling only after provenance/privacy and size checks. | R1, partial R2/R4; real-mall ReID | Devkit says CC-BY-4.0; provenance/privacy review needed |

### Optional controlled handoff pack

| Dataset / subset | Approx. download | When to add |
|---|---:|---|
| **MTA 4-minute short subset** | **~1.7 GB zipped** | Add only if a known-size non-overlap synthetic benchmark is needed before CITIC/MMPTRACK media sizes are confirmed. |

## Size budget

Using the hard caps above:

- CAVIAR selected subset: **<= 0.30 GB**
- ATC one-day sample: **~0.20 GB**
- EPFL-RLC: **~1.10 GB**
- CITIC metadata-first budget: **<= 0.10 GB**
- NVIDIA metadata/one-scene-manifest budget: **<= 0.25 GB**
- MMPTRACK metadata/access budget: **<= 0.05 GB**
- MALL-VLM devkit/annotation budget: **<= 0.10 GB**

**Immediate capped total: <= ~2.10 GB.**

This leaves roughly **2.9 GB of headroom** under the 5 GB target.

If the optional MTA 4-minute subset is later added, the capped plan becomes **<= ~3.80 GB**, still leaving about **1.2 GB** of safety margin.

The budgets for CITIC, NVIDIA, MMPTRACK and MALL-VLM are **download stop limits**, not claims about their complete dataset sizes. Their full releases should not be pulled until component-level sizes are known.

## Download order

### 1. CAVIAR first

Download only a **small set of Lisbon shopping-centre paired sequences**, not every CAVIAR file.

Choose clips that together include:

- ordinary walking through the corridor;
- stopping or waiting;
- browsing/window shopping;
- entering/exiting a shop;
- at least one more crowded/group interaction.

For every selected scenario, keep:

- both synchronized camera views when available;
- XML/CVML annotations;
- world/image reference-point metadata needed to compute the ground homography.

This is the fastest dataset for verifying the first complete path:

**video -> detect person -> stable local ID -> feet point -> floor coordinate -> dwell/zone event**

**Storage cap:** stop the CAVIAR starter selection at about **300 MB**.

### 2. ATC one-day sample

Download only the advertised **~201 MB one-day trajectory sample** plus its occupancy-grid/floor-plan metadata.

Do not download:

- the ~39.3 GB full tracking archive;
- the ~14.6 GB raw 15-minute range-sensor sample.

Use ATC to build and unit-check:

- coordinate-to-zone assignment;
- dwell-time aggregation;
- occupancy heatmaps;
- flow direction;
- bottleneck/density metrics;
- trajectory visualization.

Because ATC already contains person IDs and metric positions, any error here is in the analytics code rather than the detector/tracker.

### 3. EPFL-RLC

Download the **~1.1 GB ZIP**.

Use it to validate:

- loading Tsai calibration;
- projecting detections into a common floor grid;
- checking consistency across three synchronized views;
- generating shared occupancy maps from oblique cameras.

It does not provide full person-identity trajectories, so use CAVIAR/HDA/MTA for identity questions.

### 4. CITIC-MTMC: metadata before video

Start from the GitHub repository and Zenodo record. Pull only the small structural assets first:

- SVG/PDF floorplan;
- room/door topology;
- per-camera positions and calibration;
- synchronization/timestamp data;
- path waypoints and ground-truth world positions;
- lightweight annotation/configuration files.

**Initial storage cap: 100 MB.** If the repository or Zenodo interface exposes a large video archive, inspect its file sizes before downloading any video.

CITIC should become the preferred real-data benchmark for:

- room-to-room / section-to-section handoff;
- non-overlap transition-time gating;
- feasible path constraints from doors/corridors;
- checking global trajectories against world-position ground truth.

### 5. NVIDIA Smart Spaces 2025: metadata and one-scene planning first

Use the Hugging Face dataset card/file listing before transferring media.

Start with:

- dataset metadata/schema;
- camera intrinsics/extrinsics;
- homographies and projection matrices;
- camera pose/direction;
- top-down maps;
- world-coordinate annotation examples;
- one candidate retail/office scene manifest.

Prefer **2025** for the first NVIDIA experiment because the documented scene families explicitly include retail, office, hospital and warehouse layouts.

Use **2024** only when the larger 90-scene / 953-camera scale is needed, and use **2026** when the latest schema or the two real warehouse test captures are specifically useful.

**Initial storage cap: 250 MB.** Do not bulk-download any yearly release. The survey records 212 camera-hours for 2024, ~42 camera-hours for 2025 and ~28.7 camera-hours for 2026, so full releases are far beyond the purpose of this starter pack even though byte sizes were not recorded.

### 6. MMPTRACK Retail: register and inspect before media

MMPTRACK Retail should become the primary real/staged end-to-end MTMC benchmark once its component sizes are known.

First:

- accept the research-use terms;
- inspect the retail subset file list;
- obtain calibration/metadata separately if the release permits;
- confirm whether individual retail sequences can be downloaded independently.

The retail environment has six synchronized RGB/depth cameras, 172 video minutes, consistent cross-camera IDs, intrinsic/extrinsic calibration and common-world person footpoints.

**Initial storage cap: 50 MB for metadata/access preparation.** Do not download the full retail media until its byte size has been checked against the remaining disk budget.

### 7. MALL-VLM: devkit/annotations first

Use MALL-VLM for a realistic shopping-mall appearance and ReID stress test, not for floor-coordinate geometry.

First obtain only:

- devkit/code;
- annotation schema;
- camera/zone/timestamp metadata;
- identity lists/statistics.

The current survey records 22 cameras, 3 zones, 9,209 IDs and 1,450 IDs appearing in at least two cameras, but no calibration, homography, floorplan or world coordinates.

**Initial storage cap: 100 MB.** Do not pull the full-frame/crop image release until its size and subject-provenance/privacy terms have been reviewed.

### 8. Optional: request the MTA short subset

Request access to **only the 4-minute short subset (~1.7 GB zipped)** first.

Do not request/download the 41 GB main-video archive or the 28.6 GB compressed full-coordinate archive for the starter phase.

Use the short subset after the single-camera pipeline is stable to test:

- local track termination in camera A;
- appearance embedding without face recognition;
- candidate filtering by camera topology and travel time;
- matching the person when they reappear in camera B;
- both overlapping and non-overlapping transitions.

The MTA access conditions in the surveyed repository require research/educational use, prohibit commercial use, and require a legal GTA V copy. With CITIC and MMPTRACK now in the benchmark plan, MTA is a useful controlled synthetic fallback rather than the first MTMC dependency.

## Keep out of the starter pack

| Dataset | Reason to defer |
|---|---|
| **MOT17 full archive (~5.5 GB)** | Exceeds the entire starter budget by itself. Later obtain only MOT17-11/12 if sequence-level download is available. |
| **MOT20 full archive (~5.0 GB)** | Dense-crowd stress testing is valuable, but the full archive consumes the whole budget. |
| **ATC full tracking/raw sensor releases** | Tens of GB; the 201 MB day sample is enough to start analytics. |
| **MTA full release** | 41 GB video and much larger full-coordinate data are unnecessary for the first cross-camera experiment. |
| **MOTSynth** | Very large synthetic training corpus; useful later for scale/pretraining, not initial feasibility. |
| **NVIDIA Smart Spaces full 2024/2025/2026 yearly releases** | Hundreds of cameras and tens to hundreds of camera-hours; use metadata and one selected scene only after checking component sizes. |
| **MMPTRACK full media / full 23-camera collection** | Strong benchmark, but byte size is not recorded in the survey. Start with Retail metadata and then one retail sequence if storage allows. |
| **CITIC-MTMC full video before size check** | Keep the compact floorplan/topology/calibration/GT metadata immediately; inspect Zenodo file sizes before adding video. |
| **MALL-VLM full frames/crops before review** | Real-mall appearance data is valuable, but current survey lacks full byte size and detailed provenance/privacy documentation. Start with devkit/labels. |
| **HDA** | High-priority real indoor benchmark, but byte size and access terms should be confirmed before adding it to the <5 GB pack. |
| **WILDTRACK** | Excellent geometry benchmark, but exact archive size and license terms were not recorded in the survey. Add after checking both. |
| **JRDB** | Account-gated and broader than the immediate fixed-CCTV retail problem. |

## Optional small additions after checking size

These are potentially useful, but their exact archive sizes were not verified in the completed survey. Add them only if their actual downloads keep the running total below **4 GB**, preserving at least ~1 GB of safety margin.

- **CUHK Mall** — retail density/perspective test; no track IDs.
- **EPFL indoor laboratory subset** — very useful calibrated four-camera sanity test.
- **Edinburgh Informatics Forum trajectories** — long-horizon dwell/flow analytics; original imagery is mostly unavailable.
- **MultiviewX** — synthetic calibrated multi-view backup.
- **Market-1501** — appearance-only cross-camera re-identification benchmark.
- **One MMPTRACK Retail sequence** — add once its individual sequence size is known and fits the remaining budget.
- **One NVIDIA Smart Spaces 2025 retail/office scene** — add only after inspecting per-scene files and preserving the safety margin.
- **CITIC-MTMC video** — highest-value real non-overlap addition if its archive is modest.

## Suggested local layout

    datasets/
    ├── dataset_catalog.csv
    ├── STARTER_DOWNLOAD_PLAN.md
    ├── caviar/
    │   ├── video/
    │   ├── annotations/
    │   └── calibration/
    ├── atc/
    │   ├── trajectories/
    │   └── map/
    ├── epfl_rlc/
    │   ├── video/
    │   ├── calibration/
    │   └── ground_grid/
    ├── citic_mtmc/
    │   ├── metadata/
    │   ├── floorplan/
    │   └── calibration/
    ├── nvidia_smartspaces/
    │   └── metadata/
    ├── mmptrack_retail/
    │   └── metadata/
    ├── mall_vlm/
    │   └── annotations/
    └── mta_short/
        ├── video/
        └── annotations/

## First experiments once the pack exists

1. **CAVIAR:** run person detection and a single-camera tracker; measure ID continuity and inspect failures at occlusion.
2. **CAVIAR:** compute a ground homography from the supplied reference points and project each track's bottom-centre/feet point.
3. **ATC:** implement zone assignment, dwell-time, heatmap, flow and bottleneck calculations using perfect trajectories.
4. **EPFL-RLC:** verify that detections from different cameras map coherently into the same ground grid.
5. **CITIC-MTMC metadata:** implement camera/room topology, transition-time gates and ground-truth world-path evaluation before touching the videos.
6. **NVIDIA Smart Spaces metadata:** make the calibration loader handle intrinsic/extrinsic matrices, homography, camera pose, top-down map and shared 3D locations.
7. **MMPTRACK Retail:** once one small retail sequence fits the disk budget, run the first real/staged end-to-end synchronized MTMC test.
8. **MALL-VLM:** use a small approved image/crop subset to stress-test body appearance embeddings on real mall shoppers.
9. **MTA short, optional:** retain as a known-size synthetic non-overlap benchmark if CITIC/MMPTRACK video cannot yet be obtained.

This gives a small but balanced feasibility suite: **real retail appearance, exact retail trajectories, calibrated real multi-view geometry, topology-aware handoff metadata, and scalable MTMC schemas**, while keeping the immediate capped footprint around **2.1 GB or less**. Adding the optional MTA short subset still keeps the plan around **3.8 GB or less**.
