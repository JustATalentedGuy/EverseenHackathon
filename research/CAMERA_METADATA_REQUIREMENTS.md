# Camera Metadata Requirements for Retail Dwell-Time & Bottleneck Mapping

Research basis: `C:\Coding\ML\Everseen\research_multicamera.md`

Purpose: define the camera/site metadata needed for four practical requirements:

- **R1 — Person detection**
- **R2 — Local per-camera tracking**
- **R3 — Image-to-coordinate / store-section mapping**
- **R4 — Cross-camera history**
  - **R4A — Overlapping-camera fusion**
  - **R4B — Non-overlapping / blind-gap handoff**

This is a feasibility and implementation guide. It does not make accuracy guarantees. Performance depends on camera placement, resolution, occlusion, crowd density, synchronization, lighting, calibration quality, and how closely validation data matches the deployment.

---

## 1. Quick dependency view

| Requirement | Can work from video alone? | Metadata that changes feasibility most |
|---|---|---|
| R1 Detection | Usually yes | Resolution, FPS, codec quality, camera view, expected person size |
| R2 Local tracking | Usually yes for basic tracking | Stable FPS/timestamps, dropped-frame information, static/PTZ status |
| R3 Coordinate / section mapping | Approximate section labels may be possible; reliable metric coordinates usually need external geometry | Floorplan, homography or camera calibration, reference points/distances, zone polygons |
| R4A Cross-camera overlap | Sometimes, but reliable fusion needs timing + geometry | Clock synchronization, overlap map, calibration/homography, common world coordinates |
| R4B Cross-camera gaps | Appearance-only is possible but fragile | Accurate timestamps, camera topology, entry/exit zones, transition distances/time ranges, floorplan |

Planning rule:

- R1 and R2 are primarily vision problems.
- R3 is primarily a calibration / site-geometry problem.
- R4A is a synchronization + geometry + identity-association problem.
- R4B is a topology + timing + appearance-association problem.

---

# R1 — Person Detection

## Goal

For each frame, detect visible people and return at least:

```text
camera_id
frame_index
timestamp
bbox = [x1, y1, x2, y2]
detection_confidence
```

Optional useful outputs include segmentation mask, body keypoints, estimated foot point, occlusion estimate, and crop-quality score.

## Minimum metadata

The detector can usually operate with:

- stable camera ID,
- decodable video,
- frame resolution,
- nominal FPS or a usable timestamp sequence.

For offline files, filename-to-camera mapping must be unambiguous.

No exact image-quality threshold can be guaranteed. Detection becomes less reliable when people occupy very few pixels, compression destroys body boundaries, shelves/signage cause severe occlusion, or exposure is poor.

## Strongly recommended metadata

Ask for:

- exact camera ID,
- native resolution,
- true source FPS,
- codec/container,
- whether frames were re-encoded, resized, or aspect-ratio changed,
- camera location/role such as entrance, aisle, checkout, corridor,
- fixed/PTZ/fisheye/panoramic/dynamically cropped status,
- sample frame from each camera,
- known privacy masks,
- known low-light periods,
- known duplicated/dropped frames.

Useful scene notes:

- typical crowd density,
- common occlusion sources,
- approximate person size range,
- mirrors/reflections,
- glass doors,
- mannequins/posters/screens that may resemble people.

## What can be estimated from video

Often estimable:

- frame resolution,
- apparent frame rate,
- motion blur,
- compression severity,
- static vs moving camera,
- rough field of view,
- person size,
- crowding,
- illumination variation,
- recurring occlusion regions,
- likely reflection/mirror problems,
- detection confidence,
- crop quality,
- rough occlusion indicators.

## What cannot be reliably recovered from video alone

Do not assume video alone can recover:

- true physical camera height,
- exact focal length,
- exact lens distortion,
- exact camera pose in store coordinates,
- metric scene distances,
- true person count behind complete occlusion,
- exact source capture FPS after transcoding,
- dropped-frame history if timing metadata was lost,
- exact physical explanation of ambiguous reflection-like detections.

