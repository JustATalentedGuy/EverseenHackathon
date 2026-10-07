# Public Dataset Feasibility Study for Retail Dwell-Time & Bottleneck Mapping

Verified: 2026-10-04

## Target requirements

The retail system needs several distinct capabilities, so dataset suitability should be judged per subsystem.

| ID | Requirement |
|---|---|
| R1 | Detect people accurately from ordinary oblique CCTV views, including partial occlusion and crowding. |
| R2 | Assign stable IDs and perform single-camera multi-object tracking over time. |
| R3 | Convert image positions into an approximate store coordinate system or discrete section/zone. |
| R4 | Derive trajectories, dwell time, density, flow and bottlenecks from tracked positions. |
| R5 | Preserve identity across multiple cameras using appearance, trajectory and topology cues rather than face recognition. |
| R6 | Handle cameras whose views only partly overlap, or do not overlap, with temporal gaps between sightings. |
| R7 | Work without assuming a bird's-eye camera. |
| R8 | Be representative of indoor retail/public-space conditions. |

No single public dataset found covers all eight requirements. The strongest practical combination is:

**ATC for long-horizon retail trajectories and floor mapping; CAVIAR for real shopping-centre video and homography; HDA for indoor multi-camera identity, floor layout and homographies; MOT17/MOT20 for robust single-camera tracking; and MTA for explicit cross-camera handoff with overlapping and non-overlapping cameras.**

## Dataset comparison matrix

Legend: Y = directly useful, P = partial/indirect, N = unsuitable for that requirement.

| Dataset | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ATC Shopping Center | N | N | Y | Y | N | N | N | Y |
| CAVIAR Lisbon Shopping Centre | Y | Y | Y | Y | P | P | Y | Y |
| HDA Person Dataset | Y | Y | Y | P | Y | P | Y | Y |
| MOT17, especially sequences 11/12 | Y | Y | N | P | N | N | Y | Y |
| MOT20 | Y | Y | N | P | N | N | Y | P |
| CUHK Mall Dataset | Y | N | P | P | N | N | Y | Y |
| EPFL Multi-camera Pedestrians | Y | Y | Y | Y | Y | P | Y | Y |
| EPFL-RLC | Y | P | Y | P | P | N | Y | Y |
| WILDTRACK | Y | Y | Y | Y | Y | N | Y | N |
| MTA - Multi Camera Track Auto | Y | Y | Y | P | Y | Y | Y | N |
| Edinburgh Informatics Forum | N | P | Y | Y | N | N | N | Y |
| JRDB | Y | Y | P | P | N | N | Y | P |
| MultiviewX | Y | P | Y | P | P | N | Y | N |
| MOTSynth | Y | Y | P | P | P | N | Y | N |

---

## 1. ATC Shopping Center Pedestrian Tracking Dataset

**Primary source:** https://dil.atr.jp/crest2010_HRI/ATC_dataset/

**Environment:** Real shopping and business centre in Osaka, Japan.

### Scale / approximate size

| Item | Value |
|---|---|
| Collection period | 24 Oct 2012 to 29 Nov 2013 |
| Recorded days | 92 days |
| Typical recording time | About 09:40-20:20 on Wednesdays and Sundays |
| Covered area | About 900 m² |
| Sensors | 49 3-D range sensors in the raw sample |
| Tracking archives | 9 archives, roughly 3.9-5.1 GB each; about 39.3 GB compressed total |
| One-day sample | About 201 MB |
| Raw 15-minute sensor sample | Four archives totaling about 14.6 GB compressed |

### Annotations / data

Every trajectory row contains:

time, person_id, x, y, z(height), velocity, motion_angle, facing_angle

Coordinates are in millimetres. This is already very close to the downstream representation needed for dwell and bottleneck analysis.

### Spatial metadata

The release includes sensor description and calibration details, a 2-D occupancy grid, and a floor-plan slide with tracking-area details. The occupancy map uses the same coordinate system as the pedestrian trajectories.

### License / access

Free for **research purposes only**. The project asks users to cite the reference paper.

### What it can validate

