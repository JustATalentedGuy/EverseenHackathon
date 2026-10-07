# Architecture 1 Experiments — Section-First Topology-Aware Tracklets

Date: 2026-10-04

Workspace: `C:\Coding\ML\Everseen`

## 1. Question tested

Architecture 1 treats **section history** as the main spatial representation and uses camera/section topology to repair short local fragments and constrain cross-camera handoffs.

The tested pipeline is:

```text
camera observation / local tracklet
  -> section mapping
  -> section hysteresis
  -> short-gap local tracklet repair
  -> topology + transition-time gated cross-camera association
  -> session section history
  -> dwell / occupancy / boundary-flow analytics
```

The experiments answer five concrete questions:

1. How sensitive is section assignment to world-position error, and how much does hysteresis reduce boundary chatter?
2. Can a section/motion constrained stitcher repair controlled local fragmentation without introducing false merges?
3. Does section/camera topology improve blind-gap handoff over time gating alone?
4. Which downstream metrics remain useful when identity fragments, and which recover after repair?
5. Does the supplied CITIC homography behave sensibly on real video detections?

The primary quantitative evidence is **CITIC-MTMC**, which satisfies the high-suitability rule: multiple synchronized cameras, per-camera calibration/visibility, a floorplan and room/door graph, common world-coordinate GT, and natural gapped camera coverage.

---

## 2. Dataset and exact data used

### CITIC-MTMC

Official repository:

`https://github.com/GTEC-UDC/citic-mtmc-dataset`

Repository commit used:

`c359afd3f63a629eae9e28f2657a7a974302d70c`

Zenodo DOI:

`10.5281/zenodo.17511785`

Current archive downloaded:

- file: `GTEC-UDC/citic-mtmc-dataset-v2025-11-03_lfs.zip`
- size: **763,352,844 bytes**
- MD5 supplied by Zenodo and verified locally: **11006494bb4c7580e57b0b65d09fb139**

The GT experiments use all three official `capture*_gt.mot.txt` files plus:

- `map_config/room_map.json` — room rectangles and door coordinates;
- all `Node*.json` files — camera positions, calibration and official visibility polygons;
- fixed processed video rate of 25 FPS from the official README.

The official GT rows contain frame, person ID and `(x,y,z)` position. CITIC generates these positions by timestamping known floor waypoints and interpolating between them. They are therefore the dataset's official world-position GT, but are not frame-by-frame image-box annotations.

### Real-video component

Only one small real video was extracted for inference:

`datasets/citic_video_subset/capture1/Showroom.mp4`

Size: **32,557,290 bytes**.

The detector/tracker component uses:

- `models/yolo11n.pt`;
- Ultralytics ByteTrack;
- person class only;
- confidence threshold 0.25;
- CPU inference;
- 12 seconds / 300 frames.

The segment starts at frame 3125, the beginning of the longest contiguous capture-1 interval in which official GT lies inside the official Showroom visibility polygon.

---

## 3. Exact MMPTRACK blocker

MMPTRACK Retail was **not run**.

The official dataset page requires researchers to sign the dataset Terms & Conditions and email the signed agreement to the organizers before access is granted. There is no already-authorized MMPTRACK copy in this workspace, and sending/accepting that external agreement is outside this worker's existing authorization.

Official access page:

`https://iccv2021-mmp.github.io/subpage/dataset.html`

This is an access blocker, not a technical incompatibility. MMPTRACK Retail remains the best next real/staged-retail validation because it supplies synchronized calibrated cameras, persistent IDs and common-world footpoints.

---

## 4. Reproducible implementation

Scripts:

- `scripts/architecture1/citic_common.py`
- `scripts/architecture1/run_gt_experiments.py`
- `scripts/architecture1/run_video_component.py`

Configuration and outputs:

- `experiments/architecture1/experiment_config.json`
- `experiments/architecture1/dataset_summary.json`
- `experiments/architecture1/section_hysteresis.csv`
- `experiments/architecture1/fragmentation_repair.csv`
- `experiments/architecture1/handoff_tradeoff.csv`
- `experiments/architecture1/analytics_robustness.csv`
- `experiments/architecture1/summary.json`
- `experiments/architecture1/video_showroom_frames.csv`
- `experiments/architecture1/video_showroom_summary.json`

GT experiment command:

```powershell
.\.venv\Scripts\python.exe .\scripts\architecture1\run_gt_experiments.py `
  --dataset-root .\datasets\citic_mtmc `
  --output-dir .\experiments\architecture1 `
  --seed 20261004
