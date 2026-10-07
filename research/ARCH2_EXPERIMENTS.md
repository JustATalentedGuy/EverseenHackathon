# Architecture 2 Experiments — Geometry-First Shared-Floor Fusion

Date: 2026-10-04

Root: `C:\Coding\ML\Everseen`

## 1. Objective

Architecture 2 uses calibrated shared-floor geometry as the primary cross-camera signal:

```text
per-camera observations
-> foot/contact point
-> image-to-shared-floor projection
-> overlap agreement / duplicate fusion
-> geometry-assisted trajectory stitching
-> section mapping
-> dwell / occupancy / flow diagnostics
```

The experiments below test whether the geometry layer is accurate enough to be useful, how strongly it helps association, and how calibration/timestamp/detection errors degrade it.

No theoretical accuracy guarantee is claimed. Every headline number below was read back from the generated JSON/CSV outputs.

---

## 2. Dataset scope and provenance

### 2.1 WILDTRACK — primary quantitative experiment

**Experiment class:** real WILDTRACK calibration + real WILDTRACK annotations/IDs/boxes; noise and fragmentation are simulated perturbations of those real annotations.

The official EPFL WILDTRACK ZIP is 6,807,496,358 bytes. It was **not** downloaded in full. The official server supports byte ranges, so `scripts/architecture2/acquire_wildtrack_subset.py` reads the ZIP central directory remotely and extracts only:

- 7 `intrinsic_zero` XML files,
- 7 extrinsic XML files,
- 100 position-annotation JSON files,
- no RGB images,
- no video.

The acquired subset is only about 2.81 MB uncompressed and is recorded in:

- `samples/wildtrack_subset/subset_manifest.json`

The main run used the first **50 annotated frames** (24.5 s at the released 2 FPS annotation cadence) to keep repeated Monte Carlo noise sweeps tractable. These 50 frames contain **4,443 visible per-camera person observations** used in the clean projection experiment.

WILDTRACK world-grid convention used by the scripts:

- grid: 480 × 1440,
- spacing: 2.5 cm,
- origin: (-300, -900) cm,
- section test: 4 × 4 equal-area grid over the calibrated ground extent.

The origin was numerically checked against real bbox-bottom back-projection. Using `y=-900 cm` gives per-camera median errors around 7–14 cm; the incorrect `y=-90 cm` interpretation gives approximately 8 m errors.

### 2.2 NVIDIA PhysicalAI Smart Spaces 2026 Warehouse_000 — metadata/GT feasibility check

**Experiment class:** released synthetic-scene metadata + released synthetic-scene GT; metadata validation only.

Files already present/reused:

- `samples/physicalai/Warehouse_000/calibration.json` — 81,410 bytes,
- `samples/physicalai/Warehouse_000/map.png` — 515,978 bytes,
- `samples/physicalai/Warehouse_000/ground_truth.json` — 281,636,586 bytes.

No duplicate PhysicalAI download was made by this worker.

The first 100 GT frames were inspected quantitatively. All **25 cameras** provide:

- intrinsics,
- extrinsics,
- camera matrix,
- homography,
- camera coordinates,
- scale factor,
- translation-to-global-coordinate metadata.

The sampled 100 frames contain:

- 5,489 Person frame-records,
- 57 unique person IDs,
- mean 2.60 visible cameras per person-frame,
- median 2 cameras,
- maximum 6 cameras,
- **78.89%** of person-frame records visible in at least two cameras.

This confirms Warehouse_000 is highly suitable for overlap experiments once the coordinate-frame transform is resolved.

### 2.3 MMPTRACK Retail blocker

MMPTRACK Retail remains the preferred real retail end-to-end dataset, but no MMPTRACK files are available locally in this run. The official dataset uses controlled research access / agreement. I did not bypass that access or substitute an unverified mirror.

Therefore **no MMPTRACK metric is reported here**.

### 2.4 EPFL / MultiviewX status

EPFL Laboratory videos and calibration are local, and MultiviewX/MVDet code is present. They were kept as secondary checks only because WILDTRACK provides the stronger real calibrated overlap GT required for the same geometry questions.

Existing EPFL homography checks are useful for parsing/numerical sanity, but there is insufficient local dense identity/world GT to make them stronger evidence than the WILDTRACK experiment. No MultiviewX dataset was downloaded.

---

## 3. Reproducible scripts and outputs

Scripts:

- `scripts/architecture2/acquire_wildtrack_subset.py`
- `scripts/architecture2/run_wildtrack_gt.py`
- `scripts/architecture2/check_physicalai_scene.py`

Outputs:

- `experiments/architecture2/wildtrack_summary.json`
- `experiments/architecture2/wildtrack_noise_sweep.csv`
- `experiments/architecture2/wildtrack_projection_by_camera.csv`
- `experiments/architecture2/wildtrack_fusion_threshold_sweep.csv`
- `experiments/architecture2/physicalai_scene_check.json`
- `experiments/architecture2/README.md`

Reproduction from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\architecture2\acquire_wildtrack_subset.py --annotation-count 100
.\.venv\Scripts\python.exe scripts\architecture2\run_wildtrack_gt.py --frames 50 --seeds 3
.\.venv\Scripts\python.exe scripts\architecture2\check_physicalai_scene.py --frames 100
```

The WILDTRACK acquisition command is idempotent at the file level; it validates ZIP member CRCs after selective extraction.

---

## 4. Experiment definitions

### 4.1 Image-to-world projection

For every visible WILDTRACK bbox:

1. use bbox bottom-center as the approximate floor contact point;
2. build camera ground homography from official intrinsics/extrinsics;
3. invert world->image ground homography;
4. project bottom-center to shared ground coordinates;
5. compare to the annotation `positionID` world coordinate.

This tests the complete **annotation box -> floor coordinate** path. Error includes bottom-center footpoint approximation; it is not calibration residual alone.

### 4.2 Homography uncertainty perturbation

The script inverse-projects nine image anchor points through the nominal homography, perturbs their image locations with Gaussian noise, then refits a homography.

Tested calibration-point noise:

- 0.5 px,
- 1 px,
- 2 px,
- 4 px.

This is a **simulation using real camera calibration**, intended to measure sensitivity to imperfect manual correspondences / calibration drift.

### 4.3 Detection-position noise

BBox bottom-center is perturbed by Gaussian pixel noise:

- 2 px,
- 5 px,
- 10 px.

This approximates detector / footpoint localization error.

Separate random per-camera observation misses are tested at:

- 5%,
- 10%,
- 20%.

### 4.4 Timestamp noise

Each camera receives one fixed randomized frame offset. Because the WILDTRACK annotations are 2 FPS, the perturbation is quantized to 0.5 s annotation steps.

Tested nominal timestamp sigmas:

- 0.5 s,
- 1.0 s.

The experiment asks what happens when the system incorrectly treats temporally shifted cameras as simultaneous.

### 4.5 Overlap fusion / deduplication

Within each nominal synchronized instant:

- observations from different cameras are linked by projected world distance,
- a fused cluster cannot contain two simultaneous detections from the same camera,
- default fusion threshold = 75 cm.

GT person ID is used **only for evaluation**, not to create fusion clusters.

Measured:

- pair precision/recall/F1,
- wrong-merge cluster rate,
- duplicate excess before/after fusion,
- fused position error.

### 4.6 Overlap-agreement diagnostic

For every same-person cross-camera pair, measure distance between the two independently projected floor estimates.

This is directly usable as a calibration/data-health signal in the final architecture.

### 4.7 Geometry-assisted tracklet stitching

This is explicitly a **GT-derived simulated fragmentation experiment**:

- cross-camera projected observations are first aggregated per known person for evaluation,
- continuous trajectories are cut into 4-frame fragments,
- candidate next fragments are restricted to 1–3 frame gaps,
- compare:
  - time-only first candidate,
  - nearest world endpoint,
  - constant-velocity world prediction.

GT identity is used to score whether the chosen fragment belongs to the same person. This is not a claim about a detector-generated tracker; it isolates the information value of geometry.

### 4.8 Section accuracy

The WILDTRACK ground extent is divided into a 4 × 4 grid. Projected and GT positions are assigned to sections and compared.

The sections are synthetic analysis zones, not semantic retail departments.

### 4.9 Flow-conservation residual

A closed cohort is formed from person IDs present throughout the first 20 clean GT frames. Using estimated/fused section observations, for each section and time step:

```text
residual = occupancy(t) - occupancy(t-1) - inflow + outflow
```

Reported normalized residual divides total absolute residual by observed person occupancy.

This is a **diagnostic simulation**, not an independent identity metric. With redundant cameras, moderate per-camera misses can be hidden because another camera still observes the person.

---

## 5. WILDTRACK clean projection results

### 5.1 Overall image/world projection

| Metric | Measured value |
|---|---:|
| Visible per-camera observations | 4,443 |
| Median floor-position error | **11.15 cm** |
| P90 floor-position error | **21.87 cm** |
| Mean floor-position error | **12.14 cm** |
| 4×4 section accuracy | **97.43%** |

This is strong evidence that, with proper calibration, bbox-bottom projection is already accurate enough for metre-scale retail sections, occupancy maps and coarse path metrics on this benchmark.

It is not evidence for centimetre-accurate live retail positioning because the bottom-center point itself is an approximation and WILDTRACK differs from store cameras.

### 5.2 Projection error by camera

| Camera | N | Median error | P90 error |
|---|---:|---:|---:|
| CVLab1 | 1,003 | 14.06 cm | 19.49 cm |
| CVLab2 | 948 | 8.23 cm | 17.42 cm |
| CVLab3 | 670 | 7.84 cm | 17.21 cm |
| CVLab4 | 239 | 6.84 cm | 17.44 cm |
| IDIAP1 | 206 | 7.18 cm | 9.95 cm |
| IDIAP2 | 1,134 | 14.50 cm | 26.85 cm |
| IDIAP3 | 243 | 13.53 cm | 28.55 cm |

The camera-to-camera spread matters: the final system should maintain per-camera projection uncertainty instead of assuming one global error radius.

---

## 6. Overlap agreement and fusion

Clean same-person cross-camera overlap diagnostics:

| Diagnostic | Measured value |
|---|---:|
| Same-person camera pairs | 6,900 |
| Median projected disagreement | **12.41 cm** |
| P90 disagreement | **21.55 cm** |
| Pairs within 50 cm | **100%** |
| Pairs within 100 cm | **100%** |

At the default 75 cm fusion threshold:

| Fusion metric | Measured value |
|---|---:|
| Pair precision | **99.80%** |
| Pair recall | **99.80%** |
| Pair F1 | **99.80%** |
| Pair TP / FP / FN | 6,886 / 14 / 14 |
| Wrong-merge cluster rate | **0.344%** |
| Duplicate excess before fusion | 3,280 |
| Duplicate excess after fusion | 4 |
| Duplicate excess removed | **99.88%** |
| Fused median position error | **9.72 cm** |
| Fused P90 position error | **17.11 cm** |

The fused median error is lower than the single-view 11.15 cm median, consistent with multi-camera redundancy improving floor localization.

### 6.1 Fusion threshold sensitivity

| Threshold | Precision | Recall | F1 | Duplicate excess removed |
|---:|---:|---:|---:|---:|
| 25 cm | 99.81% | 99.48% | 99.64% | 99.57% |
| 50 cm | 99.80% | 99.80% | 99.80% | 99.88% |
| 75 cm | 99.80% | 99.80% | 99.80% | 99.88% |
| 100 cm | 99.80% | 99.80% | 99.80% | 99.88% |
| 150 cm | 99.80% | 99.80% | 99.80% | 99.88% |

On this clean subset, 50–150 cm yields the same clustering result. That plateau should not be assumed for denser retail queues; it only describes this sample.

---

## 7. Geometry-assisted stitching

Controlled 4-frame-fragment experiment, 196 eligible fragment links:

| Stitch rule | Top-1 accuracy |
|---|---:|
| Time-only candidate | **18.88%** |
| Nearest world endpoint | **95.41%** |
| Constant-velocity world prediction | **97.96%** |

This is one of the clearest Architecture 2 results: once tracks have meaningful shared-floor coordinates, geometry can repair simulated fragmentation far better than temporal ordering alone.

It does **not** prove that 97.96% will be obtained on detector-generated fragments. The fragmentation is controlled/GT-derived to isolate geometry.

---

## 8. Noise/degradation results

The table reports means over **3 deterministic seeds** for each perturbation scenario.

| Scenario | Projection median | Section acc. | Overlap disagreement median | Fusion F1 | Wrong-merge cluster rate | Duplicate removed | Geometry stitch acc. | Flow residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 11.15 cm | 97.43% | 12.41 cm | 99.80% | 0.34% | 99.88% | 95.41% | 0.0000 |
| Detection 2 px | 12.51 cm | 96.06% | 18.84 cm | 97.19% | 3.63% | 96.57% | 94.56% | 0.0000 |
| Detection 5 px | 20.36 cm | 93.32% | 37.36 cm | 82.65% | 16.92% | 79.96% | 90.48% | 0.0000 |
| Detection 10 px | 36.65 cm | 88.60% | 71.59 cm | 61.88% | 32.41% | 58.79% | 81.80% | 0.0000 |
| Calibration 0.5 px | 12.42 cm | 97.10% | 15.49 cm | 98.99% | 1.86% | 99.14% | 95.41% | 0.0000 |
| Calibration 1 px | 13.47 cm | 96.68% | 19.01 cm | 96.68% | 5.34% | 96.71% | 95.41% | 0.0000 |
| Calibration 2 px | 16.83 cm | 95.52% | 27.00 cm | 88.56% | 12.22% | 87.71% | 95.24% | 0.0000 |
| Calibration 4 px | 24.34 cm | 92.45% | 46.17 cm | 75.97% | 22.16% | 75.07% | 95.07% | 0.0000 |
| Timestamp 0.5 s | 11.18 cm | 97.43% | 25.23 cm | 84.23% | 7.53% | 85.43% | 94.03% | 0.0000 |
| Timestamp 1.0 s | 11.17 cm | 97.43% | 57.15 cm | 70.79% | 21.00% | 69.86% | 94.07% | 0.0000 |
| Miss 5% | 11.15 cm | 97.43% | 12.43 cm | 99.81% | 0.38% | 99.87% | 95.40% | 0.0000 |
| Miss 10% | 11.15 cm | 97.46% | 12.43 cm | 99.76% | 0.50% | 99.81% | 95.38% | 0.0000 |
| Miss 20% | 11.16 cm | 97.46% | 12.45 cm | 99.66% | 0.74% | 99.80% | 94.99% | 0.0000 |
| Combined mild | 14.35 cm | 95.68% | 41.08 cm | 81.63% | 12.61% | 80.68% | 93.34% | 0.0000 |
| Combined severe | 22.83 cm | 92.53% | 78.80 cm | 57.91% | 31.20% | 55.97% | 85.39% | **0.01595** |

### 8.1 Main degradation finding

Architecture 2 is much more sensitive to **calibration and synchronization error** than to moderate independent observation misses when several overlapping cameras see the same person.

Examples:

- 1 px calibration perturbation lowers fusion F1 from 99.80% to 96.68%.
- 4 px calibration perturbation lowers fusion F1 to 75.97%.
- 0.5 s timestamp error lowers fusion F1 to 84.23% even though single-view projection remains near clean.
- 1.0 s timestamp error lowers fusion F1 to 70.79% and raises median overlap disagreement to 57.15 cm.
- 20% independent per-camera misses still leave fusion F1 at 99.66% because overlapping views often provide redundant observations.

This supports making **overlap agreement a live health diagnostic**. A sudden rise in cross-camera disagreement can indicate calibration drift, clock error, or footpoint/detection degradation.

---

## 9. Flow-conservation residual

Clean closed-cohort result:

- 20-frame window,
- 11 person IDs continuously present in GT,
- normalized absolute flow-conservation residual = **0.0**.

Per-camera miss rates up to 20% also produced 0 in this particular setup because redundant cameras usually retained at least one observation for each person. The combined severe scenario produced a non-zero normalized residual of **0.01595**.

Interpretation:

- the residual is useful as a **data-health alarm**, not a guarantee of tracking correctness;
- redundancy can mask individual camera misses, which is desirable for the final analytics layer;
- systematic timing/calibration/fusion failure is more likely to break conservation than isolated missed views;
- a zero residual alone does not prove correct IDs, because compensating errors are possible.

---

## 10. NVIDIA PhysicalAI metadata findings and blocker

`experiments/architecture2/physicalai_scene_check.json` confirms:

- 25 calibrated cameras,
- all required calibration fields present,
- homography condition numbers: 7,652 to 151,587, median 40,636,
- numeric homography forward/inverse round-trip error <= 1.25e-11 px,
- first 100 GT frames: 57 unique persons and 14,285 visible person boxes,
- 78.89% of person-frame records are multi-camera visible.

However, a direct inverse of the stored homography does **not** land in the same numeric coordinate frame as the GT `3d location`. Directly comparing them gives median numeric distance 76.29 and P90 198.20; these values are intentionally **not labeled metres or projection errors**.

This means the metadata are internally invertible but require the authoritative map/global-coordinate transform convention (`scaleFactor`, `translationToGlobalCoordinates`, and scene coordinate definition) before a truthful PhysicalAI image-to-world accuracy number can be reported.

Blocker recorded in JSON:

> Need authoritative PhysicalAI coordinate-transform convention linking homography/map coordinates to the ground-truth `3d location` frame before quantitative image-to-world accuracy is claimed.

No made-up transform was fitted merely to make the metric look good.

---

## 11. What Architecture 2 is empirically supported by this run

### Supported strongly on WILDTRACK conditions

1. **Image/world mapping is practically useful.**
   - 11.15 cm median / 21.87 cm P90 from bbox bottom-center on clean real annotations.

2. **Overlap cameras are useful redundancy rather than duplicate counts.**
   - 99.88% of duplicate excess removed at 75 cm threshold.
   - fused median position error improved to 9.72 cm.

3. **Geometry is a powerful repair signal for fragmented trajectories.**
   - 95.41% nearest-world and 97.96% constant-velocity stitching in the controlled fragmentation test.

4. **Section analytics degrade gradually before exact fusion collapses.**
   - at 4 px calibration perturbation, section accuracy is still 92.45% while fusion F1 is 75.97%.
   - this supports keeping section/occupancy analytics available in a degraded-confidence mode.

5. **Clock synchronization is a first-class dependency.**
   - 0.5–1.0 s mismatch damages overlap fusion without significantly changing the per-view projection metric.

6. **Overlap agreement can be a self-diagnostic.**
   - clean median 12.41 cm,
   - 4 px calibration perturbation 46.17 cm,
   - 1 s timestamp perturbation 57.15 cm,
   - combined severe 78.80 cm.

### Not proven by this run

- performance in a live supermarket,
- MMPTRACK Retail performance,
- blind-gap ReID performance,
- performance from detector-generated WILDTRACK boxes instead of GT boxes,
- PhysicalAI metric world projection until its coordinate convention is resolved,
- non-planar floors/stairs/escalators,
- calibration recovery when no metadata are supplied.

---

## 12. Practical Architecture 2 recommendation

When shared geometry exists, Architecture 2 remains the strongest practical target:

```text
camera-local detection/MOT
-> quality-aware footpoint
-> image-to-world projection with per-camera uncertainty
-> overlap agreement monitor
-> geometry-dominant duplicate fusion
-> geometry-assisted tracklet repair
-> conservative global trajectory
-> section mapping
-> confidence-aware dwell / occupancy / flow / bottleneck metrics
```

Implementation implications from the measurements:

- calibrate and validate each camera separately;
- preserve per-camera projection uncertainty;
- keep synchronization offset/drift as configuration that can be monitored;
- do not use one fixed spatial threshold without accounting for calibration quality;
- monitor overlap disagreement continuously;
- if disagreement rises, downgrade exact world/global-ID confidence before disabling coarse section analytics;
- use geometry to repair local ID fragmentation before invoking appearance ReID;
- preserve ambiguity rather than force a merge when world/time evidence conflicts.

For the hackathon claim, the defensible wording is:

> On a 7-camera calibrated real WILDTRACK subset, shared-floor projection from annotated person boxes achieved 11.15 cm median floor error and geometry-based overlap fusion achieved 99.80% pair F1 while removing 99.88% of duplicate observations. Controlled fragmentation experiments showed 95.41–97.96% geometry-assisted stitching accuracy. Calibration and timestamp perturbations caused predictable fusion degradation, supporting explicit uncertainty and overlap-agreement health monitoring. These results demonstrate feasibility under comparable calibrated overlapping-camera conditions; they do not guarantee unseen-store performance.

---

## 13. Files produced

### Scripts

- `scripts/architecture2/acquire_wildtrack_subset.py`
- `scripts/architecture2/run_wildtrack_gt.py`
- `scripts/architecture2/check_physicalai_scene.py`

### Quantitative outputs

- `experiments/architecture2/wildtrack_summary.json`
- `experiments/architecture2/wildtrack_noise_sweep.csv`
- `experiments/architecture2/wildtrack_projection_by_camera.csv`
- `experiments/architecture2/wildtrack_fusion_threshold_sweep.csv`
- `experiments/architecture2/physicalai_scene_check.json`

### Dataset subset manifest

- `samples/wildtrack_subset/subset_manifest.json`

No large WILDTRACK/MMPTRACK/MultiviewX dataset was downloaded by this worker.
