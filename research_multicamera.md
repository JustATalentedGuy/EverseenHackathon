# Public Multi-Camera Person Tracking / ReID Datasets for Retail Dwell-Time & Bottleneck Mapping

Research date: 2026-10-04

Scope: feasibility study for a retail system that detects people from ordinary surveillance-like camera views, assigns temporary IDs, tracks them within and across multiple cameras, converts image observations into approximate store coordinates or store sections, and measures dwell time / bottlenecks without using face recognition.

No large datasets were downloaded for this study.

## Executive conclusion

Cross-camera person tracking without face recognition is technically feasible, but the design should use different association cues for overlapping and non-overlapping cameras.

- In overlapping cameras, synchronized geometry is the strongest cue. Project each person's foot point into a shared floor coordinate system and fuse detections or tracks that occupy the same place at the same time. Appearance/ReID should be secondary.
- In non-overlapping cameras, geometry cannot directly bridge the blind gap. Use body-appearance ReID together with camera topology, exit/entry zones, transition-time limits, and feasible walking speed. Carry an association confidence rather than forcing every handoff.
- For the Dwell-Time & Bottleneck Mapper, the useful persistent object is an ephemeral trajectory ID plus (x, y, t) / zone history, not a real identity.

The strongest public data sources for this project are:

1. MMPTRACK for calibrated indoor multi-camera tracking, especially its 6-camera staged retail environment.
2. NVIDIA PhysicalAI Smart Spaces / AI City MTMC 2024-2026 for large-scale synchronized indoor scenes, camera matrices, homographies, top-down maps, and world-coordinate ground truth.
3. CITIC-MTMC for a real indoor building with a floorplan, room/door topology, five cameras, synchronization data, calibration, and world-position ground truth.
4. MALL-VLM as a promising real operating-shopping-mall ReID stress test with 22 cameras, timestamps, and cross-camera IDs, but currently without the rich camera calibration/world-coordinate metadata of MMPTRACK, NVIDIA, or CITIC.
5. WILDTRACK and MultiviewX for validating overlapping-camera calibration and shared-ground-plane fusion.

DukeMTMC is historically valuable for non-overlapping handoffs, but it was withdrawn after privacy concerns. It should be treated as a literature/reference benchmark rather than a dataset to obtain or redistribute.

---

## 1. Dataset comparison

