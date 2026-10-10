# Everseen observed-presence heatmap: meaning and computation

## Before: relative frame-hit heat

The older implementation stored a 320 × 180 array and incremented one cell per nontruncated tracked person's bottom-center detection **every processed frame**. Each processed frame multiplied the whole array by `0.996`; display then blurred and normalized the current hottest spot to 255 and overlaid a JET color map. That visual could not say how many seconds or people a color represented. Its history depended on CPU frame rate, and an automatic change of normalization made color comparisons across moments/cameras unreliable.

## Now: observed person-time, with interpretable units

**Input:** YOLO person boxes → ByteTrack camera-local IDs → normalized bottom-center of each nontruncated detected person box. A **16 × 9 image grid** covers the currently selected camera frame. Store no biometric identity and make no claim of a globally unique shopper.

For each consecutive processed frame pair at times `t_previous` and `t_current`:

1. Only match identical **camera-local track IDs** appearing in *both* frames with valid foot estimates. A missing/changed ID is a censored interval, **not** an interpolated visit.
2. Require `0 < Δt ≤ 1.5 seconds`; longer camera or inference gaps are not credited.
3. Assign `Δt` to the image tile containing the midpoint of the person's two observed foot positions. If the same operator-defined zone remains confirmed in both frames, assign `Δt` to that zone too.
4. Keep timestamped track-pair intervals for the most recent **5 minutes** and prorate any interval crossing the chosen window start.
5. For a chosen display window `W = 30, 120, or 300 seconds`, define the actual elapsed window `T = min(W, last_observed_time − first_observed_time)` and calculate:

   - **Observed person-seconds per tile:** `P(tile) = sum(overlapping valid consecutive-track durations in tile)`.
   - **Average observed people in tile:** `A(tile) = P(tile) / T` for `T > 0`.
   - **Camera-wide observed person-seconds:** `sum_over_tiles P(tile)`. This is *not* unique visitors or purchases.
   - **Frame-interval coverage:** `supported_elapsed_seconds / T`, counting only adjacent decoded/processed frames at most 1.5s apart. Low coverage signals likely **underestimation**.
   - **Named zone observed time:** valid continuous track durations assigned consistently to a user-configured zone. This is **not** normalized for zone size.

Example: one continuously observed tracked person in one tile for 10 seconds of a 20-second observation period produces `10 person-seconds` and `0.5 average observed people` in that tile. Two simultaneously visible tracks can contribute a value above 1.

## How to read the dashboard

The color mapping is now **fixed across frames and selected windows**, instead of automatically rescaling to that frame's hottest cell:

| Color | Observed average people per image tile |
|---|---:|
| Uncolored | Below 0.015 (no substantial confirmed contiguous exposure) |
| Blue | 0.015 to less than 0.25 |
| Green | 0.25 to less than 0.5 |
| Amber | 0.5 to less than 1 |
| Red | 1 or more (colors saturate, but numeric summary retains the actual maximum) |

The visualization shows only nonempty squares, overlays them on the **same frame that produced the measurements**, and annotates up to four prominent tiles with their average value. Beneath it, Everseen reports actual observed person-seconds, the percentage of elapsed time with acceptable consecutive frame coverage, the hottest tile's numerical value, and up to three named-zone totals when available. Switch between 30s, 2min and 5min views without restarting the camera.

## What this *does not* measure

- The 16 × 9 cells are equally sized **in the video image**, not equal-sized real-world floor areas; perspective means `1 person / image tile` is **not** a defensible physical density or queue estimate. A future version could use verified camera-to-floor homography and physical area before producing people/m².
- Occlusion, missed YOLO detections, tracker fragmentation, truncated feet, unsupported time gaps and delayed inference **understate** true presence. The frame-interval coverage metric helps expose incomplete time sampling, but high coverage alone does not guarantee detector or tracker accuracy.
- A stopped shopper and a waiting shopper both contribute time. Location alone does **not** distinguish browsing, queuing, or purchasing.
- The current metric is observation-based **presence/exposure**, not total entries, unique visitors, full visit time, ROI, cross-camera identity or causal business recommendations.
- Historical mode freezes the last analyzed frame's window when the recorded clip finishes; it does not pretend a stopped file is a live camera.

## Next scientific improvements if validated on the target store

1. **Calibrate floor geometry:** survey real floor anchors, validate held-out homography landmarks, and then report time-weighted average persons/m² rather than equal-image-tile presence.
2. **Separate movement from lingering:** compare motion speed, stable zone presence and paths; annotate real browsing and queue examples to evaluate those categories, rather than guessing intent from a hotspot.
3. **Evaluate detection/track recall under occlusions:** hand-label representative store footage, score false negatives and track continuity for the chosen camera angles, and measure bias in cumulative person-time.
4. **Show historical baselines:** collect sufficiently long observation windows and compare like-for-like time slots with disclosed coverage, avoiding conclusions from small startup windows or busy unsynced cameras.

## Validation

Run `python -m unittest tests.test_heatmap` for numeric tests of invariance to sampling cadence, gap/identity censoring, two concurrent tracks, window prorating, stable-zone attribution, and JPEG rendering. `scripts/smoke_unified.py` exercises the local real detector/heat image/summary endpoints. `scripts/check_heatmap_dashboard.py` tests the browser time controls and captures screenshots **without modifying** `prototype/site.json` (needs the local server on 8893).
