# Dwell-Time & Bottleneck Mapper — Three Error-Aware Architecture Options

Date: 2026-10-04

Root: `C:\Coding\ML\Everseen`

## 1. Scope and new dataset rule

From this point onward, architecture design and validation should use only datasets that satisfy the following conditions:

1. multiple cameras are present;
2. camera calibration is available in a form that supports accurate ground-plane projection (homography or full intrinsic/extrinsic camera model);
3. a common floor/world coordinate system or a sufficiently explicit room/floor map is available;
4. cross-camera identity or position ground truth is available, or the dataset is otherwise strong enough to validate multi-view fusion;
5. the camera network includes overlapping views, non-overlapping/gapped views, or both;
6. the dataset is materially useful for the real retail deployment problem rather than merely convenient for one generic CV subtask.

The **strict core evidence set** is therefore:

- **MMPTRACK Retail** — primary real/staged-retail end-to-end benchmark.
- **NVIDIA PhysicalAI Smart Spaces 2025/2026** — primary large-scale calibrated geometry/MTMC benchmark; use targeted scenes/metadata only.
- **CITIC-MTMC** — primary real indoor blind-gap/topology benchmark.
- **WILDTRACK** — primary real overlap-geometry benchmark.

Secondary qualifying geometry checks may use **EPFL classic multi-camera pedestrian sequences**, **EPFL-RLC**, and **MultiviewX**, but they should not carry the main architecture claim.

The older broader dataset catalog remains useful as research history, but MOT17, MOT20, MALL-VLM, Market-1501, CAVIAR, ATC, CUHK Mall, and similar datasets should **not** be used as the main evidence for the architecture going forward because they are missing one or more of the required geometry/MTMC properties.

The filtered machine-readable list is in:

`datasets/high_suitability_catalog.csv`

---

# 2. Core design principle: analytics must survive imperfect identity tracking

The most important architecture decision is to separate **spatial flow analytics** from **identity-continuity analytics**.

Local trackers will fragment tracks and sometimes switch IDs. Cross-camera ReID will also sometimes be ambiguous. The system must therefore avoid making every downstream metric depend on a perfectly persistent global person ID.

## 2.1 Metrics that can remain useful even if identity fragments

These primarily need reliable spatial observations and duplicate suppression:

- current occupancy;
- density;
- ingress/egress flow;
- throughput;
- section heatmaps;
- flow imbalance;
- queue length at a given instant;
- direction distribution;
- velocity distribution;
- congestion score;
- time-to-congestion;
- flow-conservation residual;
- many cause-of-bottleneck features.

## 2.2 Metrics that genuinely depend on identity continuity

These are more sensitive to fragmentation and false merges:

- per-person dwell time;
- per-person movement history;
- complete store journey;
- individual queue waiting time;
- repeat section visits;
- per-person congestion-attributable dwell;
- unique visitor counts across cameras.

This separation lets us build a useful bottleneck mapper before cross-camera identity is perfect.

---

# 3. Canonical internal representation

Do not let a tracker ID become the system's permanent identity.

Use three levels.

## 3.1 Detection

```text
camera_id
frame_id
timestamp
bbox
detection_confidence
optional keypoints / mask
```

## 3.2 Local tracklet

```text
camera_id
local_track_id
tracklet_id
start_time
end_time
bboxes[]
footpoints_image[]
projected_positions[]
track_quality
appearance_summary (optional)
pose_visibility_summary (optional)
```

A **tracklet** is a contiguous high-confidence fragment. It is deliberately smaller and safer than assuming a local track ID is correct forever.

## 3.3 Global session trajectory

```text
global_session_id
ordered_tracklets[]
section_history[]
world_history[]          # if geometry exists
association_confidence
association_method
ambiguity_state
```

Possible states:

```text
confirmed
tentative
lost
ambiguous
ended
```

The system should be allowed to leave a handoff ambiguous rather than forcing a wrong merge.

---

# 4. Section mapping

Section mapping is the bridge between raw tracking and useful retail analytics.

Examples of sections:

- Entrance
- Produce
- Aisle 1
- Aisle 2
- Promotional display
- Queue approach
- Queue lane A
- Queue lane B
- Checkout service area
- Exit

## 4.1 With shared floor geometry

Each store section is a polygon in the common floor coordinate system.

For a person bounding box:

```text
u = (x1 + x2) / 2
v = y2
```

Use `(u,v)` as the first approximation of floor contact.

For image-to-floor homography `H`:

```text
[X', Y', W']^T = H [u, v, 1]^T
X = X' / W'
Y = Y' / W'
```

Then run point-in-polygon against section polygons.

If full intrinsics/extrinsics are provided rather than a direct homography, cast the image ray onto the known floor plane.

## 4.2 Without a common metric coordinate system

Architecture 1 below can still work if each camera has either:

- an image-to-local-floor transform, or
- manually defined image-space polygons mapped to canonical section IDs.

Example:

```text
Camera C04 polygon P1 -> Section "Aisle_3"
Camera C07 polygon P9 -> Section "Aisle_3"
```

This produces a consistent section-level representation even if the two cameras do not share a precise `(X,Y)` coordinate system.

## 4.3 Boundary jitter must not create fake visits

If a projected footpoint jitters around a polygon boundary, naive logic produces:

```text
A -> B -> A -> B -> A
```

within a second.

Use one or more of:

- minimum persistence time before committing a new section;
- inner/outer polygon hysteresis;
- confidence-weighted soft membership;
- smoothing in world coordinates;
- a boundary buffer in meters/pixels;
- section transition constraints (A may not directly connect to C).

Recommended event logic:

```text
candidate_section != current_section
    -> start candidate timer
    -> commit only if persistent for T_enter
    -> otherwise remain in current section
```

For congestion analytics, `T_enter` can be short (e.g. sub-second); for journey history it can be slightly longer.

