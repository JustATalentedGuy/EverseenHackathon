# Final Experimental Comparison — Dwell-Time & Bottleneck Mapper

Date: 2026-10-04

Workspace: `C:\Coding\ML\Everseen`

Deadline implementation update (2026-10-07): see [FINAL_DEADLINE_DATA_AND_DEPLOYMENT_ARCHITECTURE.md](FINAL_DEADLINE_DATA_AND_DEPLOYMENT_ARCHITECTURE.md) for the implemented CAVIAR fallback, detector adaptation experiments, zone setup prototype and progressive calibration deployment decision. The historical experiments below remain their original evidence.

## Executive decision

The experiments support a clear final direction for the hackathon:

> **Use Architecture 2 — Geometry-First Shared-Floor Fusion — as the core system, augmented with Architecture 1's section/topology fallback and conservative handoff logic. Keep Architecture 3's global-graph reconciliation and predictive TTC layer as optional stretch features, not core dependencies.**

This is not a subjective preference based on architectural elegance. It follows from the measured results:

1. On real calibrated WILDTRACK annotations, clean image-to-world projection achieved **11.15 cm median error** and **97.43% section accuracy**.
2. Geometry-based overlap fusion reached **F1 0.998**, removed **99.88%** of duplicate excess observations, and reduced fused median position error to **9.72 cm** under clean calibration.
3. In controlled fragmentation on WILDTRACK projections, geometry + velocity produced **97.96% top-1 repair accuracy**, compared with **18.88%** for time-only matching.
4. In a common CITIC-based 30-seed stress benchmark, Architecture 2 had the best B-cubed identity F1 under clean, moderate and appearance-hard conditions.
5. Architecture 1 became preferable only when geometry itself was deliberately made unreliable, which argues for a **fallback mode**, not for discarding geometry.
6. Architecture 3's tested global graph did not outperform Architecture 2; under moderate corruption it over-split trajectories and produced substantially larger dwell error.
7. On a 60-person NVIDIA PhysicalAI sequence, geometry-aware duplicate suppression reduced occupancy error and flow-conservation residual, but severe observation corruption caused bottleneck recall to collapse for every architecture. This makes **health monitoring and confidence gating mandatory**.
8. Architecture 3's 10-second future-congestion predictor produced ROC-AUC **0.683** and F1 **0.448**. It contains useful early-warning signal, but is not strong enough to be the hackathon's primary claim.

Therefore the final system should not be described as one of the three original architectures in isolation. It should be described as:

## Recommended final architecture

**Uncertainty-Aware Geometry-First Retail Flow Intelligence with Topology Fallback**

```text
Multi-camera video
    |
    v
High-recall person detector
    |
    v
Per-camera local MOT
    |
    v
Short-lag tracklet repair
    |
    v
Footpoint / floor-contact estimation
    |
    v
Image -> shared floor coordinates + uncertainty
    |
    +---------------------------+
    |                           |
    v                           v
Overlap-camera fusion      Geometry-health check
& duplicate suppression          |
    |                             | degraded
    |                             v
    |                      section/topology fallback
    |                             |
    +--------------+--------------+
                   |
                   v
          semantic section mapping
          + boundary hysteresis
                   |
                   v
       cross-camera global session ID
       overlap: geometry + time
       gaps: topology + time + conditional ReID
                   |
         +---------+----------+
         |                    |
         v                    v
 identity-independent     identity-sensitive
 spatial analytics       visitor analytics
 occupancy               dwell
 density                 movement history
 heatmaps                wait time
 flow                    path history
 queues                  congestion exposure
         |                    |
         +---------+----------+
                   |
                   v
        bottleneck reasoning engine
        - flow imbalance
        - speed-density stress
        - congestion-attributable dwell
        - dynamic queue topology
        - spillback
        - cause classification
        - optional TTC forecast
                   |
                   v
             system-health layer
        - homography uncertainty
        - overlap disagreement
        - flow-conservation residual
        - ID churn
        - observability
                   |
                   v
         confidence-aware dashboard
```

---

# 1. Objective of the experimental phase

The target is not merely to show that a detector can put boxes around people.

The hackathon objective requires evidence that the system can:

1. detect people from ordinary non-bird's-eye cameras;
2. maintain useful local trajectories despite fragmentation;
3. convert image observations into meaningful sections or approximate floor coordinates;
4. fuse overlapping cameras without double counting;
5. reconnect people across blind gaps conservatively without face recognition;
6. retain enough movement history to calculate dwell and queue waiting;
7. compute aggregate flow metrics that remain useful even if identity continuity is imperfect;
8. distinguish normal high dwell from operational congestion;
9. identify where the analytics themselves are becoming unreliable;
10. produce an operationally useful output rather than only a CV visualization.

The experiments were designed around these requirements.

---

# 2. Dataset policy and evidence hierarchy

Only calibrated, true multi-camera datasets suitable for the target system are used as primary architecture evidence.

## 2.1 Primary datasets actually used

### CITIC-MTMC

Role:

- real indoor gapped-camera topology;
- section mapping;
- blind-gap handoff;
- real-video geometry sanity check.

Data used:

- all three official world-trajectory captures;
- floor/room/door map;
- official camera calibration and visibility polygons;
- a 12-second real Showroom video subset for YOLO11n + ByteTrack projection sanity.

Important limitation:

- only two people are present per original capture;
- official world GT is waypoint/time interpolation rather than image bounding-box identity GT.

### WILDTRACK

Role:

