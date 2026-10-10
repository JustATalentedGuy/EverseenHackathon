# CCTV replay set — six real retail cameras

`prototype/site_cctv.json` wires the six supplied CCTV clips into the same pipeline the
CAVIAR demo uses. Nothing about the detector, tracker, analytics or zone logic changes:
this is a different set of cameras, and the same code reads them.

```bash
# batch replay, all six cameras, 60 s each
python3 -m prototype.run --config prototype/site_cctv.json \
    --output experiments/deadline/cctv --seconds 60

# serve the dashboard against this camera set
EVERSEEN_CONFIG=prototype/site_cctv.json python3 -m prototype.server
```

`EVERSEEN_CONFIG` only changes which site file is loaded; it exists so the original
`site.json` and this set can coexist.

All six are also listed in the dashboard's **curated footage gallery**
(`demo_catalog.json`), so a clip can be previewed and added as a camera straight from the
UI. They were audited by `scripts/test_retail_demo.py`, which decodes samples and counts
*sampled predictions only* — never accuracy.

## Cameras and zones

Zones were drawn on visible walkable floor and checked against a frame from each clip
(`python3 tools/check_zones.py` redraws the overlays for review). They are *observation
regions*, not calibrated ground areas.

| Camera | Clip | Length | Zones |
|---|---|---|---|
| `multi_aisle` | store_cctv_multi_aisle.mp4 | 60 s | Main aisle, Store entrance |
| `mall_atrium` | store_cctv_mall_atrium.mp4 | 60 s | Upper walkway, Atrium floor |
| `pharmacy` | store_cctv_pharmacy.mp4 | 110 s | Pharmacy counter, Counter service area |
| `convenience` | store_cctv_convenience.mp4 | 58 s | Counter front, Front door |
| `liquor_aisle` | store_cctv_liquor_aisle.mp4 | 67 s | Left and right walkways |
| `produce_corner` | store_cctv_produce_corner.mp4 | 118 s | Produce aisle |

## Measured results (60 s per camera, yolo11n, 5 Hz, conf 0.30)

| Camera | Zone | Peak | Mean | Observed track entries | Mean partial dwell |
|---|---|---|---|---|---|
| mall_atrium | Atrium floor | 16 | 7.0 | 76 | 5.3 s |
| mall_atrium | Upper walkway | 7 | 3.1 | 50 | 3.2 s |
| multi_aisle | Main aisle | 5 | 3.0 | 16 | 11.0 s |
| pharmacy | Counter service area | 5 | 3.0 | 25 | 6.8 s |
| pharmacy | Pharmacy counter | 4 | 1.7 | 12 | 5.4 s |
| convenience | Front door | 2 | 1.0 | 2 | 1.6 s |
| convenience | Counter front | 1 | 1.0 | 1 | 9.0 s |
| produce_corner | Produce aisle | 2 | 1.3 | 6 | 5.0 s |
| liquor_aisle | Right walkway | 1 | 1.0 | 2 | 1.6 s |
| liquor_aisle | Left walkway | 1 | 1.0 | 1 | 0.2 s |

1928 frames in 390 s wall clock on 4 CPU threads, no GPU.

The spread matches what is visible in the footage: the mall atrium is genuinely crowded,
while the convenience, liquor and produce clips are quiet single-shopper scenes. That
contrast is the useful part of the set — the analytics behave sensibly across both a
stress case and a sparse one.

## Honest limitations on this footage

These clips are much harder than the CAVIAR sequences, and the numbers above should be
read with that in mind.

- **Resolution.** All six are 360p–480p, versus the CAVIAR clips. People are small in
  frame, so occupancy under-counts whenever two people overlap.
- **False positives.** On visual review of the overlays, boxes land occasionally on
  shelving, benches and displays (most visibly in `mall_atrium` and `pharmacy`). A
  threshold at the 5 Hz target does not remove this; it is a model-capacity limit.
- **Track fragmentation.** `observed_track_entries` counts track *IDs*, so a person who
  walks behind a fixture and re-emerges can be counted twice. Treat it as an activity
  proxy, never as a person count.
- **Partial dwell only.** Every dwell figure is summed across observed intervals between
  reliable sightings, so a subject occluded by a shelf contributes only what was visible.
- **No ground truth.** Nothing here is validated against annotated counts, so accuracy
  is unquantified — the README's CAVIAR metrics do not transfer to these clips.
- **Single camera per scene.** All six are independent cameras. Nothing is synchronized,
  and no cross-camera totals are computed.
- **Short clips.** 58–118 s each. Peaks over a longer day would look different.

For a fair benchmark use `datasets/caviar`; use these clips for demos, robustness checks
and stress-testing the UI under realistic store imagery.

## Calibration status — read before quoting any distance

`~/Everseen/calib_*.json` holds six floor calibrations for these clips. Their geometry was
recovered, checked against the actual frames and written to `prototype/calibration_cctv.json`
by `tools/build_cctv_calibration.py`.

**They are deliberately not enabled as metric calibration**, for three reasons that are all
verifiable in the source files:

1. **There is no scale.** The "world" coordinates are a 420×340 plan canvas, identical for
   all six cameras. It is a rectification (image floor → top-down plan), not metres. Treat
   every stored coordinate as arbitrary plan units.
2. **Only four anchors exist per camera.** `core.fit_calibration` requires at least six
   correspondences — four to fit, plus independent ones — and refuses anything smaller.
3. **The stored `reproj_err: 0.00` is not accuracy evidence.** Four points determine a
   homography exactly (8 unknowns, 8 equations), so the residual is forced to zero on every
   clip regardless of whether the anchors are good.

This matters because `run.py` switches track speed from body-heights/s to **m/s** the moment
a calibration is present, and that value feeds the slow-motion bottleneck heuristic. A
guessed scale would therefore turn into confident, wrong "bottleneck" claims — the one thing
this project most needs to avoid.

To finish it honestly, two things are needed per camera:

- a real-world length in frame (an aisle width or a floor tile), which sets the scale; and
- two floor points whose plan position is known independently of the four anchors, so the
  metre-denominated check gate in `fit_calibration` has something real to test.

Until then the zones stay in image space, occupancy and dwell are unaffected, and no area or
speed claim is made.