This is the strongest public dataset found for R3 + R4 + R8. It can directly test per-zone dwell time, heatmaps, density by section, queue/bottleneck detection, flow direction, entry/exit counts, trajectory clustering, and conversion from metric coordinates to arbitrary retail section IDs.

### Limitation

It does not validate RGB person detection or camera-based re-identification because the main tracking release is derived from 3-D range sensors. Treat it as ground truth for the analytics layer after tracking.

---

## 2. CAVIAR Test Case Scenarios - Lisbon Shopping Centre

**Primary source:** https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA1/

**Environment:** Real indoor shopping-centre hallway in Lisbon. The project also contains INRIA lobby clips, but the Lisbon set is the most relevant here.

### Scale / approximate size

| Item | Value |
|---|---|
| Resolution | 384×288 |
| Frame rate | 25 fps |
| Cameras per Lisbon scenario | 2 synchronized views: corridor/along and frontal/across |
| Typical Lisbon sequence length | About 1,500 frames |
| Individual MPEG files | Commonly about 2-21 MB |
| Overall project collection | Commonly reported as about 52 videos / roughly 90k frames across CAVIAR |

### Annotations

Hand-labelled XML/CVML annotations include people, groups, bounding regions and activity/context information. Retail-relevant scenarios include walking past shops, stopping outside shops, entering/exiting shops, browsing/window shopping, waiting, rejoining another person and groups crossing paths.

### Camera / geometry metadata

The page provides image-to-world reference point correspondences for the Lisbon scene, so a ground-plane homography can be computed. Example world coordinates are given in centimetres.

The two views are intended to be synchronized, but the source warns that paired files can start at slightly different times and that occasional capture errors duplicate a frame while omitting the expected next frame. Embedded timestamps can be used for alignment.

### License / access

The official page says the data are publicly available and labels usability as **Creative Commons BY-SA**. Publications should acknowledge the EC-funded CAVIAR project.

### What it can validate

Very strong for real retail R1, R2, R3, R4, R7 and R8: low-resolution detection, track identity, floor projection, dwell near storefronts, and enter/leave behaviour. It can support a small cross-view experiment, but it is too small and scripted to be the only MTMC benchmark.

---

## 3. HDA Person Dataset

**Primary source:** https://vislab.isr.tecnico.ulisboa.pt/hda-dataset/

**Environment:** Real indoor office/public circulation space across three floors of the Institute for Systems and Robotics in Lisbon.

### Scale

| Item | Value |
|---|---|
| Cameras recorded simultaneously | 18 |
| Fully labelled cameras | 13 |
| Recording duration | About 30 minutes |
| People | 85 |
| Labelled frames | 75,207 |
| Bounding boxes | 64,028 |
| Camera resolutions | 640×480, 1280×800 and 2560×1600 |
| Sampling rates | 1, 2 or 5 Hz depending on camera |

### Annotations

Each labelled person has a tightly fitted bounding box, a unique person ID, an occlusion flag and a crowd flag. A special unknown-person identity is used when the annotator is uncertain. The dataset is explicitly presented for pedestrian detection, re-identification and multi-camera tracking.

### Camera / geometry metadata

The official page provides camera placement diagrams across three floors, synchronization information, and from release v1.3 a **homography for each camera from image coordinates to the ground plane**.

### License / access

The current page does not publish a clear reusable dataset license. It says the dataset is for high-definition-surveillance research and asks interested users to contact the maintainer. Subjects authorised scientific-research use. Treat commercial and redistribution rights as unverified until confirmed with the maintainer.

### What it can validate

One of the best overall datasets for real indoor detection, single-camera tracking, cross-camera re-identification without faces, image-to-ground homography, camera topology from floor placement, and multi-camera identity consistency.

The main weaknesses are office rather than retail activity and relatively low frame rates on many cameras.

---

## 4. MOT17

**Primary source:** https://motchallenge.net/data/MOT17/

**Environment:** Mixed pedestrian scenes. The official dataset explicitly describes two sequences as a **busy shopping mall**.

### Scale / download

| Item | Value |
|---|---|
| Full archive | About 5.5 GB |
| Underlying sequences | 7 train + 7 test |
| Detector versions | Each sequence is repeated with DPM, Faster-RCNN and SDP detections |
| License | CC BY-NC-SA 3.0 via MOTChallenge |

