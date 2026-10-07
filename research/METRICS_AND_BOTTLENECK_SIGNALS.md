# Metrics and Bottleneck Signals for a Retail Dwell-Time & Bottleneck Mapper

Research date: 2026-10-04

Scope: section mapping, dwell/occupancy/flow analytics, bottleneck detection, queue structure, uncertainty, tracking self-diagnosis, and cross-camera association for the Everseen retail feasibility study.

This document deliberately separates:

- **Established**: standard quantities or methods with a strong literature basis.
- **Adapted**: established traffic, queueing, tracking, or geometry ideas adapted to section-level retail analytics.
- **Proposed heuristic**: a practical project signal that is useful to test, but should not be presented as a validated universal scientific metric until evaluated on the target site.

The formulas below are implementation definitions, not theoretical accuracy guarantees.

---

## 1. Core representation: map tracks to sections before defining business metrics

The most useful abstraction for this project is a temporary visit trajectory in a common floor coordinate system:

    observation_i(t) = {
        global_track_id,
        timestamp,
        x, y,
        zone,
        velocity_x, velocity_y,
        track_confidence,
        projection_confidence,
        association_confidence,
        source_camera,
        calibration_version
    }

Each store section should be represented by a polygon in a common floor plane:

    Z_k = polygon for entrance / aisle / display / checkout / exit / corridor / service area

Also store:

- walkable area A_k in square metres;
- one or more entry/exit boundary segments;
- neighboring sections;
- service point or checkout location when relevant;
- expected travel directions if known;
- whether the section is intended for walking, browsing, waiting, or service;
- camera coverage and confidence map;
- section geometry version.

### 1.1 Section membership

For a projected floor point p_i(t) = (x_i, y_i):

    zone_i(t) = arg containing_polygon(p_i(t))

If polygons overlap, use a deterministic priority or semantic hierarchy.

If no polygon contains the point, assign UNKNOWN rather than snapping the point to the nearest section.

### 1.2 Boundary hysteresis

Raw frame-by-frame polygon membership causes rapid zone flips near boundaries.

Use either:

1. a minimum residence time before committing a transition;
2. an inner/outer hysteresis band around each section boundary;
3. probabilistic section membership from projection uncertainty.

Example rule:

    Confirm A -> B only when:
      p_i(t) is inside B for at least tau_enter seconds
      OR
      cumulative probability of B over a short window exceeds p_enter

This is a **project robustness rule**, not a standard pedestrian-flow metric.

### 1.3 Soft section membership

If the projected floor point has covariance Sigma_xy or Monte-Carlo samples:

    p_i,k(t) = P(person i is in section k at time t)

Then many aggregate metrics can use weighted counts rather than hard assignments.

For example:

    N_k(t) = sum_i p_i,k(t)

This substantially reduces boundary jitter when homography uncertainty is significant.

---

## 2. Common low-level quantities

For section k at time t:

- N_k(t): number of people in the section.
- A_k: usable walkable area of the section.
- rho_k(t) = N_k(t) / A_k: section density in persons per square metre.
- v_i(t): world-space speed of person i.
- vbar_k(t): robust mean or median speed in the section.
- q_in,k(t): arrivals per unit time across defined inbound boundaries.
- q_out,k(t): departures per unit time across defined outbound boundaries.
- F_ab(t): flow from section a to neighboring section b.

For noisy trajectories, calculate these over a window W, for example 5-30 seconds depending on the metric.

An established pedestrian-traffic identity is:

    flow approximately equals density times mean speed

for suitable homogeneous measurement regions and directional definitions. In real retail spaces with browsing, crossing flows, shelves, queues, and heterogeneous motion, this relationship should be used as a diagnostic rather than assumed exactly.

Steffen and Seyfried also show that Voronoi-based density can reduce scatter when local areas contain only a few pedestrians. If world coordinates are reliable, a Voronoi density estimate is a useful alternative to simple N/A density.

---

# 3. Dwell Time

**Status: Established quantity; implementation details are project-specific.**

## Definition

Dwell time is the elapsed time a temporary person trajectory spends inside a section.

For hard section assignment:

    D_i,k = integral 1[zone_i(t) = k] dt

For sampled timestamps:

    D_i,k approximately equals sum_j Delta_t_j * 1[zone_i(t_j) = k]

For soft membership:

    D_i,k^soft = sum_j Delta_t_j * p_i,k(t_j)

Useful section summaries:

- median dwell;
- 75th / 90th / 95th percentile;
- trimmed mean;
- fraction exceeding a business threshold;
- dwell distribution by time of day;
- dwell by entry path or previous section.

## Required inputs / metadata

Minimum:

- stable track ID;
- timestamps;
- section assignment.

Strongly recommended:

- reliable FPS/timestamps;
- section polygons;
- projection confidence;
- local/cross-camera association confidence;
- clear policy for blind gaps and occlusion.

## Sensitivity to tracking / projection errors

Very high sensitivity to:

- ID fragmentation: one real dwell becomes multiple short dwells;
- ID merge: two people become one falsely long dwell;
- dropped detections: dwell undercount;
- boundary jitter: many false exit/re-entry events;
- clock errors: direct duration bias.

Projection error matters most near section boundaries.

## Failure modes

- Shopper becomes hidden behind a shelf and track ends.
- Two similar shoppers cross and IDs swap.
- Person stands exactly on a section boundary.
- Checkout queue spills into an adjacent aisle.
- Cross-camera blind gap is counted as dwell in the wrong section.
- Video file has duplicated/dropped frames.

## Robustification

- Merge short same-ID gaps when motion/topology makes continuation plausible.
- Use boundary hysteresis.
- Store confirmed dwell and uncertain dwell separately.
- Prefer median/quantiles over mean for long-tailed dwell distributions.
- Do not bridge long blind gaps into a section unless the path is actually observed or the section attribution is explicitly marked inferred.
- Keep per-dwell confidence.

## Evaluation

Against manually annotated or ground-truth trajectories:

- dwell MAE per person-section;
- median absolute error;
- relative error for long dwells;
- section-entry/exit timestamp error;
- threshold-event F1, such as dwell > 30 s;
- distribution distance between predicted and true dwell histograms.

Evaluate separately under:

- clean tracking;
- injected ID fragmentation;
- injected ID switches;
- projection perturbation;
- timestamp offset.

