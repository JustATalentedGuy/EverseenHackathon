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

## The shopkeeper workflow

1. **Overview** (`/`) — choose a camera, click **Start monitoring**, inspect live annotated video, activity heatmap, zone dwell and evidence-based insights. Use **Manage camera zones** when you need to adjust an area.
2. **Floor plan** (`/layout`) — move and resize store sections on a grid, connect them to camera zones, and inspect the rotatable 3D view. Section observations and cautious layout suggestions update when sources are fresh.
3. **Ask Everseen** — open the assistant in the bottom-right corner. Ask about measured people, activity, dwell or areas needing review. The assistant composes numbers from recorded analytics, not guesses from a language model. Text works without an LLM or microphone.
4. **Manager briefings** — prepare a short update for your WhatsApp recipients. Everseen opens a **pre-filled** click-to-chat link; the user must press Send. It does **not** send messages automatically.
5. **Camera library** — add a direct video URL, local video file or webcam, or import an audited research sample. **Advanced setup** (`/setup`) provides optional calibration and recorded replay tools.

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

See [Implementation & evidence](docs/TECHNICAL.md) for architecture, formulas, experimental model choice, integration tests and research limitations, and [Operations & sources](docs/OPERATIONS.md) for the store workflow, alternative camera datasets and assistant options. The original research history and numeric evaluations remain in `research/` and `experiments/` as an auditable appendix.

## Footage and rights

The optional six CCTV clips supplied in the teammate branch had **unverified redistribution rights**. They are deliberately **excluded from the final `main` tree**, though they may remain in a local installation. Use your own consented store video or the officially attributed CAVIAR research examples for demonstrations. The CAVIAR dataset retains its Creative Commons terms; consult [Data and provenance](docs/OPERATIONS.md). Clips appearing in older Git history or other branches may need separate removal before publishing a repository archive.

© Everseen hackathon team — research prototype. No claim of independently validated deployment accuracy.
