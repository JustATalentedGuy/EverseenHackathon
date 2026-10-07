# Architecture 3 Experiments — Probabilistic Global Tracklet Graph + Predictive Bottleneck Digital Twin

Date: 2026-10-04

Workspace: `C:\Coding\ML\Everseen`

## 1. Architecture under test

Architecture 3 is the research-heavy option. Instead of accepting local tracker IDs as final and then greedily repairing them, it treats local tracklets as graph nodes and attempts a global trajectory association.

The conceptual pipeline is:

```text
camera observations
  -> local tracklets
  -> tracklet graph
       node = local tracklet
       edge = physically/temporally/visually plausible continuation
  -> global one-predecessor/one-successor optimization
  -> temporary global session trajectories
  -> uncertainty-aware dwell / journey metrics
  -> section-state model
  -> future congestion / bottleneck prediction
```

The goal of the experiments was not to prove that every possible global graph model is superior. The goal was to test whether the extra global optimization complexity produced a measurable advantage over the much simpler Geometry-First Architecture 2 under the same evidence and failure modes.

---

## 2. Evidence classes used

Three evidence types are deliberately kept separate.

### 2.1 Real CITIC-MTMC trajectories and camera topology

The common association stress benchmark uses:

- all six official person trajectories from the three CITIC captures;
- official world-coordinate `(x,y)` paths;
- official camera visibility polygons;
- official room/door topology;
- official camera positions.

The six real paths are time-shifted to create controlled concurrent visitors. This increases candidate ambiguity while preserving real human walking paths and real site geometry.

### 2.2 Synthetic appearance and controlled observation corruption

The common benchmark does **not** claim camera-derived ReID accuracy.

Body-appearance embeddings are synthetic latent vectors, deliberately made partially similar for selected pairs. The following errors are injected in a reproducible way:

- local fragmentation;
- missed observations;
- projected-position noise;
- per-camera clock offsets;
- appearance noise;
- appearance corruption;
- complete tracklet drops.

This is a controlled architecture stress test, not a substitute for real retail ReID evaluation.

### 2.3 NVIDIA PhysicalAI Smart Spaces 2026 global trajectories

For the analytics/prediction stage, the experiment uses:

`samples/physicalai/Warehouse_000/ground_truth.json`

Downloaded size: **281,636,586 bytes**.

The file contains:

- 9,000 frames;
- 60 unique people;
- 495,593 person annotations over the full sequence;
- globally consistent object IDs;
- shared 3D/world locations;
- per-frame visible-camera information.

The local calibration/map for this scene was already present in the workspace.

The experiment samples 300 frames at 1 Hz, producing 16,529 person-state rows over 25 world-grid sections.

There is no official retail-bottleneck event label for this scene. Therefore the experiment defines an interpretable congestion proxy from clean world trajectories and evaluates recovery of that clean proxy after controlled tracking/projection corruption. This must not be reported as benchmark ground-truth bottleneck F1.

---

## 3. Reproducible files

Common architecture association stress test:

- `scripts/common_architecture_stress.py`
- `experiments/common_architecture_stress/per_run.json`
- `experiments/common_architecture_stress/summary.json`
- `experiments/common_architecture_stress/summary.csv`
- `experiments/common_architecture_stress/site_priors.json`

PhysicalAI downstream/predictive experiment:

- `scripts/physicalai_bottleneck_experiment.py`
- `experiments/physicalai_bottleneck/results.json`
- `experiments/physicalai_bottleneck/results.csv`

Both scripts are designed to be rerun from:

```powershell
cd C:\Coding\ML\Everseen
.\.venv\Scripts\python.exe .\scripts\common_architecture_stress.py
.\.venv\Scripts\python.exe .\scripts\physicalai_bottleneck_experiment.py
```

---

## 4. Global graph implementation tested

Each local tracklet is a graph node.

Candidate edges are created only when temporal/camera topology constraints permit a continuation.

The tested edge cost includes:

```text
time compatibility
section compatibility
world endpoint / motion-prediction compatibility
appearance distance
tracklet quality penalty
```

Impossible edges are removed before optimization.

The global solver creates left/right copies of tracklets and uses maximum-weight bipartite matching to obtain a path-cover style association with at most:

- one predecessor per tracklet;
- one successor per tracklet.

An ambiguity gate rejects links whose best candidate is too weak or insufficiently separated from alternatives.

This is a practical global graph baseline. It is **not** a trained graph neural network, transformer or full multi-hypothesis Bayesian tracker.

---

## 5. Common association benchmark protocol

The same corrupted tracklets are passed to all three systems:

1. Architecture 1 — section/topology/time + conditional appearance;
2. Architecture 2 — geometry/topology/time + appearance;
3. Architecture 3 — global graph using Architecture-2 style evidence with joint assignment.

Thirty Monte-Carlo seeds are run for every scenario.

The primary clustering metric is **B-cubed precision/recall/F1**, which is well suited to comparing predicted global identity clusters against true person groups when the number of fragments varies.

Additional metrics:

- consecutive-link precision;
- consecutive-link recall;
- number of false-merge clusters;
- excess split clusters;
- predicted global ID count;
- per-person section-dwell L1 error;
- trajectory completeness.

### Scenarios

#### Clean

Very small detection/projection disturbance and essentially clean appearance.

#### Moderate

Moderate fragmentation, misses, 0.20 m position noise, clock noise and limited appearance corruption.

#### Appearance-hard

Geometry is relatively good but body appearance is deliberately ambiguous/corrupted.

#### Geometry-hard

Appearance remains relatively usable but world-position and timing evidence are substantially corrupted.

#### Severe

Heavy fragmentation, misses, position error, timing noise and appearance corruption simultaneously.

---

## 6. Global association results

### 6.1 Clean scenario

Mean results over 30 seeds:

| Method | B³ F1 | Link precision | Link recall | Mean dwell L1 error | Mean trajectory completeness |
|---|---:|---:|---:|---:|---:|
| Raw unstitched | 0.192 | 0.000 | 0.000 | 110.61 s | 0.191 |
| Architecture 1 | 0.843 | 0.944 | 0.942 | 6.73 s | 0.872 |
| **Architecture 2** | **0.954** | **0.975** | **0.975** | **2.68 s** | **0.981** |
| Architecture 3 | 0.927 | 0.967 | 0.967 | 3.39 s | 0.956 |

Architecture 3 is strong in clean conditions, but does not beat the simpler Architecture 2.

### 6.2 Moderate corruption

| Method | B³ F1 | Link precision | Link recall | Mean dwell L1 error | Mean trajectory completeness |
|---|---:|---:|---:|---:|---:|
| Raw unstitched | 0.122 | 0.000 | 0.000 | 109.77 s | 0.170 |
| Architecture 1 | 0.534 | 0.840 | 0.783 | 40.65 s | 0.579 |
| **Architecture 2** | **0.669** | **0.925** | **0.875** | **28.60 s** | **0.678** |
| Architecture 3 | 0.509 | 0.897 | 0.694 | 52.14 s | 0.528 |

The tested global graph becomes too conservative under moderate ambiguity. It protects precision reasonably well, but fails to link enough true fragments, producing too many splits.

### 6.3 Appearance-hard scenario

Mean results over 30 seeds:

| Method | B³ F1 | Link precision | Link recall | Mean dwell L1 error |
|---|---:|---:|---:|---:|
| Architecture 1 | 0.2968 | 0.6601 | 0.5306 | 69.95 s |
| **Architecture 2** | **0.5969** | **0.9093** | **0.8778** | **28.47 s** |
| Architecture 3 | 0.3636 | 0.8350 | 0.6091 | 69.32 s |

This is one of the strongest arguments for geometry-first association: when appearance becomes unreliable, the shared-floor model remains highly informative.

The current global graph again under-links because its conservative ambiguity gate treats many difficult candidates as separate visitors rather than exploiting future evidence deeply enough to recover them.

### 6.4 Geometry-hard scenario

Mean B³ F1 over 30 seeds:

| Method | B³ F1 |
|---|---:|
| **Architecture 1** | **0.4932** |
| Architecture 2 | 0.3252 |
| Architecture 3 | 0.2693 |

This is a crucial negative result for geometry-first designs: once position/synchronization evidence itself becomes badly corrupted, strongly weighting geometry can hurt more than section/topology reasoning.

Architecture 1 wins this deliberately geometry-hostile condition because it depends on coarser section/topology constraints rather than precise world continuity.

### 6.5 Severe corruption

Mean B³ F1 over 30 seeds:

| Method | B³ F1 |
|---|---:|
| **Architecture 1** | **0.2094** |
| Architecture 2 | 0.1995 |
| Architecture 3 | 0.1477 |

All methods are poor. This is the correct scientific conclusion: no association architecture should claim reliable full-person histories when detection, geometry, clocks and appearance are simultaneously bad.

The product should degrade to identity-independent occupancy/flow analytics and lower its confidence.

---

## 7. Why the global graph did not win

The result is useful precisely because it prevents choosing Architecture 3 for novelty alone.

The tested global graph has three practical limitations.

### 7.1 Conservative ambiguity gating causes over-splitting

Under moderate noise, Architecture 3 predicted an average of about 20.5 global IDs for six real visitors, versus about 9.9 for Architecture 2.