## Confidence and limitations

Detection confidence is a quality signal, not proof.

Common retail failure modes:

- partial people behind shelves,
- crowded queues,
- children/seated people,
- carts blocking lower bodies,
- staff uniforms blending into background,
- motion blur,
- backlighting at entrances,
- mirrors,
- advertisements containing people,
- very small distant shoppers.

False negatives break trajectories and undercount dwell. False positives create fake tracks. Per-camera validation is therefore strongly recommended.

## Privacy and security implications

R1 processes identifiable human imagery even without recognition.

Recommended controls:

- local/edge processing where practical,
- restricted access to raw frames,
- short raw-video retention,
- avoid exporting full frames when boxes/counts are enough,
- encrypt stored video/crops,
- log access to raw footage,
- keep stream URLs and RTSP credentials out of source code/reports.

If faces are unnecessary, avoid retaining face crops and consider masking heads before producing reusable appearance features.

---

# R2 — Local Per-Camera Tracking

## Goal

Maintain a temporary identity while a person remains visible in one camera.

```text
camera_id
local_track_id
timestamp
bbox
track_state
track_confidence
optional_appearance_embedding
```

The local ID is only a trajectory handle inside one camera.

## Minimum metadata

Minimum:

- R1 inputs,
- ordered frames,
- reliable frame index,
- approximate FPS or timestamps,
- camera ID.

A tracker can run from frame order alone, but motion and elapsed-time estimates become weaker when timing is irregular or unknown.

## Strongly recommended metadata

Ask for:

- per-frame/per-video timestamps,
- exact FPS,
- variable-frame-rate status,
- dropped-frame indicators,
- timestamp source and precision,
- whether video was sped up, slowed down, sampled, or trimmed,
- fixed/PTZ status,
- PTZ movement logs,
- stabilization/dynamic-crop information,
- recording interruptions,
- restart/reconnect/clock-reset events.

## What can be estimated from video

Often estimable:

- pixel-space motion,
- short-term velocity,
- stationary vs moving state,
- visible occlusion intervals,
- tracklet appearance consistency,
- rough track quality,
- likely entry/exit near frame boundaries.

Short-term continuity can use bounding-box overlap, motion prediction, appearance embeddings, and brief occlusion recovery.

## What cannot be reliably recovered from video alone

Video cannot reliably reveal:

- exact elapsed real time when timestamps are wrong/missing,
- frames dropped before final encoding,
- true physical speed without spatial calibration,
- correct identity after long full occlusion when similar people cross,
- whether a missing person left or is hidden behind an opaque obstacle,
- PTZ orientation history when telemetry is absent,
- exact cause of stream discontinuities.

## Confidence and limitations

Suggested local-track states:

- `confirmed`
- `tentative`
- `occluded`
- `lost`
- `ended`

Track confidence should reflect:

- detector quality,
- track age,
- occlusion duration,
- appearance consistency,
- motion consistency,
- crop size,
- recent ID-switch risk.

Retail-specific failure cases include shopper crossings, queues, family groups, bending near shelves, cart occlusion, long shelf occlusion, and people entering/exiting behind one another.

Local ID switches directly corrupt dwell duration; they should be measured rather than assumed away.

## Privacy and security implications

R2 turns detections into movement history.

Recommended controls:

- random/ephemeral local IDs,
- expire IDs after tracks end,
- do not reuse IDs across days,
- minimize crop retention,
- avoid face-specific features,
- encrypt retained appearance embeddings,
- restrict access to individual trajectories,
- define separate retention for tracking logs and raw video.

---

# R3 — Image-to-Coordinate / Store-Section Mapping

## Goal

Convert a detected person's image location into either:

- global metric coordinate `(x_m, y_m)`,
- normalized coordinate `(x_norm, y_norm)`,
- store section such as `entrance`, `aisle_03`, `checkout_queue`, or `exit`.