| Dataset | Scene / target | Cameras | Overlap | Sync / time | Calibration / geometry | Floorplan / world coordinates | Cross-camera IDs | Privacy / access | Best use here |
|---|---|---:|---|---|---|---|---|---|---|
| MMPTRACK | Indoor retail, lobby, industry, cafe, office; people | 23 total; retail 6 | Connected overlap graph | Synchronized, 15 FPS public release | Intrinsic + extrinsic pinhole calibration | Space size, voxel size, per-person world footpoints | Yes | Paid participants signed release; research-use agreement | Primary real/staged retail feasibility benchmark |
| NVIDIA PhysicalAI Smart Spaces 2025/26 | Synthetic indoor retail/warehouse/hospital/office; people + mobile objects | 504 (2025), 353 (2026) | Varies by scene | Time-synchronized, 30 FPS | Intrinsic, extrinsic, camera matrix, homography, camera pose/direction | Top-down map, global 3D locations, 2D/3D boxes | Yes | Mostly synthetic; CC-BY-4.0. 2026 also includes two real warehouse test scenes | Best large-scale geometry and MTMC benchmark |
| CITIC-MTMC | Real indoor building; people | 5 | Mixed: two cameras in entrance hall + separate rooms/passages | timesync data; videos normalized to 25 FPS | Camera position + calibration per node | SVG/PDF floorplan, room/door map, (x,y,z) ground truth | Yes | CC BY-NC-SA 4.0 | Best compact real indoor topology/floorplan benchmark |
| WILDTRACK | Real outdoor pedestrian plaza | 7 | Strongly overlapping | Jointly synchronized; synchronized frames at 10 FPS, GT at 2 FPS | High-precision intrinsic + extrinsic | 480x1440 ground grid / position IDs | Per-frame person annotations across views | Real public-space imagery; official page does not state participant-consent terms | Overlap-camera projection / BEV fusion |
| MultiviewX | Synthetic crowded pedestrian scene | 6 | Strongly overlapping | Synchronized; 400 frames at 2 FPS | Calibration supplied | 16 m x 25 m ground plane, 640x1000 grid | Position annotations | Synthetic | Safe synthetic counterpart to WILDTRACK |
| DukeMTMC | Real outdoor university campus; people | 8 | Mostly non-overlap; small overlap in camera pairs 2-8 and 3-5 | Synchronized, 60 FPS | Fully calibrated; topology / ground-plane data in original benchmark | Foot-contact trajectories / world-ground information | Yes; many inter-camera handoffs | Withdrawn/retracted due privacy concerns | Literature reference for non-overlap association only |
| MALL-VLM | Real operating shopping mall; people | 22 across 3 zones | Not clearly documented | Timestamp field in annotations | No calibration advertised in current devkit | Zone labels; no world coordinate/floorplan advertised | 1,450 IDs appear in 2+ cameras | Devkit says CC-BY-4.0; current repo has no detailed privacy statement and formal citation is still in progress | Real mall appearance / ReID stress test |
| MSMT17 | Real indoor + outdoor; people | 15 | ReID-focused | Multiple times of day; not an MTMC timing benchmark | Not provided for common ReID release | No | Yes in ReID labels | Real surveillance imagery; dataset-specific terms should be reviewed | ReID pretraining / domain diversity |
| MARS | Real video person ReID | 6 | Non-overlap-style ReID | Tracklets | Camera geometry not part of common release | No | Yes | Research benchmark | Video-ReID / tracklet embedding pretraining |
| iLIDS-VID | Airport arrival hall; people | 2 | Non-overlapping | Tracklet pairs | No calibration advertised | No | 300 identities paired across views | Real CCTV-derived | Small non-overlap ReID sanity check |
| CityFlow / CityFlowV2 | Vehicles, city cameras | 40 / 46 | Mostly non-overlap | Start-time offsets per video | Camera geometry + calibration | Spatio-temporal camera network | Yes, vehicles | Public challenge dataset under access terms | Concept transfer only for topology/time gating; not person appearance |
| ATC Shopping Center | Real shopping-center pedestrian trajectories from range sensors | Distributed range sensors, not normal RGB ReID | Spatially distributed sensors | Timestamped | Sensor calibration supplied | Occupancy grid + floorplan, common coordinate system | Trajectory IDs | Public/requested research data | Validate dwell/flow outputs, not camera ReID |

---

## 2. MMPTRACK - strongest direct match to a retail MTMC prototype

Official dataset page:
https://iccv2021-mmp.github.io/subpage/dataset.html

WACV 2023 paper:
https://openaccess.thecvf.com/content/WACV2023/html/Han_MMPTRACK_Large-Scale_Densely_Annotated_Multi-Camera_Multiple_People_Tracking_Benchmark_WACV_2023_paper.html

MMPTRACK was collected in five Microsoft indoor lab environments:

| Environment | Cameras | Total video minutes |
|---|---:|---:|
| Retail | 6 | 172 |
| Lobby | 4 | 129 |
| Industry | 4 | 115 |
| Cafe | 4 | 73 |
| Office | 5 | 87 |
| Total | 23 | 576 min = 9.6 h |

Important metadata:

- RGB/depth Azure Kinect cameras are fixed at different viewing angles.
- Every camera is connected to the camera overlap graph: each camera overlaps with at least one other camera.
- RGB/depth streams are synchronized within and across cameras.
- Public synchronized frames are described as 15 FPS.
- Intrinsic and extrinsic calibration is provided for every camera.
- Environment dimensions / discretization information is provided.
- Ground truth includes per-camera person boxes with consistent IDs and person footpoints in a common world-coordinate system.
- The retail sequence includes shopping-like behavior such as carts, baskets and queueing.

