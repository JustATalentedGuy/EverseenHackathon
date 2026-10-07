# Highly Suitable Calibrated Multi-Camera Datasets

Research date: 2026-10-04

Purpose: narrow the data strategy for the retail **Dwell-Time & Bottleneck Mapper** to datasets that can actually support calibrated multi-camera experiments.

This file intentionally excludes generic person-ReID benchmarks and camera networks that do not provide enough geometry for reliable image-to-world / image-to-section mapping.

No large datasets were downloaded while preparing this report.

---

## 1. Hard inclusion criteria

A dataset is considered **high suitability** only if it satisfies all of the following:

1. **True multi-camera acquisition**
   - at least two cameras observing the same physical scene/network,
   - synchronized or supplied with enough timing metadata to align views.

2. **Usable camera geometry**
   - intrinsics/extrinsics, projection matrices, homographies, or equivalent calibrated image-to-ground mappings.

3. **Shared spatial reference**
   - world coordinates, calibrated ground plane, top-view grid, floorplan, or enough scene geometry to create store sections consistently.

4. **People are the tracked/detected target**
   - vehicle-only datasets are excluded from the main evidence set.

5. **Data can support at least one target architecture experiment**
   - calibrated overlap fusion,
   - world/section mapping,
   - or non-overlap / gapped multi-camera identity continuation.

Cross-camera identity labels are strongly preferred but are **not mandatory** for inclusion when the dataset is specifically useful for testing geometry or multi-view detection.

---

## 2. Strict ranking

| Rank | Dataset | Suitability | Why |
|---|---|---|---|
| **1** | **MMPTRACK Retail** | **Very high** | Real indoor retail-like scene, 6 calibrated synchronized cameras, overlap graph, world footpoints, dense cross-camera IDs |
| **2** | **NVIDIA PhysicalAI Smart Spaces 2024/2025/2026** | **Very high** | Largest calibrated MTMC corpus; synchronized multi-camera video, homographies/camera matrices, global positions, maps, IDs; includes retail/warehouse |
| **3** | **CITIC-MTMC** | **Very high for mixed/gapped topology** | Real indoor building, 5 cameras across separate rooms/passages, floorplan, room/door graph, calibration, timing, world-position GT |
| **4** | **WILDTRACK** | **High for overlap geometry** | 7 synchronized calibrated real cameras, heavy overlap, metric ground grid, cross-view person annotations |
| **5** | **EPFL classic multi-camera pedestrian sequences** | **High but old/small** | Real synchronized 3-4 camera sequences, explicit ground/head-plane homographies or Tsai calibration, top-view GT |
| **6** | **EPFL-RLC** | **High for overlap mapping** | Real indoor, 3 synchronized calibrated overlapping cameras, ground grid and projection file; compact 1.1 GB |
| **7** | **MultiviewX** | **High synthetic overlap test** | 6 overlapping cameras, known synthetic geometry, calibrated ground grid; easy geometry benchmarking |
| **8** | **EPFL Soldiers Tracking** | **Useful auxiliary** | 6 fixed synchronized calibrated cameras, ground-truth trajectories/ground positions, identical uniforms stress appearance matching |
| **9** | **EPFL SportCenter** | **Useful auxiliary** | 8 fixed synchronized calibrated cameras with trajectories/3D pose, but sports layout is less representative of retail |

The **strict core shortlist for architecture claims** is:

1. **MMPTRACK Retail**
2. **NVIDIA PhysicalAI Smart Spaces**
3. **CITIC-MTMC**
4. **WILDTRACK**

EPFL-RLC, classic EPFL and MultiviewX are excellent secondary geometry checks.

---

# 3. MMPTRACK Retail

Primary sources:

- Dataset: https://iccv2021-mmp.github.io/subpage/dataset.html
- WACV paper: https://openaccess.thecvf.com/content/WACV2023/html/Han_MMPTRACK_Large-Scale_Densely_Annotated_Multi-Camera_Multiple_People_Tracking_Benchmark_WACV_2023_paper.html

## Suitability summary

**Best real dataset for the end-to-end retail prototype.**

## Real or synthetic

Real video recorded in staged Microsoft indoor lab environments.

The Retail environment was explicitly designed around shopping behavior such as:

- walking through a retail-like area,
- carts,
- baskets,
- checkout/queue behavior.

## Retail relevance

**Highest among the real calibrated datasets in this shortlist.**

It is not a live supermarket, but its layout and participant behavior are much closer to the target problem than plaza, campus or sports datasets.

## Cameras and topology

- 6 cameras in Retail.
- 23 cameras total across all five environments.
- Every camera has overlapping field of view with at least one other camera.
- The calibration system forms a connected camera/marker graph.

This is primarily an **overlap-rich network**, not a long blind-gap camera network.

## Synchronization

- RGB/depth streams synchronized within and across Azure Kinect cameras.
- Released synchronized RGB frames: 15 FPS.

## Calibration / homography

Provided:

- intrinsic parameters,
- extrinsic parameters,
- environment space size,
- voxel/grid size.

Extrinsics were estimated using ArUco markers in a shared world coordinate system.

There is no need to infer the spatial relation from appearance alone.

## World coordinates / floorplan

Provided:

- per-person ground/footpoint annotations in the shared world system,
- discretized top-down coordinates,
- space dimensions / voxel scale.