### Retail-relevant sequences

| Sequence | Frames | Duration | Tracks | Boxes | Description |
|---|---:|---:|---:|---:|---|
| MOT17-11 | 900 | 30 s | 75 | 9,436 | Forward-moving camera in a busy shopping mall |
| MOT17-12 | 900 | 30 s | 91 | 8,667 | Forward-moving camera in a busy shopping mall |

### Annotations / use

Standard MOTChallenge pedestrian track IDs and bounding boxes. Strong for detector quality, track continuity, ID switches and occlusion handling in a mall visual domain.

### Limitation

No store-floor calibration or multi-camera topology is provided. The mall camera is moving, so the sequence is not representative of the intended fixed-CCTV geometry. Use for R1/R2/R7/R8 only.

---

## 5. MOT20

**Primary source:** https://motchallenge.net/data/MOT20/

**Environment:** Extremely crowded public scenes, including several **crowded indoor train stations**.

### Scale

| Item | Value |
|---|---|
| Full archive | About 5.0 GB |
| Sequences | 4 train + 4 test |
| Frames | 8,931 train + 4,479 test |
| Training boxes | 1,336,920 |
| Test boxes listed by benchmark | 765,465 |
| License | CC BY-NC-SA 3.0 via MOTChallenge |

Indoor sequences include MOT20-01, MOT20-02 and MOT20-07. MOT20-02 alone contains 202,215 labelled boxes over 2,782 frames.

### What it can validate

Use this as the crowding/occlusion stress test: detector recall in dense scenes, ID fragmentation during long occlusion, and whether aggregate density/bottleneck estimates remain stable despite imperfect identity tracking.

It provides no floor calibration or multi-camera topology.

---

## 6. CUHK Mall Dataset

**Primary source:** https://staff.ie.cuhk.edu.hk/~ccloy/downloads_mall_dataset.html

**Environment:** Real mall webcam.

### Scale

| Item | Value |
|---|---|
| Frames | 2,000 |
| Resolution | 640×480 |
| Frame rate | Less than 2 Hz |
| Pedestrian annotations | More than 60,000 head labels |

### Annotations / geometry

The release includes exhaustive pedestrian head positions, perspective-normalised features and a **perspective normalisation map** for correcting scale changes with depth.

### License

Research purposes only; commercial use prohibited.

### What it can validate

Useful for static-camera retail density estimation and perspective-aware counting. Poor for unique-ID tracking because it contains head-point annotations rather than track identities.

---

## 7. EPFL Multi-Camera Pedestrian Videos

**Primary source:** https://www.epfl.ch/labs/cvlab/data/data-pom-index-php/

The collection has several useful subsets.

### Indoor laboratory sequence

4 synchronized cameras, approximately 2 m above ground, 4-person and 6-person variants, around 2.5 minutes, 25 fps, indoor oblique viewpoints.

### Underground passageway

4 cameras at 25 fps in a poorly lit underground passageway to a train station.

### Geometry

EPFL provides calibration for every sequence. Depending on the sequence this is a ground-plane/head-plane homography, Tsai calibration, or a generic projective camera. Some subsets include manually annotated person positions on a shared top-view grid; the 6-person laboratory ground truth uses a 56×56 grid.

### License

The page says the videos, calibration and ground truth are copyrighted by CVLab-EPFL and may be used for research purposes with citation.

### What it can validate

An excellent small sanity dataset for feet-point to floor-coordinate conversion, multi-view fusion, projection consistency across cameras and indoor multi-camera tracking before moving to larger data.

---

## 8. EPFL-RLC Multi-Camera Dataset

**Primary source:** https://www.epfl.ch/labs/cvlab/data/data-rlc/

**Environment:** EPFL Rolex Learning Center, an indoor public building.

### Scale

| Item | Value |
|---|---|
| Cameras | 3 static HD cameras |
| Capture resolution | 1920×1080 |
| Capture frame rate | 60 fps |
| Post-processed sequence | 8,000 frames per camera at 480×270 |
| Dataset ZIP | About 1.1 GB |
| Manual multi-view examples | 4,088 |