---

# 5. Tracking architecture should minimize fragmentation instead of merely reporting it

ByteTrack and BoT-SORT are useful local trackers, but neither should be treated as the final identity layer.

ByteTrack's main contribution is recovering true objects from low-score detections instead of discarding them, which directly targets fragmentation under occlusion.

BoT-SORT combines motion and appearance cues and includes a stronger motion model and optional ReID/camera-motion compensation.

The local MOT layer should therefore be followed by a **short-lag tracklet repair layer**.

## 5.1 Tracklet repair within one camera

When local track A ends and local track B begins shortly afterward, compute a stitch score using:

```text
S_stitch =
    w_t * temporal_compatibility
  + w_m * motion_continuity
  + w_s * section_continuity
  + w_g * world_position_continuity
  + w_a * appearance_similarity        # only when useful
  + w_p * pose/visible-part_similarity # optional
```

Reject if:

- time gap is too large;
- implied speed is impossible;
- section transition is impossible;
- two candidate fragments overlap in time;
- geometry strongly contradicts the match.

Use tracklet-level association rather than comparing one frame to one frame.

## 5.2 Why short-lag repair is valuable

It can fix:

- detector dropout for a few frames;
- person briefly hidden behind a shelf/cart;
- local tracker restarting an ID after occlusion;
- low-confidence detections that were not associated online.

It also allows slightly delayed decisions, which are often much safer than irrevocable frame-by-frame identity decisions.

---

# 6. Homography uncertainty must be explicit

Homography is not exact simply because a 3x3 matrix exists.

Sources of error include:

- inaccurate calibration correspondences;
- bounding-box bottom-center not equal to true foot point;
- leg occlusion by carts/shelves;
- lens distortion;
- incorrect image resize/crop after calibration;
- non-planar floors;
- ramps/stairs;
- camera movement after calibration;
- distant people where a small pixel error becomes a large world error.

## 6.1 Practical uncertainty estimate

For each camera store:

```text
calibration_RMSE
holdout_reprojection_error
camera_version
image_resolution_used_for_calibration
```

For a projected person, estimate pixel uncertainty `Sigma_p` from footpoint/keypoint confidence.

If homography-parameter covariance `Sigma_H` is available or estimated by bootstrapping calibration points, first-order uncertainty can be propagated with Jacobians:

```text
Sigma_world ~= J_p Sigma_p J_p^T + J_H Sigma_H J_H^T
```

For a hackathon implementation, a very practical alternative is Monte Carlo/bootstrap propagation:

1. perturb calibration correspondences according to measured annotation error;
2. refit `H` many times;
3. perturb footpoint location;
4. project all samples;
5. use the resulting covariance ellipse / percentile radius.

## 6.2 Use uncertainty downstream

Do not output only:

```text
(X,Y) = (12.8, 4.2)
```

Prefer:

```text
(X,Y) = (12.8, 4.2)
sigma_position = 0.24 m
section_probabilities = {Aisle_2: 0.91, Junction: 0.09}
```

If uncertainty overlaps two section boundaries, delay the transition decision.

---

# 7. Basic metrics

## 7.1 Dwell time

For person `i`, section `s`:

```text
D_i,s = sum_t I(i in s at t) * Delta_t
```

With soft section membership:

```text
D_i,s = sum_t P(i in s at t) * Delta_t
```

Important rules:

- merge brief boundary jitter;
- bridge only short high-confidence occlusion gaps;
- distinguish **complete dwell** from **censored dwell** when entry or exit was not observed;
- keep a confidence value for every dwell event.

### Censored dwell

If a person first appears already inside a section, true dwell started before observation. The measured dwell is a lower bound.

Similarly, if the track disappears inside a section, the end time is uncertain.

Store:

```text
dwell_seconds
entry_observed: true/false
exit_observed: true/false
dwell_confidence
```

This avoids pretending fragmented tracks provide exact dwell times.

## 7.2 Occupancy

```text
O_s(t) = number of spatially unique people in section s at time t
```

In overlapping cameras, first fuse/deduplicate observations; do not count camera detections directly.

Occupancy is largely identity-independent and should remain one of the most reliable metrics.

## 7.3 Density

If section area `A_s` is known:

```text
rho_s(t) = O_s(t) / A_s
```

For continuous world coordinates, local density can also be estimated using a grid, kernel density, or Voronoi cells.

## 7.4 Heatmap

Two useful heatmaps are different:

1. **presence heatmap** — where people are observed frequently;
2. **dwell heatmap** — where cumulative person-time is high.

With positional uncertainty, use a Gaussian/kernel contribution rather than one hard pixel:

```text
H(x) = sum_observations K(x - x_i ; Sigma_i)
```

## 7.5 Per-person section movement history

Compress frame-level labels into section events:

```text
Global 27:
Entrance  14:02:11 -> 14:02:18
Aisle_1   14:02:18 -> 14:03:04
Aisle_3   14:03:04 -> 14:04:12
Queue     14:04:12 -> 14:06:03
Checkout  14:06:03 -> 14:06:58
Exit      ...
```

Store confidence per transition.

## 7.6 Boundary flow / throughput

For a directed section boundary `(a -> b)`:

```text
F_a->b(t, Delta) = count of valid crossings during [t, t+Delta]
```

Use confirmed geometric crossings rather than raw section-label changes whenever possible.

---

# 8. Advanced metrics and non-obvious concepts

The concepts below include both established pedestrian/queueing ideas and project-specific derived metrics. Project-specific metrics are explicitly labelled as such.

## 8.1 Speed-density-flow state

Established pedestrian dynamics uses the relationship among:

```text
density rho
mean speed v
flow q
```

At high density, pedestrian speed generally decreases and throughput eventually saturates or degrades; the exact fundamental diagram depends on facility and flow pattern.

For a section:

```text
rho_s(t) = people / m^2
v_s(t)   = robust median world speed
q_s(t)   = boundary throughput or approximately rho * directional_speed * width
```

Do not classify congestion from density alone. A busy wide entrance and a blocked narrow aisle can have similar occupancy with very different speed/throughput behavior.

## 8.2 Flow imbalance — more informative than occupancy alone

Define windowed arrivals and departures:

```text
F_in(s,t)
F_out(s,t)
```

Raw accumulation:

```text
A_s(t) = F_in - F_out
```

Normalized imbalance:

```text
I_s(t) = (F_in - F_out) / (F_in + F_out + epsilon)
```

Interpretation:

- high occupancy + balanced flow: busy but possibly healthy;
- moderate occupancy + strongly positive imbalance: congestion is forming;
- high occupancy + negative imbalance: queue is dissipating.

## 8.3 Flow-conservation residual — project self-diagnosis metric

This is a proposed diagnostic derived from the pedestrian continuity/conservation equation.

Over a time window:

```text
Delta O_s = O_s(t+Delta) - O_s(t)
Expected Delta O_s = Entries_s - Exits_s

R_s = Delta O_s - (Entries_s - Exits_s)
```

Normalized:

```text
r_s = |R_s| / (1 + Entries_s + Exits_s)
```

In a well-observed closed section this should remain near zero.

A large persistent residual suggests:

- missed detections;
- duplicated people from overlapping cameras;
- track fragmentation producing false crossings;
- section-boundary jitter;
- calibration drift;
- clock desynchronization;
- an unmodelled entrance/exit.

This should be treated as a **tracking-health indicator**, not as evidence of congestion itself.

## 8.4 Congestion-attributable dwell (CAD) — proposed metric

Plain dwell cannot distinguish shopping interest from forced waiting.

Two complementary definitions are useful.

### A. Congestion-exposure dwell

Let `C_s(t)` be a congestion intensity in `[0,1]` based on density, speed loss, flow imbalance and persistence.

```text
CAD_exposure(i,s) = integral I(i in s) * C_s(t) dt
```

This measures how much of a person's time in the section occurred while the section was congested.

### B. Excess dwell against an uncongested baseline

Learn baseline dwell under low-congestion conditions, conditioned on section and optionally path/time-of-day:

```text
D0 = E[D | section=s, route=r, uncongested]

CAD_excess = max(0, D_observed - D0)
```

Use robust medians/quantiles rather than assuming a Gaussian distribution.

### Why both are useful

A promotional display can have high raw dwell but near-zero CAD if speed/flow remain healthy. A checkout queue can have high CAD because dwell coincides with low speed and accumulation.

## 8.5 Time to congestion (TTC) — project forecast metric

For a simple interpretable baseline, let:

```text
O = current occupancy
O_crit = learned/defined congestion threshold
a = smoothed(F_in - F_out) people/sec
```

If `a > 0`:

```text
TTC = (O_crit - O) / a
```

If `a <= 0`, TTC is infinite/undefined because congestion is not currently accumulating under this linear approximation.

Do not use raw one-second rates. Use EWMA/Kalman/state-space smoothing and publish an uncertainty interval.

Better versions can forecast a multi-feature bottleneck score using:

- exponential smoothing;
- Kalman/state-space model;
- gradient-boosted model;
- temporal convolution/LSTM/transformer if enough data exists.

The simple model should remain as an interpretable baseline.

## 8.6 Dynamic queue topology — proposed graph representation

A checkout queue is not always a rectangular polygon. It can curve, split into lanes, merge, or spill into another aisle.

Represent a live queue as a graph:

```text
node = tracked person
edge i -> j = j is the likely predecessor of i toward the service point
```

Inputs:

- service point location;
- person world positions;
- heading/velocity;
- low-speed/stationary evidence;
- proximity to expected queue corridor;
- temporal ordering/progress toward service;
- section topology.

For a simple single-lane queue:

1. define/follow a centerline toward the service point;
2. project each candidate onto centerline progress coordinate `s`;
3. sort by distance-to-service;
4. require neighboring people to be spatially plausible and moving in the same general direction.

For serpentine/multi-lane queues:

- learn/follow a principal curve from recent queue trajectories;
- cluster lateral position into lanes;
- represent merges as graph junctions.

Outputs:

- queue membership probability;
- queue order;
- physical queue length;
- people count;
- per-person wait estimate;
- service rate;
- lane imbalance;
- queue-tail position;
- spillback risk.

## 8.7 Queueing consistency using Little's Law

In a sufficiently stable observation window:

```text
L ~= lambda * W
```

where:

- `L` = average number of customers in queue/system;
- `lambda` = average effective arrival rate;
- `W` = average waiting/sojourn time.

This is useful as a **long-window consistency check**, not an instantaneous identity.

If direct measured `L`, `lambda`, and `W` strongly disagree for long periods, inspect tracking/queue-membership quality or system non-stationarity.

## 8.8 Direction / velocity entropy

Congestion can involve disordered motion even when average speed and density alone look similar.

Compute histograms over heading and optionally speed magnitude:

```text
H_dir = - sum_k p_k log(p_k)
```

High directional entropy or multimodality can indicate:

- counterflow;
- crossflow;
- people detouring around an obstruction;
- disorganized congestion.

This is especially useful at aisle intersections.

## 8.9 Counterflow index

Given the expected main flow direction `d_s`:

```text
Counterflow = fraction of moving people with dot(v_i, d_s) < -tau
```

High counterflow combined with speed reduction and density increase is a strong bottleneck feature.

## 8.10 Path tortuosity / detour index

```text
Tortuosity_i = actual_path_length / shortest_feasible_path_length
```

Unexpected increases can indicate:

- obstruction;
- temporary display/cart blocking an aisle;
- crowd avoidance behavior.

## 8.11 Stop-go oscillation score

Track section-level median speed over time.

