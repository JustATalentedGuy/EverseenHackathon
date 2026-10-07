# Feasibility Study: Detection, Local Tracking, Spatial Mapping, and Cross-Camera Tracking

Date: 2026-10-04

Root: `C:\Coding\ML\Everseen`

## 1. Scope

This study investigates whether the first four technical requirements of the Dwell-Time & Bottleneck Mapper can be implemented with sufficiently high confidence before designing downstream dwell/congestion metrics.

The four requirements are:

1. **R1 — Person detection:** identify visible people in ordinary oblique CCTV footage.
2. **R2 — Local tracking:** assign stable temporary IDs and keep them through consecutive frames in one camera.
3. **R3 — Spatial mapping:** convert each tracked person's image position into either an approximate common floor coordinate or a store section/zone.
4. **R4 — Cross-camera history:** maintain a session-scoped global trajectory when people move between cameras, including overlapping views and non-overlapping blind gaps, without face recognition.

The study deliberately avoids assuming that these stages will work in a real store. It separates what is directly demonstrated, what is feasible only when metadata is available, and what remains probabilistic or site-specific.

---

## 2. Executive conclusion

### R1 — person detection

**Feasibility: high, but camera-specific validation is mandatory.**

Modern person detectors can operate directly on oblique CCTV video without calibration. The main risks are small distant people, severe occlusion, carts/shelves blocking bodies, reflections, compression, backlighting, and very crowded checkout scenes.

An empirical MOT17 shopping-mall stress test using a lightweight COCO-pretrained YOLO11n detector and two trackers produced useful but not production-grade tracking accuracy. This proves that the pipeline is technically runnable on modest hardware, but also proves that default pretrained models should not be assumed to give highly reliable trajectories without tuning.

### R2 — local tracking

**Feasibility: medium-high for fixed cameras; moderate in difficult crowded/moving-camera scenes.**

ByteTrack and BoT-SORT both produced coherent tracks in the tested mall sequence. BoT-SORT was slightly better on IDF1/MOTA and had fewer ID switches, but slightly more track fragmentation. The result does not establish that one tracker is universally better; it shows that local tracking is feasible and measurable, and that model/tracker selection should be validated on representative footage.

### R3 — coordinate or section mapping

**Section-level mapping: high feasibility with minimal manual setup.**

**Metric/common-floor coordinates: high feasibility only when geometry is available or can be calibrated.**

If the organizer supplies a floorplan plus homography/calibration for each camera, a bounding-box foot point can be projected into a common floor coordinate system. If full calibration is unavailable, a practical hackathon fallback is manual section polygons in image space, or a one-time homography estimated from known floor points.

The EPFL calibration test and NVIDIA PhysicalAI metadata inspection both confirmed that the required data structures are technically sufficient for deterministic image-to-floor transforms.

### R4A — overlapping-camera history

**Feasibility: medium-high when cameras are synchronized and share calibration.**

For overlapping views, appearance should not be the primary cue. Project detections/tracklets into the same world/floor coordinate system and fuse observations that occur at the same time and place. Appearance embeddings can be used as supporting evidence.

### R4B — non-overlapping/blind-gap history

**Feasibility: medium, probabilistic, and metadata-dependent.**

Appearance-only ReID is not reliable enough to force global identity continuity in a real store. The correct design is multi-cue association:

- body/tracklet appearance embedding,
- camera adjacency/topology,
- exit and entry zones,
- transition-time windows,
- feasible walking speed / route distance,
- direction constraints,
- optionally gait/body-shape cues where privacy policy permits.

The system should be allowed to return **ambiguous** or start a new temporary ID rather than confidently merging two different shoppers.

---

## 3. What was actually tested locally

The following evidence was generated in this workspace.

### 3.1 ByteTrack vs BoT-SORT on a shopping-mall sequence

Dataset/sample:

- MOT17-11 shopping-mall sequence preview video.
- 900 frames.
- Ground-truth person boxes/IDs from MOT17 training labels.
- Preview video is 960x540 while annotations are 1920x1080; predictions were scaled by 2 before evaluation.

Detector:

- YOLO11n, COCO pretrained.
- person class only.
- confidence 0.20.
- input size 640.
- CPU execution.

Results:

| Metric | ByteTrack | BoT-SORT |
|---|---:|---:|
| MOTA | 0.528 | 0.540 |
| IDF1 | 0.530 | 0.545 |
| ID precision | 0.664 | 0.674 |
| ID recall | 0.442 | 0.457 |
| ID switches | 30 | 26 |
| False positives | 636 | 635 |
| Misses | 3,791 | 3,681 |
| Mostly tracked identities | 16 | 18 |
| Fragmentations | 57 | 62 |

Important interpretation:

- BoT-SORT was modestly better in this run, not dramatically better.
- The main weakness was detector recall: thousands of ground-truth boxes were missed.
- This was a **moving-camera mall sequence**, which is harder and geometrically different from fixed CCTV.
- The scores are an internal MOT-style evaluation, not official MOTChallenge leaderboard scores.
- For dwell-time estimation, ID fragmentation is important even when aggregate occupancy remains usable.

Files:

- `experiments/mot17_11_tracker_eval_scaled.json`
- `experiments/mot17_predictions/`
- `scripts/evaluate_trackers_mot17.py`
- `scripts/reevaluate_mot17_scaled.py`

### 3.2 EPFL ground-plane homography sanity check

The EPFL laboratory calibration provides a 3x3 image-to-ground-plane homography for each camera.

The local verification script checked:

- matrix invertibility,
- numerical conditioning,
- sample image-to-ground projection,
- ground-to-image round trip.

Maximum round-trip errors were far below one pixel for the tested sample points.

This verifies the **mechanics** of using provided homographies. It does **not** independently establish physical localization accuracy because a separate set of ground-truth image/world point correspondences was not available in the local sample.

Files:

- `experiments/epfl_homography_check.json`
- `scripts/verify_homography.py`

### 3.3 NVIDIA PhysicalAI calibration metadata check

A metadata-only sample from `MTMC_Tracking_2026/train/Warehouse_000` was inspected without downloading the huge videos/depth data.

Observed:

- 25 cameras.
- top-down map present.
- all 25 cameras provide:
  - camera ID,
  - camera x/y position,
  - FPS and frame size,
  - intrinsic matrix,
  - extrinsic matrix,
  - camera projection matrix,
  - homography.

The homographies were invertible on the sample check and produced a maximum pixel round-trip error of about **0.017 px** across tested cameras.

This is strong evidence that the metadata package we should request from the organizers is realistic and sufficient for common-coordinate tracking.

Files:

- `samples/physicalai/Warehouse_000/calibration.json`
- `samples/physicalai/Warehouse_000/map.png`
- `experiments/physicalai_metadata_check.json`
- `scripts/verify_physicalai_metadata.py`

### 3.4 Cross-camera appearance baseline sanity check

A simple ImageNet ResNet-50 embedding baseline was tested on ReID crops included in a cloned EPFL multi-camera demonstration repository.

The nominal matchable-query rank result looked unrealistically strong. A data-integrity check found **41 byte-identical image collisions carrying different identity labels** in those evaluation crops.

Therefore:

- the apparent ReID accuracy is **not accepted as evidence** that cross-camera matching is solved;
- the test is retained as an example of why dataset/annotation sanity checks are essential;
- future ReID claims must use a clean benchmark such as MMPTRACK, CITIC-MTMC, MALL-VLM after provenance review, MARS/MSMT17 for component testing, or organizer-labeled handoffs.

Files:

- `experiments/reid_baseline_resnet50.json`
- `scripts/eval_reid_baseline.py`

### 3.5 Small EPFL tracker test

ByteTrack and BoT-SORT were also run on part of the EPFL laboratory camera sequence with YOLO11n.

The early frames contained very few detector outputs; therefore this run is useful only as a pipeline sanity test, not a reliable tracker comparison. BoT-SORT happened to preserve one detected person over a longer uninterrupted short track than ByteTrack in this segment.

File:

- `experiments/tracker_benchmark_epfl_cam0.json`

---

## 4. Confidence status by requirement