Why it is particularly useful:

- It is close to the planned retail problem.
- It supports image tracking and world-coordinate evaluation in the same dataset.
- It lets us test whether projecting a detected person's bottom-center / footpoint from each camera to one common floor plane yields stable coordinates.
- The retail set has enough cameras to test overlapping fusion, camera handoff, dwell zones and checkout-queue bottlenecks.

Privacy/access:

- The official page says 28 participants were paid and signed an agreement releasing their data for public research use.
- Dataset access is research-only and requires accepting its terms/conditions.

Limitations:

- The environments are staged laboratories rather than a live supermarket with hundreds of uncoordinated shoppers.
- Only 28 participants are represented, so appearance diversity is much smaller than a real store.
- The retail environment is still useful because it exposes domain-specific tracking and ReID difficulty.

Recommendation: make MMPTRACK Retail the first real-data end-to-end experiment after a synthetic proof of concept.

---

## 3. NVIDIA PhysicalAI Smart Spaces / AI City MTMC - best geometry and scale

Dataset:
https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces

AI City 2025 track:
https://www.aicitychallenge.org/2025-track1/

AI City 2024:
https://www.aicitychallenge.org/2024-data-and-evaluation/

The current dataset card provides nearly everything a geometry-based retail tracker would want:

- time-synchronized multi-camera RGB video,
- consistent object IDs across cameras,
- camera coordinates and directions,
- intrinsic matrix,
- extrinsic matrix,
- camera projection matrix,
- homography,
- top-down map,
- 2D boxes per visible camera,
- 3D location and 3D bounding boxes in a shared world coordinate system.

Current scale:

- 2024: 90 scenes, 953 cameras, 212 camera-hours, 2,481 people, over 135M 2D boxes.
- 2025: 23 scenes, 504 cameras, about 42 camera-hours, 292 people plus mobile robots/forklifts in ground truth.
- 2026: 28 scenes, 353 cameras, about 28.7 camera-hours, 901 people plus other mobile classes. The release also lists two real-world warehouse test captures with 4 and 7 cameras plus calibration; the main annotated corpus is synthetic.

The 2025 challenge explicitly includes indoor warehouse, hospital, retail and office layouts.

Why this is useful:

1. Train and debug the whole spatial pipeline without manual calibration uncertainty.
2. Evaluate global trajectory error directly in world coordinates rather than only IDF1 on image boxes.
3. Simulate overlapping and separated views at much larger scale than MMPTRACK.
4. The top-down map and camera pose fields closely match the metadata we should request from organizers.

Privacy/access:

- The main training corpus is synthetic, so there is no captured-person privacy issue.
- The current dataset card lists CC-BY-4.0.
- It is therefore a strong choice for early development.

Limitations:

- Synthetic people and rendering do not fully reproduce real store clothing texture, motion blur, crowded occlusion, exposure changes, reflections, shelving occlusions, camera compression and customer behavior.
- Use it for geometry, tracking logic, scalability and synthetic pretraining. Do not use synthetic benchmark accuracy as the final real-retail feasibility claim.

Recommendation: use NVIDIA Smart Spaces first for the shared-coordinate MTMC engine, then validate appearance/generalization on MMPTRACK and real mall/indoor data.

---

## 4. CITIC-MTMC - compact real indoor dataset with floorplan and room topology

Repository:
https://github.com/GTEC-UDC/citic-mtmc-dataset

Zenodo DOI:
https://doi.org/10.5281/zenodo.17511785

Paper:
https://doi.org/10.1016/j.iot.2023.100940

Five cameras cover four indoor spaces:

- entrance hall: 2 cameras,
- passageway PF: 1 camera,
- passageway PC: 1 camera,
- showroom: 1 camera.

It includes:

- a floorplan in SVG and PDF,
- a simplified room/door graph,
- per-camera position and calibration parameters,
- timestamp synchronization data,
- person path waypoints,
- ground-truth (x,y,z) positions,
- optional BLE beacon measurements,
- videos normalized to 25 FPS.

