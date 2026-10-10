# Curated demonstration videos (October 8, 2026)

**Location:** `C:\Coding\ML\Everseen`
**Open:** http://127.0.0.1:8791/ → **Curated demonstration footage** (right column).

The gallery automatically marks local files as **validated** only after a frame-decoding + sampled YOLO person-detection audit. Click **Add demo camera**, then **Show original frame** (usually automatic), draw a floor region, and **Start monitoring**. Adding to the active camera list does not change your two default CAVIAR cameras or claim that different clips represent synchronized views. Imported demo cameras start with **no zones**, because arbitrary frame-wide polygons would generate misleading occupancy/dwell numbers.

## Sources and best demo uses

| Demo clip | What the judges can see | Original source and reuse condition | Local file |
|---|---|---|---|
| Walk-by storefront — corridor | Shop approach, crossing trajectories and entrance-area observations | [CAVIAR shopping-centre set](https://groups.inf.ed.ac.uk/vision/DATASETS/CAVIAR/CAVIARDATA1/), **CC BY-SA**; cite EC Funded CAVIAR project/IST 2001 37540 | `datasets/caviar/WalkByShop1cor.mpg` |
| Shop assistant — front view | Stopping and interacting near a shop; explain visible dwell and *not* conversion | CAVIAR, **CC BY-SA** | `datasets/caviar/ShopAssistant1front.mpg` |
| Two couples enter — front view | Entry traffic, occlusion and changing camera-local track observations | CAVIAR, **CC BY-SA** | `datasets/caviar/TwoEnterShop3front.mpg` |
| Busy shopping corridor | Group movement and occupancy fluctuations | CAVIAR (already downloaded previously) | `datasets/caviar/OneShopOneWait2cor.mpg` |
| Paired-view store entry | Entrance traffic with different viewing angle | CAVIAR (already downloaded previously) | `datasets/caviar/TwoEnterShop1front.mpg` |
| Mall crowd (420 sampled images) | A crowded mall webcam: demonstrate **undercount risk**, not validated dwell | [CUHK Mall Dataset](https://staff.ie.cuhk.edu.hk/~ccloy/downloads_mall_dataset.html), **research only, not commercial use** | `samples/retail_demo/mall_crowd.mp4` |
| MERL overhead shelf browsing | Fixed top-down video, prolonged browsing, person-detection challenge | [MERL Shopping Dataset](https://www.merl.com/research/downloads/MERL_Shopping_Dataset), **noncommercial research only** | `samples/retail_demo/merl_shelf_browse.mp4` |
| Teammate store clip | Multi-person store video, more modern resolution | [EverseenML teammate repository](https://github.com/myselfGokul-1111/EverseenML), **permission to redistribute/use publicly must be confirmed** | `.cache/teammate-EverseenML/store.mp4` |

| **Store CCTV multi-aisle** | Ordinary aisle traffic and occupancy change | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_multi_aisle.mp4` |
| **Store CCTV mall atrium** | Crowded two-level mall; undercount and false-positive stress test | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_mall_atrium.mp4` |
| **Store CCTV pharmacy** | Counter-area dwell; explicitly not a checkout-wait measurement | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_pharmacy.mp4` |
| **Store CCTV convenience** | Sparse-traffic control case | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_convenience.mp4` |
| **Store CCTV liquor aisle** | Narrow-aisle zone placement and track fragmentation | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_liquor_aisle.mp4` |
| **Store CCTV produce corner** | Second sparse case, contrast against the mall clip | User-supplied clip, **provenance/redistribution rights unverified** | `data/cctv/store_cctv_produce_corner.mp4` |

**Store CCTV clips:** all six are `research_only` and carry an unverified provenance note. The gallery asks for confirmation before adding them, and they must not be redistributed as repository assets or used in commercial material until the source is established.

**Licensing:** CAVIAR's official page lists CC BY-SA and requests acknowledgment; verify the applicable share-alike/attribution requirements for external demo materials. Mall and MERL are research-only and must **not** be placed into a commercial marketing video or redistributed as repository assets without permission. All footage is excluded from Git. Research/demo permission is distinct from a commercial product license. For public product marketing, use your own consented footage or a commercial-friendly stock clip with proper rights. Pexels has [free-use terms](https://www.pexels.com/license/), but its catalog landing-page URLs are **not direct video streams**; they were not downloaded/validated here, so none have been falsely added as playable cameras.

## Reproduce downloads and audit

On a fresh machine after setting up dependencies, run:

```powershell
cd C:\Coding\ML\Everseen
.\.venv\Scripts\python.exe scripts\prepare_retail_demo.py
.\.venv\Scripts\python.exe scripts\test_retail_demo.py
.\.venv\Scripts\python.exe -m prototype.server
```

The preparation script downloads three **new** official CAVIAR clips, one MERL MP4 (from a single subject's Hugging Face dataset mirror), and the CUHK Mall ZIP (about 92 MB). It extracts a local **420-frame illustrative sequence** from the Mall data at a nominal 2 FPS; its camera's true sampling cadence was *less than 2 FPS*, so the derived clip is **not suitable for real-time dwell, queue or speed evaluation**. The Mall original labels head points, not full-body bounding boxes. The teammate video must be cloned separately if unavailable (`git clone` to ignored `.cache/teammate-EverseenML`).

`scripts/test_retail_demo.py` checks sequential MPEG decode when frame-count metadata is unreliable, validates 8–12 actual frames per candidate through the selected YOLO11n ONNX CPU export, and records sample detection counts, duration, resolution, local file size and SHA-256 in ignored `runs/retail_demo_validation.json`. Sampled person detections are only evidence that the model produces observations, not F1, precision, recall or accurate customer counts. Gallery activation checks the same file hash again before adding the camera; missing/changed/unvalidated clips cannot be activated. Changes to the default detector require retesting with the new model.

**Do not put model-generated observations on a slide labelled ground truth.** The team research's CAVIAR held-out evaluation applies to its specific experiment and scenario split, not these newly chosen individual clips, the MERL action labels, or the Mall head-count annotations.

## Presenting the demo logically

Start with **CAVIAR WalkByShop** for a clean fixed-camera corridor where movement is easy to explain. Draw a store-approach polygon. Next, select **the teammate store video** for a more realistic retail presentation, draw one or two non-overlapping floor regions and explain the partial dwell, foot-position heatmap and measurement health. Use **CAVIAR ShopAssistant** to show why standing still is not automatically a congestion event. Use **MERL** as an example of a difficult overhead angle and the **Mall** sequence to show possible under-detection in busy scenes. State the limitations directly instead of promising purchase conversion or certified waiting times.

No external video page is guaranteed to be OpenCV-playable. Everseen's manual URL input accepts *direct RTSP/HTTP video streams*, not YouTube/Pexels page addresses. Videos downloaded from sources are saved locally for a reproducible, offline-capable hackathon demonstration.