| Requirement | Current evidence | Confidence now | What is still needed before making a strong claim |
|---|---|---|---|
| R1 Detection | Real mall MOT17 run; retail/indoor datasets surveyed | Medium-high | Fixed retail CCTV validation; detector tuning; crowded checkout test |
| R2 Local tracking | ByteTrack and BoT-SORT evaluated against MOT17 IDs | Medium | Fixed-camera test with representative occlusion and carts; HOTA/IDF1 on closer domain |
| R3 Section mapping | Architecture straightforward; zone polygons need no metric calibration | High | Organizer section definitions or manual polygon setup |
| R3 World coordinates | EPFL + PhysicalAI homography/calibration mechanics verified | High if metadata exists | Measure actual position error against world-coordinate GT on MMPTRACK/PhysicalAI/WILDTRACK |
| R4A Overlap fusion | Strong benchmark/data support; geometry available in multiple datasets | Medium-high conceptually | Run quantitative geometry-only vs appearance-only vs fused experiment |
| R4B Blind-gap handoff | Strong literature/dataset support; no clean local end-to-end handoff benchmark run yet | Medium/uncertain | CITIC-MTMC or MTA/MMPTRACK handoff test with ReID + time + topology |

---

## 5. Dataset landscape

No one dataset covers the whole problem perfectly. Use complementary datasets for different failure modes.

### Tier A — strongest end-to-end / geometry datasets

#### MMPTRACK Retail

Best direct real/staged-retail benchmark found.

- 6 cameras in the retail environment.
- synchronized multi-camera video.
- camera intrinsics/extrinsics.
- consistent cross-camera person IDs.
- person footpoints/world coordinates.
- retail behavior including carts, baskets and queueing.

Use it for:

- R1/R2 local tracking,
- R3 floor-coordinate error,
- overlapping-camera fusion,
- cross-camera ID continuity,
- later dwell/queue experiments.

#### NVIDIA PhysicalAI Smart Spaces / AI City MTMC

Best metadata/scale benchmark.

- synchronized multi-camera scenes,
- consistent IDs,
- 2D and 3D ground truth,
- camera positions/directions,
- intrinsics/extrinsics,
- camera matrices,
- homographies,
- top-down maps,
- shared global coordinates.

Full releases are huge; use metadata and targeted scenes only.

#### CITIC-MTMC

Best compact real indoor topology/handoff benchmark found.

- 5 cameras across four indoor spaces.
- floorplan and simplified room/door graph.
- camera position/calibration.
- timestamp synchronization data.
- person path waypoints and world-position ground truth.

Use it specifically for non-overlap/blind-gap association.

### Tier B — targeted real retail/indoor tests

#### CAVIAR Lisbon Shopping Centre

- real shopping-centre video,
- paired views,
- person/group annotations,
- stopping/browsing/waiting scenarios,
- image/world correspondences for homography.

Small and useful for a quick end-to-end fixed-camera test.

#### HDA Person Dataset

- 18 simultaneously recorded cameras, 13 labelled,
- 85 people,
- global person IDs,
- homography for each camera,
- indoor floor layout.

Good real indoor MTMC benchmark after access/size is confirmed.

#### MALL-VLM

- 22 cameras,
- real operating shopping mall,
- timestamped annotated person boxes/crops,
- thousands of identities and many cross-camera IDs.

Very useful for hard appearance/ReID stress testing, but current public material does not advertise the same calibration/world-coordinate metadata as MMPTRACK or NVIDIA. Privacy/provenance should also be reviewed before using it in a public demo.

### Tier C — component-specific datasets

#### MOT17 / MOT20

Use for detection/local tracking and crowd/occlusion stress tests, not for floor mapping or MTMC.

#### WILDTRACK / MultiviewX

Excellent for synchronized multi-camera overlapping geometry, common-ground-plane localization and multi-view fusion.

#### MTA

Synthetic six-camera network with overlapping and non-overlapping views. Useful for controlled cross-camera handoff/time-gap tests. Full release is too large for the current disk budget; use only the short subset if access is granted.

#### MSMT17 / MARS / iLIDS-VID / Market-1501

Useful for appearance or video-ReID component evaluation, but insufficient for the complete store trajectory problem.

#### ATC Shopping Center

Provides long metric pedestrian trajectories from range sensors, not standard RGB CCTV. Excellent for testing later dwell/flow/bottleneck analytics independently of vision errors.

The full machine-readable comparison is in:

- `datasets/dataset_catalog.csv`

Detailed literature/data notes are in:

- `research_datasets_indoor.md`
- `research_multicamera.md`

---

## 6. Required architecture implication: do not treat tracking as one problem

The tracking stack should be split into three identity scopes.

### A. Detection

Output:

```text
camera_id
timestamp
bbox
confidence
optional mask/keypoints
```

### B. Local per-camera track

Output:

```text
camera_id
local_track_id
timestamp
bbox
foot_point
track_confidence
optional appearance embedding
```