ATC is especially useful for analytics-level dwell validation; MMPTRACK Retail and calibrated NVIDIA scenes can test end-to-end dwell from cameras.

---

# 4. Occupancy and Density

**Status: Established.**

## Definition

Occupancy:

    N_k(t) = number of active people in section k

Confidence-weighted occupancy:

    N_k^w(t) = sum_i w_i(t) * p_i,k(t)

where w_i can combine track, projection, and association confidence.

Density:

    rho_k(t) = N_k(t) / A_k

If a section includes shelves or inaccessible space, A_k should be the **effective walkable area**, not the raw polygon area.

## Required inputs / metadata

- section polygon;
- usable area;
- person trajectories or detections;
- timestamps;
- preferably world coordinates.

For image-space occupancy without homography, a camera-specific section polygon is sufficient, but density in persons/m² is not defensible without scale.

## Sensitivity

Occupancy is less sensitive to ID switches than dwell because identity is not needed at a single instant.

It is sensitive to:

- detector false negatives in crowds;
- double counting in overlapping cameras;
- duplicate tracks after occlusion;
- inaccurate overlap fusion;
- wrong section area.

## Failure modes

- Multiple cameras count the same shopper twice.
- Dense queue hides several people.
- Store fixtures reduce real usable area.
- Person crops at image edge are missed.

## Robustification

- Fuse overlapping calibrated-camera observations before counting.
- Use short temporal smoothing, such as EWMA or median filtering.
- Track both raw and smoothed occupancy.
- Maintain camera coverage confidence per section.
- Use Voronoi-based local density where exact world trajectories support it.

## Evaluation

- occupancy MAE / RMSE over time;
- count bias;
- density error;
- peak occupancy error;
- error during crowded intervals separately;
- calibration of confidence intervals.

For bottleneck analytics, peak and upper-tail occupancy are usually more informative than global average occupancy.

---

# 5. Heatmaps

**Status: Established visualization; normalization choices are project-specific.**

## Definition

A dwell/occupancy heatmap accumulates trajectory exposure over a spatial grid.

For cell c:

    H_c = sum_i sum_t Delta_t * 1[p_i(t) in c]

or with a spatial kernel:

    H(x) = sum_i,t Delta_t * K_sigma(x - p_i(t))

Alternative heatmaps:

- visit count;
- unique-track count;
- dwell seconds;
- mean speed;
- congestion score;
- queue probability;
- projection uncertainty.

## Required inputs

- world coordinates or normalized floor coordinates;
- floorplan;
- grid cell size;
- timestamps.

## Sensitivity

- Small projection bias creates systematic shifted hotspots.
- Track fragmentation inflates unique-visitor heatmaps.
- Long stationary tracking errors create false high-dwell hotspots.
- Uneven camera coverage creates false cold spots.

## Robustification

- Normalize by observable time/coverage when cameras have outages.
- Use a bandwidth larger than typical projection error.
- Keep separate layers for dwell time and unique visits.
- Mask inaccessible floor regions.
- Generate confidence/uncertainty heatmaps beside business heatmaps.

## Evaluation

- cell-wise MAE against GT exposure;
- spatial correlation;
- Earth Mover / Wasserstein distance between predicted and GT heatmaps;
- hotspot precision/recall;
- peak-location displacement in metres.

---

# 6. Per-Person Section History

**Status: Established trajectory abstraction; section-state representation is project-specific.**

## Definition

Compress a trajectory into section visits:

    [(entrance, t0, t1),
     (aisle_1, t1, t2),
     (promo_zone, t2, t3),
     (checkout_queue, t3, t4),
     (exit, t4, t5)]

Store:

- entry time;
- exit time;
- dwell;
- confidence;
- observed vs inferred transition;
- source cameras;
- blind-gap duration;
- transition evidence.

## Algorithm

1. Map trajectory points to sections.
2. Apply boundary hysteresis.
3. Run-length encode consecutive section labels.
4. Merge very short A-B-A flicker when B is caused by boundary uncertainty.
5. Retain UNKNOWN intervals instead of silently filling them.

## Required inputs

- local/global track IDs;
- timestamps;
- section map;
- cross-camera handoff confidence if multiple cameras are used.

## Sensitivity

Highly sensitive to identity merges and cross-camera mistakes.

Section history can still be useful with fragmented identities if transitions are analyzed at aggregate level rather than interpreted as complete customer journeys.

## Failure modes

- false A-B-A switching;
- impossible section jump due wrong ReID;
- missing blind-zone section;
- long period incorrectly assigned to nearest visible section;
- multi-floor confusion.

## Robustification

- topology check every transition;
- retain UNKNOWN state;
- confidence per transition;
- reject physically impossible jumps;
- require stronger evidence for cross-camera history than local tracking.

## Evaluation

- section classification accuracy;
- transition precision/recall;
- sequence edit distance;
- path-level exact-match rate;
- dwell-weighted sequence accuracy;
- impossible-transition rate.

---

# 7. Congestion-Attributable Dwell

**Status: Proposed operational heuristic built on established dwell, density and speed concepts. It is not causal proof.**

## Purpose

Raw dwell cannot distinguish:

- intentional browsing;
- queue waiting;
- congestion delay;
- service time;
- tracking failure.

The project should estimate **excess dwell associated with congested conditions**, while clearly calling it an operational attribution.

## Baseline

For each section and movement class, estimate a low-congestion baseline:

    T_free(k, path_class)

Possible baselines:

- median traversal time during low-density periods;
- 20th-30th percentile of traversal time;
- path_length / empirical free-flow speed;
- separate baselines for browsing zones and transit corridors.

## Simple formula

For traversal visit j:

    excess_j = max(0, dwell_j - T_free)

But this alone wrongly calls shopping/browsing time congestion.

## Stronger congestion-gated formula

Define congestion score C_k(t) in [0,1].

Define speed suppression:

    S_i(t) = clip(1 - v_i(t) / v_free,k, 0, 1)

Then:

    CAD_i,k = integral 1[zone_i(t)=k] * C_k(t) * S_i(t) dt

For queue sections, replace speed suppression with queue-membership probability if available.

## Required inputs

- section dwell;
- speed;
- density/occupancy;
- free-flow baseline;
- section semantic type;
- optional queue membership.