Repeated oscillation between near-zero and moving states can indicate stop-and-go waves or unstable queue discharge.

Possible measures:

- number of threshold crossings per minute;
- speed autocorrelation;
- spectral power in a low-frequency band;
- repeated acceleration/deceleration events.

## 8.12 Congestion hysteresis state

Use different thresholds for entering and leaving congestion:

```text
enter congestion if score > T_high for K seconds
leave congestion if score < T_low for M seconds
T_low < T_high
```

This avoids alert flapping and reflects the fact that queue buildup and recovery can behave differently.

## 8.13 Spillback risk

For a dynamic queue, track the queue-tail position relative to upstream boundaries.

```text
spillback_distance = distance(queue_tail, upstream_section_boundary)
```

Forecast when the tail will cross into an aisle/intersection.

This is often more operationally important than current queue length.

## 8.14 Observability score — proposed reliability metric

For every section, maintain a live observability score using:

- number of cameras covering it;
- projected person pixel height;
- average detector confidence;
- occlusion level;
- homography uncertainty;
- timestamp health;
- overlap agreement.

If observability is poor, lower confidence in downstream alerts instead of silently presenting precise numbers.

## 8.15 Overlap agreement score — proposed calibration/tracking health metric

When two cameras see the same world area, compare independently projected positions.

For associated observations:

```text
E_overlap = median ||p_camA - p_camB||
```

Persistent growth can indicate:

- calibration drift;
- timestamp offset;
- wrong cross-camera association;
- incorrect footpoint estimation.

## 8.16 ID churn rate — proposed tracking-health metric

```text
ID_churn_s = number of new local track IDs created in section s / person-minute
```

If occupancy is stable but ID churn suddenly rises, local tracking is fragmenting and per-person dwell becomes unreliable even though occupancy may remain valid.

## 8.17 Spatial density heterogeneity

Two sections can have the same mean density but very different internal structure.

Split a section into cells/Voronoi regions and measure variation in local density:

```text
Heterogeneity_s = variance(local_density_cells)
```

High heterogeneity can reveal a localized choke point even when average section density is moderate.

## 8.18 Crowd pressure / velocity-variance signal

An established crowd-dynamics idea combines local density with variability in pedestrian velocities. A practical section adaptation is:

```text
Pressure_s ~ rho_s * Var(vectors_i)
```

Treat this as a stress/disorder signal rather than a retail bottleneck truth label. It becomes useful at crossings and dense merges where average speed alone hides unstable motion.

## 8.19 Bottleneck severity integral

If `C_s(t)` is the normalized congestion score:

```text
Severity(event) = integral_event C_s(t) dt
```

This differentiates a brief severe spike from a long moderate bottleneck and is useful for ranking chronic operational problems.

## 8.20 Transition matrix

For sections `a,b`:

```text
P(a -> b) = confirmed transitions a->b / all confirmed exits from a
```

Use it for route understanding, impossible-jump detection, topology learning, and as a prior for cross-camera handoff.

## 8.21 Boundary churn

```text
Boundary_churn = number of rapid A<->B flips / person-minute near boundary
```

This should be very low after hysteresis. A spike is a useful diagnostic for bad projection, poorly drawn polygons, or calibration drift.

## 8.22 Trajectory completeness

For each global visit, store whether the system observed:

- a plausible store/camera-network entry;
- the middle of the path;
- a plausible exit.

An incomplete trajectory should not be used to claim exact total visit time or full path statistics.

## 8.23 Metric uncertainty intervals

For important metrics, carry uncertainty from detection/tracking/projection instead of publishing a single precise value.

Examples:

```text
Occupancy: 18.4 expected people, 95% interval [17.1, 19.8]
Queue length: 7.3 m +/- 0.8 m
TTC: 52 s, plausible range 35-88 s
```

Bootstrap over track/projection samples is a practical implementation when analytic propagation is difficult.

---

# 9. Conditional ReID and pose

Do not run appearance matching as the dominant decision mechanism on every frame.

Use ReID **conditionally** when geometry/motion alone is insufficient.

## 9.1 Trigger conditions

Invoke ReID when:

- a local association has two similar candidates;
- a track was lost behind an occluder and multiple people emerge;
- a person exits one camera and appears in another;
- projected geometry overlaps multiple candidates;
- the local tracker's assignment margin is low.

Do not invoke/weight it strongly when:

- crop is tiny;
- person is heavily occluded;
- motion blur is severe;
- most visible pixels are cart/shelf/background;
- geometry already uniquely identifies the match.

## 9.2 Tracklet-level appearance

Aggregate several high-quality crops rather than one frame:

```text
embedding_tracklet = quality_weighted_mean(embedding(frame_j))
```

or use median/prototype aggregation.

## 9.3 Pose-guided visible-part ReID

Pose/keypoints can be used to identify which body parts are actually visible and compare only compatible visible regions.

This is useful for shelf/cart occlusion and large viewpoint changes.

Pose should be an optional second-line cue because it adds computation and can itself fail under heavy occlusion.

## 9.4 Privacy

- do not use face recognition;
- optionally mask the head before appearance embedding extraction;
- use session-scoped embeddings/IDs;
- expire embeddings after handoff/session timeout;
- retain derived trajectories longer than person crops.

---

# 10. Cause-aware bottleneck classification

A bottleneck alert is more useful if it explains the likely mechanism.

Recommended classes:

1. **Demand surge**
2. **Service bottleneck / checkout queue**
3. **Physical constriction**
4. **Temporary obstruction**
5. **Counterflow/crossflow conflict**
6. **High engagement / browsing — not a bottleneck**
7. **Tracking/calibration fault — do not trust alert**

## 10.1 Feature vector

```text
occupancy / baseline occupancy
density / baseline density
median speed / free-flow speed
inflow
outflow
flow imbalance
throughput relative to historical capacity
congestion-attributable dwell
direction entropy
counterflow index
queue orderedness
queue service rate
queue-tail position
path tortuosity
flow-conservation residual
homography uncertainty
observability score
```