For a floor-standing person, the estimated foot contact point or box bottom-center is usually the most useful image point.

## Minimum metadata

### Coarse section mapping

Minimum may be:

- camera ID,
- representative frame,
- manually defined image polygons mapped to section labels.

Example:

```text
camera_07:
  polygon_A -> aisle_3
  polygon_B -> checkout_queue
  polygon_C -> entrance
```

This can support section dwell without metric calibration.

### Global coordinates

Minimum practical metadata is either:

- valid image-to-floor homography, or
- enough image/world correspondences to estimate one.

For a planar floor, at least four non-collinear correspondences are mathematically required, but more well-distributed points are strongly preferred.

Each correspondence needs:

```text
image pixel: (u, v)
known floor point: (X, Y)
```

All cameras must use the same world coordinate system if their trajectories will be fused.

## Strongly recommended metadata

Best-case package:

- floorplan,
- floorplan scale,
- global origin,
- coordinate units,
- camera (x, y, z),
- yaw/pitch/roll or full extrinsics,
- intrinsic matrix,
- lens distortion coefficients,
- image-to-floor homography,
- camera floor-coverage polygon,
- verified landmark correspondences,
- store-section polygons,
- camera height,
- planar/non-planar floor notes,
- stairs, ramps, escalators, split levels,
- calibration date/version,
- calibration residual/error,
- crop/resize transform applied after calibration.

## What can be estimated from video

Possible estimates:

- vanishing directions,
- rough perspective structure,
- approximate ground plane under favorable geometry,
- rough camera orientation,
- visual correspondences,
- homography when world reference points are manually supplied,
- section polygons by manual annotation,
- approximate overlap between views when shared landmarks are visible.

If a floorplan exists, useful manual correspondences can often be created from aisle corners, shelf endpoints, tile intersections, checkout corners, doors, and floor markings.

## What cannot be reliably recovered from video alone

Without known physical references, video alone generally cannot reliably recover:

- absolute metric scale,
- exact store-coordinate origin,
- exact camera height,
- exact extrinsics,
- accurate floorplan geometry,
- distances behind shelves,
- business-defined section boundaries,
- exact correspondence of similar-looking landmarks across cameras,
- correct global coordinates for non-planar regions using one planar homography,
- accurate foot coordinates when feet are continuously occluded.

Monocular self-calibration can provide estimates, but these should not be treated as ground truth for a deployment requiring spatial accuracy.

## Confidence and limitations

R3 output should include:

```text
world_x
world_y
zone
projection_confidence
source_camera
calibration_version
```

Confidence should account for detection quality, foot visibility, calibration residual, image-boundary distance, distortion, calibration coverage, and whether the person is on stairs/escalators.

Important limitations:

- box bottom-center is only an approximation of foot contact,
- occlusion can shift the apparent foot point,
- carts/shadows may distort boxes,
- planar-homography error grows when assumptions fail,
- small camera movements can invalidate calibration,
- post-calibration crop/resize can invalidate mappings unless transformed correctly.

For a hackathon, section-level mapping may be more defensible than claiming fine metric precision.

## Privacy and security implications

R3 creates spatial movement data that can reveal where someone waited, how long they stayed, and which areas they visited.

Recommended controls:

- store only needed spatial precision,
- prefer section IDs when fine coordinates are unnecessary,
- aggregate historical analytics,
- restrict access to person-level trajectories,
- expire session trajectories,
- keep geometry/config files separate from camera credentials.

Floorplans and camera positions are security-sensitive infrastructure data and should be treated as restricted configuration.

---

# R4 — Cross-Camera History

## Goal

Link local tracks into one temporary visit-level trajectory.

```text
global_track_id
  camera_01 local_17  10:05:02-10:05:20
  camera_03 local_04  10:05:18-10:06:11
  camera_08 local_31  10:06:24-10:07:40
```

The system should allow uncertainty. A global match should not be forced only because one candidate has the best score.

Suggested association output:

```text
candidate_global_id
association_score
association_confidence
evidence = [appearance, time, topology, spatial_overlap]
status = confirmed | tentative | ambiguous | rejected
```

---

# R4A — Cross-Camera History with Overlapping Views

## Minimum metadata

Minimum practical metadata for fusing simultaneous observations:

- stable camera IDs,
- knowledge of which camera pairs overlap,
- approximate temporal alignment,
- some way to compare location between the two views.

The location relationship can come from:

- shared floor coordinates,
- per-camera homographies to the same floor plane,
- full intrinsic/extrinsic calibration,
- manually defined correspondences or overlap regions.

Appearance-only matching can be attempted without geometry, but it is weaker and should not be treated as equivalent to spatial fusion.

## Strongly recommended metadata

Ask for:

- common clock source,
- per-frame timestamps,
- synchronization accuracy,
- per-camera clock offsets,
- clock drift,
- camera intrinsics,
- extrinsics,
- homographies,
- common world coordinate system,
- floor-coverage polygons,
- overlap polygons,
- valid calibration region,
- camera position/orientation,
- distortion coefficients,
- known occlusion structures within overlaps.

Best-case camera record:

```text
camera_id
timestamp
K
distortion
R
t
homography_to_floor
floor_coverage_polygon
overlap_with = [...]
```

## What can be estimated from video

When overlap is visually substantial, video may allow estimation of:

- whether two views overlap,
- rough temporal offset from shared moving people/events,
- cross-view landmarks,
- approximate relative geometry,
- approximate homography when shared floor landmarks are visible,
- approximate simultaneous identities using appearance and motion.

For fixed cameras, repeated shared events can sometimes estimate a timing offset.

## What cannot be reliably recovered from video alone

Difficult or unreliable to recover:

- guaranteed frame-accurate synchronization,
- long-term clock drift,
- exact metric scale,
- high-quality extrinsics when overlap is narrow/feature-poor,
- correct person correspondence in dense crowds with similar clothing,
- hidden overlap behind shelving,
- exact floor geometry without physical references,
- true simultaneous timing after independent trimming/re-encoding.

A plausible cross-camera match can still be wrong. Geometry and timestamps reduce ambiguity but do not remove it.

## Confidence and limitations

Use multiple independent cues:

1. temporal proximity,
2. projected world-coordinate proximity,
3. body appearance,
4. movement direction,
5. camera overlap constraints.

Simultaneous visibility in calibrated, synchronized cameras generally provides stronger evidence than a blind-gap handoff.

Confidence drops with:

- loose synchronization,
- inaccurate calibration,
- dense crowds,
- hidden feet,
- strong viewpoint changes,
- tiny person crops.

Keep the evidence behind each association rather than only the final global ID.

## Privacy and security implications

Overlap fusion increases tracking persistence.

Recommended controls:

- ephemeral global IDs,
- no face recognition,
- optional head masking before appearance embedding,
- retain cross-camera crops only when needed for debugging,
- expire appearance embeddings after the session,
- restrict floorplan/calibration files because they expose surveillance coverage.

---

# R4B — Cross-Camera History across Non-Overlapping Cameras / Blind Gaps

## Minimum metadata

A blind-gap handoff can technically be attempted using:

- camera IDs,
- timestamps,
- body appearance/ReID tracklets.

Appearance-only handoff is fragile in retail scenes because of similar clothing, staff uniforms, family groups, orientation changes, and long unseen intervals.

For a practically defensible blind-gap system, the minimum should also include:

- camera adjacency or feasible-transition graph,
- entry/exit regions for each camera,
- approximate clock alignment.

Example topology:

```text
camera_01.exit_right -> camera_03.entry_left
camera_01.exit_front -> camera_04.entry_back
camera_03 cannot directly reach camera_08
```

## Strongly recommended metadata

Ask for:

- synchronized timestamps or measured clock offsets,
- clock drift,
- floorplan,
- camera positions,
- camera coverage polygons,
- camera adjacency graph,
- entry/exit polygons,
- walking paths between camera regions,
- approximate path distances,
- minimum/typical/maximum transition times,
- directionality constraints,
- stairs/escalators/doors,
- one-way passages,
- known blind regions,
- access restrictions that affect possible routes.

For evaluation, strongly request:

- sample ground-truth handoffs,
- manually annotated cross-camera IDs for a short validation clip,
- empirical transition-time examples between neighboring views.

## What can be estimated from video

With enough observations and some already-confident matches, the system may estimate:

- common camera-transition pairs,
- empirical travel-time distributions,
- likely camera adjacency,
- recurring exit-to-entry patterns,
- appearance similarity between tracklets,
- direction of travel at exit/entry.

A bootstrap approach is possible:

1. start from high-confidence appearance matches,
2. estimate frequent transitions,
3. estimate time distributions,
4. use those priors for later association.

The learned topology should still be checked against site reality.

## What cannot be reliably recovered from video alone

Blind regions create ambiguity that observation cannot remove.

Video alone cannot reliably tell:

- which path a person took while invisible,
- whether they stopped in a blind region,
- whether they exited and re-entered,
- whether visually similar people crossed in the blind region,
- true path distance without site geometry,
- whether a transition is physically impossible when topology is unknown,
- exact transition-time limits without repeated evidence,
- identity through a long gap when appearance is weak or changed,
- whether a person removed/added a jacket, bag, or other strong appearance cue.

The system can only infer a plausible continuation from available evidence.

## Confidence and limitations

Blind-gap associations should be conservative.

Useful evidence:

- tracklet appearance similarity,
- exit timestamp,
- entry timestamp,
- camera-pair feasibility,
- exit/entry-zone compatibility,
- feasible travel-time window,
- movement direction,
- prior world/section history.

Suggested interpretation:

- **high confidence:** strong appearance + valid topology + plausible travel time,
- **medium confidence:** multiple supporting cues and no contradiction,
- **low confidence:** appearance-only or weak timing/topology,
- **ambiguous:** multiple candidates with comparable evidence.

For dwell analytics, incorrectly merging two people can be more damaging than splitting one visit into two temporary tracks. Ambiguous handoffs should therefore remain unresolved instead of being forced.

Longer blind gaps should generally reduce association confidence unless strong independent evidence exists.

## Privacy and security implications

R4B is the most privacy-sensitive stage because it deliberately links movement across distinct surveillance regions.

Even without face recognition, body ReID and cross-camera history are pseudonymous person tracking.

Recommended safeguards:

- random session-scoped global IDs,
- reset IDs at store exit or retention timeout,
- avoid cross-day identity matching,
- do not link tracking IDs to payment, loyalty, phone, Wi-Fi, license plate, or other identity systems unless separately approved and necessary,
- avoid face embeddings,
- consider masking heads in ReID crops,
- minimize appearance-vector retention,
- aggregate historical analytics after the operational window,
- define a trajectory-retention period,
- encrypt association logs.

---

# 5. Proposed organizer metadata request / checklist

The request should distinguish basic execution, spatial mapping, cross-camera association, evaluation, and privacy/use constraints.

## A. Required for basic execution

For every video/stream:

- [ ] Unique camera ID
- [ ] File/stream mapped unambiguously to camera ID
- [ ] Native resolution
- [ ] Nominal FPS
- [ ] Constant vs variable frame rate
- [ ] Recording start time
- [ ] Timestamp format and timezone/reference clock
- [ ] Whether files were re-encoded, resampled, or trimmed
- [ ] Known dropped/duplicated frames
- [ ] Fixed camera vs PTZ/dynamic view
- [ ] Sample frame from each camera
- [ ] Recording duration
- [ ] Codec/container

## B. Strongly requested for R3 coordinate/section mapping

For every camera:

- [ ] Camera position in a common site coordinate system
- [ ] Camera height
- [ ] Camera orientation
- [ ] Intrinsic matrix
- [ ] Lens distortion coefficients
- [ ] Extrinsic matrix
- [ ] Image-to-floor homography, if available
- [ ] Image size used for calibration
- [ ] Crop/resize applied after calibration
- [ ] Floor-coverage polygon
- [ ] Calibration date/version
- [ ] Calibration residual/error if available

For the site:

- [ ] Floorplan
- [ ] Real-world scale and units
- [ ] Coordinate origin
- [ ] Store-section/zone polygons
- [ ] Known floor reference points visible in cameras
- [ ] Aisle/shelf layout
- [ ] Entrances/exits
- [ ] Checkout/queue regions
- [ ] Stairs, ramps, escalators, or split levels

## C. Strongly requested for R4A overlapping-camera history

- [ ] Overlapping camera-pair list
- [ ] Approximate overlap polygons
- [ ] Common clock source, if any
- [ ] Per-camera clock offset
- [ ] Synchronization precision
- [ ] Clock drift
- [ ] Per-frame timestamps, if available
- [ ] Shared world-coordinate mapping/calibration
- [ ] Known occlusion structures in overlap regions

## D. Strongly requested for R4B blind-gap history

- [ ] Camera adjacency graph
- [ ] Which exits from camera A can reach which entries in camera B
- [ ] Entry/exit polygons per camera
- [ ] Approximate walking routes
- [ ] Route distances
- [ ] Typical transition time
- [ ] Reasonable minimum/maximum transition time
- [ ] One-way/direction restrictions
- [ ] Doors/escalators/stairs affecting movement
- [ ] Known blind regions
- [ ] Known impossible camera transitions

## E. Strongly requested for evaluation

- [ ] Small annotated validation subset for person detection
- [ ] Local track IDs for short clips
- [ ] Ground-truth store coordinate/section for selected frames, if available
- [ ] Cross-camera same-person IDs for selected handoffs
- [ ] Several annotated simultaneous overlap identities
- [ ] Several annotated blind-gap handoffs
- [ ] Evaluation metric definition
- [ ] Coordinate-error tolerance
- [ ] Required dwell-time tolerance
- [ ] Whether ID splits and ID merges are penalized differently

Without a labeled validation subset, the system can demonstrate plausible behavior but cannot objectively establish deployment accuracy.

## F. Privacy, licensing, and security

- [ ] Confirmation organizer is authorized to provide footage
- [ ] Permitted purpose of use
- [ ] Applicable participant/customer notice or consent
- [ ] Video retention rules
- [ ] Whether local storage is allowed
- [ ] Whether cloud processing is allowed
- [ ] Whether person crops may be stored
- [ ] Whether appearance embeddings may be stored
- [ ] Whether outputs may appear in a public demo
- [ ] Whether screenshots/video examples may be published
- [ ] Required deletion date
- [ ] Required encryption/access controls

---

# 6. Concise organizer request

> We are building a multi-camera dwell-time and bottleneck mapper and need to understand the available camera metadata. Could you please confirm, for each camera/video:
>
> 1. camera ID, resolution, FPS, recording start timestamp, and whether cameras are synchronized;
> 2. any clock offset/drift or frame-drop information;
> 3. whether the camera is fixed or PTZ;
> 4. camera intrinsics, distortion coefficients, extrinsics, camera position/orientation, or image-to-floor homography if available;
> 5. a store/facility floorplan with scale and coordinate system;
> 6. camera floor-coverage regions and which camera pairs overlap;
> 7. camera adjacency/topology, entry/exit zones, and approximate travel distances/times for non-overlapping cameras;
> 8. store-section/zone polygons or labels;
> 9. whether any cross-camera person IDs, world-coordinate ground truth, or annotated validation clips are available;
> 10. permitted data use, retention, privacy constraints, and whether derived crops/embeddings can be stored during the challenge.
>
> If full calibration is unavailable, even a floorplan plus several known floor points visible in each camera would help us estimate image-to-floor mappings.

---

# 7. Minimum viable metadata packages