## Sensitivity

- Position jitter can create false speed.
- ID fragmentation changes dwell.
- Bad baseline can dominate the result.
- A shopper intentionally standing still resembles congestion.

## Failure modes

- Product display causes legitimate long dwell.
- Service counter is slow but walking area is uncongested.
- Family waits together.
- Promotion/event attracts standing crowd.
- Low frame rate makes speed noisy.

## Robustification

- Use section semantics: transit aisle vs browsing display vs service queue.
- Condition baseline on time-of-day and direction if enough data exists.
- Use median speeds over multi-second windows.
- Require congestion evidence from both crowd state and individual slowdown.
- Report raw dwell and attributable dwell together.
- Never label this as causal delay without controlled evidence.

## Evaluation

Manual-label sample visits as:

- normal traversal;
- browsing;
- queue/service waiting;
- crowd-delay;
- uncertain.

Evaluate:

- attributable-delay MAE;
- binary congestion-delay precision/recall;
- ranking correlation between CAD and human-rated congestion delay;
- robustness across different baseline definitions.

---

# 8. Flow Imbalance

**Status: Adapted from flow conservation and traffic analysis.**

## Definition

For a section over window W:

    I_k = inbound crossing count / W
    O_k = outbound crossing count / W

Net accumulation pressure:

    A_k = I_k - O_k

Normalized imbalance:

    B_k = (I_k - O_k) / (I_k + O_k + epsilon)

B_k near +1 means mostly accumulating inflow; near -1 means draining.

For a bidirectional aisle with directional flows q_plus and q_minus:

    directional_imbalance = abs(q_plus - q_minus) / (q_plus + q_minus + epsilon)

This direction metric is different from accumulation imbalance.

## Required inputs

- section boundary lines/polygons;
- timestamps;
- trajectories;
- direction of crossing;
- topology.

## Sensitivity

Boundary jitter causes repeated false crossings.

Track fragmentation near an entrance causes false arrivals/departures.

Wrong camera synchronization can distort inflow/outflow timing across sections.

## Failure modes

- shopper walks along a boundary;
- detector disappears exactly at boundary;
- entrance/exit not modeled;
- queue extends across section boundary;
- staff enter through unmodeled door.

## Robustification

- directional crossing state machine;
- minimum displacement across boundary;
- crossing cooldown;
- only count confirmed trajectories;
- distinguish external doors from internal transitions;
- aggregate in windows longer than typical tracking jitter.

## Evaluation

- boundary crossing precision/recall;
- inflow/outflow count MAE;
- net accumulation error;
- correlation with true occupancy change.

---

# 9. Time to Congestion

**Status: Proposed forecasting heuristic built on occupancy/flow dynamics.**

## Definition

Time-to-congestion (TTCg) estimates how long remains before a section enters an empirically defined congested state.

First define a threshold:

    N_crit,k

or:

    rho_crit,k

Do not assume one universal density threshold. Estimate the threshold per section from:

- the observed speed-density knee;
- queue spillback onset;
- manual operational labels;
- a service-level rule.

## First-order predictor

Estimate smoothed net arrival rate:

    r_k = q_in,k - q_out,k

If r_k > delta and N_k < N_crit:

    TTCg_k = (N_crit - N_k) / r_k

Otherwise return infinity / no imminent congestion.

## Better forecast

Fit a short horizon state model:

    N(t+1) = N(t) + arrivals(t) - departures(t) + noise

Forecast a distribution for the first threshold crossing.

Output:

- median predicted TTC;
- probability congestion occurs within 30/60/120 s;
- confidence interval.

## Required inputs

- occupancy;
- inflow/outflow;
- congestion threshold;
- stable timestamps;
- preferably historical baseline.

## Sensitivity

TTCg is highly unstable when net rate is close to zero.

Short burst arrivals can produce absurdly short predictions.

Flow count errors accumulate.

## Failure modes

- group arrives briefly then disperses;
- service rate suddenly increases;
- downstream congestion clears;
- camera loses detections just before threshold;
- threshold itself is poorly calibrated.

## Robustification

- EWMA or robust local trend estimation;
- minimum sustained positive net inflow;
- cap prediction horizon;
- probabilistic instead of single-value output;
- condition on opening/closing of checkout lanes if available;
- estimate threshold empirically for each section.

## Evaluation

Define congestion onset manually or from reliable ground truth, then measure:

- TTC MAE;
- median absolute timing error;
- event precision/recall at multiple horizons;
- Brier score for P(congestion within H);
- calibration plots;
- false-alarm lead time.

---

# 10. Dynamic Queue Topology

**Status: Proposed project graph heuristic informed by established queueing and pedestrian-flow concepts.**

## Goal

A single queue-length number is insufficient when retail queues:

- bend around fixtures;
- split into multiple lines;
- merge before service;
- spill into an aisle;
- contain gaps;
- form informal clusters.

Represent the queue as a dynamic graph.

## Candidate queue membership

For person i, calculate:

- low-speed probability;
- dwell duration;
- distance to service area;
- heading toward service direction;
- local neighbor alignment;
- position inside queue catchment region.

Example score:

    Q_i = w1 * slow_i
        + w2 * dwell_i
        + w3 * service_proximity_i
        + w4 * alignment_i
        + w5 * local_density_i

Q_i is a project heuristic and should be trained/calibrated rather than treated as a universal formula.

## Build the queue graph

Nodes:

    active queue-candidate tracks

Edges:

    connect nearby candidates if distance < d_max
    and direction / ordering is compatible

Anchor the graph at:

- checkout/service point;
- lane entrance;
- known service polygon.

Order people by geodesic distance along the queue graph rather than straight-line distance.

## Derived topology metrics

- queue length in people;
- physical queue length in metres;
- number of branches;
- number of service lanes;
- merge/split events;
- head position;
- tail position;
- tail-to-aisle spillback distance;
- queue compactness;
- queue-direction stability.

## Required inputs

Minimum:

- trajectories;
- section/service geometry;
- timestamps.

Recommended:

- service counter/lane locations;
- obstacles/shelves;
- walkable map;
- heading/speed;
- known checkout boundaries.

## Sensitivity

- Track loss in dense queues breaks graph connectivity.
- Projection noise changes nearest neighbors.
- Similar low-speed browsing groups can be mistaken for queues.
- One family/group may stand compactly but not queue.