- real calibrated overlapping-camera geometry;
- ground projection accuracy;
- overlap fusion;
- duplicate suppression;
- geometry-assisted fragmentation repair;
- calibration/detection/timestamp noise sensitivity.

Data used:

- calibration files for all 7 cameras;
- real multi-view person annotations;
- 50 synchronized annotation frames spanning 24.5 seconds;
- 4,443 view observations.

RGB imagery was not required for this experiment because the test focuses on the geometry and annotation layer. Perturbation experiments are explicitly simulated on top of real annotations/calibration.

### NVIDIA PhysicalAI Smart Spaces 2026 — Warehouse_000

Role:

- dense 60-person global-world trajectory analysis;
- downstream occupancy/flow/bottleneck robustness;
- future-congestion prediction.

Data used:

- 281.6 MB official ground-truth JSON;
- calibration metadata and top-down map;
- 9,000-frame sequence;
- 60 unique people;
- 300 sampled 1-Hz states for analytics.

The separate Architecture-2 metadata check confirmed that all 25 scene cameras expose rich calibration fields, but a naive inverse use of the supplied homography did **not** numerically align with the `3d location` coordinate frame. The authoritative map/global-frame convention is not yet resolved. Therefore the PhysicalAI experiments in this report operate directly on official GT world locations for downstream analytics and **do not claim a measured image-to-GT projection error on PhysicalAI**. WILDTRACK is the quantitative projection benchmark.

Important limitation:

- primary corpus is synthetic;
- no official retail congestion-event label exists;
- the bottleneck label used here is a reproducible derived proxy, not an official benchmark label.

## 2.2 High-value dataset not run: MMPTRACK Retail

MMPTRACK Retail remains the most important missing validation because it combines:

- real/staged retail imagery;
- synchronized cameras;
- camera calibration;
- common world coordinates;
- global identities;
- carts/baskets/queue-like behavior.

It was **not** evaluated because official access requires a signed Terms & Conditions agreement to be sent to the dataset maintainers. No authorized copy was present in the workspace.

No MMPTRACK result is simulated or claimed.

This is the largest remaining external validation gap.

---

# 3. Architecture 1 — Section-First Topology-Aware Tracklets

Detailed report:

`research/ARCH1_EXPERIMENTS.md`

## 3.1 Core hypothesis

Reliable semantic sections plus topology/time constraints can provide useful retail analytics even when exact shared metric geometry is unavailable or degraded.

Architecture 1 emphasizes:

- camera-scoped local tracking;
- short-gap tracklet repair;
- semantic section assignment;
- section adjacency;
- camera transition topology;
- transition-time priors;
- conditional appearance only when needed.

It intentionally makes precise shared-floor coordinates optional.

---

## 3.2 Section mapping / hysteresis experiment

Real CITIC world coordinates are treated as truth. Gaussian world-position noise is injected and section transitions are recomputed.

Key results:

| Position noise | Persistence | Section accuracy | Transition F1 | Boundary churn |
|---:|---:|---:|---:|---:|
| 0.05 m | ~0.04 s | 0.964 | 0.114 | 775 |
| 0.05 m | **0.24 s** | 0.934 | **0.840** | **0** |
| 0.10 m | ~0.04 s | 0.960 | 0.099 | 911 |
| 0.10 m | **0.24 s** | 0.950 | **0.764** | **1** |
| 0.25 m | 0.24 s | 0.921 | 0.444 | 1 |

Scientific conclusion:

- hysteresis is highly effective at removing false section flips when projection error is small/moderate;
- hysteresis is not a substitute for good calibration once position error becomes large;
- section-transition precision/recall should be measured, not inferred from high frame-level section accuracy.

Practical implication:

**Section state must be temporally filtered before dwell or movement histories are created.**

---

## 3.3 Local fragmentation repair experiment

Controlled short gaps are injected into official CITIC owner-camera paths.

At 10 cuts/minute:

- 159 fragments;
- 51 eligible true repair links.

At stitch threshold 0.35:

- 51/51 repaired;
- zero false merges in this sparse controlled experiment.

This is mechanism validation only. CITIC's two-person captures make this far easier than a crowded retail aisle.

---

## 3.4 Blind-gap handoff experiment

Time-only association is compared with topology + time gating.

There are 34 true handoffs inside the evaluation window.

Representative result:

| Strategy | Precision | Recall | F1 | False merges | False splits |
|---|---:|---:|---:|---:|---:|
| Time-only | 0.938 | 0.882 | 0.909 | 2 | 4 |
| **Topology + time** | **1.000** | **0.971** | **0.985** | **0** | **1** |

The primary conclusion is not that blind-gap tracking is solved. The useful result is:

> **Physical topology removes impossible appearance/time candidates before ReID, making conservative cross-camera association much safer.**

---

## 3.5 Dwell/occupancy/flow under fragmentation

At 10 cuts/minute:

| Stage | Occupancy MAE | Dwell MAE | Relative section-flow error |
|---|---:|---:|---:|
| Raw fragmented | **0.038 people** | 24.38 s | 50% |
| Local repair | **0.038 people** | 21.50 s | 50% |
| Local + topology handoff | **0.038 people** | **3.94 s** | **0%*** |

`*` Only eight reference flow events per capture; do not generalize the 0% figure.

This directly validates one of the final architecture's most important principles:

- occupancy can stay useful even with broken identities;
- dwell requires repaired visitor continuity.

---

## 3.6 Real-video sanity check

On 12 seconds / 300 frames of the real CITIC Showroom camera with YOLO11n + ByteTrack:

- official GT visible people/frame: 1.000;
- detector mean people/frame: 1.337;
- count MAE: **0.390 person/frame**;
- exact-count frames: **61%**;
- detected footpoints inside official camera visibility: **92.52%**;
- projected inside Showroom room polygon: **92.77%**;
- 4 ByteTrack IDs observed;
- median track length: 2.16 s.

This is a useful warning: geometry can be sound while detector/tracker imperfections still limit end-to-end performance.

---

## 3.7 Architecture 1 assessment

### Strengths

- robust when precise world geometry is unavailable or degraded;
- topology is extremely effective for removing impossible handoffs;
- easiest to explain;
- low implementation risk;
- section-level metrics can remain operational with imperfect IDs.

### Weaknesses

- loses information available from calibrated overlap;
- coarse spatial resolution;
- physical speed/density/queue length less defensible without shared scale;
- blind-gap association still needs appearance if multiple candidates survive topology/time gating;
- camera ownership can sacrifice valid multi-view coverage.

### Final role

**Fallback / robustness layer.**

Architecture 1 should not be discarded; its topology and section logic should be embedded inside the selected Architecture 2 system.

---

# 4. Architecture 2 — Geometry-First Shared-Floor Fusion

Detailed raw experiment output:

`experiments/architecture2/wildtrack_summary.json`

Dedicated narrative report:

`research/ARCH2_EXPERIMENTS.md`

## 4.1 Core hypothesis

When synchronized calibration is available, shared world geometry should become the strongest association cue for overlapping cameras and a major cue for repairing local fragmentation.

Appearance should become secondary rather than the primary identity mechanism.

---

## 4.2 Real WILDTRACK projection accuracy

Using real WILDTRACK calibration and annotations:

- observations: **4,443**;
- median ground-position error: **11.15 cm**;
- P90 error: **21.87 cm**;
- mean error: 12.14 cm;
- 4×4 section accuracy: **97.43%**.

Per-camera median error ranged roughly from:

- **6.84 cm** (CVLab4)
- to **14.50 cm** (IDIAP2).

This validates the key architectural assumption:

> With genuine calibration, ordinary oblique multi-camera annotations can be mapped into a common floor plane with useful section-level accuracy.

---

## 4.3 Cross-camera overlap agreement

For 6,900 same-person cross-camera pairs:

- median projected disagreement: **12.41 cm**;
- P90 disagreement: **21.55 cm**;
- 100% were within 50 cm in the clean annotation/calibration condition.

This is the direct justification for making geometry dominant in overlapping views.

---

## 4.4 Geometry-based overlap fusion

At a 75 cm fusion threshold:

- pair precision: **0.99797**;
- pair recall: **0.99797**;
- pair F1: **0.99797**;
- false-pair counts: 14 FP / 14 FN;
- duplicate excess before fusion: 3,280;
- duplicate excess after: **4**;
- duplicate-excess removal: **99.878%**;
- fused median position error: **9.72 cm**;
- fused P90 error: 17.11 cm.

The fusion threshold sweep from 50–150 cm gave essentially the same clean F1 in this subset, showing a wide clean-data operating plateau.

This is one of the strongest results in the entire study.

---

## 4.5 Fragment repair: time vs geometry

Controlled fragment links: 196.

| Association cue | Top-1 repair accuracy |
|---|---:|
| Time-only | **18.88%** |
| Geometry nearest | **95.41%** |
| Geometry + velocity prediction | **97.96%** |

This is the clearest measured evidence for Architecture 2.

It shows why the shared floor plane should be used to repair identities, not only to draw a top-down heatmap.

---

## 4.6 Detection/footpoint noise sensitivity

Controlled pixel noise is added to annotated image positions before world projection.

| Pixel noise | Median projection error | Section accuracy | Fusion F1 | Wrong-merge cluster rate |
|---:|---:|---:|---:|---:|
| 0 px | 11.15 cm | 97.43% | 0.998 | 0.34% |
| 2 px | 12.51 cm | 96.06% | 0.972 | 3.63% |
| 5 px | 20.36 cm | 93.32% | 0.826 | 16.92% |
| 10 px | 36.65 cm | 88.60% | 0.619 | 32.41% |

This produces an important deployment requirement:

> A fixed world-distance fusion threshold is safe only while projection uncertainty remains controlled.

The system therefore needs uncertainty-aware gates and a geometry-health score.

---

## 4.7 Calibration perturbation

At only 0.5 px calibration perturbation:

- section accuracy remained ~97.10%;
- fusion F1 remained ~0.990;
- geometry+velocity stitching remained ~0.981.

Larger calibration perturbations increasingly degraded overlap agreement and fusion reliability.

This justifies:

- versioned calibration;
- periodic overlap-agreement monitoring;
- automatic downgrade to topology/section mode if calibration health degrades.

---

## 4.8 Missed observations

Missed detections alone were less damaging to geometry fusion than spatial calibration/detection error:

At 10% misses:

- section accuracy ~97.46%;
- fusion F1 ~0.998;
- geometry+velocity stitch ~0.968.

At 20% misses:

- section accuracy ~97.46%;
- fusion F1 ~0.997;
- geometry+velocity stitch ~0.974.

This result is intuitive: missing a view reduces redundancy, while inaccurate geometry can actively create wrong merges.

---

## 4.9 Combined error scenarios

### Combined mild

Perturbations:

- 2 px detection noise;
- 1 px calibration noise;
- 0.5 s timestamp noise;
- 5% misses.

Results:

- median projection error: **14.35 cm**;
- P90: 55.98 cm;
- section accuracy: **95.68%**;
- fusion F1: **0.816**;
- wrong-merge cluster rate: **12.61%**;
- geometry+velocity stitching: **94.94%**;
- time-only stitching: 17.54%.

### Combined severe

Perturbations:

- 5 px detection noise;
- 2 px calibration noise;
- 1 s timestamp noise;
- 10% misses.

Results:

- median projection error: 22.83 cm;
- P90: 114.38 cm;
- section accuracy: **92.53%**;
- fusion F1: **0.579**;
- wrong-merge cluster rate: **31.20%**;
- geometry-nearest stitching: 85.39%;
- geometry+velocity stitching: 79.82%;
- time-only stitching: 17.78%.

The most important observation is subtle:

**Section accuracy can remain above 90% while precise overlap identity fusion has already become unsafe.**

Therefore the system should not have one global “camera calibration good/bad” flag. It should use metric-specific confidence:

- section analytics may remain valid;
- exact cross-camera identity fusion may need to be disabled.

---

## 4.10 Architecture 2 assessment

### Strengths

- strongest measured identity continuity in realistic calibrated conditions;
- excellent overlap deduplication;
- much less dependent on appearance;
- supports metric distance, speed, density, queue length and spillback;
- geometry provides interpretable reasons for associations;
- maps naturally onto the metadata the sponsor/organizer can supply.

### Weaknesses

- accuracy can fail sharply when calibration/timestamps are wrong;
- footpoint error is a first-class source of world error;
- requires careful handling of stairs/ramps/non-planar floors;
- needs an explicit uncertainty/health layer;
- blind gaps still require topology/time and often ReID.

### Final role

**Primary architecture.**

---

# 5. Architecture 3 — Global Tracklet Graph + Predictive Digital Twin

Detailed report:

`research/ARCH3_EXPERIMENTS.md`

## 5.1 Core hypothesis

A joint global graph should be able to repair errors inherited from local trackers better than sequential greedy association, while preserving ambiguity and enabling future-aware decisions.

This is scientifically attractive, but the experiment asks whether it is worth the extra complexity now.

---

## 5.2 Common CITIC-based stress benchmark

The same real paths and injected errors are given to all three architectures.

### Clean

| Architecture | B³ F1 | Dwell L1 error |
|---|---:|---:|
| Architecture 1 | 0.843 | 6.73 s |
| **Architecture 2** | **0.954** | **2.68 s** |
| Architecture 3 | 0.927 | 3.39 s |

### Moderate

| Architecture | B³ F1 | Link precision | Link recall | Dwell L1 error |
|---|---:|---:|---:|---:|
| Architecture 1 | 0.534 | 0.840 | 0.783 | 40.65 s |
| **Architecture 2** | **0.669** | **0.925** | **0.875** | **28.60 s** |
| Architecture 3 | 0.509 | 0.897 | 0.694 | 52.14 s |

### Appearance-hard

Mean B³ F1 over 30 seeds:

- Architecture 1: 0.2968;
- **Architecture 2: 0.5969**;
- Architecture 3: 0.3636.

This validates the value of geometry when appearance becomes unreliable.

### Geometry-hard

Mean B³ F1 over 30 seeds:

- **Architecture 1: 0.4932**;
- Architecture 2: 0.3252;
- Architecture 3: 0.2693.

This validates the need for a topology/section fallback when geometry health is poor.

### Severe

All methods perform badly:

- Architecture 1: 0.2094;
- Architecture 2: 0.1995;
- Architecture 3: 0.1477.

At this point the correct product behavior is to report reduced confidence and rely on aggregate spatial statistics rather than claim complete person histories.

---

## 5.3 Why the tested global graph underperformed

The graph did not fail because “global methods are bad.”

It underperformed because:

- the ambiguity gate was deliberately conservative;
- it over-split uncertain visitors;
- edge evidence was still hand-engineered;
- the experiment did not train a GNN/transformer on large handoff data;
- joint assignment cannot recover information that is absent or badly corrupted.

Under moderate corruption, the graph produced about **20.5 global IDs for six visitors**, while Architecture 2 produced about 9.9. Its precision remained reasonable but recall/completeness suffered.

For a 48-hour hackathon, this is strong evidence against making the global graph a mandatory dependency.

---

## 5.4 60-person PhysicalAI bottleneck robustness

The clean world trajectory is converted into 25 spatial sections.

An interpretable clean congestion proxy is derived from:

- occupancy relative to section baseline;
- speed loss;
- positive flow imbalance;
- direction entropy;
- persistence.

The clean positive rate is 10.56%.

### Mild observation corruption

| Architecture | Bottleneck P | R | F1 | Occupancy MAE | Conservation residual |
|---|---:|---:|---:|---:|---:|
| Architecture 1 | 0.938 | **0.757** | **0.837** | 0.114 | 0.216 |
| Architecture 2 | **0.943** | 0.748 | 0.834 | **0.099** | **0.189** |
| Architecture 3 spatial layer | **0.943** | 0.748 | 0.834 | **0.099** | **0.189** |

### Moderate corruption

| Architecture | Bottleneck P | R | F1 | Occupancy MAE | Conservation residual |
|---|---:|---:|---:|---:|---:|
| Architecture 1 | 0.871 | **0.359** | **0.508** | 0.287 | 0.473 |
| Architecture 2 | **0.887** | 0.343 | 0.494 | **0.243** | **0.383** |
| Architecture 3 spatial layer | **0.887** | 0.343 | 0.494 | **0.243** | **0.383** |