## R1-MIN — detection

```text
camera_id
video
resolution
fps or frame order
```

Expected: person boxes and detection confidence.

Main limitation: no spatial meaning beyond image pixels.

## R2-MIN — local tracking

```text
camera_id
ordered video
fps or timestamps
```

Expected: temporary local IDs inside one camera.

Main limitation: long occlusions can still create ID switches.

## R3-SECTION — section-level mapping

```text
camera_id
representative frame
image-space polygons -> section labels
```

Expected: approximate section occupancy/dwell.

Main limitation: no common metric coordinate system.

## R3-WORLD — world-coordinate mapping

```text
camera_id
homography_to_common_floor
or
camera calibration + floor/world coordinate definition
```

Expected: approximate common floor coordinates.

Main limitation: calibration and foot-point error directly affect position error.

## R4A-OVERLAP — overlap fusion

```text
camera IDs
overlap map
timestamps / measured offsets
shared coordinate mapping
```

Recommended addition: body appearance embeddings.

Expected: same visitor can often be fused across simultaneous overlapping views.

Main limitation: crowding plus timing/calibration error can make matches ambiguous.

## R4B-GAP — blind-gap handoff

```text
camera IDs
timestamps
camera adjacency
entry/exit zones
appearance tracklets
```

Strongly recommended:

```text
floorplan
path distances
transition-time ranges
direction constraints
annotated sample handoffs
```

Expected: probabilistic continuation through unseen areas.

Main limitation: the blind interval is unobserved, so some cases remain fundamentally ambiguous.

---

# 8. Metadata that should be versioned

Treat these as versioned configuration:

- calibration,
- homography,
- camera position/orientation,
- coverage polygon,
- section polygons,
- camera topology,
- transition-time priors,
- timestamp offsets.

Store configuration versions with every derived trajectory.

```text
camera_id: C07
calibration_version: 2026-10-04-v2
topology_version: store_layout_v3
clock_offset_version: sync_run_2026-10-04
```

If a camera is moved, zoomed, digitally cropped, or replaced, its old calibration should be considered invalid until rechecked.

---

# 9. Confidence model for the final system

No single confidence value should be interpreted as certainty. Preserve component evidence:

```text
detection_confidence
local_track_confidence
projection_confidence
appearance_match_score
temporal_consistency_score
topology_consistency
cross_camera_association_confidence
```

For every global trajectory point, keep provenance:

```text
source_camera
local_track_id
timestamp
coordinate_source
calibration_version
association_method
```

This allows later analysis to distinguish:

- direct visible tracking,
- overlapping-camera spatial fusion,
- inferred blind-gap association.

---

# 10. Main feasibility conclusions

1. **R1 detection does not require camera calibration.** Video quality and viewpoint dominate.

2. **R2 local tracking does not require a floorplan.** Reliable timing and a stable camera view improve motion reasoning and make duration measurements meaningful.

3. **R3 is where external camera/site metadata becomes critical.** Section mapping can be manually approximated; common metric coordinates require calibration, homography, or known image/world correspondences.

4. **R4A overlapping-camera history benefits strongly from synchronized cameras and a shared calibrated coordinate system.** Geometry supplies evidence that appearance-only ReID cannot.

5. **R4B blind-gap history remains probabilistic.** Topology, entry/exit zones, and transition-time constraints are the most useful metadata beyond appearance.

6. **The system should expose uncertainty instead of forcing identity continuity.** Ambiguous handoffs should remain ambiguous or split into separate temporary IDs.

7. **Avoiding face recognition does not remove privacy risk.** Cross-camera body tracking is still pseudonymous movement tracking and should use session-scoped IDs, short retention, and controlled access.

8. **The highest-value organizer bundle is:** synchronized timestamps, camera IDs, floorplan, calibration/homographies, coverage/overlap map, camera topology, entry/exit zones, and a small cross-camera ground-truth validation subset.

These inputs support empirical evaluation instead of theoretical assumptions about the camera network.