## Failure modes

- serpentine queue;
- multiple queues merge;
- people reserve a place while moving away;
- trolley creates large spatial gap;
- staff stand in queue region;
- self-checkout has no single service point.

## Robustification

- temporal persistence for membership;
- obstacle-aware/geodesic distance;
- service-direction prior;
- merge components only after sustained proximity;
- use queue state machine: forming, stable, splitting, spilling, clearing;
- allow multiple queues per service region.

## Evaluation

Manual annotations for selected intervals:

- queue membership precision/recall;
- queue length MAE;
- tail-location error in metres;
- queue-order Kendall tau or pairwise-order accuracy;
- split/merge event F1;
- spillback onset timing error.

---

# 11. Homography / Projection Uncertainty

**Status: Established projective geometry plus project-specific uncertainty propagation.**

## Projection

For image point u = (u,v,1):

    x_tilde = H * u
    x = x_tilde_x / x_tilde_w
    y = x_tilde_y / x_tilde_w

The person point should ideally represent floor contact. Bounding-box bottom-center is only an approximation.

## Sources of uncertainty

- landmark annotation error;
- imperfect homography fit;
- lens distortion;
- camera vibration/movement;
- image resize/crop after calibration;
- foot occlusion;
- box error;
- non-planar floor;
- stairs/escalators;
- people standing above/below reference plane.

## Recommended uncertainty model

Do not expose only x,y. Also estimate:

    Sigma_xy

or an empirical radius / confidence ellipse.

### Practical Monte-Carlo method

1. Perturb calibration landmarks according to expected pixel error.
2. Refit H.
3. Perturb detected footpoint according to box/keypoint uncertainty.
4. Reproject repeatedly.
5. Estimate covariance and section-membership probability.

This is easier to audit than assuming one fixed pixel-to-metre error everywhere.

## Calibration diagnostics

Use held-out reference points:

- image reprojection error;
- world-coordinate transfer error;
- median and P90 world error;
- error vs image location;
- error near section boundaries.

Hartley and Zisserman's Multiple View Geometry provides the standard projective geometry foundation; the deployment uncertainty layer above is a practical extension.

## Sensitivity

Homography error is not spatially uniform. A few pixels at the far end of an oblique view can correspond to a much larger floor displacement than near the camera.

## Failure modes

- camera moved after calibration;
- digital crop changed;
- autofocus/zoom changed field of view;
- wrong image resolution used with H;
- floor is not planar;
- feet hidden by cart/shelf.

## Robustification

- version calibration;
- automatic landmark drift checks;
- reject coordinates outside calibrated region;
- probabilistic section assignment;
- use pose ankle keypoints only when reliable;
- fall back to coarse image-space section mapping if metric confidence is poor.

## Evaluation

- median / P90 / max world-position error;
- section classification accuracy;
- boundary-conditioned accuracy by distance to nearest zone edge;
- calibration drift detection recall;
- downstream metric sensitivity after injecting projection noise.

---

# 12. Flow-Conservation Residual / Self-Diagnosis

**Status: Adapted from the conservation identity; proposed as a tracking-system health signal.**

## Definition

For a section over interval [t, t+Delta]:

    predicted occupancy change = arrivals - departures

Observed:

    Delta_N = N(t+Delta) - N(t)

Residual:

    R_k = Delta_N - (I_k - O_k)

Normalized:

    Rn_k = R_k / (I_k + O_k + N_k + epsilon)

For a well-observed closed section, R should fluctuate around zero.

## Why it is valuable

A large residual can indicate:

- missed boundary crossing;
- detector dropout;
- duplicate tracks;
- ID fragmentation;
- unmodeled door;
- camera outage;
- section geometry error;
- overlap double count.

This makes the analytics system partially self-diagnosing.

## Required inputs

- occupancy;
- boundary crossings;
- section topology;
- timestamps;
- known external entrances/exits.

## Sensitivity

Very sensitive to counting convention and section definition.

It is not meaningful if:

- section has unobserved entrances;
- camera coverage is incomplete;
- occupancy and flows are computed from different confidence filters.

## Failure modes

- hidden side entrance;
- person appears from behind shelf inside section;
- queue boundary moves but section polygon is static;
- coverage gap looks like disappearance.

## Robustification

- define conservation-valid sections;
- model external sources/sinks;
- confidence-weighted residual;
- keep residual per camera and per section;
- alert only on sustained deviations;
- suppress during known stream outages.

## Evaluation

Inject controlled faults:

- delete detections;
- duplicate tracks;
- add ID splits;
- remove boundary events;
- introduce camera clock offsets.

Measure:

- detection rate of faults;
- false alarm rate;
- time to detect;
- relationship between residual magnitude and downstream metric error.

---

# 13. Conditional ReID and Conditional Pose

**Status: Adapted from established ReID, pose-guided ReID, and topology-aware MTMC. The conditional-compute policy is project-specific.**

## Principle

Do not run expensive or privacy-sensitive appearance/pose logic on every track at every frame.

Use geometry and temporal continuity first. Invoke ReID/pose when identity ambiguity is high.

### ReID triggers

Examples:

- blind-gap cross-camera handoff;
- two candidate tracks are spatially plausible;
- local tracker recovers after long occlusion;
- appearance is needed to reject a false merge;
- overlapping-camera geometry is insufficient because projection confidence is low.

### Cases where ReID can be skipped

- strong same-camera motion continuity;
- synchronized overlap with high-confidence world-position coincidence;
- obvious impossible topology.

## Conditional pose use

Pose/keypoints are valuable when:

- lower body is occluded and footpoint needs estimation;
- only some body parts are visible for ReID;
- heading/orientation is ambiguous;
- queue posture/orientation helps disambiguate membership.

Pose-guided visible-part matching is supported by established occluded-ReID literature. The project does not need to claim that pose always improves ReID.

## Quality-weighted tracklet embedding

For good crop frames j:

    e_track = sum_j q_j * e_j / sum_j q_j

where q_j can include:

- crop resolution;
- detector confidence;
- visible-body fraction;
- blur score;
- pose visibility;
- occlusion estimate.

Compare tracklets rather than one frame.

## Required inputs

- tracklets;
- crop-quality score;
- camera topology;
- timestamps;
- optional keypoints;
- optional overlap geometry.