Why it matters:

- The problem is naturally expressed as a person moving through rooms and corridors, which is close to store-section tracking.
- A room/door graph is exactly the camera-topology prior that helps bridge non-overlapping cameras.
- It allows testing: exit from camera/room A, expected door/path, feasible travel time, entry to camera/room B, appearance match, and global identity continuation.

License:

- Dataset: CC BY-NC-SA 4.0.
- Code: MIT.

Recommendation: use CITIC-MTMC specifically to test non-overlap section handoffs and topology/time gating.

---

## 5. WILDTRACK - excellent for overlapping-camera localization

Official EPFL page:
https://www.epfl.ch/labs/cvlab/data/data-wildtrack/

Paper:
https://arxiv.org/abs/1707.09299

WILDTRACK contains seven static HD cameras whose fields of view overlap substantially.

It provides:

- synchronized views,
- high-precision joint calibration,
- pinhole intrinsic and extrinsic camera parameters,
- distortion-corrected synchronized 1920x1080 frames,
- a shared ground grid of 480x1440 positions,
- a positions file mapping each ground-volume location into each camera,
- ground-truth annotations for 400 synchronized frames at 2 FPS.

The official page reports about 20 people per annotated frame and roughly 56,000 single-view boxes across the seven views.

Why it is useful:

- It is ideal for testing whether multiple noisy image detections of the same person can be fused into one stable (x,y) location.
- A geometry-first method can project a person's footpoint from each camera to a common ground plane and merge the projections.
- It is also a good calibration sanity test.

Limitations:

- Most views overlap, so it does not test long blind-zone handoffs well.
- It is outdoors, not retail.
- It has a small annotated time window by modern standards.
- The official page describes real public-space acquisition but does not provide the explicit participant-consent statement that MMPTRACK does.

Recommendation: use WILDTRACK as an overlapping-camera geometry unit test, not as the main retail dataset.

---

## 6. MultiviewX - synthetic WILDTRACK-style benchmark

Official repositories:
https://github.com/hou-yz/MVDet
https://github.com/hou-yz/MultiviewX

MultiviewX was generated in Unity using PersonX pedestrian models.

Properties:

- 6 synchronized cameras,
- overlapping fields of view,
- 1920x1080 images,
- 400 annotated frames at 2 FPS,
- a 16 m x 25 m ground area,
- 640x1000 discretized ground grid,
- average 4.41 cameras cover the same location,
- calibration files are supplied.

Why it is useful:

- privacy-safe and reproducible,
- same style of BEV/projection evaluation as WILDTRACK,
- can be used before any real surveillance data is handled.

Limitations:

- purely synthetic,
- mainly an overlapping-camera localization benchmark rather than a blind-handoff benchmark.

---

## 7. DukeMTMC - historically important, but do not make it a dependency

Original paper:
https://arxiv.org/abs/1609.01775

Privacy/removal background:
https://exposing.ai/duke_mtmc/
https://www.aiaaic.org/aiaaic-repository/ai-algorithmic-and-automation-incidents/dukemtmc-dataset

DukeMTMC originally provided:

- 8 fixed synchronized 1080p cameras at 60 FPS,
- 85 minutes per camera,
- over 2 million frames,
- over 2,700 identities,
- calibrated cameras,
- full person trajectories / ground-contact annotations,
- 4,159 camera handovers reported in the original paper.

The benchmark is particularly relevant because evaluation regions are essentially non-overlapping. The physical views had only small overlap in camera pairs 2-8 and 3-5; most handoffs therefore include blind gaps.

Its published literature is useful for understanding:

- appearance matching after a person disappears and reappears,
- camera topology constraints,
- travel-time gating,
- identity switches caused by multiple people traversing blind areas simultaneously.

However:

- DukeMTMC and its ReID derivatives were withdrawn/retracted after privacy concerns about captured university students.
- Third-party mirrors still exist, but that does not make redistribution appropriate.