Its link precision remained relatively high, but recall fell sharply. For dwell-time analytics, those splits are expensive.

### 7.2 The matching objective is global, but the evidence model is still hand-engineered

Joint assignment cannot create information that is missing from the edge features.

A stronger Architecture 3 would need one or more of:

- learned transition likelihoods;
- uncertainty-calibrated edge probabilities;
- multi-frame appearance embeddings from actual video;
- multi-hypothesis delayed inference over longer windows;
- graph neural scoring;
- explicit mutual-exclusion/occupancy constraints;
- iterative smoothing after future observations arrive.

### 7.3 Extra complexity does not automatically improve accuracy

Architecture 2's greedy but strongly constrained geometry-first matcher was easier to tune and performed better in the clean/moderate/appearance-hard conditions that most closely match the intended calibrated deployment assumption.

Therefore the experiment does **not** show that global trajectory association is inherently inferior. It shows that the tested global graph baseline is not mature enough to justify becoming the hackathon's core dependency.

---

## 8. PhysicalAI downstream analytics experiment

### 8.1 Data

The experiment samples:

- 300 time steps at 1 Hz;
- 60 unique people;
- 16,529 person observations;
- 25 equal world-grid sections.

### 8.2 Clean congestion proxy

For each section, clean baselines are estimated from the clean world trajectories.

The proxy bottleneck state combines:

- occupancy relative to that section's historical distribution;
- speed loss relative to free-flow speed;
- positive inflow/outflow imbalance;
- direction entropy;
- temporal persistence.

The resulting clean positive rate is **10.56%**.

Again: this is a reproducible analysis target, not an official NVIDIA bottleneck label.

### 8.3 Corruption scenarios

#### Mild

- 3% missed observations;
- 0.12 m position noise;
- 1% duplicate/global-track observations;
- 1% ID-switch corruption.

#### Moderate

- 8% misses;
- 0.30 m position noise;
- 4% duplicate observations;
- 4% ID switches.

#### Severe

- 18% misses;
- 0.65 m position noise;
- 10% duplicate observations;
- 10% ID switches.

Architecture 2 and Architecture 3 use geometry-based spatial duplicate suppression for the identity-independent analytics layer. Architecture 1 does not use that world-space fusion in this test.

---

## 9. Bottleneck-state recovery results

### Mild corruption

| Method | Precision | Recall | F1 | Occupancy MAE | Mean abs. conservation residual |
|---|---:|---:|---:|---:|---:|
| Architecture 1 | 0.938 | **0.757** | **0.837** | 0.114 | 0.216 |
| Architecture 2 | **0.943** | 0.748 | 0.834 | **0.099** | **0.189** |
| Architecture 3 analytics layer | **0.943** | 0.748 | 0.834 | **0.099** | **0.189** |

At mild corruption, both representations remain operationally useful. Architecture 2/3 recover occupancy more accurately due to geometry deduplication; Architecture 1 happens to recover slightly more positive events in this particular proxy.

### Moderate corruption

| Method | Precision | Recall | F1 | Occupancy MAE | Conservation residual |
|---|---:|---:|---:|---:|---:|
| Architecture 1 | 0.871 | **0.359** | **0.508** | 0.287 | 0.473 |
| Architecture 2 | **0.887** | 0.343 | 0.494 | **0.243** | **0.383** |
| Architecture 3 analytics layer | **0.887** | 0.343 | 0.494 | **0.243** | **0.383** |

Precision remains high, but recall falls substantially. This means corrupted tracking/projection tends to hide true congestion more often than create false alarms.

### Severe corruption

| Method | Precision | Recall | F1 | Occupancy MAE | Conservation residual |
|---|---:|---:|---:|---:|---:|
| Architecture 1 | 0.811 | 0.0257 | 0.0497 | 0.543 | 0.752 |
| Architecture 2 | 0.824 | 0.0256 | 0.0495 | **0.501** | **0.613** |
| Architecture 3 analytics layer | 0.824 | 0.0256 | 0.0495 | **0.501** | **0.613** |

The alert layer is no longer dependable. The large conservation residual is useful precisely because it provides an internal signal that the scene estimate has become unreliable.

---

## 10. Predictive bottleneck experiment

Architecture 3's distinctive downstream feature is forecasting rather than only current-state detection.

### Target

Predict whether a section will enter the clean congestion proxy within the next **10 seconds**.

### Features

Current section state includes:

- occupancy;
- median speed;
- inflow;
- outflow;
- flow imbalance;
- direction entropy;
- recent occupancy trend.

### Model

An intentionally modest `GradientBoostingClassifier` is used before considering neural temporal models.