A polished architectural floorplan is not the main artifact, but the supplied world coordinate system is sufficient for:

- homography/projection evaluation,
- zone polygons defined by us,
- occupancy and dwell maps,
- distance and trajectory error.

## Cross-camera IDs

**Yes.**

The dataset provides dense frame-wise bounding boxes with person IDs consistent across camera views.

This is a major reason MMPTRACK is stronger than detection-only multi-view datasets.

## Downloadable subset / size

Retail is a distinct environment:

- 6 cameras,
- 172 total video minutes:
  - 84 min train,
  - 43 min validation,
  - 45 min test.

The official page does not publish a simple current GB figure.

Access requires accepting/signing the research-use terms and requesting the dataset. In practice, the environment/split structure allows us to focus on **Retail only** instead of all five environments.

Do not download the full corpus until the exact experiment is fixed.

## Best experiments

1. End-to-end:
   `detection -> local tracking -> shared world coordinate -> global ID -> dwell/section history`.

2. Overlap fusion:
   - appearance only,
   - geometry only,
   - appearance + synchronized world position.

3. Retail queue/dwell:
   - define checkout and aisle polygons in world coordinates,
   - measure occupancy and dwell using ground-truth footpoints,
   - replace GT with detected/projected footpoints and quantify error.

4. ID-switch sensitivity:
   - measure how local/global ID fragmentation affects dwell estimates.

## Limitations

- staged research environment rather than a live store,
- only 28 participants in the full collection,
- overlap-rich topology does not strongly test long blind camera gaps,
- released RGB resolution is 640x320, lower than many modern deployments.

## Privacy / access

Research-use access is controlled by a dataset agreement.

The collection used recruited participants; this is preferable to uncontrolled public-surveillance footage for project development.

## Verdict

**CORE DATASET.**

Use it to prove that the retail architecture can work on real calibrated multi-camera imagery.

---

# 4. NVIDIA PhysicalAI Smart Spaces — 2024

Primary sources:

- Dataset: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
- 2024 Challenge: https://www.aicitychallenge.org/2024-data-and-evaluation/
- 2024 FAQ: https://www.aicitychallenge.org/2024-faqs/

## Real or synthetic

Synthetic indoor environments generated with NVIDIA Omniverse / Isaac Sim.

## Retail relevance

High.

The 2024 corpus spans six synthetic environments and includes:

- retail store,
- warehouse,
- hospital,
- other indoor spaces.

## Cameras and topology

- 90 scenes,
- 953 cameras,
- 212 camera-hours.

Camera count varies by scene.

The safest interpretation is **mixed multi-camera geometry**: some views overlap strongly and some cameras are spatially separated. The dataset supplies enough geometry to derive camera coverage/relationships per scene rather than assuming one topology for the whole corpus.

The dataset documentation specifically notes that scenes 071-080 include a separate storage room connected to the primary retail space, which is useful for testing spatially separated regions in a continuous synchronized scene.

## Synchronization

- Time-synchronized video.
- 1080p.
- 30 FPS.

## Calibration / homography

For each camera:

- 3x4 camera matrix,
- 3x3 homography.

The current Hugging Face release also provides the newer 2025-style calibration JSON for 2024 scenes.

Some richer fields such as camera coordinates/directions/scale factors are unavailable for some original 2024 scenes, so 2025/2026 are cleaner if those fields matter.

## World coordinates / floorplan

Ground truth includes:

- consistent object IDs,
- 2D boxes,
- global `xworld, yworld` projected bottom points.

Top-down maps/calibration are available in the current consolidated Smart Spaces release.

## Cross-camera IDs

**Yes.**

Object IDs are explicitly intended to remain consistent across cameras.

## Downloadable subset / size

Full 2024 release:

- **216.95 GB**.

The Hugging Face repository is organized by split -> scene -> camera, so individual scenes/camera videos can be downloaded rather than the entire edition.

Example from the current repository:

- a single 2024 test camera video can be around 162 MB,
- one complete scene can be a few GB.

This makes 2024 the easiest NVIDIA edition for a small RGB-only experiment.

## Best experiments

1. Validate homography/world projection over many camera layouts.
2. Large-scale global-coordinate MTMC.
3. Derive overlap graph from camera calibration/map.
4. Simulate section polygons on top-down layouts.
5. Evaluate online vs offline global tracking.

## Limitations

- synthetic domain gap,
- 2024 metadata schema is less complete than 2025/2026,
- scene topology must be inspected per scene,
- excellent synthetic results do not prove robustness to real compression, shoppers, reflections or occlusion.

## Privacy

Main corpus is synthetic, so it has minimal captured-person privacy risk.

## Verdict

**CORE SYNTHETIC DATASET.**

Best edition if we want a manageable, calibrated NVIDIA subset without depth maps.

---

# 5. NVIDIA PhysicalAI Smart Spaces — 2025

Primary sources:

- Dataset: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
- Track description: https://www.aicitychallenge.org/2025-track1/
- FAQ: https://www.aicitychallenge.org/2025-faqs/

## Real or synthetic

Synthetic.

## Retail relevance

High.

The edition explicitly includes 19 indoor layouts across:

- warehouse,
- hospital,
- retail,
- office.

## Cameras and topology

- 23 scenes total in the current consolidated release,
- 504 cameras,
- about 42 camera-hours.