Recommendation: read papers/results from DukeMTMC, but do not build project reproducibility around acquiring this dataset.

---

## 8. MALL-VLM - promising real-shopping-mall appearance data, but currently immature

Devkit:
https://github.com/harshm2601/mall-vlm-devkit

The current public devkit describes:

- 22 surveillance cameras,
- 3 mall zones,
- 3 recording days,
- 9,209 unique IDs,
- 125,229 annotated person boxes,
- 1,450 identities seen in 2 or more cameras,
- some identities observed in as many as 14 cameras,
- camera ID, zone and timestamp fields,
- full-frame images and person crops.

This is directly relevant because it comes from a real operating shopping mall and therefore contains realistic retail occlusion, clothing similarities, viewpoint changes, illumination variation, long-tailed shopper visibility and hard cross-camera ReID cases.

Current limitations:

- The repo does not advertise camera calibration, homographies, a floorplan, or world coordinates.
- The current README says the formal citation is in progress.
- The devkit is based on selected frames/crops; it should not yet be assumed to provide the dense continuous frame-by-frame timing needed for precise dwell-time evaluation.
- The README does not currently provide a detailed subject-consent/privacy description. Because the data are from a real shopping mall, this should be checked before final use.

Recommendation: use it as an auxiliary real-mall ReID benchmark after verifying provenance/privacy terms. It is not a substitute for MMPTRACK/NVIDIA/CITIC for geometry.

---

## 9. ReID-focused datasets: useful for appearance, insufficient for the whole problem

### MSMT17

Paper:
https://openaccess.thecvf.com/content_cvpr_2018/html/Wei_Person_Transfer_GAN_CVPR_2018_paper.html

- 15 cameras,
- indoor and outdoor scenes,
- 4,101 identities,
- 126,441 boxes,
- broad lighting/time variation.

Use: training/evaluating a body-appearance embedding.

Missing for this project: convenient calibrated floor coordinates, camera topology, and synchronized dense trajectories.

### MARS

Microsoft Research:
https://www.microsoft.com/en-us/research/publication/mars-video-benchmark-large-scale-person-re-identification/

- 1,261 identities,
- around 20,000 tracklets,
- 6 cameras,
- automatically generated pedestrian tracklets including practical detector/tracker errors.

Use: video/tracklet ReID, where an embedding is aggregated over several frames instead of matching one crop.

Missing: public world-coordinate and camera-network metadata for the geometry problem.

### iLIDS-VID

Dataset page:
https://xiatian-zhu.github.io/downloads_qmul_iLIDS-VID_ReID_dataset.html

- 300 pedestrians,
- 2 non-overlapping cameras,
- 600 image sequences,
- airport arrival hall,
- 23-192 frames per sequence.

Use: small sanity test for non-overlapping-camera ReID under occlusion and viewpoint change.

These are ReID component datasets, not end-to-end dwell-time datasets.

---

## 10. CityFlow - not a person dataset, but useful for camera-network reasoning

Original paper:
https://openaccess.thecvf.com/content_CVPR_2019/html/Tang_CityFlow_A_City-Scale_Benchmark_for_Multi-Target_Multi-Camera_Vehicle_Tracking_and_CVPR_2019_paper.html

CityFlowV2:
https://www.aicitychallenge.org/2022-data-and-evaluation/

CityFlow is for vehicles, not people, so its visual ReID models are not directly useful. Its network design is relevant:

- CityFlowV2 has 46 cameras over 16 intersections,
- 3.58 hours of video,
- majority at 10 FPS,
- video start-time offsets for synchronization,
- 880 cross-camera vehicle identities,
- camera geometry/calibration,
- long spatial gaps between cameras.

Transferable idea:

appearance similarity + camera topology + time-of-travel constraints

is much stronger than appearance-only association in a non-overlap network.

The same principle should be used for people in a store, with a transition graph defined by aisles, doors, escalators and neighboring camera zones.

---

## 11. ATC Shopping Center - useful for dwell/flow validation, not ReID