The time sequence is split chronologically into train/validation/test intervals.

The classification threshold is selected only on the validation interval to maximize validation F1, then frozen for the test interval.

### Measured test result

| Quantity | Value |
|---|---:|
| Validation-selected probability threshold | 0.223 |
| Validation best F1 | 0.456 |
| Test samples | 2,000 |
| Test positive rate | 25.4% |
| Precision | 0.348 |
| Recall | **0.628** |
| Test F1 | **0.448** |
| ROC-AUC | **0.683** |

There is useful predictive signal, but the result is not strong enough to justify presenting learned forecasting as the core hackathon accomplishment.

The appropriate interpretation is:

> A lightweight section-state model can provide an experimental early-warning layer, but it should remain a stretch feature until real retail bottleneck labels are available.

---

## 11. Practical Architecture 3 strengths

1. **Correct conceptual treatment of uncertain identity.** A tracklet graph is a much better abstraction than treating a tracker ID as a permanent customer ID.
2. **Can delay decisions.** A production version can use future evidence to resolve an ambiguous handoff.
3. **Naturally supports multiple cues.** Geometry, topology, timing, appearance, pose and uncertainty all fit as edge evidence.
4. **Provides a path toward explicit probabilities.** This is valuable for confidence-aware dwell and journey analytics.
5. **Naturally connects to a store-state/digital-twin model.** Section states can support prediction, simulation and cause-aware bottleneck reasoning.

---

## 12. Practical Architecture 3 weaknesses exposed experimentally

1. **No measured accuracy advantage over Architecture 2.** In the common stress test, Architecture 2 wins clean, moderate and appearance-hard conditions.
2. **Over-splitting under ambiguity.** Conservative graph matching leaves too many unresolved fragments.
3. **Large engineering scope.** Building/training a robust global graph model plus the underlying detector/tracker/geometry stack is risky in a 48-hour prototype.
4. **Needs labelled handoffs or reliable self-supervised calibration to train well.** Public calibrated data help, but MMPTRACK Retail is gated and real target-store labels are unknown.
5. **Forecasting is only moderately predictive.** ROC-AUC 0.683 and F1 0.448 are encouraging but not compelling as the core innovation.
6. **Harder to explain to judges.** A geometry-first system can show exactly why two observations were fused; a learned global graph can be less transparent.

---

## 13. Scientific conclusion for Architecture 3

The experiments **do not support selecting the current Architecture 3 implementation as the primary hackathon architecture**.

This is not a failure of the research direction. It is an evidence-based scope decision.

The strongest Architecture-3 concepts should be retained selectively:

- represent data as tracklets rather than permanent local IDs;
- allow tentative/ambiguous global identity state;
- keep association confidence;
- optionally delay difficult handoff decisions;
- use a section-state vector for TTC/early-warning experiments;
- preserve the tracklet graph as a future research extension.

But the prototype should not depend on a full global graph model to obtain correct dwell and bottleneck analytics.

---

## 14. Recommended role in the final hackathon system

Use Architecture 3 as a **research extension layer on top of Architecture 2**, not as the core stack.

Recommended final hierarchy:

```text
Architecture 2 geometry-first system = production/demo core

Architecture 1 section/topology logic = fallback and robustness layer

Architecture 3 = optional:
  - ambiguous-handoff queue
  - delayed reconciliation
  - confidence posterior
  - TTC / future congestion prediction
```

This keeps the scientifically interesting ideas while avoiding the highest implementation and validation risk.

---

## 15. Limitations

- CITIC has only two simultaneous people per original capture; concurrency was created by time-aligning six real paths.
- Appearance embeddings in the common benchmark are synthetic; no real ReID accuracy is claimed.
- Position/timing/fragmentation corruptions are controlled perturbations, not an empirically learned error distribution from the target cameras.
- PhysicalAI is synthetic smart-space data, not a live supermarket.
- PhysicalAI congestion labels are derived proxies, not official event annotations.
- The graph implementation is a global bipartite path-cover baseline, not a learned GNN/transformer/global trajectory model.
- MMPTRACK Retail could not be used because access requires accepting/signing the dataset agreement externally.
- A stronger learned Architecture 3 may outperform the tested baseline once target-domain handoff data are available; that possibility is not contradicted by these experiments.

---

## 16. Bottom line

Architecture 3 provides the most ambitious research story, but the measured evidence favors a simpler design for the hackathon.

The key result is:

> **Global optimization did not compensate for uncertain evidence strongly enough to beat a well-constrained geometry-first association pipeline.**

Architecture 3 should therefore remain an optional reconciliation/prediction extension, while Architecture 2 becomes the core and Architecture 1 provides robust section/topology fallback behavior.