## 10.2 Interpretable first version

Use rules / decision tree.

Example:

```text
if queue_orderedness high
   and service_rate low
   and inflow > service_rate:
       cause = service_bottleneck

elif inflow sharply increased
     and outflow remains near historical capacity:
       cause = demand_surge

elif direction_entropy high
     and counterflow high
     and speed low:
       cause = counterflow_conflict

elif dwell high
     and flow_imbalance near zero
     and speed outside stopped subgroup is normal:
       cause = likely_engagement

elif conservation_residual high
     or observability low:
       cause = measurement_fault
```

## 10.3 Learned version

Later train a gradient-boosted tree or temporal model using manually labelled bottleneck episodes.

Keep the interpretable features and explanation even if a learned classifier is used.

---

# 11. Architecture 1 — Section-First Topology-Aware Tracklet System

## 11.1 When to use it

Use when:

- cameras are calibrated individually or section polygons can be defined;
- exact common `(X,Y)` geometry across every camera is unavailable or unreliable;
- a floor/section topology is known;
- cameras may have blind gaps;
- reliable section-level analytics matters more than centimeter-level trajectories.

This architecture intentionally avoids making global metric geometry a hard dependency.

## 11.2 Required metadata

Minimum:

- camera IDs;
- timestamps/FPS;
- per-camera section polygons or image-to-floor transform;
- canonical section names;
- section adjacency graph;
- camera coverage/ownership map;
- camera transition graph;
- entry/exit zones.

Strongly recommended:

- approximate travel-time ranges between camera exit/entry pairs;
- approximate section areas;
- known service/checkout points;
- small labelled cross-camera handoff subset.

Shared metric coordinates across all cameras are **not required**.

## 11.3 Pipeline

```text
Camera streams
   -> high-recall person detector
   -> local MOT (ByteTrack / BoT-SORT candidate)
   -> short-lag intra-camera tracklet stitcher
   -> per-camera footpoint
   -> section mapper + hysteresis
   -> section event stream
   -> topology/time-gated global tracklet associator
         -> conditional body ReID only for ambiguous handoffs
   -> session-level section history
   -> section analytics / queue analytics / bottleneck engine
```

## 11.4 How it limits tracking error

### Fragmentation

Repair local fragments before global association using:

- same camera;
- short time gap;
- same/adjacent section;
- plausible motion;
- appearance only if ambiguous.

### Cross-camera ID switch

Only compare candidates that:

- occur in a reachable next camera;
- appear in a compatible entry zone;
- fall inside feasible transition time;
- do not conflict with another simultaneous observation.

### Double counting without shared geometry

Assign **camera ownership** for each section or sub-region.

Example:

```text
Aisle_2 occupancy source = Camera_04
Queue entrance count source = Camera_07 line L2
```

Use secondary cameras for identity continuation and redundancy, not independent occupancy addition.

This sacrifices some multi-view precision but prevents uncontrolled duplicate counts.

## 11.5 Metrics supported well

- section occupancy;
- dwell time by section;
- section heatmap;
- section transition matrix;
- entry/exit flow;
- flow imbalance;
- congestion-attributable dwell at section level;
- simple TTC;
- dynamic queue membership/order if service area geometry is known;
- cause-aware section bottleneck classification.

## 11.6 Metrics limited

- exact m/s speed if no shared scale;
- fine-grained local density map;
- centimeter-level queue length;
- precise overlap-camera spatial fusion.

## 11.7 Best validation datasets

1. **CITIC-MTMC** — ideal: room/door graph, visibility polygons, calibrated cameras, real world coordinates, blind transitions.
2. **MMPTRACK Retail** — convert world positions into artificial store sections and test section handoffs.
3. **EPFL-RLC / EPFL classic** — secondary calibrated indoor geometry sanity checks; use them for section/projection behavior rather than as the primary identity-handoff proof.

## 11.8 Main strengths

- least fragile deployment requirements;
- highly explainable;
- easier to build in a 48-hour prototype;
- useful metrics do not collapse if exact world geometry is missing;
- topology strongly reduces ReID search space.

## 11.9 Main limitations

- coarse spatial analytics;
- overlap cameras cannot be optimally fused without common geometry;
- blind-gap identity still depends partly on appearance;
- camera ownership reduces redundancy for occupancy.

---

# 12. Architecture 2 — Geometry-First Shared-Floor Fusion

## 12.1 When to use it

Use when the organizer can provide the metadata package we should ideally request:

- calibrated cameras;
- synchronized timestamps;
- shared floor/world coordinate system;
- floorplan;
- camera coverage/overlap polygons;
- topology for blind gaps.

This is the strongest practical architecture if that metadata is available.

## 12.2 Required metadata

- camera ID;
- image size/FPS/timestamps;
- clock offset/drift;
- intrinsics/extrinsics or image-to-common-floor homography;
- distortion/crop information;
- common floor coordinate system;
- floorplan and section polygons;
- camera coverage polygons;
- overlap pairs;
- camera adjacency/entry-exit mapping for blind gaps.

## 12.3 Pipeline

```text
Camera streams
   -> person detector
   -> local MOT
   -> local tracklet repair
   -> footpoint estimator
         bbox bottom-center baseline
         pose/keypoint refinement when reliable
   -> image-to-world projection + covariance
   -> per-camera world-space tracklet smoother
   -> overlapping-camera fusion / duplicate suppression
         geometry + time dominant
         appearance secondary
   -> global trajectory manager
   -> blind-gap handoff
         topology + transition time + conditional ReID
   -> uncertainty-aware world trajectories
   -> section mapper
   -> analytics / queue / forecasting / cause engine
```

## 12.4 Key innovation: use shared geometry to repair IDs, not only to draw a map