Dataset:
https://dil.atr.jp/crest2010_HRI/ATC_dataset/

This dataset provides real shopping-center pedestrian trajectories from distributed range sensors rather than ordinary RGB surveillance cameras.

It includes:

- sensor calibration information,
- a 2D occupancy grid,
- a floorplan,
- pedestrian positions in a common coordinate system.

It is useful for testing downstream analytics:

- per-zone dwell time,
- trajectory smoothing,
- traffic density,
- bottleneck heatmaps,
- entry/exit flow,
- path clustering.

It is not useful for training a camera-based person detector or ReID model.

---

## 12. Is cross-camera tracking possible without face recognition?

Yes. The practical approach is to associate tracks, not faces.

For each visible person, maintain:

local track -> body appearance embedding -> world/zone position -> time -> global temporary ID

### A. Within one camera

Use:

1. person detector,
2. motion model,
3. bounding-box overlap / Kalman prediction,
4. optional body-appearance embedding.

Typical tracker families include ByteTrack, BoT-SORT, DeepSORT-style trackers, OC-SORT and StrongSORT-style variants.

For dwell time, minimizing ID switches during occlusion matters. A person may stand still near a shelf for a long period, so the tracker cannot assume continual motion.

### B. Across overlapping cameras

If cameras overlap and are calibrated:

1. detect a person in every camera,
2. take bottom-center / estimated foot point,
3. project the image point onto the shared ground plane,
4. compare projected positions at the same timestamp,
5. combine observations that are close in world coordinates,
6. use appearance only to resolve ambiguous cases.

This is more robust than asking a ReID model to decide identity from clothing alone.

WILDTRACK, MultiviewX, MMPTRACK and NVIDIA Smart Spaces all support this style of experiment.

### C. Across non-overlapping cameras

When there is a blind gap:

1. person exits camera A through a known exit zone,
2. camera topology gives the small set of reachable next cameras,
3. store geometry gives an expected transition-time range,
4. camera B reports one or more new tracks,
5. compare body appearance embeddings,
6. reject candidates with impossible timing/path/speed,
7. match only if the combined score is sufficiently confident.

A simple association cost is:

cost = w_app * appearance_distance + w_time * time_penalty + w_topology * topology_penalty + w_space * spatial_penalty

For overlapping cameras, make spatial consistency dominant.

For separated cameras, time + topology + appearance become more important.

### D. Use tracklets, not single frames

One frame may show only a back view, heavy occlusion, motion blur or a shirt similar to another shopper.

Instead:

- filter tiny, blurred or heavily occluded crops,
- compute body ReID embeddings from several good frames,
- aggregate them by median, quality-weighted mean, or a temporal model.

This gives a more stable cross-camera signature.

---

## 13. Privacy: no face recognition is feasible, but call the result pseudonymous tracking

Avoid claiming that a persistent cross-camera tracker is fully anonymous.

Even without face embeddings:

- body appearance can distinguish people,
- clothing can identify a visitor during a session,
- gait/body-shape embeddings may have privacy implications,
- the output intentionally links a person's movement across space and time.

A safer design is session-scoped pseudonymous tracking:

1. Never run face recognition for identity.
2. Optionally mask/crop the head region before ReID embedding extraction.
3. Generate random temporary global IDs.
4. Reset/expire IDs when a shopper leaves or after a short timeout.
5. Store derived trajectories / zone dwell counts instead of raw crops where possible.
6. Keep ReID embeddings only as long as required for active association.
7. Process on-premise/edge where practical.
8. Do not link visit IDs to names, payment identities, phone identifiers or previous-day visits.

NVIDIA's MTMC workflow describes global IDs derived from visual embeddings/appearance rather than personal biometric information:
https://www.nvidia.com/en-us/ai-data-science/ai-workflows/multi-camera-tracking/

That supports the engineering feasibility of face-free MTMC. It should still be treated as tracking personal movement and reviewed under applicable privacy rules.

---

## 14. Camera/site metadata to request from organizers

