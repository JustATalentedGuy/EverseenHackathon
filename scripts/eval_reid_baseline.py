from pathlib import Path
import json
import re

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision.models import resnet50, ResNet50_Weights


ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "references" / "epfl_multicam_pipeline" / "data" / "reid_eval" / "query"
GALLERY = ROOT / "references" / "epfl_multicam_pipeline" / "data" / "reid_eval" / "gallery"
OUT = ROOT / "experiments" / "reid_baseline_resnet50.json"


PATTERN = re.compile(r"gid_(\d+)_cam_(cam\d+)_frame_(\d+)\.png")


def parse(path: Path):
    m = PATTERN.fullmatch(path.name)
    if not m:
        raise ValueError(path.name)
    return int(m.group(1)), m.group(2), int(m.group(3))


def load_items(folder: Path):
    items = []
    for p in sorted(folder.glob("*.png")):
        gid, cam, frame = parse(p)
        img = cv2.imread(str(p))
        if img is None:
            continue
        items.append((p, gid, cam, frame, img.shape[:2]))
    return items


def main():
    q = load_items(QUERY)
    g = load_items(GALLERY)
    print(f"query={len(q)} gallery={len(g)}")
    print("query ids", sorted(set(x[1] for x in q)))
    print("gallery ids", sorted(set(x[1] for x in g)))

    weights = ResNet50_Weights.DEFAULT
    preprocess = weights.transforms()
    model = resnet50(weights=weights)
    model.fc = torch.nn.Identity()
    model.eval()

    def embeddings(items):
        arr = []
        bs = 16
        for i in range(0, len(items), bs):
            ims = []
            for p, *_ in items[i:i+bs]:
                ims.append(preprocess(Image.open(p).convert("RGB")))
            x = torch.stack(ims)
            with torch.inference_mode():
                f = model(x)
            f = torch.nn.functional.normalize(f, dim=1)
            arr.append(f.numpy())
        return np.concatenate(arr, axis=0)

    qf = embeddings(q)
    gf = embeddings(g)
    sim = qf @ gf.T

    ranks = []
    per_query = []
    for qi, item in enumerate(q):
        p, gid, cam, frame, shape = item
        order = np.argsort(-sim[qi])
        # Main metric: cross-camera only; same-camera matches are too easy and not useful here.
        order = [j for j in order if g[j][2] != cam]
        rank = None
        for r, j in enumerate(order, start=1):
            if g[j][1] == gid:
                rank = r
                break
        ranks.append(rank)
        top = [
            {
                "rank": r,
                "gid": g[j][1],
                "cam": g[j][2],
                "frame": g[j][3],
                "similarity": float(sim[qi, j]),
            }
            for r, j in enumerate(order[:5], start=1)
        ]
        per_query.append({
            "file": p.name,
            "gid": gid,
            "cam": cam,
            "frame": frame,
            "shape": shape,
            "cross_camera_rank": rank,
            "top5": top,
        })

    valid = [r for r in ranks if r is not None]
    n = len(ranks)
    metrics = {
        "n_queries": n,
        "n_queries_with_cross_camera_match": len(valid),
        "cmc1_all_queries": sum(r == 1 for r in ranks) / n,
        "cmc3_all_queries": sum(r is not None and r <= 3 for r in ranks) / n,
        "cmc5_all_queries": sum(r is not None and r <= 5 for r in ranks) / n,
        "cmc1_matchable_only": (sum(r == 1 for r in valid) / len(valid)) if valid else None,
        "cmc3_matchable_only": (sum(r <= 3 for r in valid) / len(valid)) if valid else None,
        "median_rank_matchable": float(np.median(valid)) if valid else None,
    }

    # Detect byte-identical crops carrying different identity labels; that makes an evaluation invalid.
    import hashlib
    hashes = {}
    collisions = []
    for p, gid, cam, frame, shape in q + g:
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h in hashes and hashes[h][0] != gid:
            collisions.append({"a": hashes[h], "b": [gid, cam, frame, p.name]})
        else:
            hashes[h] = [gid, cam, frame, p.name]

    report = {"metrics": metrics, "label_collision_count": len(collisions), "label_collisions": collisions[:20], "queries": per_query}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({"metrics": metrics, "label_collision_count": len(collisions)}, indent=2))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