## Sensitivity

Appearance changes with:

- camera color response;
- viewpoint;
- illumination;
- coat/bag changes;
- occlusion.

Pose models fail on small or crowded people.

## Failure modes

- two shoppers in similar clothing;
- family/group with matching outfits;
- only back view is visible;
- trolley hides lower body;
- long blind gap;
- wrong camera transition prior.

## Robustification

- topology/time gating before ReID;
- tracklet-level aggregation;
- visible-part matching;
- minimum quality threshold;
- ambiguous state when top candidates are too close;
- avoid forced merge;
- session-scoped IDs only.

## Evaluation

Tracking:

- HOTA;
- AssA / DetA components;
- IDF1;
- ID switch count.

Handoff-specific:

- cross-camera match precision/recall;
- false-merge rate;
- false-split rate;
- handoff latency;
- accuracy vs blind-gap duration.

Efficiency:

- fraction of transitions invoking ReID;
- pose invocation rate;
- compute time saved;
- accuracy degradation or gain relative to always-on ReID.

---

# 14. Cause-Aware Bottleneck Classification

**Status: Proposed project heuristic/classification task.**

## Goal

Detecting congestion is not enough. A useful system should estimate the likely mechanism.

Suggested classes:

1. **Demand surge / capacity shortage**
2. **Service queue**
3. **Merge/intersection conflict**
4. **Counterflow interference**
5. **Physical obstruction / effective narrowing**
6. **Downstream spillback**
7. **Intentional attraction / browsing cluster**
8. **Sensor/tracking artifact**
9. **Unknown**

## Feature set

For each section/window:

- occupancy/density;
- mean/median speed;
- inflow/outflow;
- flow imbalance;
- directional entropy;
- counterflow ratio;
- queue graph state;
- queue tail position;
- density upstream/downstream;
- crowd pressure;
- stop/start oscillation;
- conservation residual;
- camera health;
- section semantics;
- neighboring-section congestion.

## Rule-based starting classifier

Examples:

**Service queue**

    sustained low speed
    + ordered queue topology
    + queue anchored at service point
    + positive arrival/service imbalance

**Merge conflict**

    multiple incoming directions
    + high directional entropy
    + speed drop at junction
    + density concentrated near merge

**Downstream spillback**

    congestion appears downstream first
    + queue tail moves upstream
    + upstream outflow collapses

**Obstruction**

    persistent localized low-capacity region
    + path detours / effective width reduction
    + not explained by demand alone

**Tracking artifact**

    metric anomaly
    + high conservation residual
    + degraded detector/coverage confidence
    + no consistent physical pattern

These are **rules to test**, not validated universal causal criteria.

## Required inputs

- several section-level metrics;
- section topology;
- section semantic labels;
- ideally manually labeled bottleneck episodes.

## Sensitivity

The classifier inherits all upstream errors.

Most confusing pairs:

- browsing cluster vs queue;
- demand surge vs service slowdown;
- obstruction vs camera blind spot;
- downstream spillback vs independent upstream surge.

## Robustification

- require multi-signal agreement;
- temporal persistence;
- use UNKNOWN when evidence conflicts;
- output evidence and confidence;
- train a simple supervised model only after enough labeled episodes exist.

## Evaluation

- per-class precision/recall/F1;
- macro F1;
- confusion matrix;
- onset detection delay;
- calibration of class probabilities;
- inter-annotator agreement for human ground truth.

Evaluate the classifier separately from congestion detection itself.

---

# 15. Additional High-Value Metrics

The following signals are useful because they reveal issues that occupancy or average dwell alone can hide.

## 15.1 Throughput and service rate

**Status: Established.**

At a cross-section:

    q = crossings / time

For a checkout/service queue:

    mu = completed service events / time

Use rolling quantiles rather than only one long-term average.

**Inputs:** boundary crossings, service-completion boundary or service-zone exits.

**Sensitivity:** missed crossings and ID fragmentation near the line.

**Robustification:** line-crossing state machine, manual validation.

**Evaluation:** count MAE and rate error.

---

## 15.2 Little's-Law consistency

**Status: Established queueing relation, adapted as a sanity check.**

For a sufficiently stable queue:

    L approximately equals lambda * W

where:

- L = mean number in system/queue;
- lambda = mean arrival rate;
- W = mean time in system/queue.

Do not expect exact equality in short, non-stationary retail windows.

Use the discrepancy:

    E_Little = abs(L - lambda*W)

as a diagnostic of:

- non-stationarity;
- missed customers;
- bad queue membership;
- wrong dwell boundaries.

---

## 15.3 Speed-density operating point / capacity stress

**Status: Established pedestrian-flow concept; thresholding is site-specific.**

Track:

    (rho_k(t), vbar_k(t), q_k(t))

Rather than choosing a universal congestion density, learn the section's empirical low-density speed and identify where speed degrades as density grows.

Possible normalized stress:

    speed_loss = 1 - vbar / v_free
    density_ratio = rho / rho_ref

Use the joint state rather than density alone.

**Evaluation:** ability to separate manually labeled free-flow vs constrained intervals.

---

## 15.4 Spatial density heterogeneity

**Status: Adapted from pedestrian macroscopic-flow research.**

Two sections can have identical mean density but very different local crowding.

Divide a section into cells:

    CV_rho = std(rho_c) / (mean(rho_c) + epsilon)

or use variance of cell densities.

High heterogeneity may reveal:

- localized blockage;
- lane formation;
- queue spillback;
- unused space;
- obstruction.

The pedestrian macroscopic fundamental diagram literature explicitly notes that spatial density variation can matter for network flow.

---

## 15.5 Directional entropy

**Status: Proposed/adapted signal.**

Bin velocity directions into B angular bins with probabilities p_b.

    H_dir = -sum_b p_b * log(p_b)

Normalize by log(B).

Low entropy:

- mostly one-direction flow.

High entropy:

- crossings;
- merging;
- milling;
- counterflow;
- browsing.

**Sensitivity:** noisy velocities and stationary people.

**Robustification:** exclude speeds below a minimum for direction calculation; compute stationary fraction separately.

**Evaluation:** compare against manually labeled one-way, bidirectional, crossing, and milling intervals.

---

## 15.6 Counterflow conflict index