### Geometry / annotations

The cameras are synchronized and calibrated with the Tsai model. The shared ground area is discretized into a **55×45 grid**, and a positions file records where each ground position projects into all three cameras.

The labels are balanced occupied/free multi-view position examples rather than full identity trajectories.

### License

The current page does not state a dedicated dataset license. Treat reuse/redistribution terms as not explicitly specified and confirm before non-research distribution.

### What it can validate

Strong proof of the floor-grid architecture:

camera image -> projected person location -> shared floor grid -> occupancy/density

It is weaker for identity/re-identification.

---

## 9. WILDTRACK

**Primary source:** https://www.epfl.ch/labs/cvlab/data/data-wildtrack/

**Environment:** Outdoor public area in front of ETH Zurich. It is not retail, but it is one of the strongest public calibration benchmarks for multi-camera pedestrians.

### Scale

| Item | Value |
|---|---|
| Cameras | 7 static cameras |
| Resolution | 1920×1080 |
| Original capture | 60 fps |
| Synchronized frames supplied | 10 fps |
| Fully annotated frames | 400 frames at 2 fps |
| Typical people per frame | About 20 |
| Approx. single-view boxes | About 56,000 |

### Camera / world metadata

The release contains accurate intrinsic and extrinsic calibration, synchronized cameras, a dense **480×1440 ground grid**, a positions file mapping each world-grid cell into all seven views, and person annotations linked to occupied ground-position IDs.

### What it can validate

Excellent for multi-view detection, world-coordinate fusion, shared ground-plane occupancy and trajectory estimation from several oblique cameras.

### Limitations / license

Coverage is largely overlapping, so it is not a long-gap handoff benchmark. The current project page provides downloads but does not state a clear standalone dataset license in the inspected text; verify redistribution/commercial terms separately.

---

## 10. MTA - Multi Camera Track Auto

**Primary dataset repository:** https://github.com/schuar-iosb/mta-dataset

**Paper:** https://openaccess.thecvf.com/content_CVPRW_2020/html/w70/Kohl_The_MTA_Dataset_for_Multi-Target_Multi-Camera_Pedestrian_Tracking_by_Weighted_CVPRW_2020_paper.html

**Environment:** Synthetic GTA-V urban environment. It is not retail, but it is one of the most directly relevant datasets for the identity-handoff problem.

### Scale

| Item | Value |
|---|---|
| Cameras | 6 |
| Person identities | More than 2,800 |
| Total video duration | About 102 minutes |
| Main video archive | 41 GB zipped / 42 GB unzipped |
| Full-coordinate annotations | 28.6 GB zipped / 235 GB unzipped |
| Short subset | 4 minutes; 1.7 GB zipped / 1.8 GB unzipped |
| Re-ID subset | 0.8 GB zipped / 1.2 GB unzipped |

### Annotations / topology

The data includes per-frame person ID, camera ID, bounding box, day/night periods, and extensive world/body-joint coordinates in the full release.

The paper explicitly studies detection, per-camera tracking, re-identification, camera transition-time constraints, homography matching, overlapping/non-overlapping cameras, and motion prediction across time gaps.

The six-camera layout intentionally contains **both overlapping and non-overlapping cameras**.

### License / access

Request-gated by email. The official repository asks users to declare research/educational use only, states that commercial use is prohibited, and requires purchase of a legal GTA V copy.

### What it can validate

This should be the main controlled benchmark for R5 + R6: matching a track ending in one camera to the correct person entering another camera, appearance-based re-ID without facial recognition, camera topology and expected travel-time gating, and identity recovery after a non-overlap gap.

The visual domain is synthetic/outdoor, so results must be checked again on HDA/CAVIAR or later private retail footage.

---

## 11. Edinburgh Informatics Forum Pedestrian Database

**Primary source:** https://homepages.inf.ed.ac.uk/rbf/FORUMTRACKING/

**Environment:** Indoor atrium/circulation area at the University of Edinburgh Informatics Forum.

### Scale