### Severe corruption

All methods have bottleneck F1 near **0.05**, dominated by almost-zero recall.

This is one of the most valuable negative findings in the study:

> **A bottleneck model cannot compensate for a badly corrupted observation layer.**

The conservation residual increases substantially under the same errors, so it can help detect when alerts are no longer trustworthy.

---

## 5.5 Future-congestion prediction

Architecture 3 also tests prediction of congestion within the next 10 seconds using a section-state gradient-boosted model.

Chronological train/validation/test split is used, and the classification threshold is selected on validation only.

Test result:

- threshold: 0.223;
- precision: 0.348;
- recall: **0.628**;
- F1: **0.448**;
- ROC-AUC: **0.683**.

Interpretation:

- useful signal exists;
- recall is sufficient for an experimental early-warning indicator;
- precision is too low for autonomous action;
- prediction should be presented as a stretch feature, not a primary accuracy claim.

---

## 5.6 Architecture 3 assessment

### Strengths

- most principled long-term solution for ambiguous tracklets;
- supports delayed decisions;
- natural home for probabilistic identity confidence;
- strongest future research direction;
- enables predictive section-state modeling.

### Weaknesses

- tested implementation did not outperform Architecture 2;
- highest complexity and tuning burden;
- requires more training data;
- hardest to finish/validate convincingly in hackathon time;
- current forecast performance is modest.

### Final role

**Selective optional extension, not core.**

---

# 6. Scientific cross-architecture comparison

## 6.1 Identity continuity

Under calibrated/healthy geometry:

**Architecture 2 > Architecture 3 prototype > Architecture 1**

Under deliberately broken geometry:

**Architecture 1 > Architecture 2 > Architecture 3 prototype**

This strongly supports an adaptive Geometry-First system with topology fallback.

## 6.2 Spatial accuracy

Architecture 2 is the only architecture that fully exploits common calibrated coordinates for:

- overlap fusion;
- metric path length;
- speed;
- local density;
- physical queue length;
- queue-tail distance;
- camera-to-camera agreement checks.

Architecture 1 can still deliver section-level analytics, but loses these metric quantities.

Architecture 3 inherits Architecture 2's spatial requirements and adds association complexity rather than improving the underlying geometry.

## 6.3 Robustness to ID fragmentation

Occupancy is largely stable without identity repair.

Dwell and complete histories are not.

This means the architecture should carry two output confidence levels:

```text
Spatial analytics confidence
Identity/journey confidence
```

rather than one global system confidence.

## 6.4 Robustness to calibration failure

Architecture 2's clean results are excellent but its fusion deteriorates rapidly as projection/timestamp error rises.

Architecture 1 loses fine geometry but can continue operating at section level.

Therefore architecture mode should depend on measured geometry health.

## 6.5 False merge vs false split

For dwell/visitor history, a false merge is generally worse than a false split:

- split: one visitor becomes two incomplete visits;
- merge: two real visitors become one impossible long visit, corrupting path and dwell statistics.

The final system should therefore use conservative global association thresholds and explicitly mark uncertain handoffs.

---

# 7. Practical hackathon comparison

| Criterion | Architecture 1 | Architecture 2 | Architecture 3 |
|---|---|---|---|
| Data requirement | Low-medium | Medium-high | High |
| Needs common metric geometry | No | **Yes** | **Yes** |
| Overlap-camera capability | Limited | **Excellent** | Potentially excellent |
| Blind-gap handoff | Good topology baseline | **Good with topology + ReID** | Highest theoretical ceiling |
| Measured identity performance | Good | **Best** | Below Arch2 prototype |
| Spatial metrics | Coarse | **Rich / metric** | Rich / metric |
| Calibration failure tolerance | **Best** | Needs fallback | Needs fallback |
| Explainability | **Excellent** | **Excellent** | Medium |
| Compute complexity | **Lowest** | Medium | Highest |
| Implementation risk | **Low** | **Medium** | High |
| Research novelty | Medium | **High** | Very high |
| 48-hour demonstrability | Excellent | **Best balance** | Risky |
| Final recommendation | Fallback | **CORE** | Stretch |

---

# 8. Final architecture in detail

## 8.1 Perception layer

### Detector

Use a strong person detector tuned for **recall**, because missing a person for long intervals is more damaging than a modest increase in false positives.

The exact detector should remain swappable.

Required output:

```text
camera_id
timestamp
bbox
confidence
optional keypoints
```

### Local MOT

Use ByteTrack or BoT-SORT as local tracklet generators rather than final identity systems.

Do not let `local_track_id` propagate directly into business analytics.

---

# 8.2 Tracklet repair layer

Repair short local breaks using:

1. time gap;
2. world endpoint distance;
3. velocity/motion prediction;
4. section continuity;
5. topology constraints;
6. conditional appearance if multiple candidates remain;
7. optional pose/visible-part evidence only for difficult occlusions.

The WILDTRACK experiment strongly supports geometry + velocity for this task.

---

# 8.3 Floor-contact estimation

Baseline:

```text
u = (x1 + x2) / 2
v = y2
```

This approximates the contact point with the floor.

Optional refinement:

- ankle/foot keypoints if reliable;
- visible-foot weighting;
- learned footpoint estimator.

Pose should be conditional rather than mandatory because pose estimation itself fails in severe occlusion.

---

# 8.4 Homography / world projection

For camera homography `H`:

```text
[X',Y',W']^T = H [u,v,1]^T
X = X'/W'
Y = Y'/W'
```

