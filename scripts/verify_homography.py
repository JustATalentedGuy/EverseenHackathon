from pathlib import Path
import json
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parents[1]
CALIB = ROOT / "references" / "epfl_multicam_pipeline" / "data" / "floor_plan" / "calibration-4p.txt"
OUT = ROOT / "experiments" / "epfl_homography_check.json"


def parse(path: Path):
    lines = path.read_text().splitlines()
    out = {}
    current = None
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("# Camera"):
            current = f"cam{s.split()[-1]}"
        elif s == "# Ground plane homography" and current:
            rows = [[float(v) for v in lines[i+j].split()] for j in (1,2,3)]
            out[current] = np.asarray(rows, dtype=np.float64)
            i += 3
        i += 1
    return out


def main():
    hs = parse(CALIB)
    report = {}
    # We cannot claim metric accuracy without ground-truth point correspondences here.
    # We can verify invertibility/numerical conditioning and demonstrate deterministic mapping.
    test_pixels = np.array([[[0.0,0.0]], [[360.0,288.0]], [[719.0,575.0]]], dtype=np.float32)
    for cam, H in hs.items():
        det = float(np.linalg.det(H))
        cond = float(np.linalg.cond(H))
        mapped = cv2.perspectiveTransform(test_pixels, H.astype(np.float32)).reshape(-1,2).tolist()
        inv = np.linalg.inv(H)
        round_trip = cv2.perspectiveTransform(
            cv2.perspectiveTransform(test_pixels, H.astype(np.float32)), inv.astype(np.float32)
        )
        err = np.linalg.norm(round_trip.reshape(-1,2) - test_pixels.reshape(-1,2), axis=1)
        report[cam] = {
            "determinant": det,
            "condition_number": cond,
            "sample_pixel_to_ground": mapped,
            "round_trip_pixel_error": err.tolist(),
            "max_round_trip_error": float(err.max()),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