| Item | Value |
|---|---|
| Observation duration | Several months |
| Target detections | 27+ million |
| Estimated real-person detections | About 7.9 million |
| Tracked trajectories | 92,000+ |
| Typical volume | About 1,000 trajectories per working day |
| Capture rate | About 9 fps, with variation |

### Spatial setup / data

One fixed overhead camera is mounted about 23 m above the floor. Images are 640×480 and correspond to approximately 24.7 mm per pixel on the ground. Known floor-dot spacing and marked entry/exit areas are given for the front door, cafe, stairs, elevator/night exit and labs.

The full historical raw imagery was not retained. The dataset provides detections and tracked trajectories as track ID plus centre-x, centre-y and time samples, with track start/end metadata.

### License

The page asks users to cite the associated dissertation but does not state a clear dataset license. Do not assume commercial redistribution rights.

### What it can validate

Very useful for high-volume dwell calculations, entry/exit flow, trajectory clustering, bottleneck logic and storage design.

Because the viewpoint is bird's-eye and the original images are mostly unavailable, it should not be used as evidence that the proposed front-end will work on ordinary retail CCTV.

---

## 12. JRDB

**Primary source:** https://jrdb.erc.monash.edu.au/dataset/

**Environment:** Mixed indoor and outdoor human environments collected from a mobile robot at approximately human height.

### Scale

| Item | Value |
|---|---|
| Sequences | 54 |
| Video | About 60,000 frames / 64 minutes |
| 2-D human bounding boxes | About 2.4 million |
| 3-D human bounding boxes | About 1.8 million |
| Individual action labels | About 2.8 million |
| Body poses | About 600,000 |
| Panoptic masks | About 428,000 |
| Mask tracklets | About 27,000 |

### Sensors / metadata

360-degree RGB, LiDAR, 2-D and 3-D person boxes, tracking/trajectory tasks, stationary and moving viewpoints, and heavy occlusion/crowding.

### License / access

Current downloads require a JRDB account/login. The public dataset page did not expose a clear data license in the inspected text, so terms should be checked at download time.

### What it can validate

Useful for hard human-height person detection, heavy occlusion, 2-D/3-D tracking and trajectory prediction. It is a robustness supplement rather than a fixed retail-CCTV benchmark.

---

## 13. MultiviewX

**Primary repository:** https://github.com/hou-yz/MultiviewX

**Associated implementation:** https://github.com/hou-yz/MVDet

**Environment:** Synthetic multi-view pedestrian scene built in Unity.

### Scale / geometry

| Item | Value |
|---|---|
| Cameras | 6 synchronized cameras |
| Image resolution | 1920×1080 |
| Annotated frames | 400 frames at 2 fps |
| Ground area | 16 m × 25 m |
| Ground grid | 640×1000 |
| Average cameras covering a location | About 4.41 |

The release includes camera calibrations, ground-plane positions and WILDTRACK-compatible multi-view evaluation structure.

### License

No explicit dataset license was visible in the official repository metadata inspected. Treat the dataset license as unknown/needs confirmation.

### What it can validate

A controlled test of calibration code, multi-view projection, world-grid occupancy and detector fusion. It is synthetic and mainly overlap-based, so it is weaker for retail appearance and non-overlap handoff.

---

## 14. MOTSynth

**Primary project page:** https://aimagelab-legacy.ing.unimore.it/imagelab/page.asp?IdPage=42

**Paper:** https://openaccess.thecvf.com/content/ICCV2021/html/Fabbri_MOTSynth_How_Can_Synthetic_Data_Help_Pedestrian_Detection_and_Tracking_ICCV_2021_paper.html

**Environment:** Synthetic GTA-V scenes designed for pedestrian detection, segmentation and tracking.

### Released dataset scale

| Item | Value |
|---|---|
| Videos | 764 full-HD videos on the current AImageLab release page |
| Frames per video | 1,800 |
| Total frames | 1,375,200 |
| Person instances | 33,397,139 on the release page |
| Extra labels | 3-D pose, instance segmentation and depth |

The ICCV paper describes 768 generated recordings and reports more than 40M boxes; the current release page lists 764 videos / 33.4M instances. Use the release-page figures for storage planning.

### License