ByteTrack/BoT-SORT operate primarily here.

### C. Global session trajectory

Output:

```text
global_session_id
timestamp
camera_id
local_track_id
x, y or section_id
association_method
association_confidence
```

This identity should be temporary and operational, not a persistent real-world identity.

---

## 7. Recommended local tracker strategy

Do not choose ByteTrack or BoT-SORT from reputation alone.

Recommended test order:

1. Detector + ByteTrack baseline.
2. Detector + BoT-SORT baseline.
3. Compare on the same videos using:
   - HOTA if available,
   - IDF1,
   - ID switches,
   - fragmentation,
   - recall/misses,
   - runtime FPS.
4. Inspect errors specifically at:
   - people crossing,
   - shelf occlusion,
   - carts hiding legs,
   - queue crowding,
   - entry/exit frame borders.

The MOT17 test suggests that improving detector recall may have more impact than micro-tuning the tracker, because both trackers missed many person instances.

For fixed store cameras, disable/avoid unnecessary camera-motion compensation unless it improves measured results. For PTZ or shaky cameras, compensation becomes more relevant.

---

## 8. R3: image position to floor coordinate or section

### Preferred person location point

Use the bottom-center of the bounding box as the first approximation to foot contact:

```text
u = (x1 + x2) / 2
v = y2
```

This is usually more meaningful for floor mapping than the box center.

Possible improvement:

- use pose/keypoints to estimate visible ankle/foot location;
- infer the foot point when legs are occluded;
- attach a projection confidence score.

### If homography is available

For floor point `p = [u, v, 1]^T`:

```text
p_world ~ H * p_image
```

Normalize by the third homogeneous coordinate.

This works when the target is approximately on the calibrated ground plane.

### If full camera calibration is available

Use intrinsics/extrinsics plus the floor-plane equation to cast the image ray onto the floor. This can be preferable when distortion and full camera geometry matter.

### If calibration is not available

Fallback hierarchy:

1. Manual image-space section polygons.
2. At least four image-floor point correspondences + planar homography.
3. Normalized store coordinates if metric scale is not known.

Do **not** infer metric coordinates from a single arbitrary video without reference geometry and present them as accurate physical positions.

---

## 9. Cross-camera strategy

### 9.1 Overlapping cameras

Use a geometry-first association.

Candidate score:

```text
score =
  w_space * spatial_consistency
  + w_time * synchronization_consistency
  + w_app * appearance_similarity
```

Reject candidates if projected world locations are incompatible at the same timestamp.

Why this is better than appearance-only:

- two people can wear similar clothes;
- the same person's appearance changes with viewpoint;
- simultaneous common-ground coordinates are a much stronger physical constraint.

### 9.2 Non-overlapping cameras / blind gaps

There is no direct observation during the gap. The problem is therefore a probabilistic data-association problem.

Candidate generation should be gated before expensive appearance matching:

```text
if camera_B not reachable from camera_A:
    reject

if time_gap < min_transition[A,B] or time_gap > max_transition[A,B]:
    reject

if exit_zone_A incompatible with entry_zone_B:
    reject

remaining candidates -> appearance/tracklet matching
```

Then combine:

- body appearance similarity,
- several-frame tracklet embedding rather than one crop,
- transition-time probability,
- route distance / feasible walking speed,
- direction/door constraints,
- previous global trajectory context.

Never force a match when the top candidates are close.

Use states such as:

```text
confirmed
tentative
lost
ambiguous
ended
```

---

## 10. ReID without face recognition

Face recognition is not required for session-level cross-camera tracking.

Useful appearance cues:

- clothing colors/textures,
- body silhouette,
- footwear/bag/backpack,
- temporal aggregation over multiple crops,
- pose-normalized body features where useful.

Avoid claiming full anonymity. A system intentionally linking one person's movements across cameras is better described as **pseudonymous session tracking**.

Recommended privacy design:

- do not use face recognition;
- optionally mask/crop head regions before body embedding extraction;
- use random session-scoped IDs;
- expire IDs after exit/timeout;
- retain coordinates/zone events longer than raw crops;
- keep appearance embeddings only for the active association window;
- process on-premise/edge where practical;
- never link session IDs to payment, name, phone, loyalty account, or previous-day identity.

---

## 11. Metadata: what is actually necessary

### R1 minimum

- video/stream,
- camera ID,
- resolution,
- frame order / FPS.

### R2 strongly recommended