Store with every point:

```text
x
y
position_uncertainty
source_camera
calibration_version
```

Do not treat the result as exact.

---

# 8.5 Geometry uncertainty

Sources:

- calibration residual;
- footpoint uncertainty;
- image scaling/cropping mismatch;
- distance from camera;
- partial occlusion;
- camera movement.

Practical hackathon implementation:

1. estimate camera calibration holdout error;
2. perturb image footpoint and homography/reference points;
3. Monte-Carlo project to floor;
4. estimate world covariance/radius;
5. use the uncertainty in fusion thresholds and section membership.

---

# 8.6 Overlapping-camera fusion

When synchronized cameras both see the same region:

```text
candidate pair must satisfy:
  timestamp compatibility
  uncertainty-aware world-distance compatibility
```

Then score:

```text
cost =
    geometry_distance
  + temporal_difference
  + small appearance term if needed
```

Appearance should not dominate when the cameras observe the person at the same physical location/time.

---

# 8.7 Section mapping

Define semantic polygons in floor coordinates:

- Entrance;
- aisles;
- displays;
- junctions;
- queue approach;
- individual queue lanes;
- checkout/service points;
- Exit.

Use:

- point-in-polygon;
- boundary hysteresis;
- minimum persistence;
- soft membership when uncertainty overlaps boundaries.

---

# 8.8 Blind-gap handoff

When a person leaves all visible cameras:

```text
exit tracklet
  -> reachable-camera filter
  -> compatible entry-zone filter
  -> transition-time filter
  -> feasible route/speed filter
  -> appearance matching only among survivors
  -> optional pose/visible-part comparison
  -> confidence / ambiguity decision
```

The CITIC experiment shows why topology should come before ReID.

Possible state:

```text
confirmed
tentative
ambiguous
lost
ended
```

---

# 8.9 Identity-independent analytics layer

These should update even if the global ID is uncertain:

### Occupancy

```text
O_s(t) = spatially unique people in section s
```

### Density

```text
rho_s(t) = O_s(t) / walkable_area_s
```

### Heatmaps

- presence heatmap;
- dwell/person-time heatmap;
- congestion heatmap.

### Boundary flow

```text
F_A->B(window) = confirmed geometric crossings A to B
```

### Flow imbalance

```text
I_s = (F_in - F_out) / (F_in + F_out + epsilon)
```

These are critical because they allow useful operational analytics even when identity history is partially broken.

---

# 8.10 Identity-sensitive analytics

Only report these as high confidence when association confidence is sufficient:

### Dwell

```text
D_i,s = sum_t P(i in section s at t) Delta_t
```

Store:

- entry observed?;
- exit observed?;
- censored/incomplete?;
- association confidence.

### Per-person movement history

Store a compressed event stream rather than every frame:

```text
Entrance  14:02:11 -> 14:02:18
Aisle_1   14:02:18 -> 14:03:06
Display   14:03:06 -> 14:03:48
Queue     14:03:48 -> 14:05:23
Checkout  14:05:23 -> 14:06:10
Exit      ...
```

---

# 9. Bottleneck metrics to implement

## 9.1 Congestion-attributable dwell

Raw dwell should not be interpreted as friction.

Define congestion intensity `C_s(t)` and calculate:

```text
CAD_i,s = integral I(i in s) * C_s(t) dt
```

Also calculate excess dwell relative to an uncongested section/path baseline.

This is one of the strongest differentiators between a simple dwell heatmap and a useful bottleneck mapper.

---

## 9.2 Flow imbalance

Prioritize net accumulation rather than occupancy alone.

Interpretation:

- high occupancy + balanced flow = busy;
- rising positive imbalance = queue/bottleneck forming;
- negative imbalance = recovery.

---

## 9.3 Dynamic queue topology

Do not assume a queue is a fixed rectangle.

Represent it as an ordered graph toward a service point.

Outputs:

- queue membership probability;
- count;
- physical length;
- service rate;
- wait estimate;
- tail position;
- lane imbalance;
- spillback risk.

This is particularly valuable at checkouts where the line bends or overflows into an aisle.

---

## 9.4 Time to congestion

First interpretable baseline:

```text
a = smoothed(F_in - F_out)
TTC = (O_critical - O_current) / a, if a > 0
```

Use uncertainty ranges.

The learned PhysicalAI forecast should remain a secondary optional model.

---

## 9.5 Cause-aware bottleneck classification

Classify likely mechanism:

1. demand surge;
2. checkout/service bottleneck;
3. physical constriction;
4. temporary obstruction;
5. counterflow/crossflow conflict;
6. high engagement/browsing — not a bottleneck;
7. measurement fault / low observability.

Use interpretable features before training an opaque end-to-end classifier.

---

# 10. Self-diagnosis / trust layer

This is a major final-system requirement supported by the experiments.

## 10.1 Flow-conservation residual

For section `s`:

```text
R_s = Delta occupancy - (entries - exits)
```

Large persistent residual suggests:

- misses;
- duplicates;
- bad boundary crossings;
- broken identity continuity;
- synchronization error;
- unmodeled entrances;
- calibration drift.

It is a system-health metric, not a congestion metric.

---

## 10.2 Overlap agreement

In overlapping cameras:

```text
E_overlap = median distance between independently projected same-location observations
```

If disagreement grows beyond the calibrated distribution, downgrade geometry confidence.

---

## 10.3 ID churn

Monitor new local IDs per person-minute/section.