```

Real-video command:

```powershell
.\.venv\Scripts\python.exe .\scripts\architecture1\run_video_component.py `
  --dataset-root .\datasets\citic_mtmc `
  --video .\datasets\citic_video_subset\capture1\Showroom.mp4 `
  --model .\models\yolo11n.pt `
  --output-dir .\experiments\architecture1 `
  --capture 1 --camera Showroom --seconds 12 --conf 0.25
```

Random seed for controlled fragmentation/noise: **20261004**.

---

## 5. Section and camera model derived from official metadata

The room graph is derived only from shared door coordinates in `room_map.json`:

```text
ESC <-> HA <-> HA3 <-> PC <-> PF
                         <-> SH
```

`HA2`, `OUT`, and `SG` have no matching room-door edge in the supplied simplified room map.

To follow Architecture 1's duplicate-avoidance rule, each section is assigned a primary camera from official visibility polygons by sampling the section area and selecting the camera with the largest visible fraction.

Important measured coverage examples:

| Section | Primary camera | Approx. sampled coverage |
|---|---|---:|
| HA | HallWide | 92.1% |
| HA3 | PC | 46.7% |
| PC | PC | 89.9% |
| PF | PF | 72.6% |
| SH | Showroom | 66.8% |

Across the three GT captures, the owner-camera model retained on average **90.74%** of official GT observations. This missing ~9.3% is a real limitation of the coverage/ownership abstraction and later appears as a small occupancy error even when identity linking is correct.

CITIC capture summary:

| Capture | GT rows | People | GT duration | Owner-visible rows | Natural owner-camera tracklets | Natural camera handoffs |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7,001 | 2 | 169.28 s | 6,306 | 16 | 12 |
| 2 | 8,089 | 2 | 194.16 s | 7,283 | 17 | 12 |
| 3 | 7,631 | 2 | 159.44 s | 7,028 | 16 | 12 |
| **Total** | **22,721** | — | **522.88 s** | **20,617** | **49** | **36** |

The handoff benchmark below evaluates **34** of those transitions because it applies a maximum 12-second handoff gap; two natural transitions exceed that evaluation window.

---

## 6. Experiment A — section mapping and hysteresis

### Procedure

The official GT `(x,y)` trajectory is treated as the reference position. Isotropic Gaussian position noise is injected independently at each observation:

```text
x' = x + Normal(0, sigma)
y' = y + Normal(0, sigma)
```

Tested `sigma`:

`0, 0.05, 0.10, 0.25, 0.50 m`

Room assignment uses the official rectangular room definitions. Section hysteresis commits a new label only after it persists for:

`1, 3, 6, 12 frames = 0.04, 0.12, 0.24, 0.48 s`.

The injected noise is a **controlled sensitivity test**, not a claim about CITIC's measured calibration error.

### Metrics

No custom score is used. The CSV reports:

- frame-level section accuracy;
- section-transition precision, recall and F1;
- transition timing MAE in seconds for matched events;
- dwell MAE in seconds per person-section;
- count of rapid `A -> B -> A` boundary-churn events.

Transition events are matched when the section pair agrees and timing is within 12 frames / 0.48 seconds.

### Measured results

Selected rows from `section_hysteresis.csv`:

| Noise sigma | Hysteresis | Section accuracy | Transition P | Transition R | Transition F1 | Churn events | Pred. transitions |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.00 m | 0.04 s | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 50 |
| 0.05 m | 0.04 s | 0.964 | 0.061 | 1.000 | 0.114 | 775 | 824 |
| 0.05 m | 0.24 s | 0.934 | 0.840 | 0.840 | **0.840** | **0** | 50 |
| 0.10 m | 0.04 s | 0.960 | 0.052 | 1.000 | 0.099 | 911 | 960 |
| 0.10 m | 0.24 s | 0.950 | 0.700 | 0.840 | **0.764** | **1** | 60 |
| 0.25 m | 0.04 s | 0.949 | 0.036 | 1.000 | 0.070 | 1,285 | 1,382 |
| 0.25 m | 0.12 s | 0.960 | 0.288 | 0.980 | 0.445 | 89 | 170 |
| 0.25 m | 0.24 s | 0.921 | 0.414 | 0.480 | 0.444 | **1** | 58 |
| 0.50 m | 0.04 s | 0.873 | 0.011 | 1.000 | 0.023 | 3,421 | 4,348 |
| 0.50 m | 0.12 s | 0.951 | 0.237 | 0.900 | **0.375** | 92 | 190 |

At 5–10 cm injected position noise, a 0.24-second persistence rule converted hundreds of false boundary events into almost none, at the cost of some transition latency and recall.