Highest priority:

- camera ID for every stream,
- exact FPS,
- hardware/software synchronization method,
- start timestamp / clock offset per camera,
- frame resolution,
- camera intrinsics,
- camera extrinsics or image-to-floor homography,
- camera position (x,y,z) and orientation,
- store floorplan with dimensions,
- polygon showing each camera's floor coverage,
- which camera pairs overlap,
- camera adjacency/topology for non-overlap handoffs,
- entry/exit zones for each camera.

Very useful:

- real distances between doors, aisle junctions, escalators and camera boundaries,
- whether clocks drift during long recordings,
- PTZ/dynamically changing views,
- lens distortion coefficients,
- camera height/angle,
- known blind spots,
- store section polygons such as entrance, aisle, checkout queue and exit.

If calibration is not provided:

- manually mark at least four floor correspondences per camera and estimate a planar homography,
- use floor tiles, aisle corners and shelf endpoints,
- if metric dimensions are unavailable, define normalized floor coordinates or section polygons.

Manual one-time calibration is simpler and more reliable for a hackathon than relying on calibration-free research methods.

---

## 15. Recommended experiment sequence

### Experiment 1 - single-camera ID stability

Dataset: MMPTRACK Retail or a small organizer-provided video.

Goal:

- detect people,
- assign local track IDs,
- survive short occlusion,
- output frame, local ID, box and confidence.

Evaluate with HOTA/IDF1 when ground truth exists and inspect ID switches.

### Experiment 2 - pixel-to-floor localization

Datasets: MultiviewX, WILDTRACK, MMPTRACK, or NVIDIA Smart Spaces.

Goal:

- project bottom-center/footpoint to (x,y),
- compare with world-coordinate ground truth.

Metric: median and 90th-percentile position error in meters or grid cells.

### Experiment 3 - overlap fusion

Dataset: WILDTRACK or MultiviewX first, then MMPTRACK Retail.

Compare:

1. appearance-only matching,
2. geometry-only matching,
3. geometry + appearance.

Expected result: geometry + temporal synchronization should reduce ambiguous appearance matches in overlapping regions.

### Experiment 4 - non-overlap handoff

Dataset: CITIC-MTMC.

Compare:

1. ReID only,
2. ReID + transition-time gate,
3. ReID + topology + transition-time gate.

This directly represents store cameras separated by shelving, doors or corridors.

### Experiment 5 - real retail appearance stress test

Dataset: MALL-VLM, after verifying provenance/privacy and temporal sampling.

Goal: test confusion among similarly dressed shoppers under real mall conditions.

### Experiment 6 - dwell/bottleneck analytics

Input:

global_id, timestamp, x, y, zone, confidence

Compute:

- dwell per zone,
- queue duration,
- occupancy over time,
- heatmap,
- transition counts,
- congestion/bottleneck score,
- average speed,
- path density.

ATC shopping-center trajectories can test this downstream layer independently of vision.

---

## 16. Recommended system architecture

Camera streams
-> person detector
-> per-camera tracker
-> quality-filtered body embeddings
-> local tracklets
-> ground-plane projection / zone assignment
-> multi-camera association:
   - overlap spatial fusion
   - ReID similarity
   - camera topology
   - travel-time gating
   - confidence / ambiguity handling
-> temporary global person ID
-> (x, y, zone, timestamp)
-> dwell / flow / bottleneck analytics

The global association service should support:

- confirmed,
- tentative,
- lost,
- ended,
- optionally ambiguous.

For a dwell-time product, a wrong merge between two people is usually worse than temporarily splitting one visitor into two IDs, so use conservative cross-camera association thresholds.

---

## 17. What can be claimed after these public-data experiments?

If the prototype performs well on:

- WILDTRACK/MultiviewX for overlap localization,
- MMPTRACK Retail for indoor calibrated MTMC,
- CITIC-MTMC for topology-based handoff,
- a real retail ReID set such as MALL-VLM for appearance robustness,

then there is strong evidence that the overall idea is feasible.