**Status: Proposed heuristic based on established bidirectional-flow concepts.**

Choose dominant aisle axis a.

Classify moving people by sign(v dot a).

    CFI = 2 * min(q_plus, q_minus) / (q_plus + q_minus + epsilon)

CFI is near 0 for one-way flow and near 1 for balanced opposing flow.

Combine with speed loss:

    conflict_severity = CFI * speed_loss

This prevents healthy bidirectional movement from automatically being called a bottleneck.

---

## 15.7 Crowd pressure / kinetic stress proxy

**Status: Established research metric, but thresholds do not transfer universally.**

Helbing-style crowd pressure:

    P = rho * Var(v)

where the velocity variance is local in space/time.

It is useful for irregular high-density motion, not only slow queues.

For retail, treat it as an exploratory signal. Published critical thresholds from mass-crowd disasters should **not** be reused as universal retail thresholds.

**Sensitivity:** velocity noise can strongly inflate variance.

**Robustification:** world-coordinate smoothing, minimum track quality, robust local variance.

**Evaluation:** compare with annotated unstable/milling/cross-flow intervals.

---

## 15.8 Stop-and-go / oscillation index

**Status: Adapted from established stop-and-go pedestrian-flow observations; project metric is heuristic.**

For section mean speed vbar(t):

    SGI = power in low-frequency oscillatory band / total speed-series power

Simpler implementation:

    count repeated transitions between
      vbar < v_stop
      and
      vbar > v_move

per minute.

Use with density to distinguish:

- a stable slow queue;
- unstable stop-and-go motion.

---

## 15.9 Queue spillback distance

**Status: Proposed operational metric.**

For a queue anchored at service location s:

    spillback_distance = geodesic_distance(s, queue_tail)

Also report:

    blocked_neighbor_sections
    tail_inside_aisle = true/false

This is often more actionable than queue length because a short queue in a narrow junction can be more harmful than a longer queue in a dedicated holding area.

---

## 15.10 Bottleneck persistence and severity integral

**Status: Proposed operational metric.**

Let C_k(t) be normalized congestion severity.

    persistence = duration C_k(t) > threshold

    severity_area = integral C_k(t) dt

This distinguishes:

- brief spike;
- moderate long-running blockage;
- severe sustained bottleneck.

Evaluate onset/offset timing and severity ranking against human labels.

---

## 15.11 Per-person congestion exposure

**Status: Proposed operational metric.**

For person i:

    exposure_i = integral C_zone_i(t)(t) dt

Alternative:

    weighted_exposure_i = integral C(t) * speed_suppression_i(t) dt

Useful for:

- comparing routes;
- measuring how many shoppers are affected;
- separating a localized bottleneck affecting 3 people from one affecting 100.

Do not interpret it as customer dissatisfaction without behavioral evidence.

---

## 15.12 Path efficiency / detour ratio

**Status: Adapted trajectory metric.**

For a known origin and destination:

    detour_ratio = observed_path_length / shortest_walkable_path_length

High values can indicate:

- obstruction;
- queue avoidance;
- browsing;
- route confusion.

Interpretation depends strongly on section semantics.

Projection noise inflates path length, so trajectories must be smoothed before use.

---

## 15.13 Section transition matrix

**Status: Established Markov/flow summary.**

For sections a,b:

    P_ab = transitions a->b / all departures from a

Also retain absolute flow F_ab.

Useful for:

- dominant shopper routes;
- unusual rerouting;
- topology validation;
- expected-next-camera priors.

**Robustification:** exclude low-confidence cross-camera transitions and impossible A->B jumps.

---

## 15.14 Boundary churn rate

**Status: Proposed data-quality metric.**

For person i:

    churn_i = number of A-B-A reversals within tau seconds

High churn near one boundary usually indicates:

- projection jitter;
- bad polygon placement;
- tracking noise.

It can also represent real indecision, so compare with physical displacement.

Use churn as an alert that section-level dwell may be unreliable.

---

## 15.15 Track fragmentation and trajectory completeness

**Status: Established tracking-quality idea; downstream completeness score is project-specific.**

Useful measures:

- HOTA / AssA;
- IDF1;
- ID switches;
- fragments;
- visible-time coverage;
- blind-time fraction;
- fraction of a visit with high-confidence identity.

Proposed trajectory completeness:

    completeness_i =
        high_confidence_observed_time
        / estimated_visit_time

Report business metrics stratified by completeness.

---

## 15.16 Metric uncertainty / confidence interval

**Status: Proposed system requirement.**

Every aggregate should ideally expose uncertainty, not only a point estimate.

For example:

    occupancy = 17.4 expected people
    90% interval = [15.9, 19.1]

Sources:

- detection confidence;
- projection uncertainty;
- association ambiguity;
- camera coverage;
- timestamp uncertainty.

Bootstrap or Monte-Carlo resampling of uncertain trajectory points is adequate for a prototype.

---

# 16. Recommended composite congestion score

**Status: Proposed heuristic for ranking/alerting, not a scientific universal index.**

Avoid one hard-coded magic formula initially.

First retain the component signals:

- density percentile;
- speed loss;
- net accumulation;
- queue spillback;
- stop-and-go;
- crowd pressure;
- directional conflict;
- persistence.

Then a simple normalized score can be tested:

    C =
      w_rho * density_score
      + w_v * speed_loss
      + w_a * accumulation_score
      + w_q * queue_spill_score
      + w_o * oscillation_score

Potentially add:

    + w_p * crowd_pressure_score
    + w_d * directional_conflict_score

Rules:

- learn or tune weights on labeled intervals;
- calibrate per section type;
- show components beside the final score;
- avoid interpreting C as a probability unless probability calibration is explicitly performed.

---

# 17. Bottleneck event state machine

**Status: Proposed operational design.**

A state machine reduces alert flicker:

    NORMAL
      -> BUILDING
      -> CONGESTED
      -> RECOVERING
      -> NORMAL

Possible transition logic:

NORMAL -> BUILDING:

- sustained positive accumulation;
- rising occupancy;
- falling speed.

BUILDING -> CONGESTED:

- congestion score above threshold for tau_on;
- or queue spillback crosses operational boundary.

CONGESTED -> RECOVERING:

- outflow >= inflow;
- occupancy falling;
- speed recovering.