At 25–50 cm noise, hysteresis still suppresses chatter but cannot make the section-transition problem reliable by itself. This is a useful deployment finding: **hysteresis is a boundary-noise filter, not a substitute for adequate projection accuracy**.

The full sweep is retained rather than reporting one universal hysteresis constant because the precision/recall tradeoff changes strongly with spatial noise.

---

## 7. Experiment B — controlled local fragmentation and repair

### Procedure

Official GT owner-camera tracklets are fragmented synthetically to isolate the tracklet-repair problem from detector variation.

Tested fragmentation rates:

`2, 5, 10, 15 random cuts/minute`

Each injected cut removes 6 frames / **0.24 seconds** around the break.

Local repair candidates must satisfy:

- same camera;
- gap <= 1.5 seconds;
- same or adjacent section in the official room graph;
- implied endpoint speed <= 3.0 m/s;
- no temporal overlap through greedy one-in/one-out linking.

The stitch score uses normalized gap duration, endpoint speed, and section hop count. No appearance/ReID is used in this experiment.

### Metrics

- precision = true accepted repair links / all accepted links;
- recall = true accepted repair links / all injected repair links eligible under the evaluation window;
- F1;
- false-merge rate = `1 - precision`;
- false-split rate = `1 - recall`.

### Measured results

At threshold 0.20, the stitcher is conservative and leaves splits:

| Cuts/min | Fragments | True repair links | TP | False merges | False splits | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 80 | 22 | 13 | 0 | 9 | 1.000 | 0.591 | 0.743 |
| 5 | 101 | 30 | 22 | 0 | 8 | 1.000 | 0.733 | 0.846 |
| 10 | 159 | 51 | 43 | 0 | 8 | 1.000 | 0.843 | 0.915 |
| 15 | 193 | 68 | 52 | 0 | 16 | 1.000 | 0.765 | 0.867 |

At threshold **0.35 and above**, all injected local repair links were recovered with zero false merges in this deterministic run, including at 15 cuts/minute.

That perfect local result must be interpreted narrowly. Each CITIC capture contains only two people and the perturbation creates short gaps along already-correct world trajectories, so geometry/topology makes the repair task unusually separable. It demonstrates that the proposed constraints can recover **controlled short fragmentation**; it does not establish tracker repair accuracy in a dense store.

---

## 8. Experiment C — cross-camera handoff: time-only vs topology + time

### Procedure

The benchmark uses natural camera changes in the owner-camera GT simulation.

For each test capture, transition-time priors are learned from the other two captures only. This is a leave-one-capture-out protocol for the **time prior**.

Two candidate strategies are compared:

### Time-only

Candidate must occur within a maximum 12-second gap. Score is based only on gap duration.

### Topology + time

Candidate must additionally satisfy camera reachability derived from:

- official room/door topology;
- official camera visibility polygons;
- section compatibility.

Its score combines deviation from leave-one-capture-out transition-time priors and room-hop distance.

No ReID appearance embedding is used, which directly tests the value of Architecture 1's topology/time filtering.

### Measured false-merge / false-split tradeoff

There are **34 true handoffs** inside the 12-second evaluation window.

| Strategy | Threshold | Accepted | TP | False merges | False splits | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Time only | 0.10 | 27 | 26 | 1 | 8 | 0.963 | 0.765 | 0.852 |
| Time only | 0.20 | 32 | 30 | 2 | 4 | 0.938 | 0.882 | 0.909 |
| Time only | 0.50 | 33 | 31 | 2 | 3 | 0.939 | 0.912 | 0.925 |
| Time only | 0.70 | 34 | 32 | **2** | **2** | 0.941 | 0.941 | **0.941** |
| Topology + time | 0.10 | 22 | 22 | **0** | 12 | 1.000 | 0.647 | 0.786 |
| Topology + time | 0.20 | 28 | 28 | **0** | 6 | 1.000 | 0.824 | 0.903 |
| Topology + time | 0.35 | 33 | 33 | **0** | **1** | 1.000 | 0.971 | **0.985** |
| Topology + time | 0.70 | 33 | 33 | **0** | **1** | 1.000 | 0.971 | **0.985** |
| Topology + time | 1.00 | 34 | 34 | **0** | **0** | 1.000 | 1.000 | 1.000 |

The important evidence is the shape of the tradeoff, not the single 1.0 point: **topology removed false merges throughout this sweep**, while the threshold controlled how many true continuations were left split.

At a more conservative threshold of 0.35, topology+time delivered F1 0.985 with zero false merges and one false split, compared with time-only F1 0.909 with two false merges and four false splits at the same threshold.

Because CITIC has only two people per capture, these absolute accuracies are optimistic. The result supports topology gating as a search-space constraint; it does not prove appearance-free MTMC in crowded retail scenes.

