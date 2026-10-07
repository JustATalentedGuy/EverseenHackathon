"""Acquire a tiny WILDTRACK metadata/annotation subset with HTTP byte ranges.

The official EPFL archive is ~6.8 GB. Architecture 2 does not need the images
for GT-derived geometry experiments, so this script fetches only:

* 7 undistorted-image intrinsic calibration XML files
* 7 extrinsic calibration XML files
* the first N position-annotation JSON files

It reads the ZIP central directory with range requests and extracts only the
selected members. This keeps the download in the low-MB range and avoids a
full dataset download.
"""

from __future__ import annotations

import argparse
import binascii
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "samples" / "wildtrack_subset"
URL = (
    "https://documents.epfl.ch/groups/c/cv/cvlab-unit/www/data/Wildtrack/"
    "Wildtrack_dataset_full.zip"
)
CAMERAS = ["CVLab1", "CVLab2", "CVLab3", "CVLab4", "IDIAP1", "IDIAP2", "IDIAP3"]


@dataclass
class ZipEntry:
    name: str
    compression: int
    crc32: int
    compressed_size: int
    uncompressed_size: int
    local_offset32: int


def get_range(session: requests.Session, start: int, end: int) -> bytes:
    response = session.get(
        URL,
        headers={"Range": f"bytes={start}-{end}"},
        timeout=60,
    )
    response.raise_for_status()
    expected = end - start + 1
    if len(response.content) != expected:
        raise RuntimeError(
            f"range {start}-{end}: expected {expected} bytes, got {len(response.content)}"
        )
    return response.content


def read_central_directory(session: requests.Session) -> tuple[int, dict[str, ZipEntry]]:
    head = session.head(URL, timeout=30)
    head.raise_for_status()
    archive_size = int(head.headers["Content-Length"])

    tail_size = min(65536, archive_size)
    tail = get_range(session, archive_size - tail_size, archive_size - 1)
    eocd_idx = tail.rfind(b"PK\x05\x06")
    if eocd_idx < 0:
        raise RuntimeError("ZIP EOCD not found")
    eocd = tail[eocd_idx : eocd_idx + 22]
    (
        _sig,
        _disk,
        _cd_disk,
        _entries_disk,
        n_entries,
        cd_size,
        _wrapped_cd_offset,
        comment_len,
    ) = struct.unpack("<4s4H2LH", eocd)

    # The EPFL ZIP is >4 GiB but was written without ZIP64, so the 32-bit
    # central-directory offset wraps. Its true location is unambiguous from
    # the EOCD itself: immediately before the EOCD + optional comment.
    eocd_abs = archive_size - tail_size + eocd_idx
    cd_start = eocd_abs - cd_size
    cd = get_range(session, cd_start, eocd_abs - 1)

    entries: dict[str, ZipEntry] = {}
    cursor = 0
    fixed = struct.Struct("<4s6H3L5H2L")
    for _ in range(n_entries):
        fields = fixed.unpack_from(cd, cursor)
        if fields[0] != b"PK\x01\x02":
            raise RuntimeError(f"bad central-directory signature at {cursor}")
        compression = fields[4]
        crc32 = fields[7]
        compressed_size = fields[8]
        uncompressed_size = fields[9]
        name_len, extra_len, comment_len_entry = fields[10], fields[11], fields[12]
        local_offset32 = fields[16]
        name_start = cursor + fixed.size
        name = cd[name_start : name_start + name_len].decode("utf-8")
        entries[name] = ZipEntry(
            name=name,
            compression=compression,
            crc32=crc32,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            local_offset32=local_offset32,
        )
        cursor = name_start + name_len + extra_len + comment_len_entry

    return archive_size, entries


def resolve_local_offset(
    session: requests.Session, archive_size: int, entry: ZipEntry
) -> tuple[int, int]:
    candidates = [entry.local_offset32]
    wrapped = entry.local_offset32 + (1 << 32)
    if wrapped < archive_size:
        candidates.append(wrapped)

    local_fixed = struct.Struct("<4s5H3L2H")
    for offset in candidates:
        header = get_range(session, offset, offset + local_fixed.size - 1)
        fields = local_fixed.unpack(header)
        if fields[0] != b"PK\x03\x04":
            continue
        name_len, extra_len = fields[-2], fields[-1]
        name = get_range(
            session,
            offset + local_fixed.size,
            offset + local_fixed.size + name_len - 1,
        ).decode("utf-8")
        if name != entry.name:
            continue
        data_start = offset + local_fixed.size + name_len + extra_len
        return offset, data_start
    raise RuntimeError(f"could not resolve local header for {entry.name}")


def extract_entry(
    session: requests.Session, archive_size: int, entry: ZipEntry, out_root: Path
) -> int:
    _, data_start = resolve_local_offset(session, archive_size, entry)
    compressed = get_range(
        session,
        data_start,
        data_start + entry.compressed_size - 1,
    )
    if entry.compression == 0:
        raw = compressed
    elif entry.compression == 8:
        raw = zlib.decompress(compressed, -zlib.MAX_WBITS)
    else:
        raise RuntimeError(
            f"{entry.name}: unsupported compression method {entry.compression}"
        )
    if len(raw) != entry.uncompressed_size:
        raise RuntimeError(
            f"{entry.name}: expected {entry.uncompressed_size} bytes, got {len(raw)}"
        )
    crc = binascii.crc32(raw) & 0xFFFFFFFF
    if crc != entry.crc32:
        raise RuntimeError(
            f"{entry.name}: CRC mismatch {crc:08x} != {entry.crc32:08x}"
        )

    prefix = "Wildtrack_dataset/"
    relative = entry.name[len(prefix) :] if entry.name.startswith(prefix) else entry.name
    dest = out_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return len(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--annotation-count",
        type=int,
        default=100,
        help="Number of annotation frames from the start (400 exist total).",
    )
    args = parser.parse_args()

    session = requests.Session()
    archive_size, entries = read_central_directory(session)

    wanted: list[str] = []
    for cam in CAMERAS:
        wanted.append(
            f"Wildtrack_dataset/calibrations/intrinsic_zero/intr_{cam}.xml"
        )
        wanted.append(
            f"Wildtrack_dataset/calibrations/extrinsic/extr_{cam}.xml"
        )

    annotation_names = sorted(
        name
        for name in entries
        if name.startswith("Wildtrack_dataset/annotations_positions/")
        and name.endswith(".json")
    )
    wanted.extend(annotation_names[: args.annotation_count])

    missing = [name for name in wanted if name not in entries]
    if missing:
        raise RuntimeError(f"archive members not found: {missing[:5]}")

    total = 0
    manifest = {
        "source_url": URL,
        "archive_content_length": archive_size,
        "requested_annotation_count": args.annotation_count,
        "files": [],
    }
    for index, name in enumerate(wanted, 1):
        entry = entries[name]
        size = extract_entry(session, archive_size, entry, args.out)
        total += size
        manifest["files"].append(
            {
                "archive_member": name,
                "uncompressed_bytes": size,
                "crc32": f"{entry.crc32:08x}",
            }
        )
        if index % 20 == 0 or index == len(wanted):
            print(f"[{index}/{len(wanted)}] extracted; {total / 1e6:.2f} MB uncompressed")

    manifest["total_uncompressed_bytes"] = total
    manifest_path = args.out / "subset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"saved {manifest_path}")


if __name__ == "__main__":
    main()