Topology varies by scene.

This is good for testing an architecture that computes camera relationships from calibration/map rather than using one hand-coded topology.

## Synchronization

- temporally synchronized RGB videos,
- 1080p,
- 30 FPS.

## Calibration / homography

Comprehensive per-camera metadata includes:

- intrinsic matrix,
- extrinsic matrix,
- 3x4 camera matrix,
- 3x3 homography,
- camera coordinates,
- camera direction / 3D direction,
- frame dimensions,
- scale / translation fields in the released schema.

## World coordinates / floorplan

Provided:

- top-down map,
- 2D boxes,
- 3D boxes,
- 3D global locations,
- shared coordinate system.

## Cross-camera IDs

**Yes.**

Multi-camera tracking IDs are part of the annotations.

## Downloadable subset / size

Full release:

- **3.31 TB** with depth maps,
- roughly **70 GB without depth maps**.

For this project, do **not** download the depth maps initially.

Use one scene and only:

- RGB videos,
- calibration JSON,
- ground-truth JSON,
- map.

That is enough for the camera/world mapping and MTMC experiments.

## Best experiments

1. 3D/global-coordinate multi-camera association.
2. Homography error analysis across many cameras.
3. Derive overlap and adjacency from camera/map metadata.
4. Synthetic stress tests with large camera count.
5. Section occupancy / dwell with exact ground truth.

## Limitations

- synthetic appearance/domain gap,
- huge depth release if downloaded indiscriminately,
- no guarantee that every scene contains realistic retail camera placement,
- topology needs scene-level inspection.

## Privacy

Synthetic training/evaluation scenes avoid customer surveillance privacy issues.

## Verdict

**CORE SYNTHETIC DATASET.**

Use 2025 when we want the richest stable calibration/3D schema.

---

# 6. NVIDIA PhysicalAI Smart Spaces — 2026

Primary source:

- https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces

## Real or synthetic

Primarily synthetic, with two real warehouse test scenes included in the current totals.

## Retail relevance

Moderate to high for indoor smart-space tracking.

The edition is broader than retail and is especially warehouse-heavy, but the underlying task is very close to real multi-camera indoor tracking.

## Cameras and topology

Current release totals:

- 28 scenes,
- 353 cameras,
- about 28.7 camera-hours.

These totals include two short real warehouse test scenes.

## Synchronization

Time-synchronized multi-camera video.

## Calibration / homography

Same rich 2025-style schema:

- intrinsics,
- extrinsics,
- camera matrix,
- homography,
- camera pose/direction metadata.

The real warehouse scenes also include calibration.

## World coordinates / floorplan

Synthetic scenes include:

- maps,
- 2D/3D annotations,
- global coordinates,
- cross-camera IDs.

For the two real test scenes, the current dataset card notes that ground truth/depth are withheld, so they are useful for qualitative realism but not the same quantitative GT evaluation as the synthetic scenes.

## Cross-camera IDs

**Yes for annotated synthetic data.**

Real test-scene GT is withheld.

## Downloadable subset / size

Full release:

- **2.94 TB** including depth,
- roughly **50 GB without depth**.

Recommended use:

- one synthetic scene,
- optionally one real test scene,
- RGB + calibration only unless 3D depth experiments are explicitly needed.

## Best experiments

1. Validate current Smart Spaces pipeline on a newer, more varied corpus.
2. Stress multi-object tracking with humans plus forklifts/pallet trucks/robots.
3. Qualitative transfer from synthetic to the released real warehouse views.

## Limitations

- lower retail specificity than MMPTRACK Retail,
- real scene ground truth is withheld,
- very large if depth is pulled.

## Privacy

Synthetic corpus is low privacy risk. Treat any real warehouse footage under its dataset terms.

## Verdict

**CORE/SECONDARY NVIDIA DATASET.**

Prefer 2025 for the cleanest fully annotated 3D benchmark; use 2026 for broader stress testing and limited real-scene transfer.

---

# 7. CITIC-MTMC

Primary sources:

- Repository: https://github.com/GTEC-UDC/citic-mtmc-dataset
- Paper: https://doi.org/10.1016/j.iot.2023.100940
- Dataset DOI: https://doi.org/10.5281/zenodo.17511785

## Real or synthetic

Real indoor video.

## Retail relevance

Moderate.

It is an office/research-center environment rather than retail, but its **rooms + passages + entrances** are extremely useful as a proxy for:

- aisles,
- departments,
- corridor transitions,
- camera blind gaps.

## Cameras and topology

5 cameras across 4 spaces:

- HallWide,
- HallSeg,
- PF passageway,
- PC passageway,
- Showroom.

The entrance hall has two cameras; the other spaces each have one.

This produces a valuable **mixed topology**:

- some same-area coverage,
- separate rooms/passages,
- natural cross-camera gaps.

The supplied `room_map.json` encodes simplified rooms/doors.

## Synchronization

The source cameras originally had different/variable frame rates.

The released videos were processed to a fixed 25 FPS and the repository provides:

- `timesyncs.csv`,
- path/timestamp data used to generate aligned ground truth.

This is useful because it resembles the messy timing conditions of real CCTV more than perfectly synthetic synchronization.

## Calibration / homography

The `Node*.json` files provide per-camera:

- camera position,
- calibration parameters.

Lens distortion was corrected in preprocessing.