RECOVERING -> NORMAL:

- metrics below lower hysteresis threshold for tau_off.

Use different on/off thresholds to prevent oscillation.

Evaluate event-level precision, recall, onset delay, offset delay, and false alerts/hour.

---

# 18. Error propagation: which metrics survive imperfect tracking?

| Metric | ID switch sensitivity | Projection sensitivity | Detection sensitivity | Timing sensitivity | Relative robustness |
|---|---|---|---|---|---|
| Occupancy | Low-medium | Medium near boundaries | High | Low | High |
| Density | Low-medium | Medium | High | Low | High |
| Heatmap dwell exposure | Medium | High | Medium | Medium | Medium |
| Per-person dwell | High | Medium-high | High | High | Low-medium |
| Section transition counts | Medium-high | High near boundaries | Medium | Medium | Medium |
| Aggregate boundary flow | Low-medium | High at boundary | Medium | High | Medium-high |
| Flow imbalance | Low-medium | High at boundary | Medium | High | Medium |
| Queue length | Medium | Medium-high | High in dense queue | Medium | Medium |
| Queue topology/order | High | High | High | Medium | Low-medium |
| TTCg | Indirect | Medium | High | High | Low-medium |
| Crowd pressure | Low ID dependence | High through velocity | Medium | High | Medium |
| Congestion-attributable dwell | High | Medium-high | High | High | Low |
| Conservation residual | Low-medium | High at boundary | High | High | Diagnostic rather than business metric |
| Cause-aware class | Inherits components | Inherits components | Inherits components | Inherits components | Depends on evidence |

Practical implication:

**Start the demo with robust aggregate metrics, then add person-history metrics only after tracking quality is measured.**

---

# 19. Evaluation framework

The system should be evaluated in layers instead of only comparing the final dashboard.

## Layer A — geometry

Metrics:

- median world-position error;
- P90 world-position error;
- zone accuracy;
- boundary-conditioned zone accuracy.

Datasets:

- NVIDIA PhysicalAI Smart Spaces;
- MMPTRACK;
- WILDTRACK / MultiviewX;
- CITIC-MTMC.

## Layer B — tracking

Metrics:

- HOTA;
- DetA;
- AssA;
- IDF1;
- ID switches;
- fragmentation.

Datasets:

- MMPTRACK Retail;
- MOT17/20 for local tracking;
- CITIC/MTA for cross-camera handoff.

## Layer C — primitive analytics

Metrics:

- occupancy/count MAE;
- dwell MAE;
- flow count MAE;
- heatmap similarity;
- section transition accuracy.

Datasets:

- ATC;
- CAVIAR;
- MMPTRACK;
- NVIDIA Smart Spaces.

## Layer D — bottleneck signals

Manually label short episodes with:

- normal flow;
- queue;
- merge/cross-flow;
- spillback;
- obstruction;
- browsing crowd;
- uncertain.

Evaluate:

- event precision/recall;
- onset error;
- severity ranking;
- cause macro-F1;
- false alerts/hour.

## Layer E — robustness perturbation tests

Starting from accurate trajectories, inject:

1. Gaussian position noise;
2. biased homography;
3. missed detections;
4. short track gaps;
5. ID splits;
6. ID merges;
7. timestamp offsets;
8. camera outage;
9. false boundary crossings.

Plot metric error vs perturbation strength.

This directly answers which dashboard claims remain reliable when the vision system is imperfect.

---

# 20. Recommended implementation order

## Phase 1 — trustworthy section analytics

Implement:

1. section polygons and topology;
2. hard + soft section membership;
3. occupancy/density;
4. dwell;
5. heatmaps;
6. section histories;
7. boundary flow;
8. conservation residual.

These create the common data model.

## Phase 2 — bottleneck primitives

Implement:

1. speed-density state;
2. flow imbalance;
3. queue membership;
4. queue length/tail;
5. spillback;
6. stop-and-go index;
7. directional entropy/counterflow.

## Phase 3 — predictive / diagnostic signals

Implement:

1. time-to-congestion;
2. congestion-attributable dwell;
3. composite congestion score;
4. cause-aware classification;
5. metric uncertainty.

## Phase 4 — expensive identity helpers

Add:

- conditional ReID;
- conditional pose;
- tracklet quality aggregation;
- topology/time-gated cross-camera association.

This ordering keeps the first system useful even if cross-camera ReID is imperfect.

---

# 21. Minimum metadata needed by metric family

| Metric family | Minimum metadata |
|---|---|
| Dwell / occupancy | timestamps + section assignment |
| Metric density | section polygon + walkable area + calibrated positions |
| Heatmap | world/normalized floor positions |
| Boundary flow | section boundaries + trajectory direction + timestamps |
| Speed-density | metric spatial calibration + timestamps |
| Queue topology | service area + walkable geometry + trajectories |
| Spillback | queue anchor + section/aisle geometry |
| Flow conservation | closed section topology + all entrances/exits modeled |
| TTCg | occupancy + inbound/outbound flow + empirical congestion threshold |
| Cross-camera history | timestamps + camera topology + overlap/gap metadata |
| Conditional ReID | tracklets + camera topology + quality estimates |
| Homography uncertainty | calibration correspondences/residuals + image geometry |
| Cause-aware bottleneck | section semantics + neighboring topology + multiple primitive metrics |

If only coarse image polygons are available, section occupancy and approximate dwell remain possible, but metric speed, density per m², path distance, and geometric fusion should not be claimed precisely.

---

# 22. Recommended dashboard signals

For each section, show:

- current occupancy;
- occupancy percentile vs normal for this time;
- median speed;
- inflow / outflow;
- net accumulation;
- current queue length if applicable;
- congestion state;
- bottleneck persistence;
- projected time-to-congestion if stable enough;
- flow-conservation/data-health indicator;
- confidence.

For drill-down:

- heatmap;
- dwell distribution;
- queue tail history;
- section transition flows;
- congestion-attributable dwell estimate;
- cause classification with evidence;
- tracking/projection quality.

Do not hide data quality. A section should be allowed to report:

    analytics_state = LOW_CONFIDENCE

instead of emitting a precise-looking bottleneck score from poor tracking.

---

# 23. Established vs proposed summary