---

## 9. Experiment D — dwell / occupancy / flow robustness under fragmentation

### Procedure

The controlled corruption level is:

- 10 cuts/minute;
- 6 frames removed per cut.

Three stages are compared:

1. raw fragmented tracklets;
2. after local repair;
3. after local repair plus topology+time handoff.

The thresholds used here are the best-F1 settings from the deterministic sweeps above. Therefore these analytics results are **data-tuned descriptive results**, not held-out deployment estimates.

### Metrics

Only concrete downstream errors are reported:

- instantaneous section occupancy MAE in people;
- per-person-section dwell MAE in seconds;
- absolute and relative section-flow count error;
- number of predicted identity clusters;
- retained observation recall after injected drops.

For dwell evaluation, predicted clusters are assigned one-to-one to GT identities by maximizing shared observations. This prevents multiple fragments from all being credited to the same GT person.

### Per-capture measured results

| Capture | Stage | Occupancy MAE | Dwell MAE | Flow abs. error / GT events | Pred. clusters | Point recall |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Raw fragments | 0.045 people | 22.456 s | 4 / 8 | 58 | 95.75% |
| 1 | Local repair | 0.045 | 19.592 s | 4 / 8 | 14 | 95.75% |
| 1 | + topology handoff | 0.045 | **4.604 s** | **0 / 8** | 3 | 95.75% |
| 2 | Raw fragments | 0.030 | 25.536 s | 4 / 8 | 53 | 97.03% |
| 2 | Local repair | 0.030 | 22.632 s | 4 / 8 | 15 | 97.03% |
| 2 | + topology handoff | 0.030 | **1.452 s** | **0 / 8** | 3 | 97.03% |
| 3 | Raw fragments | 0.040 | 25.136 s | 4 / 8 | 51 | 96.78% |
| 3 | Local repair | 0.040 | 22.260 s | 4 / 8 | 14 | 96.78% |
| 3 | + topology handoff | 0.040 | **5.764 s** | **0 / 8** | 3 | 96.78% |

### Average over the three captures

| Stage | Occupancy MAE | Dwell MAE | Relative flow error | Mean predicted clusters |
|---|---:|---:|---:|---:|
| Raw fragmented | **0.0384 people** | 24.376 s | 50.0% | 54.0 |
| After local repair | **0.0384** | 21.495 s | 50.0% | 14.33 |
| After local + handoff | **0.0384** | **3.940 s** | **0.0%** | 3.0 |

Mean retained observation recall was **96.52%** at every stage because identity linking cannot recreate observations deliberately removed by fragmentation injection.

This experiment supports the architecture's central separation:

- **occupancy is largely identity-independent** and remained unchanged by repair;
- **per-person dwell is identity-sensitive** and improved strongly after tracklet linking;
- boundary flow in this small simulation recovered once cross-camera/section continuity was restored.

The remaining average of 3 predicted clusters for 2 real people means one split remained per capture in this analytics setting, which is consistent with the non-zero residual dwell error.

Only eight reference section-flow events exist per capture under this owner-camera representation, so the 0% final flow error should not be generalized beyond this small experiment.

---

## 10. Experiment E — real CITIC Showroom video sanity check

### Why this component exists

The GT perturbation experiments isolate Architecture 1 mechanics, but they bypass detection. To verify that the supplied camera geometry is usable with real detections, one small real video was processed through YOLO11n + ByteTrack.

### Evaluation basis

CITIC does not provide image bounding-box GT. Therefore detector precision/recall, HOTA or IDF1 **cannot be computed honestly from this release**.

Instead, official world GT is filtered by the official Showroom visibility polygon to obtain the expected number of visible GT people per frame. Detection bottom-centers are then projected through the official Showroom homography.

### Measured results on 300 frames / 12 seconds

| Quantity | Measured value |
|---|---:|
| Mean official GT people visible / frame | 1.000 |
| Mean YOLO person detections / frame | 1.337 |
| Person-count MAE / frame | **0.390 people** |
| Frames with exact count | **61.0%** |
| Total person detections | 401 |
| Detection footpoints projecting inside official camera visibility | **92.52%** |
| Detection footpoints projecting inside SH room polygon | **92.77%** |
| ByteTrack IDs observed | 4 |
| Median ByteTrack track length | 54 frames / 2.16 s |

The projection result is encouraging as a **geometry sanity check**: most detected box bottom-centers land in the region that the official camera metadata says is visible.

The count result also shows why GT-only robustness tests must not be confused with real end-to-end performance: this small YOLO model over-detected relative to the one-person GT interval and produced four temporary track IDs over 12 seconds.