## World coordinates / floorplan

Provided:

- floorplan in SVG/PDF,
- simplified room/door graph,
- camera positions,
- known waypoint locations,
- global ground-truth `x, y, z` positions in MOT-format files.

This is one of the strongest datasets for **section-level / room-level mapping**.

## Cross-camera IDs

**Yes at the trajectory/world-ground-truth level.**

Ground-truth rows contain:

`frame, id, ..., x, y, z`

The position/waypoint mechanism preserves subject identity across the captured path.

It is less like MMPTRACK's dense per-camera bounding-box GT, but is very useful for global path evaluation.

## Downloadable subset / size

Public video data are archived on Zenodo and organized as:

- capture1,
- capture2,
- capture3.

The currently accessible authoritative pages do not expose a reliable total byte-size figure, so do not assume a specific GB size.

For a first experiment, download **one capture only** plus:

- `map_config`,
- `Node*.json`,
- `timesyncs.csv`,
- corresponding GT.

## Best experiments

1. **Blind-gap global-ID continuation**:
   - appearance only,
   - appearance + timestamp,
   - appearance + topology,
   - appearance + topology + transition time.

2. **Section history**:
   - map person position to room/section,
   - measure time per room,
   - test transition counts.

3. **Topology-aware self-diagnosis**:
   - reject physically impossible camera transitions.

4. **Timing sensitivity**:
   - perturb clock alignment and measure handoff degradation.

## Limitations

- not retail,
- only five cameras,
- heterogeneous source cameras,
- videos were normalized from variable frame rates,
- world GT is based on waypoint-assisted subject paths rather than dense motion-capture truth at every instant.

## Privacy

CC BY-NC-SA 4.0 dataset.

The associated paper emphasizes an edge-processing approach where images need not be transmitted to the central server.

## Verdict

**CORE DATASET FOR GAPS / TOPOLOGY.**

This is the strongest real dataset in the shortlist for proving that topology and timing improve cross-camera handoff through unseen regions.

---

# 8. WILDTRACK

Primary sources:

- Official dataset: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- Paper: https://arxiv.org/abs/1707.09299

## Real or synthetic

Real outdoor pedestrian video.

## Retail relevance

Low-to-moderate scene similarity, but **very high geometry relevance**.

It is one of the cleanest real datasets for testing projection from multiple ordinary perspective cameras to one ground plane.

## Cameras and topology

- 7 static HD cameras.
- Fields of view overlap heavily.
- Average target is visible from several views.

This is an **overlap benchmark**, not a blind-gap benchmark.

## Synchronization

- high-precision joint synchronization,
- original video captured at 60 FPS,
- released synchronized image stream at 10 FPS,
- full annotations for 400 multi-view frames at 2 FPS.

## Calibration / homography

Provided:

- pinhole intrinsics,
- extrinsics,
- distortion-corrected frames,
- projection/position files.

## World coordinates / floorplan

Ground surface:

- 480 x 1440 grid,
- 2.5 cm grid spacing,
- known ground-plane origin,
- person position IDs that map to world `X,Y`.

This gives a direct metric target for homography/world-coordinate error.

## Cross-camera IDs

**Yes in the annotated frames.**

The multi-view annotation contains:

- unique person ID,
- ground position / position ID,
- per-camera boxes.

Temporal annotation is sparse compared with MMPTRACK.

## Downloadable subset / size

Official page provides:

- annotated dataset ZIP,
- separate full camera videos.

Published repacks put the annotated frame package around **6.8 GB** and the seven full videos around **62 GB total**, but the official site itself should remain the preferred source.

For our needs, use the **annotated synchronized frame package**, not the full ~hour-long videos.

## Best experiments

1. Pixel footpoint -> world-coordinate accuracy.
2. Geometry-only vs appearance-only overlap association.
3. Multi-view occupancy/heatmap fusion.
4. Homography uncertainty vs distance from calibrated region.

## Limitations

- outdoors,
- strong overlap but essentially no useful blind-gap handoff,
- only 400 densely annotated time instants,
- not designed around long dwell behavior.

## Privacy

Real public-space video.

The official page does not present the same explicit recruited-participant consent statement as MMPTRACK.

## Verdict

**CORE GEOMETRY VALIDATION DATASET.**

Use it to prove accurate overlap fusion and common-ground-plane localization on real imagery.

---

# 9. EPFL classic multi-camera pedestrian datasets

Primary source:

- https://www.epfl.ch/labs/cvlab/data/data-pom-index-php/

This is a family of small calibrated synchronized datasets:

- Laboratory,
- Campus,
- Terrace,
- Passageway,
- Basketball.

## Real or synthetic

Real.

## Retail relevance

Moderate for Laboratory/Passageway/Terrace.

The old surveillance-style viewpoints are actually useful for checking whether the method depends on ideal overhead views.

## Cameras and topology

- Laboratory: 4 cameras.
- Campus: 3 cameras.
- Terrace: 4 cameras.
- Passageway: 4 cameras.
- Basketball: 4 cameras.

All sequences are described as synchronized streams filming the same area from different angles, so they are predominantly **overlapping-view datasets**.

## Synchronization

- synchronized multi-camera streams,
- typically 25 FPS.

## Calibration / homography

Every sequence has calibration.

Depending on the sequence, EPFL supplies:

- ground-plane homography,
- head-plane homography,
- Tsai calibration,
- or generic projective camera calibration.

For the POM-style calibration:

`H * X_image = X_topview`

directly supports image-to-ground mapping.

## World coordinates / floorplan

Top-view ground grids and ground-truth position tracks are available for selected sequences:

- 6-person Laboratory,
- Terrace sequence 1,
- Passageway sequence 1.

The documentation provides:

- grid dimensions,
- top-view origin,
- top-view dimensions,
- calibration used to create the GT.

This is enough for common-ground / section experiments even though there is no polished store floorplan.

## Cross-camera IDs

Ground truth represents person positions through time in the shared top-view grid.

It is suitable for small trajectory experiments, but the annotations are older/sparser and do not provide the dense modern per-camera identity structure of MMPTRACK.

## Downloadable subset / size

The official page exposes each camera video and calibration file separately.

Examples:

- Laboratory sequence: roughly 2.5 minutes, 4 cameras.
- Terrace: roughly 3.5 minutes, 4 cameras.
- Passageway: one 4-camera sequence.

Exact current byte sizes are not shown on the page, but these are much smaller than NVIDIA/MMPTRACK and are well suited to quick smoke tests.

## Best experiments

- manual/official homography validation,
- top-view section mapping,
- projection consistency,
- small real-data overlap tracking.

## Limitations

- old codecs / low resolution,
- very small participant counts,
- short sequences,
- limited modern cross-camera tracking GT,
- not retail.

## Privacy

EPFL states that pedestrians in these sequences are laboratory members; basketball participants provided consent.

## Verdict

**HIGH-VALUE SMALL REAL SANITY SET.**

Very useful when we want a tiny real calibrated example before running larger datasets.

---

# 10. EPFL-RLC

Primary source:

- https://www.epfl.ch/labs/cvlab/data/data-rlc/

## Real or synthetic

Real indoor footage from the EPFL Rolex Learning Center.

## Retail relevance

Moderate.

It is an indoor public/building environment with surveillance-like camera views, but not a shop.

## Cameras and topology

- 3 static HD cameras.
- Overlapping fields of view.

## Synchronization

- cameras recorded at 60 FPS,
- downloadable post-processed sequences are synchronized,
- each sequence contains about 8,000 frames per view at 480x270.

## Calibration / homography

- Tsai calibration supplied for all cameras.

## World coordinates / floorplan

Intersecting ground region is discretized as:

- 55 x 45 grid.

The dataset includes a positions file mapping each ground-grid location into all three camera views using calibration.

This is sufficient for ground-plane occupancy / projection experiments.

## Cross-camera IDs

**No dense persistent MTMC identity ground truth.**

The main annotations are 4,088 positive/negative multi-view examples tied to ground position IDs. They are aimed at multi-view detection/occupancy, not long person-history tracking.

## Downloadable subset / size

Very practical:

- dataset ZIP: **1.1 GB**,
- test GT JSON: **123 KB**.

## Best experiments

- compact real overlap geometry smoke test,
- shared-ground occupancy,
- projection consistency,
- multi-view detection fusion.

## Limitations

- only 3 cameras,
- low released resolution,
- partial detection annotations,
- no strong temporal/global-ID evaluation,
- no blind gaps.

## Privacy

Real indoor footage; use under EPFL research terms.

## Verdict

**HIGH-SUITABILITY GEOMETRY DATASET, NOT A GLOBAL-HISTORY DATASET.**

Its small size makes it especially useful for fast prototype validation.

---

# 11. MultiviewX

Primary sources:

- https://github.com/hou-yz/MVDet
- https://github.com/hou-yz/MultiviewX

## Real or synthetic

Synthetic Unity dataset built using PersonX pedestrian models.

## Retail relevance

Low scene similarity, high multi-view geometry relevance.

## Cameras and topology

- 6 cameras,
- overlapping fields of view,
- 1920x1080 images,
- average 4.41 cameras cover the same location.

## Synchronization

400 synchronized annotated frames at 2 FPS.

## Calibration / homography

The dataset follows the WILDTRACK setup and supplies camera geometry used by the standard MVDet loaders/projectors.

## World coordinates / floorplan

- physical area: 16 m x 25 m,
- ground plane discretized to 640 x 1000.

This provides an exact synthetic ground reference.

## Cross-camera IDs

The benchmark is primarily **multi-view detection / occupancy**, not persistent temporal MTMC identity tracking.

Use the shared per-frame ground positions for geometry; do not treat it as a strong proof of cross-camera history.

## Downloadable subset / size

Download is provided through the MVDet project.

Only 400 annotated multi-view frames are required for the standard benchmark, so it is far lighter than full video MTMC corpora. The official repository does not publish a clear total GB number.

## Best experiments

- deterministic synthetic projection test,
- unit-test the ground-plane transformer,
- compare WILDTRACK real vs MultiviewX synthetic,
- stress crowd density with exact known geometry.

## Limitations

- synthetic domain gap,
- no retail semantics,
- no long temporal histories,
- an open repository issue has raised questions about interpretation/orientation of the provided extrinsics; use the official dataset loader/conventions and verify projection numerically before relying on raw pose visualization.

## Privacy

Synthetic, so no captured-person privacy issue.

## Verdict

**HIGH-SUITABILITY SYNTHETIC GEOMETRY TEST.**