Suppose local camera A changes a person's ID from 17 to 43 after an occlusion.

If both tracklets project onto a physically continuous path in the world plane, the global stitcher can repair the identity fragmentation.

Likewise, if Camera B overlaps Camera A, simultaneous projected observations of the same physical location provide a strong cross-view constraint.

Geometry therefore helps solve the tracking problem itself.

## 12.5 Overlap association

Candidate pair `(track a, track b)` should satisfy:

```text
|timestamp_a - timestamp_b| < sync_tolerance
world_distance(a,b) < uncertainty_aware_threshold
```

Association cost:

```text
C =
    w_g * Mahalanobis_world_distance
  + w_t * time_error
  + w_a * appearance_distance
  + w_p * pose/visible-part_distance
```

For well-calibrated synchronized overlap, `w_g` should dominate.

## 12.6 Fuse coordinates using uncertainty

If two cameras produce:

```text
p_A with covariance Sigma_A
p_B with covariance Sigma_B
```

fuse them using inverse-covariance weighting / Kalman update rather than averaging blindly.

Low-quality distant views naturally receive lower weight.

## 12.7 Blind-gap handoff

Once a person leaves all visible coverage:

1. enumerate reachable cameras;
2. restrict to compatible entry zones;
3. apply transition-time distribution;
4. predict a coarse reachable world/section region;
5. compare appearance embeddings only among surviving candidates;
6. preserve ambiguity if top matches are close.

## 12.8 Metrics supported well

Everything in Architecture 1 plus:

- metric speed;
- path length;
- local density;
- world-coordinate KDE heatmap;
- speed-density-flow relationships;
- counterflow index;
- direction entropy;
- path tortuosity;
- physical queue length;
- queue-tail/spillback distance;
- homography uncertainty;
- overlap agreement;
- flow-conservation self-diagnosis;
- geometry-aware congestion score.

## 12.9 Best validation datasets

1. **MMPTRACK Retail** — most direct real-retail end-to-end proof.
2. **NVIDIA PhysicalAI 2025/2026** — large-scale geometry and world-coordinate evaluation.
3. **WILDTRACK** — strong real overlap-fusion test.
4. **CITIC-MTMC** — blind-gap/topology portion.
5. **MultiviewX** — controlled synthetic geometry ablations.

## 12.10 Main strengths

- reduces dependence on appearance ReID;
- overlap cameras become redundancy rather than duplication;
- directly supports accurate sections, speed, density and physical queue length;
- calibration can be quantitatively validated;
- strongest balance of explainability and accuracy.

## 12.11 Main limitations

- requires accurate camera metadata;
- footpoint error propagates into world location;
- planar homography fails on stairs/ramps/split levels unless modeled separately;
- camera movement invalidates calibration;
- blind gaps remain probabilistic despite geometry.

---

# 13. Architecture 3 — Probabilistic Global Tracklet Graph + Predictive Bottleneck Digital Twin

## 13.1 When to use it

Use when the goal is maximum research novelty and minimum identity fragmentation, and enough data/compute is available.

This architecture treats tracking as a **global association problem** rather than accepting local tracker IDs as truth.

Recent multi-camera research increasingly explores global trajectory association rather than only the classic two-stage "single-camera tracking first, cross-camera repair second" pattern. This architecture follows that direction while retaining a practical local detector/tracklet frontend.

## 13.2 Required metadata/data

Everything from Architecture 2 plus preferably:

- historical transition-time distributions;
- labelled cross-camera handoffs;
- enough scenes to train/calibrate an association model;
- examples of queues/bottlenecks for cause prediction;
- consistent calibration versions over long recordings.

## 13.3 Tracklet graph

Create graph node `v_i` for every high-confidence local tracklet.

Candidate edge `e_ij` exists only when tracklets could belong to the same person.

Edge features:

```text
time gap
same/different camera
camera topology probability
exit-zone -> entry-zone compatibility
world endpoint distance
predicted motion consistency
appearance similarity
visible-part/pose similarity
tracklet quality
homography uncertainty
overlap simultaneity
mutual exclusion violations
```

Hard constraints remove impossible edges before learning/optimization.

## 13.4 Association solvers

Three levels of sophistication are possible:

### Baseline

Weighted graph + Hungarian/min-cost-flow association.

### Intermediate

Factor graph / multi-hypothesis tracking with sliding-window delayed decisions.

### Research-heavy

Graph neural network or transformer/global trajectory association model trained to score tracklet-to-global-trajectory matches.

The key requirement is that the global system can revise or delay local associations instead of being permanently damaged by one early ID switch.

## 13.5 Multi-hypothesis identity

For ambiguous gap transitions, preserve:

```text
P(global_12 | tracklet_83) = 0.58
P(global_31 | tracklet_83) = 0.37
P(new_person | tracklet_83) = 0.05
```

Later observations can resolve the ambiguity.

Do not immediately collapse to one answer unless the margin/confidence is sufficient.

## 13.6 Probabilistic dwell/history

When association is uncertain, either:

- report per-person dwell only after identity resolves; or
- maintain expected dwell with posterior weights.

Example:

```text
E[D(global_12, Queue)] += 0.58 * Delta_t
E[D(global_31, Queue)] += 0.37 * Delta_t
```

For operational alerts, occupancy remains based on spatially unique people and does not need this identity uncertainty.

## 13.7 Predictive bottleneck state model

Maintain section state vector:

```text
x_s(t) = [
  occupancy,
  density,
  median_speed,
  inflow,
  outflow,
  flow_imbalance,
  queue_length,
  service_rate,
  direction_entropy,
  congestion_attributable_dwell,
  conservation_residual,
  observability
]
```

Forecast:

- bottleneck probability in 30/60/120 seconds;
- expected time to congestion;
- queue spillback probability;
- recovery time after intervention.