The four IDs are descriptive only. Without image-level person-ID GT, it would be incorrect to call them four ID switches or compute a tracking F1/HOTA value.

---

## 11. What the experiments support

### Supported under the tested CITIC conditions

1. **Section hysteresis is necessary once projection noise is non-trivial.** At 0.05 m injected noise, 0.24 s hysteresis reduced boundary-churn events from 775 to 0; at 0.10 m, from 911 to 1.

2. **Topology is useful for conservative handoff.** In the evaluated 34-handoff set, topology+time removed all false merges across the threshold sweep; time-only produced one or two false merges depending on threshold.

3. **False merge vs false split is a tunable operating point.** Conservative topology thresholds retained precision 1.0 but left more splits; relaxing the threshold recovered them in this small dataset.

4. **Aggregate occupancy is much less dependent on identity continuity than dwell.** Under controlled fragmentation, occupancy MAE remained ~0.038 people regardless of linking, while mean dwell MAE fell from 24.376 s to 3.940 s after the complete repair/handoff pipeline.

5. **The supplied direct Showroom homography is usable with real detector bottom-centers.** 92.52% of projected detections landed inside the official visibility polygon in the 12-second test.

### Not supported / not proven

- dense retail-crowd performance;
- MMPTRACK Retail end-to-end behavior;
- robust ReID under similar clothing;
- detector/tracker HOTA or IDF1 on CITIC, because image-box identity GT is absent;
- universal noise/hysteresis thresholds;
- universal travel-time thresholds;
- performance with many simultaneous handoff candidates;
- centimeter-level localization accuracy;
- accurate analytics in unobserved sections such as CITIC's SG or poorly covered ESC area.

---

## 12. Important limitations and exact blockers

### CITIC is sparse

Each of the three supplied captures has only **two people**. The perfect or near-perfect association numbers are therefore much easier than a busy store and should be treated as mechanism validation.

### GT is interpolated world trajectory, not image annotation

The official GT is created from known waypoints and timestamps with interpolation. It is well suited to section/topology experiments but cannot directly score image detector boxes or image-level identity association.

### Controlled fragmentation is not a learned tracker failure distribution

The fragmentation experiment removes short deterministic-random intervals at specified cuts/minute. It tests whether Architecture 1 can repair such gaps. It does not claim those rates reproduce ByteTrack or BoT-SORT error statistics.

### Hysteresis noise is injected, not measured calibration uncertainty

The 5–50 cm Gaussian noise sweep is a sensitivity curve. A deployment must estimate actual projection error per camera before selecting a persistence time.

### Owner-camera simulation discards some valid observations

The owner-camera policy intentionally avoids duplicate occupancy counting but retains ~90.7% of CITIC GT observations on average. This demonstrates the architecture tradeoff: duplicate safety can sacrifice coverage.

### MMPTRACK is access-gated

The missing high-value experiment is MMPTRACK Retail. Access requires a signed research agreement sent to the dataset organizers. No authorized data were available in this session, so no MMPTRACK result is claimed.

---

## 13. Recommended next experiment

The next Architecture 1 step should be **MMPTRACK Retail**, once the access agreement is completed:

1. use actual per-camera person annotations/IDs to measure local fragmentation rather than injecting it;
2. map MMPTRACK world footpoints into artificial retail sections;
3. compare raw tracker -> local repair -> topology handoff on HOTA/IDF1/ID switches plus section dwell error;
4. add conditional appearance ReID only where topology/time leaves more than one candidate;
5. repeat false-merge/false-split curves at higher simultaneous-person density.

For CITIC itself, a stronger real-video follow-up would manually annotate a short multi-camera clip with image boxes/IDs around one camera handoff. That would allow the GT-derived section/topology result to be connected to measured detector/tracker errors without inventing image-level labels.

---

## 14. Reproducibility and validation status

- All three Architecture 1 Python scripts pass `py_compile`.
- The CITIC archive checksum matches the Zenodo MD5.
- Every numeric result in this report is present in the generated CSV/JSON artifacts listed above.
- The initial implementation exposed two issues during development: a stateful door-boundary GT tie-break and application of global handoff before local tracklet collapse. Both were fixed **before** the reportable run; current outputs are from the corrected pipeline.
- No MMPTRACK or other inaccessible data were simulated or presented as measured.

The current evidence makes Architecture 1 a credible **deployment-safe fallback** for section-level analytics: it can keep occupancy useful even when identities fragment, while topology/time constraints can selectively restore the person histories needed for dwell and journey metrics. The main unresolved question is how well those association gains survive the much denser appearance ambiguity of real retail data.
