# Everseen: implementation & experimental evidence

## Architecture

`prototype/server.py` exposes the local FastAPI endpoints. `prototype/live.py` reads camera/video frames, runs the selected Ultralytics person detector and ByteTrack, and calculates per-zone metrics using `prototype/core.py`. `prototype/heatmap.py` computes a time-weighted occupancy map. `prototype/topology.py` validates a 12×8 operator-defined schematic, assembles camera-zone evidence and derives cautious topology recommendations. Assistant behavior is separated into `assistant.py` (deterministic routing and guardrails), `assistant_docs.py` (BM25 retrieval), `assistant_context.py`, `assistant_ingest.py`, `assistant_llm.py`, `assistant_stt.py` and `briefing.py` (manual WhatsApp hand-off).

The frontend is deliberately dependency-light: `prototype/dashboard.html` and `prototype/layout.html` load reusable scripts and styles from `prototype/assets/`. The 3D floor uses native CSS perspective and illustrated person glyphs, so no proprietary WebGL library or cloud service is required. `prototype/index.html` remains the optional advanced replay/calibration screen.

## Data and measurement definitions

1. **Detection:** YOLO identifies person bounding boxes; a box's bottom center approximates the foot position. ByteTrack associates detections with temporary camera-local track IDs, which may fragment or collide after camera interruptions.
2. **Zone occupancy:** number of active observed person tracks whose foot points lie in a validated polygon. Unsupported frames and boundary ambiguities are excluded.
3. **Visible dwell:** accumulate `Δt` only for consecutive valid observations of the same camera-local ID in the same zone, within the allowed time gap. Missing observations are *censored*, not filled in. This cannot report completed visitor dwell.
4. **Heatmap:** for a valid consecutive track pair with `0<Δt≤1.5s`, add `Δt` seconds to the 16×9 image tile at the midpoint of the observed feet. For a selected 30, 120 or 300-second window, `person_seconds(tile)=Σ Δt`; `average_visible_people(tile)=person_seconds(tile)/elapsed_window_seconds`. Fixed heat colors allow comparisons without per-frame max-normalization. Report supported frame-interval coverage to disclose likely under-observation. Grid tiles are equal in the **image**, not equal physical floor area.
5. **Zone trend:** rolling 5-minute sampled occupancy mean and P90; values depend on available processed frames. Very slow processing decreases representative coverage.
6. **Cross-camera floor section:** for each operator-mapped section, take the **maximum fresh mapped camera-zone occupancy** (not the sum) and report supporting source(s). The displayed “overall observed section sum” is not a deduplicated number of people. Physical identities and floor overlap are not verified.
7. **Topology:** schematic rectangles are adjacent only when they share a positive-length edge. Breadth-first traversal from assigned bottom/entrance sections towards top/exit sections produces candidate internal paths. The graph does **not** validate walls or actual visitor journeys.
8. **Recommendations:** a sustained camera review cue (configured crowd threshold maintained across at least four contiguous samples for at least five seconds) is necessary before recommending attention. A redistribution candidate additionally requires a separate fresh low-activity, sufficiently sampled, graph-connected section; the recommendation is an inspection/trial, never a proven business benefit. Unmonitored sections are marked unknown.

## Research model selection

The project evaluated a YOLO11n pretrained baseline, reviewed-label adaptation and pseudo-label adaptation on a CAVIAR-derived split. The detector F1 used `precision=TP/(TP+FP)`, `recall=TP/(TP+FN)` and `F1=2·precision·recall/(precision+recall)` under the experiment's box matching rules. The recorded selection was driven by **validation**, not by the highest held-out test score:

| Candidate | Validation F1 | Held-out test F1 |
|---|---:|---:|
| Pretrained YOLO11n baseline | 0.7365 | 0.786 |
| Reviewed supervised adaptation | 0.7340 | 0.823 |
| Uncorrected pseudo-label adaptation | 0.5818 | 0.747 |

The pretrained model narrowly won validation, so it remains the default. See `experiments/deadline/selection.json`, `experiments/deadline/comparison.json` and `research/EVERSEEN_FINAL_PROJECT_DOCUMENTATION.md` for raw evidence and experimental decisions. The optional CPU ONNX export is an inference optimization of the selected weights; a small parity sample is **not** a new accuracy evaluation. CAVIAR numbers do not certify accuracy on unrelated CCTV angles, the optional six local videos, or a new store.

## Reproducibility and integration checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe scripts\smoke_unified.py --seconds 10
.\.venv\Scripts\python.exe scripts\check_layout_v2.py
```

The last script requires the local server and Chrome/Playwright. Unit tests cover source validation, polygon and identity handling, time-censored heatmap calculations, topology mapping, camera overlap rules, assistant refusals, and WhatsApp link behavior. Real browser acceptance should also verify video decoding, the live floor map and assistant+briefing UI—not just HTTP 200.

## Limitations that matter for deployment

Physical deployment requires permissioned cameras, privacy policy and retention controls, per-site validation under crowds and occlusion, measured time synchronization/calibration for true physical density, and a more scalable inference backend than the current four-live-camera CPU prototype. There is no verified unique store footfall, causal bottleneck classifier, purchase conversion model or 3D human localization.