| Concept | Classification |
|---|---|
| Dwell time | Established quantity |
| Occupancy / density | Established |
| Heatmaps | Established visualization/aggregation |
| Per-person section history | Established trajectory abstraction |
| Speed-density-flow relation | Established pedestrian-flow foundation |
| Voronoi density | Established research method |
| Little's Law | Established queueing relation |
| Crowd pressure rho * Var(v) | Established research metric; thresholds context-specific |
| HOTA / IDF1 | Established tracking evaluation |
| Homography | Established projective geometry |
| Topology/time-gated ReID | Established research direction |
| Pose-guided visible-part ReID | Established research direction |
| Congestion-attributable dwell | Proposed operational attribution heuristic |
| Flow imbalance | Adapted flow signal |
| Time-to-congestion | Proposed forecasting heuristic |
| Dynamic queue topology graph | Proposed project heuristic |
| Flow-conservation residual as self-diagnosis | Adapted conservation identity / proposed diagnostic |
| Conditional ReID/pose policy | Proposed compute/association policy |
| Cause-aware bottleneck classification | Proposed project classifier |
| Directional entropy / counterflow score | Proposed/adapted signal |
| Stop-and-go index | Adapted phenomenon, proposed implementation metric |
| Queue spillback distance | Proposed operational metric |
| Congestion exposure | Proposed operational metric |
| Boundary churn | Proposed data-quality metric |

---

# 24. Primary / authoritative references

## Pedestrian density, speed, flow and bottlenecks

1. Bernhard Steffen and Armin Seyfried, **Methods for measuring pedestrian density, flow, speed and direction with minimal scatter**, Physica A 389(9), 2010. DOI: https://doi.org/10.1016/j.physa.2009.12.015

2. Armin Seyfried et al., **The fundamental diagram of pedestrian movement revisited**, Journal of Statistical Mechanics, 2005. DOI: https://doi.org/10.1088/1742-5468/2005/10/P10002

3. Armin Seyfried et al., **New Insights into Pedestrian Flow Through Bottlenecks**, Transportation Science 43(3), 2009. DOI: https://doi.org/10.1287/trsc.1090.0263

4. Weichen Liao et al., **Experimental Study on Pedestrian Flow through Wide Bottleneck**, Transportation Research Procedia 2, 2014. DOI: https://doi.org/10.1016/j.trpro.2014.09.005

5. Pedestrian macroscopic fundamental diagram work: **Macroscopic Fundamental Diagram for pedestrian networks: Theory and applications**, Transportation Research Part C. https://www.sciencedirect.com/science/article/pii/S0968090X17302449

## Queueing

6. John D. C. Little, **A Proof for the Queuing Formula: L = lambda W**, Operations Research 9(3), 1961. DOI: https://doi.org/10.1287/opre.9.3.383

## Crowd pressure / unstable flow

7. Dirk Helbing, Anders Johansson, Habib Zein Al-Abideen, **Dynamics of crowd disasters: An empirical study**, Physical Review E 75, 046109, 2007. DOI: https://doi.org/10.1103/PhysRevE.75.046109

8. **Pedestrian collective motion in competitive room evacuation**, Scientific Reports, 2017. https://www.nature.com/articles/s41598-017-11197-x

## Tracking evaluation

9. Jonathon Luiten et al., **HOTA: A Higher Order Metric for Evaluating Multi-object Tracking**, International Journal of Computer Vision 129, 2021. DOI: https://doi.org/10.1007/s11263-020-01375-2

## Camera topology and cross-camera ReID

10. Yeong-Jun Cho et al., **Unified Framework for Automated Person Re-Identification and Camera Network Topology Inference in Camera Networks**, ICCV Workshops 2017. https://openaccess.thecvf.com/content_ICCV_2017_workshops/w37/html/Cho_Unified_Framework_for_ICCV_2017_paper.html

11. Yeong-Jun Cho et al., **Joint person re-identification and camera network topology inference in multiple cameras**, Computer Vision and Image Understanding 180, 2019. DOI: https://doi.org/10.1016/j.cviu.2019.01.003

## Occlusion / pose-aware ReID

12. Jiaxu Miao et al., **Pose-Guided Feature Alignment for Occluded Person Re-Identification**, ICCV 2019. https://openaccess.thecvf.com/content_ICCV_2019/html/Miao_Pose-Guided_Feature_Alignment_for_Occluded_Person_Re-Identification_ICCV_2019_paper.html

13. Shang Gao et al., **Pose-Guided Visible Part Matching for Occluded Person ReID**, CVPR 2020. https://openaccess.thecvf.com/content_CVPR_2020/html/Gao_Pose-Guided_Visible_Part_Matching_for_Occluded_Person_ReID_CVPR_2020_paper.html

## Projective geometry

14. Richard Hartley and Andrew Zisserman, **Multiple View Geometry in Computer Vision, Second Edition**, Cambridge University Press, 2004. https://www.robots.ox.ac.uk/~vgg/hzbook/

## Project-specific dataset references

15. **MMPTRACK** dataset and paper: https://iccv2021-mmp.github.io/subpage/dataset.html

16. **NVIDIA PhysicalAI Smart Spaces**: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces

17. **CITIC-MTMC**: https://github.com/GTEC-UDC/citic-mtmc-dataset

18. **WILDTRACK**: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/

---

# 25. Main design recommendation

The dashboard should not try to infer one opaque "bottleneck score" directly from video.

Build an auditable chain:

    detections
      -> local tracks
      -> world/section positions with uncertainty
      -> section occupancy / speed / flow
      -> queue + imbalance + persistence signals
      -> bottleneck event
      -> likely cause + confidence

The highest-value implementation detail is to preserve confidence and provenance at every stage. That makes it possible to distinguish a real operational bottleneck from a tracking failure, calibration drift, or ambiguous cross-camera handoff.

For the first empirical system, prioritize:

1. section mapping with hysteresis and uncertainty;
2. occupancy, dwell, flow and heatmaps;
3. flow-conservation self-diagnosis;
4. queue length/tail and spillback;
5. speed-density and flow-imbalance signals;
6. time-to-congestion only after stable flow estimates exist;
7. cause-aware classification only after bottleneck episodes have been manually labeled;
8. conditional ReID/pose as targeted helpers rather than mandatory always-on components.

This progression keeps the system useful even when perfect identity continuity across every camera is impossible.