Remaining deployment risk will be site-specific:

- actual camera angles,
- exact overlap gaps,
- low-resolution or distant shoppers,
- crowded checkout queues,
- identical uniforms/clothing,
- reflections and shelves,
- clock synchronization,
- camera compression,
- calibration drift,
- store geometry.

The final hackathon design should treat camera metadata plus a small store-specific calibration/validation set as an expected deployment step.

---

## 18. Practical dataset priority

### Tier A - use first

1. NVIDIA PhysicalAI Smart Spaces
   - best calibration/world-coordinate/top-down metadata,
   - huge scale,
   - synthetic/privacy-safe,
   - retail-like indoor scenes.

2. MMPTRACK Retail
   - direct retail behavior,
   - calibrated synchronized cameras,
   - real consenting participants,
   - cross-camera IDs + world footpoints.

3. CITIC-MTMC
   - real indoor,
   - floorplan and room graph,
   - ideal non-overlap/topology experiment.

### Tier B - focused component tests

4. WILDTRACK - overlap geometry and projection.
5. MultiviewX - synthetic overlap geometry.
6. MALL-VLM - real shopping-mall appearance stress test after privacy/provenance review.

### Tier C - ReID pretraining / literature

7. MSMT17
8. MARS
9. iLIDS-VID

### Reference / downstream only

10. DukeMTMC - useful research history; withdrawn due privacy concerns.
11. CityFlow - vehicle data; useful topology + time-gating concept.
12. ATC Shopping Center - useful downstream trajectory/dwell analytics, not RGB ReID.

---

## Sources

- MMPTRACK dataset: https://iccv2021-mmp.github.io/subpage/dataset.html
- MMPTRACK paper: https://openaccess.thecvf.com/content/WACV2023/html/Han_MMPTRACK_Large-Scale_Densely_Annotated_Multi-Camera_Multiple_People_Tracking_Benchmark_WACV_2023_paper.html
- NVIDIA PhysicalAI Smart Spaces: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
- AI City 2025 MTMC: https://www.aicitychallenge.org/2025-track1/
- AI City 2024 MTMC: https://www.aicitychallenge.org/2024-data-and-evaluation/
- NVIDIA MTMC workflow: https://www.nvidia.com/en-us/ai-data-science/ai-workflows/multi-camera-tracking/
- CITIC-MTMC: https://github.com/GTEC-UDC/citic-mtmc-dataset
- CITIC paper: https://doi.org/10.1016/j.iot.2023.100940
- WILDTRACK official: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- WILDTRACK paper: https://arxiv.org/abs/1707.09299
- MultiviewX/MVDet: https://github.com/hou-yz/MVDet
- MultiviewX toolkit: https://github.com/hou-yz/MultiviewX
- DukeMTMC paper: https://arxiv.org/abs/1609.01775
- DukeMTMC privacy/removal: https://exposing.ai/duke_mtmc/
- DukeMTMC incident summary: https://www.aiaaic.org/aiaaic-repository/ai-algorithmic-and-automation-incidents/dukemtmc-dataset
- MALL-VLM: https://github.com/harshm2601/mall-vlm-devkit
- MSMT17: https://openaccess.thecvf.com/content_cvpr_2018/html/Wei_Person_Transfer_GAN_CVPR_2018_paper.html
- MARS: https://www.microsoft.com/en-us/research/publication/mars-video-benchmark-large-scale-person-re-identification/
- iLIDS-VID: https://xiatian-zhu.github.io/downloads_qmul_iLIDS-VID_ReID_dataset.html
- CityFlow: https://openaccess.thecvf.com/content_CVPR_2019/html/Tang_CityFlow_A_City-Scale_Benchmark_for_Multi-Target_Multi-Camera_Vehicle_Tracking_and_CVPR_2019_paper.html
- CityFlowV2: https://www.aicitychallenge.org/2022-data-and-evaluation/
- ATC Shopping Center: https://dil.atr.jp/crest2010_HRI/ATC_dataset/
