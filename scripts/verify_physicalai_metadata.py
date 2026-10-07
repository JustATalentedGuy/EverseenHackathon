from pathlib import Path
import json
import math

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "samples" / "physicalai" / "Warehouse_000"
CALIB = SCENE / "calibration.json"
MAP = SCENE / "map.png"
OUT = ROOT / "experiments" / "physicalai_metadata_check.json"


def attr_dict(sensor):
    return {x.get("name"): x.get("value") for x in sensor.get("attributes", [])}


def main():
    data = json.loads(CALIB.read_text())
    sensors = [s for s in data.get("sensors", []) if s.get("type") == "camera"]
    map_img = cv2.imread(str(MAP))
    report = {
        "scene": "PhysicalAI Smart Spaces MTMC_Tracking_2026/train/Warehouse_000 metadata sample",
        "camera_count": len(sensors),
        "map_shape_hw": list(map_img.shape[:2]) if map_img is not None else None,
        "camera_ids": [],
        "all_have_intrinsic": True,
        "all_have_extrinsic": True,
        "all_have_camera_matrix": True,
        "all_have_homography": True,
        "all_have_xy_coordinates": True,
        "all_have_fps_and_frame_size": True,
        "homography_checks": {},
    }

    sample_pixels = np.asarray([[[960.0, 900.0]], [[960.0, 540.0]], [[300.0, 900.0]], [[1600.0, 900.0]]], dtype=np.float32)
    for s in sensors:
        cid = s.get("id")
        report["camera_ids"].append(cid)
        report["all_have_intrinsic"] &= bool(s.get("intrinsicMatrix"))
        report["all_have_extrinsic"] &= bool(s.get("extrinsicMatrix"))
        report["all_have_camera_matrix"] &= bool(s.get("cameraMatrix"))
        report["all_have_homography"] &= bool(s.get("homography"))
        report["all_have_xy_coordinates"] &= all(k in s.get("coordinates", {}) for k in ("x", "y"))
        attrs = attr_dict(s)
        report["all_have_fps_and_frame_size"] &= all(k in attrs for k in ("fps", "frameWidth", "frameHeight"))

        H = np.asarray(s.get("homography"), dtype=np.float64)
        if H.shape != (3, 3):
            report["homography_checks"][cid] = {"valid_matrix": False}
            continue
        det = float(np.linalg.det(H))
        cond = float(np.linalg.cond(H))
        try:
            Hinv = np.linalg.inv(H)
            ground = cv2.perspectiveTransform(sample_pixels, H.astype(np.float32))
            back = cv2.perspectiveTransform(ground, Hinv.astype(np.float32))
            err = np.linalg.norm(back.reshape(-1, 2) - sample_pixels.reshape(-1, 2), axis=1)
            finite = bool(np.isfinite(ground).all())
            max_err = float(err.max())
        except np.linalg.LinAlgError:
            finite = False
            max_err = math.inf
        report["homography_checks"][cid] = {
            "valid_matrix": True,
            "determinant": det,
            "condition_number": cond,
            "finite_sample_projection": finite,
            "max_pixel_roundtrip_error": max_err,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    summary = {k: v for k, v in report.items() if k != "homography_checks"}
    summary["max_roundtrip_error_over_cameras"] = max(
        (x.get("max_pixel_roundtrip_error", 0.0) for x in report["homography_checks"].values() if x.get("valid_matrix")),
        default=None,
    )
    print(json.dumps(summary, indent=2))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