- accurate timestamps,
- true FPS,
- dropped/duplicated-frame information,
- fixed vs PTZ status.

### R3 section-level

- representative frame,
- section/zone polygons in image coordinates.

### R3 metric/common-coordinate

- floorplan and coordinate system,
- homography or camera intrinsics/extrinsics,
- lens distortion if relevant,
- calibration resolution/cropping details,
- known reference points/distances.

### R4A overlap

- synchronized timestamps / measured offsets,
- overlap-pair map,
- common coordinate mapping,
- floor coverage polygons.

### R4B gaps

- camera adjacency graph,
- entry/exit zones,
- route distances,
- reasonable transition-time ranges,
- impossible-transition constraints,
- small labeled handoff validation set.

The full metadata specification and ready-to-send organizer checklist are in:

- `research/CAMERA_METADATA_REQUIREMENTS.md`

---

## 12. What cannot be reliably recovered from video alone

Do not assume we can recover all of the following accurately from arbitrary footage:

- exact physical camera height,
- exact intrinsics/focal length after unknown transcoding/cropping,
- accurate lens distortion,
- exact camera pose in store coordinates,
- metric floor distances,
- the true path a person took during a blind gap,
- identity after long disappearance when multiple similar candidates exist,
- hidden people during complete occlusion,
- exact original timestamps if they were discarded during export.

Some parameters can be approximately self-calibrated, but that should be treated as an optional research enhancement, not as a required assumption for the hackathon architecture.

---

## 13. Recommended evaluation sequence before downstream bottleneck metrics

### Experiment A — fixed-camera local MOT

Use CAVIAR first, then MMPTRACK Retail if available.

Measure:

- detector precision/recall,
- HOTA/IDF1,
- ID switches,
- fragmentation,
- occlusion recovery,
- runtime.

### Experiment B — coordinate accuracy

Use MMPTRACK, NVIDIA PhysicalAI, WILDTRACK, or MultiviewX.

For each tracked person:

1. estimate foot point,
2. project to common coordinates,
3. compare against ground-truth world position.

Measure:

- median position error,
- 90th-percentile error,
- section classification accuracy,
- error vs distance from camera / occlusion.

### Experiment C — overlapping multi-camera fusion

Compare:

1. appearance only,
2. geometry only,
3. geometry + appearance.

Measure:

- global IDF1/HOTA,
- duplicate-track rate,
- wrong-merge rate,
- localization error.

### Experiment D — blind-gap handoff

Use CITIC-MTMC, MTA short subset, or another labeled topology dataset.

Compare:

1. ReID only,
2. ReID + time gating,
3. ReID + time + topology + entry/exit zones.

Measure:

- handoff top-1 accuracy,
- false merge rate,
- false split rate,
- global IDF1,
- ambiguity rate.

For our downstream application, a **false merge is usually worse than a temporary split**, because merging two shoppers corrupts dwell history and path statistics in a way that is hard to undo.

---

## 14. Recommended architecture at this stage

```text
camera stream
    |
    v
person detector
    |
    v
per-camera MOT (ByteTrack / BoT-SORT candidate)
    |
    +--> track quality / occlusion / crop quality
    |
    v
foot-point estimator
    |
    v
image -> floor coordinate OR section assignment
    |
    v
local tracklet record
    |
    +-------------------------------+
    |                               |
    v                               v
overlap association             blind-gap association
geometry + sync + appearance    topology + time + appearance
    |                               |
    +---------------+---------------+
                    |
                    v
        temporary global session ID
                    |
                    v
 timestamp + x/y + section + confidence
                    |
                    v
 downstream dwell / flow / bottleneck analytics
```

Every global point should preserve provenance:

```text
source_camera
local_track_id
timestamp
coordinate_source
calibration_version
association_method
association_confidence
```

This lets downstream analytics distinguish directly observed tracking from inferred blind-gap continuation.

---

## 15. Practical data download strategy under limited disk space

Do not download full giant releases yet.

Recommended order:

1. **CAVIAR selected Lisbon pairs** — small real-retail fixed-camera end-to-end test.
2. **ATC one-day trajectory sample** — downstream trajectory/zone analytics ground truth.
3. **EPFL-RLC** — calibrated real multi-view geometry test.
4. **CITIC-MTMC**, if archive size is acceptable — real topology/blind-gap handoff.
5. **MMPTRACK Retail**, if access/download size is practical — strongest real retail MTMC benchmark.
6. **NVIDIA PhysicalAI** — use only selected scene metadata/ground truth/video files; never pull depth maps or the full multi-TB releases for this feasibility phase.
7. **MTA short subset** — optional controlled non-overlap test if access is granted.