Use as a projection regression/unit test, not as final evidence for real retail tracking.

---

# 12. EPFL Soldiers Tracking

Primary source:

- https://www.epfl.ch/labs/cvlab/data/soldiers-tracking/

## Real or synthetic

Real indoor footage.

## Retail relevance

Low scene similarity, but useful as a deliberately difficult appearance-association test.

All subjects wear the same uniform, which reduces the usefulness of color/clothing cues and forces the tracker to rely more heavily on:

- geometry,
- motion,
- temporal continuity.

That is valuable for retail scenes containing:

- staff uniforms,
- groups wearing similar colors,
- visually similar shoppers.

## Cameras and topology

- 6 fixed cameras.
- Cameras are synchronized and calibrated.
- Subjects walk in a building atrium.

The setup is primarily multi-view / overlap-oriented rather than a long blind-gap network.

## Synchronization

- synchronized camera streams,
- approximately 24 FPS.

## Calibration / homography

Provided:

- intrinsic parameters,
- extrinsic parameters.

## World coordinates / floorplan

Provided:

- ground-truth position of every subject on the ground,
- ground-truth trajectories.

There is no retail floorplan, but shared ground coordinates are sufficient for:

- position-error tests,
- geometry-based fusion,
- trajectory evaluation.

## Cross-camera IDs

**Yes.**

The dataset provides ground-truth trajectories for the subjects.

## Downloadable subset / size

- 6 camera videos,
- each roughly 11 minutes,
- about 16,800 images per view.

The official page does not state a current aggregate byte size.

Access is through the EPFL dataset page/contact.

## Best experiment

Test whether geometry and temporal consistency prevent identity swaps when appearance is deliberately weak.

Useful comparison:

1. appearance-only,
2. geometry-only,
3. geometry + appearance.

## Limitations

- uniforms are artificial relative to normal shoppers,
- atrium rather than retail,
- limited scene diversity,
- primarily overlap rather than blind-gap topology.

## Privacy

Real human subjects. Use according to EPFL research-use terms.

## Verdict

**QUALIFYING AUXILIARY DATASET.**

Good stress test for the claim that geometry should dominate when appearance is ambiguous.

---

# 13. EPFL SportCenter

Primary source:

- https://www.epfl.ch/labs/cvlab/data/sportcenter-dataset/

## Real or synthetic

Real.

## Retail relevance

Low.

The value is geometric/multi-view rather than semantic.

## Cameras and topology

- 8 fixed cameras,
- synchronized,
- calibrated,
- viewing one basketball court from multiple viewpoints.

Coverage is strongly overlapping.

## Synchronization

Synchronized image sequences.

## Calibration / homography

The official dataset describes all eight cameras as calibrated.

## World coordinates / floorplan

Provided derived labels include:

- player trajectories through the sequence,
- manually annotated 2D poses for a subset,
- triangulated 3D poses.

This supplies strong multi-view spatial ground truth, though not a store floorplan.

## Cross-camera IDs

Player trajectories provide persistent identity information across the multi-camera scene.

## Downloadable subset / size

- roughly 370,000 images in total,
- 560 images with manually provided 2D/3D pose,
- 1,000 temporal frames with additional pose estimates.

Official page provides a dataset download/contact but not a simple aggregate GB figure.

## Best experiment

- multi-view geometric fusion under fast motion,
- identity continuity during heavy occlusion,
- optional pose-assisted footpoint estimation.

## Limitations

- sports behavior is much faster than retail walking/dwell,
- court layout is unlike a store,
- strong overlap,
- pose annotations cover only subsets.

## Privacy

Real sports footage; use under the dataset's research conditions.

## Verdict

**QUALIFYING AUXILIARY DATASET, NOT CORE.**

Useful if we specifically want fast-motion/occlusion stress tests after the main retail experiments.

---

# 14. Datasets deliberately excluded from this narrowed scope

The following may be useful for related tasks, but they do **not** satisfy the current strict evidence requirement or are unsuitable for responsible project dependence.

| Dataset | Reason excluded |
|---|---|
| MALL-VLM | Real mall and cross-camera IDs, but current public devkit does not provide the calibration/homography/world/floor metadata needed for accurate common-coordinate mapping |
| MSMT17 | ReID benchmark; no useful common camera geometry/floor mapping |
| MARS | Video ReID tracklets; no shared world geometry |
| iLIDS-VID | Non-overlap ReID only; no calibrated floor/world mapping |
| DukeMTMC | Historically excellent calibrated MTMC, but withdrawn/retracted due privacy concerns; do not build project reproducibility around it |
| CityFlow / CityFlowV2 | Calibrated MTMC but targets vehicles, not people; useful conceptually, outside this strict person-tracking evidence set |
| ATC Shopping Center | Excellent world pedestrian trajectories, but acquired from range sensors rather than ordinary multi-camera RGB; suitable for downstream analytics only |
| USC Campus | Multi-camera pedestrian coverage but lacks calibration in the standard benchmark |
| CamNet | Multi-camera person tracking but lacks the calibration required by the current scope |
| CMU Panoptic Studio | Technically calibrated and synchronized with world 3D pose, but its 480+ camera motion-capture dome is too unlike practical retail surveillance; it does not help discriminate between our deployment architectures enough to justify inclusion |

---

# 15. Download strategy: smallest useful subset first