The project describes the data as open research data and the baseline code is MIT-licensed, but the dataset itself does not present a simple permissive commercial license on the inspected page. It was generated from GTA V, so commercial redistribution/use should be checked separately.

### What it can validate

Useful for large-scale detector/tracker pretraining or stress testing without collecting real shoppers. It cannot by itself establish retail-domain accuracy.

---

## Optional auxiliary: Market-1501

**Reference page:** https://cove.thecvf.com/datasets/87

Market-1501 contains **32,668 bounding boxes of 1,501 identities from 6 cameras**, collected in front of a supermarket at Tsinghua University. It is a classic appearance-based re-identification benchmark.

It can test the visual embedding/matching component used for cross-camera identity, but it has no continuous track-level handoff or floor-plan reasoning. Use it only as an auxiliary re-ID sanity check.

---

## Recommended project benchmark stack

| Development question | Best dataset(s) | Why |
|---|---|---|
| Can we reliably detect and track each shopper in an ordinary view? | MOT17-11/12, MOT20, CAVIAR | Real people, oblique views, crowding; MOT17 includes actual busy-shopping-mall sequences. |
| Can we map a track feet point onto a floor coordinate? | CAVIAR, HDA, EPFL lab, WILDTRACK | Homography/calibration/world-ground correspondences are provided. |
| Can the analytics layer compute dwell, heatmaps and bottlenecks correctly? | ATC, Edinburgh Forum | Long trajectories with timestamps and metric/known spatial coordinates. |
| Can one person keep the same global ID after leaving one camera and appearing in another? | MTA, HDA | MTA explicitly covers overlap and non-overlap with consistent IDs; HDA adds a real indoor check. |
| Can multi-view detections be fused into one floor grid? | WILDTRACK, EPFL-RLC, MultiviewX | Calibrated cameras plus explicit shared ground-position representations. |
| Can the tracker survive heavy occlusion and crowding? | MOT20, JRDB | Dense public scenes with many partially occluded people. |
| Can training scale without collecting sensitive retail video? | MOTSynth, MultiviewX, MTA | Synthetic data with exact labels and no real-person collection. |

## Key feasibility finding

The public-data landscape supports a modular architecture:

**person detector -> per-camera tracker -> feet-point/world projection -> per-camera trajectories -> cross-camera association -> zone/dwell/flow analytics**

The best retail trajectory dataset, ATC, has no RGB CCTV video. The best real retail video dataset, CAVIAR, is small. The strongest real indoor multi-camera geometry dataset, HDA, is an office. The strongest explicit non-overlap handoff dataset, MTA, is synthetic.

Therefore feasibility should be demonstrated as a **composite benchmark**, with each subsystem evaluated against the dataset that contains the required ground truth.

## Practical first experiments

| Priority | Experiment | Dataset | Success signal |
|---:|---|---|---|
| 1 | Person detection + ByteTrack/BoT-SORT style single-camera tracking | MOT17-11 train, CAVIAR | Stable IDs through partial occlusion and low fragmentation |
| 2 | Pixel-to-floor projection using track feet points | CAVIAR or HDA | Projected paths stay on walkable ground and align between cameras |
| 3 | Zone dwell + heatmap + bottleneck analytics using perfect trajectories | ATC one-day sample | Correct dwell/flow results independent of vision errors |
| 4 | Cross-camera global identity using appearance + time/topology gating | MTA 4-minute short subset | Global ID survives a camera transition, including non-overlap gaps |
| 5 | Real indoor MTMC transfer check | HDA | Identity and homography pipeline still works outside synthetic data |
| 6 | Dense-crowd failure analysis | MOT20 indoor-station sequences | Quantified misses, ID switches and count errors under extreme crowding |

This sequence tests the critical unknowns without first downloading the largest archives. Small starting points are CAVIAR, ATC's 201 MB one-day sample, selected MOT17 sequences, and MTA's 4-minute subset if access is granted.

## Source note

Figures above were taken from official dataset pages/repositories or associated published papers wherever possible. Where an official page did not state a license or byte size, the field is deliberately marked unknown instead of inferred. No large datasets were downloaded during this research.
