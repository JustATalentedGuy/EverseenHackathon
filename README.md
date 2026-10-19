# Everseen — Retail Spatial Intelligence

**Camera analytics, a live floor plan and an evidence-backed store assistant, in one local application.**

Everseen helps store managers see where activity is happening, how long visitors are visibly present, and which areas deserve attention. Configure cameras and floor zones, view a rotatable occupancy-aware store layout, and ask operational questions in plain English. All analysis runs locally by default; no customer identification or cloud processing is required.

## Get started

**Python 3.12** and an internet connection are needed for the *first* model/dataset download. The web app runs on Windows, macOS or Linux; the commands below show Windows PowerShell.

```powershell
git clone https://github.com/JustATalentedGuy/EverseenHackathon.git
cd EverseenHackathon
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\setup_demo.py --data
.\.venv\Scripts\python.exe -m prototype.server
```

Open **http://127.0.0.1:8791**. The first run seeds a two-camera CAVIAR demo and its matching example floor plan. The evaluated detector weights and CAVIAR research footage are downloaded separately; third-party data and model weights are not committed. The project includes the original source URLs and research attribution.

## Start using your store

The easiest way to set up Everseen is to **build your floor plan first, then connect your cameras to it**:

1. **Draw the store:** Open **[Floor plan](http://127.0.0.1:8791/layout)**. Click **+ Add section**, drag and resize each box, give it a name (such as *Entrance*, *Aisle*, or *Checkout*), and click **Save changes**.
2. **Set up cameras:** On **[Overview](http://127.0.0.1:8791)**, open **Camera library** to add a camera or video. Return to **Live dashboard**, select a camera, click **Preview**, and expand **Manage camera zones** to draw the areas visible in that camera.
3. **Connect cameras to the floor plan:** Go back to **Floor plan**. Select each section and tick the camera zone that covers it under **Camera zones covering this section**. Click **Save changes** again.
4. **Start monitoring:** Return to Overview, select a camera and click **Start monitoring**. Check **Area performance**, the **Activity heatmap**, and **Insights**. The floor plan shows mapped counts and a rotatable 3D view as fresh camera observations arrive.
5. **Decide what to check:** Review repeated busy areas, compare quieter sections, and confirm the situation in the video before moving a display or changing staff assignments. Use **Ask Everseen** for questions or prepare a **WhatsApp briefing** that you send yourself.

**New to the app? Read the [Shopkeeper's step-by-step guide](docs/SHOPKEEPER_README.md).** It includes floor-plan examples, camera-zone mapping, explanations of every metric, daily checklists, and common fixes.

Changes to cameras, recipients and floor layouts are stored in **Git-ignored, machine-local files**, preserving the documented sample configurations for every clone.

## Features at a glance

| Feature | Implementation |
|---|---|
| Person tracking | YOLO11n + ByteTrack; camera-scoped identities |
| Occupancy and dwell | Person-box foot point in user-defined zones; **partial visible dwell**, not whole visits |
| Heatmap | Observed person-time per image tile with fixed colors and coverage estimate |
| Multi-camera sections | Explicit zone mapping; highest fresh overlapping camera count, **not** a duplicate-free store total |
| Topology | Internal adjacency and entrance-to-back routes from the editable schematic grid |
| Store recommendations | Human-review prompts, requiring sustained crowding and measured low activity elsewhere |
| Store assistant | Evidence-gated deterministic answers, optional local/cloud *phrasing* and voice |
| Briefings | Scheduled preparation and manual WhatsApp hand-off |
| Live sources | Camera/video/RTSP/HTTP(S); CPU prototype supports four concurrent inference streams |

### Important boundaries

This is a hackathon prototype, **not** validated retail decision-making software. It does not infer purchases, identify shoppers, measure verified unique store footfall, or establish true checkout wait times. Overlapping camera views are not automatically deduplicated. The drawn layout is a schematic until calibrated to a physical floor. “Crowding” and “low-use” recommendations are hypotheses to inspect, not proven causes or profitable department swaps.

## Testing and implementation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-research.txt
.\.venv\Scripts\python.exe -m pytest -q tests
```

See the [Shopkeeper's guide](docs/SHOPKEEPER_README.md) for everyday use, [Implementation & evidence](docs/TECHNICAL.md) for architecture, formulas and evaluation, and [Operations & sources](docs/OPERATIONS.md) for advanced configuration and dataset information. The original research history and numeric evaluations remain in `research/` and `experiments/` as an auditable appendix.

© Everseen hackathon team — research prototype. No claim of independently validated deployment accuracy.