If occupancy is steady but ID creation spikes, per-person dwell/history should be marked low-confidence even if occupancy remains usable.

---

## 10.4 Observability

Combine:

- number of covering cameras;
- person pixel height;
- detection confidence;
- occlusion;
- projection uncertainty;
- clock health;
- overlap agreement.

This should influence alert confidence.

---

# 11. Adaptive operating modes

The final architecture should explicitly degrade based on evidence quality.

## Mode A — Full geometry mode

Condition:

- calibration healthy;
- timestamp alignment healthy;
- overlap agreement low;
- position uncertainty acceptable.

Features:

- metric world coordinates;
- geometry-first overlap fusion;
- physical queue lengths;
- speed/density;
- path metrics;
- high-confidence cross-camera overlap stitching.

## Mode B — Section/topology mode

Condition:

- exact geometry uncertain but per-camera section mapping remains usable.

Features:

- section occupancy;
- dwell;
- boundary flow;
- topology-constrained handoffs;
- queue counts;
- flow imbalance.

Disable or lower confidence on:

- fine metric distances;
- aggressive overlap fusion.

## Mode C — Aggregate-only safety mode

Condition:

- severe tracking/calibration/observability failure.

Features:

- conservative occupancy estimates;
- raw detector counts where appropriate;
- low-confidence warning;
- no complete-person-history claims.

This behavior is supported by the severe-noise experiments where all global tracking methods became unreliable.

---

# 12. Final hackathon scope

## Must-have demo components

1. multi-camera input;
2. person detection;
3. local tracking IDs;
4. footpoint projection into a common floor view;
5. semantic sections;
6. overlap fusion/deduplication;
7. topology-aware blind-gap handoff;
8. per-person section movement history with confidence;
9. dwell, occupancy, heatmap and boundary flow;
10. flow imbalance;
11. queue count/length where service points are defined;
12. bottleneck state with an explanation;
13. health/confidence indicators.

## High-value advanced features

1. congestion-attributable dwell;
2. dynamic queue topology;
3. queue spillback prediction;
4. homography uncertainty visualization;
5. flow-conservation self-diagnosis;
6. cause-aware bottleneck classification;
7. conditional body ReID / pose;
8. simple interpretable TTC.

## Stretch features

1. learned future-congestion model;
2. delayed global graph reconciliation;
3. multi-hypothesis global identity posterior;
4. learned graph/transformer association.

---

# 13. Recommended hackathon demo story

The demo should show one complete operational narrative.

### Scene 1 — normal traffic

Dashboard shows:

- people moving across sections;
- calibrated top-down positions;
- stable occupancy;
- balanced flow;
- normal dwell.

### Scene 2 — high engagement

A promotional section gets high dwell, but:

- flow remains healthy;
- speed is normal outside stationary shoppers;
- imbalance remains near zero.

The system labels this:

> High dwell / likely engagement — not operational congestion.

### Scene 3 — queue begins growing

Checkout approach shows:

- positive inflow-outflow imbalance;
- queue graph growing;
- median speed falling;
- congestion-attributable dwell increasing;
- TTC decreasing.

System reports:

> Checkout queue developing; expected capacity threshold in ~N seconds.

### Scene 4 — bottleneck established

System shows:

- persistent high occupancy;
- low movement speed;
- queue tail approaching upstream aisle;
- high CAD;
- service throughput below arrival rate.

Cause:

> Likely checkout service-capacity bottleneck.

Suggested action:

> Open additional checkout / redirect staff.

### Scene 5 — system confidence degradation

Deliberately perturb/reload a bad calibration or simulate a clock offset.

Show:

- overlap agreement worsening;
- conservation residual increasing;
- system automatically lowering geometry confidence;
- fallback to section-level analytics.

This is a particularly strong research/product demonstration because it shows the system understands not only the store, but also **when it should not trust itself**.

---

# 14. Required organizer metadata

For the recommended system, request:

### Required

- camera IDs;
- video/stream mapping;
- exact resolution;
- FPS/timestamps;
- synchronization/clock offsets;
- camera intrinsics;
- extrinsics or homography;
- calibration image resolution/cropping details;
- store floorplan / common coordinate system;
- semantic section polygons or sufficient layout to define them;
- camera coverage polygons;
- overlap pairs;
- camera topology / reachable next cameras;
- entry/exit regions.

### Strongly recommended

- distortion coefficients;
- camera height/orientation;
- route distances;
- expected transition-time ranges;
- known blind spots;
- checkout/service-point coordinates;
- small cross-camera ID validation subset;
- small world-position validation subset.

If full shared geometry is unavailable, the system can fall back to Architecture 1's section-first mode, but the strongest Architecture 2 claims require the shared calibration package.

---

# 15. Privacy design

The system does not need face recognition.

Recommended policy:

- session-scoped pseudonymous global IDs;
- no name/payment/phone/loyalty linking;
- no cross-day persistent identity;
- body ReID used only when geometry/topology cannot decide;
- optionally mask heads before appearance embeddings;
- retain embeddings only during active association window;
- store derived section/world trajectories rather than person crops where possible;
- edge/on-prem processing where practical;
- explicit data retention rules.

This should be described as **privacy-conscious pseudonymous tracking**, not perfectly anonymous tracking.

---

# 16. Claims supported by the current evidence

We can reasonably claim:

1. calibrated multi-camera geometry can provide accurate enough floor mapping for section analytics under healthy calibration;
2. overlapping cameras can be fused with very high accuracy on WILDTRACK annotations;
3. world geometry provides a major improvement over time-only fragmentation repair;
4. topology materially improves blind-gap association and reduces false merges on CITIC;
5. occupancy is substantially less sensitive to ID fragmentation than per-person dwell;
6. section hysteresis is essential near boundaries;
7. geometry-based fusion degrades materially under projection/timing error, so uncertainty must be explicit;
8. conservation/overlap health signals can help identify unreliable analytic windows;
9. advanced bottleneck metrics can be computed from the resulting section/world state;
10. a lightweight future-congestion model shows some predictive signal but is not yet strong enough for an autonomous intervention claim.

---

# 17. Claims that are NOT supported yet

Do not claim:

- perfect person identity across a crowded supermarket;
- production-grade ReID accuracy in real retail crowds;
- centimeter-level accuracy for arbitrary cameras without calibration validation;
- robust global handoff through long gaps with many similarly dressed shoppers;
- production-ready bottleneck event F1 on actual supermarket labels;
- validated customer-engagement classification;
- validated cause classification across diverse real stores;
- reliable automatic action under severe camera/track failure;
- MMPTRACK performance, because that dataset was not available under authorized access.

---

# 18. Remaining validation priority

The single highest-value next dataset is **MMPTRACK Retail**, once access is legitimately obtained.

Run:

1. real detector/local tracker evaluation;
2. local tracklet repair with actual tracker fragmentation;
3. shared-floor localization error;
4. overlap geometry vs appearance association;
5. global IDF1/HOTA;
6. section dwell error;
7. checkout/queue section analytics;
8. appearance-hard cases involving carts/baskets/occlusion.

Then, if organizer footage becomes available, calibrate a small labelled sample from the actual target store. This is more valuable than adding another generic public dataset.

---

# 19. Final recommendation by objective

| Objective | Recommended mechanism |
|---|---|
| Detect people | High-recall detector |
| Track within camera | ByteTrack/BoT-SORT local tracklets |
| Reduce fragmentation | Geometry + velocity short-lag repair |
| Map to store | Calibrated shared floor + semantic polygons |
| Fuse overlapping cameras | Geometry/time first, appearance secondary |
| Track across gaps | Topology + transition time + entry/exit + conditional ReID |
| Maintain privacy | Session-scoped pseudonymous IDs, no face recognition |
| Dwell | Confidence-aware section history |
| Occupancy | Spatially unique fused observations, independent of identity where possible |
| Heatmap | World-space uncertainty-aware accumulation |
| Detect emerging congestion | Flow imbalance + occupancy + speed + persistence |
| Separate browsing from friction | Congestion-attributable dwell + flow context |
| Queue analytics | Dynamic ordered queue graph toward service point |
| Predict congestion | Interpretable TTC first; learned forecast optional |
| Explain bottleneck | Cause-aware feature rules/model |
| Detect system failure | Conservation residual + overlap agreement + ID churn + observability |

---

# 20. Final scientific conclusion

The original problem appears at first to be a tracking problem. The experiments show that this framing is incomplete.

The technically strongest solution is a **confidence-aware spatial-flow system** in which tracking is one noisy input.

The most important findings are:

1. **Shared geometry is extremely valuable when it is trustworthy.** WILDTRACK geometry produced strong projection, overlap fusion and fragmentation-repair results.
2. **Topology remains essential.** Geometry cannot observe a blind gap; CITIC shows that topology/time gating substantially reduces wrong handoffs.
3. **Identity should not gate all analytics.** Occupancy and many flow signals remain useful even when the person history fragments.
4. **Precise geometry and coarse sections should coexist.** Fine geometry gives power; sections provide robustness.
5. **The system must measure its own reliability.** Severe corruption caused bottleneck recall to collapse for all architectures.
6. **Greater model complexity is not automatically better.** The global graph did not outperform the well-constrained geometry-first pipeline in the experiments.

Therefore the preferable architecture is not the most complex architecture. It is the architecture that uses the strongest evidence first, falls back safely when that evidence becomes weak, and does not pretend uncertain identities are certain.

---

# 21. Final hackathon thesis

The project should be pitched as:

> **A privacy-conscious, uncertainty-aware multi-camera retail flow intelligence system that maps anonymous shopper movement into a calibrated store coordinate/section model, repairs fragmented tracks using geometry and topology, distinguishes engagement dwell from congestion-attributable dwell, detects and explains bottlenecks using flow rather than occupancy alone, and continuously checks whether its own tracking/calibration is trustworthy.**

That is a much stronger objective than “track people and draw a heatmap.”

---

# 22. Reproducibility index

Architecture 1:

- `research/ARCH1_EXPERIMENTS.md`
- `scripts/architecture1/`
- `experiments/architecture1/`

Architecture 2:

- `research/ARCH2_EXPERIMENTS.md`
- `scripts/architecture2/`
- `experiments/architecture2/`

Architecture 3:

- `research/ARCH3_EXPERIMENTS.md`
- `scripts/common_architecture_stress.py`
- `scripts/physicalai_bottleneck_experiment.py`
- `experiments/common_architecture_stress/`
- `experiments/physicalai_bottleneck/`

Supporting design research:

- `research/ARCHITECTURE_OPTIONS.md`
- `research/METRICS_AND_BOTTLENECK_SIGNALS.md`
- `research/HIGH_SUITABILITY_DATASETS.md`
- `research/CAMERA_METADATA_REQUIREMENTS.md`
- `datasets/high_suitability_catalog.csv`

Final compact quantitative table:

- `experiments/final_architecture_comparison.csv`