Do not begin by downloading whole datasets.

Recommended sequence:

## Step 1 — tiny geometry smoke test

Use **EPFL-RLC**:

- 1.1 GB total,
- 3 cameras,
- synchronized,
- calibrated,
- ground grid.

Goal:

- validate calibration parsing,
- image-to-ground projection,
- multi-view visualization,
- section polygon logic.

## Step 2 — synthetic regression test

Use **MultiviewX**:

- only standard 400 multi-view annotated frames needed.

Goal:

- deterministic unit/regression test for the world-projection layer,
- verify camera convention handling.

## Step 3 — real calibrated overlap

Use **WILDTRACK annotated frame package**:

- avoid seven full videos,
- use synchronized annotated frames + calibration.

Goal:

- world-coordinate error,
- overlap association,
- crowding sensitivity.

## Step 4 — real retail end-to-end

Request **MMPTRACK Retail** only.

Goal:

- retail local tracking,
- world projection,
- cross-camera IDs,
- dwell/queue metrics.

## Step 5 — real gap/topology

Use one **CITIC-MTMC capture**.

Goal:

- camera handoff through rooms/passages,
- topology/time gating,
- section history.

## Step 6 — scale

Use **one NVIDIA Smart Spaces scene**.

Download only:

- RGB MP4 files,
- calibration JSON,
- map,
- ground truth.

Skip depth maps unless a 3D-depth architecture is actually being evaluated.

---

# 16. Strict recommended shortlist

If we are allowed to use only a small number of datasets, use the following.

## 1. MMPTRACK Retail — mandatory real retail evidence

Use to test:

- R1 detection,
- R2 local tracking,
- R3 image -> world/section,
- R4 overlap/global identity,
- retail dwell and queue histories.

Why it stays:

- real,
- retail-like,
- synchronized,
- calibrated,
- common world GT,
- persistent cross-camera identity.

## 2. CITIC-MTMC — mandatory real gap/topology evidence

Use to test:

- movement across distinct rooms/passages,
- entry/exit handoff,
- camera topology,
- travel-time constraints,
- floorplan section history.

Why it stays:

- real indoor network,
- floorplan + room graph,
- camera calibration,
- synchronization metadata,
- global position/identity GT,
- natural gaps.

## 3. NVIDIA PhysicalAI Smart Spaces — mandatory scale/geometry evidence

Recommended edition:

- **2025 first** for richest fully annotated calibration/3D schema,
- **2024** if storage/simplicity matters,
- **2026** for broader/current stress testing and limited real warehouse transfer.

Use to test:

- many-camera scaling,
- exact global coordinate evaluation,
- camera geometry parsing,
- derived overlap/topology graph,
- robust section/occupancy logic.

## 4. WILDTRACK — mandatory real overlap geometry benchmark

Use to test:

- calibrated overlap fusion,
- world projection error,
- multi-camera occupancy,
- crowding and footpoint uncertainty.

## Optional 5. EPFL-RLC

Use as the fastest compact real calibrated smoke test.

## Optional 6. MultiviewX

Use as a reproducible synthetic projection regression test.

---

# 17. Architecture proof matrix

The wording below is intentionally empirical. A successful experiment on one dataset supports a claim under similar conditions; it does not guarantee deployment performance in an arbitrary store.

## Architecture A — Geometry-first overlapping-camera fusion

Pipeline:

```text
per-camera detection/tracking
-> footpoint estimation
-> calibrated projection to common ground plane
-> temporal + spatial fusion across overlapping cameras
-> optional ReID only for ambiguity
-> global temporary track
```

### Best datasets

1. **WILDTRACK**
2. **MMPTRACK Retail**
3. **EPFL-RLC**
4. **MultiviewX**
5. classic EPFL Terrace/Lab/Passageway

### What can be demonstrated

- common-ground projection from multiple perspective views,
- spatial fusion of duplicate observations,
- geometry vs appearance ablation,
- coordinate error caused by detection/footpoint noise,
- occupancy/heatmap generation from fused tracks,
- behavior in dense overlap.

### Strongest claim

If it succeeds on WILDTRACK and MMPTRACK Retail:

> A geometry-first overlap architecture can maintain useful shared-floor trajectories on both a standard calibrated real benchmark and a retail-like real multi-camera environment.

### What it does not prove

- blind-gap identity continuation,
- robustness to unknown/unprovided calibration,
- arbitrary live-store camera layouts.

---

## Architecture B — Hybrid mixed-topology MTMC

Pipeline:

```text
local tracklets
-> common world/section coordinates when visible
-> overlap: geometry + synchronization
-> blind gap: ReID + camera topology + transition-time gating
-> conservative global-ID association
```

### Best datasets

- **CITIC-MTMC** for real gapped/room transitions.
- **MMPTRACK Retail** for real overlap and retail local/global tracking.
- **NVIDIA Smart Spaces** for large mixed-layout synthetic scaling.

No single public dataset in this shortlist perfectly provides **real retail + large gaps + rich calibration + dense MTMC GT**. The architecture therefore needs a complementary evidence set.

### What can be demonstrated

On CITIC-MTMC:

- topology/time gating improves or constrains blind-gap association,
- impossible transitions can be rejected,
- section history can be reconstructed across rooms/passages.

On MMPTRACK Retail:

- appearance + geometry can maintain cross-camera identity in real retail-like overlap,
- local ID fragmentation effects can be measured.

On NVIDIA:

- the same association framework can scale across much larger calibrated camera networks,
- overlap/adjacency can be derived from site/camera geometry.

### Strongest claim

> A hybrid system can use geometry where observations overlap and topology/time/appearance where a person is temporarily unobserved, with the two parts validated on complementary calibrated datasets.

### What it does not prove

- perfect identity across arbitrary long blind gaps,
- face-free ReID accuracy for all clothing combinations,
- real supermarket performance without site-specific validation.

---

## Architecture C — World/section-first analytics with uncertainty

Pipeline:

```text
local/global tracks
-> calibrated world coordinate
-> section polygon assignment
-> confidence-aware trajectory
-> dwell / occupancy / flow / bottleneck analytics
```

This architecture deliberately makes **spatial history** the core product rather than identity itself.

### Best datasets

- **MMPTRACK Retail**: retail behavior + world footpoints.
- **CITIC-MTMC**: explicit floorplan/rooms/doors + world paths.
- **NVIDIA Smart Spaces**: exact maps/global coordinates at scale.
- **WILDTRACK**: high-quality metric ground-plane localization.

### What can be demonstrated

- image-to-world projection accuracy,
- zone assignment stability,
- dwell error caused by projection error,
- occupancy heatmaps,
- section transition counts,
- confidence propagation from detection/tracking to analytics,
- sensitivity of dwell/bottleneck metrics to ID switches.

### Strongest claim

If section/dwell metrics remain stable across MMPTRACK, CITIC and selected NVIDIA scenes:

> The analytics layer can operate on calibrated spatial trajectories across different indoor/multi-camera layouts, while exposing uncertainty from the underlying tracker.

### What it does not prove

- that every global identity is correct,
- that a homography is valid for stairs/non-planar areas,
- accurate metric results when site calibration is missing.

---

# 18. Recommended experimental evidence package

For the hackathon/report, the strongest practical evidence package is:

| Question | Dataset | Experiment |
|---|---|---|
| Can we map perspective detections to one floor? | WILDTRACK | Compare projected footpoint to metric ground GT |
| Does the same pipeline work indoors/retail-like? | MMPTRACK Retail | World projection + cross-camera ID + zone dwell |
| Can we survive non-overlap gaps? | CITIC-MTMC | ReID only vs + topology vs + topology/time |
| Does it scale to many cameras? | NVIDIA 2025 | Run selected scene with map/calibration/GT |
| Can we regression-test geometry cheaply? | EPFL-RLC / MultiviewX | Projection and multi-view occupancy smoke tests |

This gives five different forms of evidence without needing any weak/no-geometry ReID dataset.

---

# 19. Final recommendation

The development order should be:

1. **EPFL-RLC or MultiviewX**
   - validate calibration parser and world mapping quickly.

2. **WILDTRACK**
   - prove real multi-view overlap geometry.

3. **MMPTRACK Retail**
   - prove the core retail-like end-to-end path.

4. **CITIC-MTMC**
   - prove topology/time-aware continuation through camera gaps.

5. **one NVIDIA 2025 scene**
   - prove scaling and rich 3D/map integration.

Keep 2024/2026 NVIDIA editions as additional stress-test pools rather than downloading all versions.

The most defensible final architecture is the **hybrid mixed-topology design**:

- calibrated spatial fusion in overlap,
- local tracking inside each camera,
- topology + travel-time + body-ReID gating through gaps,
- temporary global IDs,
- world/section trajectory as the downstream analytics object,
- explicit confidence rather than forced identity matches.

The public datasets can provide strong empirical evidence for each component, but they should not be presented as a theoretical guarantee that the same accuracy will hold on an unseen store.

---

# 20. Primary source list

- MMPTRACK dataset: https://iccv2021-mmp.github.io/subpage/dataset.html
- MMPTRACK paper: https://openaccess.thecvf.com/content/WACV2023/html/Han_MMPTRACK_Large-Scale_Densely_Annotated_Multi-Camera_Multiple_People_Tracking_Benchmark_WACV_2023_paper.html
- NVIDIA PhysicalAI Smart Spaces: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
- AI City 2024 Track 1: https://www.aicitychallenge.org/2024-data-and-evaluation/
- AI City 2024 FAQ: https://www.aicitychallenge.org/2024-faqs/
- AI City 2025 Track 1: https://www.aicitychallenge.org/2025-track1/
- AI City 2025 FAQ: https://www.aicitychallenge.org/2025-faqs/
- CITIC-MTMC repository: https://github.com/GTEC-UDC/citic-mtmc-dataset
- CITIC-MTMC paper: https://doi.org/10.1016/j.iot.2023.100940
- WILDTRACK: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- EPFL classic multi-camera pedestrian sequences: https://www.epfl.ch/labs/cvlab/data/data-pom-index-php/
- EPFL-RLC: https://www.epfl.ch/labs/cvlab/data/data-rlc/
- MultiviewX / MVDet: https://github.com/hou-yz/MVDet
- MultiviewX toolkit: https://github.com/hou-yz/MultiviewX
- EPFL Soldiers Tracking: https://www.epfl.ch/labs/cvlab/data/soldiers-tracking/
- EPFL SportCenter: https://www.epfl.ch/labs/cvlab/data/sportcenter-dataset/
