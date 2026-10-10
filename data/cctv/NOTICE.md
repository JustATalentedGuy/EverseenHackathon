# Footage licensing notice

## Store CCTV clips in `data/cctv/`

Six retail CCTV clips may be present locally from the teammate's experimental branch.
They are **not included in the final public `main` tree** because permission to
redistribute them has not been established. The optional `prototype/site_cctv.json`
configuration works only when an operator has placed authorized clips at those paths:

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

These clips capture people on shop premises; some faces may be identifiable.
The system does not attempt to identify anyone: it reports only zone occupancy,
track entries and partial visible dwell. Treat the files as sensitive workplace CCTV.

### Contrast with the other footage in this repository

`datasets/caviar` (CC BY-SA, CAVIAR project) and the MERL / CUHK Mall samples referenced in
`prototype/demo_catalog.json` come from documented research datasets with explicit terms,
which is why those are fetched by `scripts/prepare_retail_demo.py` rather than committed.

The final submission leaves these files untracked and Git-ignored. Previous commits or
other branches may still reference footage until repository history is separately
rewritten or those branches are removed; removing them from `main` does not purge
historic objects. Use the CAVIAR setup for publicly reproducible testing.
