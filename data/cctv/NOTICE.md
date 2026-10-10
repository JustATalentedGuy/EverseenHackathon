# Footage licensing notice

## Store CCTV clips in `data/cctv/`

Six retail CCTV clips are included so the camera configuration `prototype/site_cctv.json`
works from a fresh clone:

| File | Size | Scene |
|---|---|---|
| `store_cctv_multi_aisle.mp4` | 2.4 MB | Convenience store, wide aisle |
| `store_cctv_mall_atrium.mp4` | 4.5 MB | Two-level mall atrium, crowded |
| `store_cctv_pharmacy.mp4` | 7.0 MB | Pharmacy counter, steep overhead angle |
| `store_cctv_convenience.mp4` | 2.0 MB | Small convenience store counter |
| `store_cctv_liquor_aisle.mp4` | 3.5 MB | Narrow liquor aisle |
| `store_cctv_produce_corner.mp4` | 2.7 MB | Produce aisle |

### Provenance status: unverified

**The source and redistribution rights for these six clips have not been established.**
They were supplied directly rather than downloaded from a documented dataset, and the
original file names (`bestone`, `clearpix`, `azmarket`, a YouTube-style identifier)
suggest they may have originated from publicly posted surveillance footage.

They are therefore treated as **research and demonstration material only**:

- Do not use them in marketing, a demo reel, a customer presentation or any commercial
  material.
- Do not redistribute them as standalone assets.
- Before any public release or commercial use, confirm that recording and consent
  requirements were met at the location and that the uploader had the right to share the
  footage, or replace them with footage you own.

Every person visible in these clips is captured on shop premises. None of it is
identifying material, and the system makes no attempt to identify anyone: it reports only
zone occupancy, observed track entries and partial visible dwell. Even so, footage of
identifiable people in a workplace carries privacy expectations, and these clips should
be handled the way you would handle any CCTV recording.

### Contrast with the other footage in this repository

`datasets/caviar` (CC BY-SA, CAVIAR project) and the MERL / CUHK Mall samples referenced in
`prototype/DEMO_FOOTAGE.md` come from documented research datasets with explicit terms,
which is why those are fetched by `scripts/prepare_retail_demo.py` rather than committed.

If this repository is going to be published, replacing `data/cctv/` with consented or
publicly licensed footage is the right thing to do.