The maintained download plan is:

- `datasets/STARTER_DOWNLOAD_PLAN.md`

---

## 16. Decision for architecture design

We have enough evidence to proceed with architecture design, but the architecture should be conditional on the organizer metadata.

### Safe assumptions

- R1/R2 can run from video and timestamps alone.
- local tracking IDs should be camera-scoped, not treated as global identities.
- section-level dwell can be implemented even without metric coordinates.
- a floor homography/calibration materially improves all spatial reasoning.
- overlapping and non-overlapping camera association require different logic.

### Unsafe assumptions

- pretrained detector/tracker accuracy will automatically be high enough.
- appearance-only ReID will correctly identify every person across cameras.
- camera clocks are synchronized.
- camera geometry can be reconstructed accurately from arbitrary video alone.
- every cross-camera gap has a uniquely identifiable continuation.
- no-face-recognition means no privacy risk.

### Architecture requirement

The system should operate in degraded modes:

1. **Video only:** detection + local tracking + image-space zones.
2. **Video + zones:** reliable section-level dwell/occupancy.
3. **Video + calibration/floorplan:** common-coordinate trajectories and overlap fusion.
4. **Video + calibration + topology + synchronized timestamps:** strongest multi-camera global tracking.

This prevents the entire project from depending on metadata the organizers may not provide.

---

## 17. Immediate next technical milestone

Before implementing bottleneck metrics, run the following validation matrix:

| Test | Dataset | Pass condition for proceeding |
|---|---|---|
| Fixed-camera local ID stability | CAVIAR / MMPTRACK | IDF1/HOTA acceptable for dwell use; failures understood |
| Floor projection | MMPTRACK / PhysicalAI / WILDTRACK | position/section errors quantified, not visually guessed |
| Overlap fusion | WILDTRACK / MMPTRACK | fused method beats appearance-only on wrong merges/duplicates |
| Blind-gap handoff | CITIC-MTMC / MTA | topology+time improves over ReID-only; ambiguity handled |
| Real-mall appearance | MALL-VLM / organizer data | similar-clothing/viewpoint failures measured |

Only after this should the downstream dwell, density, queue and bottleneck scoring layer be treated as the main optimization target.

---

## 18. Workspace index

### Research

- `research_datasets_indoor.md` — indoor/retail dataset survey.
- `research_multicamera.md` — multi-camera/ReID/topology dataset and strategy survey.
- `research/CAMERA_METADATA_REQUIREMENTS.md` — full organizer metadata requirements and checklist.
- `research/FEASIBILITY_STUDY.md` — this consolidated decision document.

### Dataset planning

- `datasets/dataset_catalog.csv` — machine-readable catalog.
- `datasets/STARTER_DOWNLOAD_PLAN.md` — storage-conscious acquisition plan.

### Experiments

- `experiments/mot17_11_tracker_eval_scaled.json`
- `experiments/epfl_homography_check.json`
- `experiments/physicalai_metadata_check.json`
- `experiments/reid_baseline_resnet50.json`
- `experiments/tracker_benchmark_epfl_cam0.json`

### Scripts

- `scripts/evaluate_trackers_mot17.py`
- `scripts/reevaluate_mot17_scaled.py`
- `scripts/verify_homography.py`
- `scripts/verify_physicalai_metadata.py`
- `scripts/eval_reid_baseline.py`
- `scripts/benchmark_trackers_epfl.py`

---

## 19. Bottom line

The project is technically feasible, but confidence is not uniform across the four requirements.

- **R1 person detection:** feasible and standard, but must be tuned/validated for the actual cameras.
- **R2 local tracking:** feasible, with measurable ID-switch/fragmentation risk under occlusion.
- **R3 section mapping:** straightforward; **metric coordinates require calibration/reference geometry**.
- **R4 overlap tracking:** realistically achievable with synchronization + shared geometry + appearance.
- **R4 blind-gap tracking:** possible only as a probabilistic association problem; cannot be guaranteed from appearance alone.

The most important architecture decision is therefore to make confidence, metadata availability, and ambiguity first-class parts of the system rather than hiding them behind a single global person ID.