Start with state-space/Kalman or gradient-boosting before using a neural sequence model.

## 13.8 Cause-aware digital twin layer

Represent the store as a graph:

```text
node = section / service point
edge = walkable transition
capacity = learned healthy throughput
state = occupancy/flow/speed/queue
```

This enables reasoning such as:

```text
Entrance demand increased 40%
        -> Aisle junction flow still normal
        -> Checkout outflow did not increase
        -> queue state growing
        -> likely service-capacity bottleneck
```

rather than simply "red heatmap here".

## 13.9 Self-diagnosis before alerting

If:

- flow-conservation residual is high;
- overlap agreement is poor;
- homography uncertainty is large;
- ID churn spikes;
- observability is low;

then mark the bottleneck inference as low confidence and suppress high-severity automatic action.

This is a major advantage over a black-box bottleneck classifier.

## 13.10 Best validation datasets

1. **NVIDIA PhysicalAI 2025/2026** — scale, synthetic supervision, controlled perturbation and global trajectories.
2. **MMPTRACK Retail** — real/staged retail generalization and world-coordinate MTMC.
3. **CITIC-MTMC** — real blind-gap/topology association.
4. **WILDTRACK/MultiviewX** — overlap geometry and uncertainty ablations.

## 13.11 Main strengths

- strongest mechanism for repairing fragmentation/ID switches;
- can delay uncertain decisions;
- naturally combines geometry, topology, timing and appearance;
- supports explicit uncertainty;
- highest research novelty;
- best foundation for prediction and cause-aware bottleneck reasoning.

## 13.12 Main limitations

- highest implementation complexity;
- more compute and memory;
- requires more labelled/calibrated data;
- uncertainty calibration itself needs validation;
- graph/global models are harder to complete convincingly in 48 hours;
- learned models may overfit synthetic datasets unless validated on MMPTRACK/CITIC.

---

# 14. Side-by-side comparison

| Property | Architecture 1: Section-First | Architecture 2: Geometry-First | Architecture 3: Probabilistic Global Graph |
|---|---|---|---|
| Shared world `(X,Y)` required | No | Yes | Yes |
| Per-camera calibration useful | Yes | Required | Required |
| Section graph required | Required | Strongly recommended | Required |
| Precise clock sync | Helpful | Important | Important |
| ReID dependence | Medium for gaps | Low-medium | Conditional / learned fusion |
| Overlap fusion | Coarse / camera ownership | Strong geometry fusion | Joint probabilistic fusion |
| Local fragmentation repair | Short-lag stitcher | World+appearance stitcher | Global graph optimization |
| Handles blind gaps | Yes, topology/time/ReID | Yes, topology/time/ReID | Yes, multi-hypothesis graph |
| Metric coordinates | Optional | Core | Core |
| Dwell/section history | Good | Very good | Best potential |
| Physical queue length | Limited | Strong | Strong |
| Homography uncertainty | Limited/optional | Explicit | Explicit and propagated |
| Flow self-diagnosis | Section-level | Strong | Strongest |
| Cause-aware bottleneck | Rule-based | Rich rule/ML | Rich temporal/graph model |
| Time-to-congestion | Simple | Strong | Predictive |
| Explainability | Highest | High | Medium-high if feature-based |
| 48-hour prototype risk | Low | Medium | High |
| Research novelty | Medium | High | Very high |

---

# 15. Dataset-to-architecture validation matrix

| Dataset | Arch 1 | Arch 2 | Arch 3 | Main proof |
|---|---|---|---|---|
| MMPTRACK Retail | Excellent | Excellent | Excellent | Real retail-like local/global IDs + calibration + world footpoints |
| NVIDIA PhysicalAI 2025 | Good | Excellent | Excellent | Large-scale common geometry, GT, controlled synthetic training |
| NVIDIA PhysicalAI 2026 | Good | Excellent | Excellent | Newest geometry/scale plus selected real-warehouse robustness |
| CITIC-MTMC | Excellent | Very good | Excellent | Floor/room topology, blind transitions, time gating, real-world coordinates |
| WILDTRACK | Limited section semantics | Excellent | Very good | Real overlapping calibrated multi-view fusion |
| MultiviewX | Limited section semantics | Excellent | Very good | Synthetic overlap/calibration perturbation experiments |

---

# 16. Evaluation metrics by layer

## Detection

- recall/precision/AP;
- recall vs person pixel height;
- recall vs occlusion.

## Local tracking

- HOTA;
- IDF1;
- ID switches;
- fragmentations;
- mostly-tracked ratio;
- ID churn rate.

HOTA is particularly useful because it balances detection, association and localization rather than emphasizing only one component.

## Spatial mapping

- median world-position error;
- P90/P95 world-position error;
- section accuracy;
- section-boundary transition precision/recall;
- overlap agreement error;
- error vs distance from camera;
- error vs homography uncertainty estimate.

## Cross-camera tracking

- global IDF1/HOTA if supported;
- handoff top-1 accuracy;
- false merge rate;
- false split rate;
- ambiguity rate;
- wrong-camera candidate rejection rate.

Report false merge and split separately. For this application, false merges are generally more damaging.

## Analytics

- occupancy MAE;
- boundary flow count MAE;
- dwell MAE for complete dwell events;
- queue-count MAE;
- queue waiting-time MAE;
- physical queue-length error;
- bottleneck event precision/recall/F1;
- alert delay;
- TTC MAE/calibration;
- cause-classification macro F1.

## Self-diagnosis

Inject known errors and test whether health metrics detect them:

- drop random detections;
- introduce ID switches;
- perturb homography points;
- add timestamp offset;
- create camera duplicate observations.

Measure AUROC/precision-recall for detecting "analytics unreliable" windows using conservation residual, overlap disagreement, ID churn and observability.

---

# 17. Experiments that should be performed before choosing one architecture

## Experiment 1 — Local fragmentation repair

Dataset: MMPTRACK Retail.

Compare:

1. raw ByteTrack;
2. raw BoT-SORT;
3. best local tracker + short-lag tracklet stitcher;
4. stitcher + conditional appearance.

Primary metrics:

- IDF1/HOTA;
- fragmentations;
- ID switches;
- dwell MAE after section mapping.

## Experiment 2 — Section-only vs world-coordinate mapping

Datasets: MMPTRACK and CITIC.

Compare:

1. image-space section polygons;
2. projected world coordinate + hard polygon;
3. uncertainty-aware world coordinate + soft/hysteretic polygon.

Measure section transition accuracy and dwell error.

## Experiment 3 — Overlap-camera fusion

Datasets: MMPTRACK + WILDTRACK.

Compare:

1. appearance only;
2. geometry only;
3. geometry + appearance;
4. geometry + appearance + uncertainty.

Measure:

- duplicate count;
- false merge rate;
- global IDF1;
- position error.

## Experiment 4 — Blind-gap handoff

Dataset: CITIC-MTMC.

Compare:

1. ReID only;
2. ReID + time gate;
3. ReID + topology + time gate;
4. ReID + topology + time + section/entry-exit constraint;
5. multi-hypothesis delayed association.

This experiment is critical for deciding whether Architecture 3's complexity is justified.

## Experiment 5 — Homography uncertainty

Datasets: NVIDIA PhysicalAI + MMPTRACK/WILDTRACK.

Perturb calibration point/matrix parameters and footpoints.

Measure:

- projected position error;
- section transition error;
- density error;
- queue-length error;
- whether estimated covariance predicts actual error.

## Experiment 6 — Identity-independent bottleneck robustness

Use world GT from NVIDIA/MMPTRACK to generate clean analytics, then deliberately fragment IDs.

Compare degradation of:

- occupancy;
- flow;
- queue length;
- dwell;
- per-person journey;
- bottleneck score.

The target result is that occupancy/flow/bottleneck detection degrade much less than per-person journey metrics.

## Experiment 7 — Flow-conservation self-diagnosis

Inject:

- missed frames;
- false detections;
- duplicate camera counts;
- boundary jitter;
- clock offset.

Verify whether conservation residual and overlap agreement flag the corrupted windows.

## Experiment 8 — Cause-aware bottleneck toy scenarios

Use synthetic or annotated sequences for:

- demand surge;
- slow service;
- physical obstruction;
- counterflow;
- browsing/engagement.

Test whether the feature-based classifier can distinguish them without using an opaque end-to-end model.

---

# 18. Current interpretation of the three options

No architecture should be selected finally yet.

### Architecture 1 should be treated as the deployment-safe fallback.

It proves the product can work at section level even if the organizer does not give a perfect shared coordinate frame.

### Architecture 2 should be treated as the strongest practical target when shared geometry exists.

It uses calibration to reduce the exact tracking errors we are worried about, rather than merely using homography for visualization.

### Architecture 3 should be treated as the research/novelty branch.

It directly attacks the weakness of the classic two-stage MTMC pipeline — local fragmentation propagating into global IDs — by making tracklet association global, delayed and probabilistic.

The next phase should quantitatively compare these three approaches on the shortlisted datasets before choosing one for the final hackathon proposal.

---

# 19. Primary literature/technical foundations used in this design

- ByteTrack — Zhang et al., ECCV 2022: associate low-score detections to reduce missed/fragmented tracks.
- BoT-SORT — Aharon et al., 2022: motion + appearance + camera-motion compensation + improved Kalman state.
- HOTA — Luiten et al., IJCV 2021: balanced detection/association/localization tracking evaluation.
- Pedestrian fundamental-diagram literature: density-speed-flow relationships vary with facility and flow pattern.
- Pedestrian macroscopic fundamental diagram: network flow depends on mean density and spatial variation; queue buildup/recovery can show hysteresis.
- Pedestrian continuity equation / Voronoi field formulations: population change and boundary flow should satisfy conservation.
- Little's Law: long-run queue length `L = lambda W` under appropriate stable-system conditions.
- Velocity entropy congestion detection: motion magnitude/direction disorder can detect crowd congestion.
- Pose-guided occluded ReID literature: visible body parts/keypoints can reduce occlusion-induced appearance errors.
- Tracklet/global graph association literature: tracklets can be globally linked using motion, appearance, geometry and topology constraints.
- 2026 GMT global MCMT direction: global trajectory-target association can reduce dependence on errors inherited from purely two-stage local-then-cross-camera pipelines.

Dataset-specific evidence:

- MMPTRACK: https://iccv2021-mmp.github.io/subpage/dataset.html
- NVIDIA PhysicalAI Smart Spaces: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
- CITIC-MTMC: https://github.com/GTEC-UDC/citic-mtmc-dataset
- WILDTRACK: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- MultiviewX: https://github.com/hou-yz/MultiviewX

---

# 20. Immediate next decision questions

Before finalizing architecture, answer experimentally:

1. How much does tracklet repair reduce fragmentation beyond raw ByteTrack/BoT-SORT on MMPTRACK Retail?
2. How accurately can footpoints be projected into sections under realistic calibration/occlusion noise?
3. How much does geometry reduce overlap-camera false associations compared with ReID?
4. How much do topology + transition-time + entry/exit constraints improve blind-gap handoff on CITIC?
5. Can flow/occupancy/bottleneck metrics stay accurate even after deliberately injecting ID fragmentation?
6. Does homography uncertainty correlate with actual section/location errors strongly enough to gate alerts?
7. Does the flow-conservation residual reliably identify tracking/calibration failures?
8. Are dynamic queue topology and TTC accurate enough to add operational value beyond simple occupancy?

Those answers should determine whether the final proposal uses Architecture 1, Architecture 2, or the research-heavy Architecture 3.
