"""Record the F1_scaled.png size for every preview plan.

CubiCasa draws symbol coordinates in the pixel space of F1_scaled.png.
The preview image is F1_original.png. The scale between them places each
symbol on the challenge image. The scaled files are deleted after the
PNG header is read.
"""

from __future__ import annotations

import csv
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

import fetch_svgs as fetch

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT.parent / "junction-dataset-preview" / "data" / "cubicasa5k"
OUT = ROOT / "scaled_size.csv"


def png_size(blob: bytes) -> tuple[int, int]:
    image = Image.open(__import__("io").BytesIO(blob))
    return image.size


def extract_png(method: int, comp: int, offset: int) -> bytes:
    header = fetch.get_range(offset, offset + 511)
    if header[:4] != b"PK\x03\x04":
        raise RuntimeError("bad local header")
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    start = offset + 30 + name_len + extra_len
    payload = fetch.get_range(start, start + comp - 1)
    if method == 0:
        return payload
    if method == 8:
        return zlib.decompress(payload, -15)
    raise RuntimeError(f"unsupported method {method}")


def main() -> None:
    plans = fetch.preview_plans()
    entries = fetch.load_directory()
    scaled = {}
    for name, method, comp, _uncomp, offset in entries:
        normalized = name.replace("\\", "/")
        if not normalized.endswith("/F1_scaled.png"):
            continue
        parts = normalized.split("/")
        scaled[(parts[-3], parts[-2])] = (method, comp, offset)

    missing = [f"{style}-{sample_id}" for style, sample_id in plans if (style, sample_id) not in scaled]
    if missing:
        raise SystemExit(f"missing F1_scaled.png: {missing[:8]}")

    def one(item):
        style, sample_id = item
        method, comp, offset = scaled[item]
        width, height = png_size(extract_png(method, comp, offset))
        with Image.open(PREVIEW / f"{style}-{sample_id}.png") as preview:
            preview_w, preview_h = preview.size
        return {
            "style": style,
            "sample_id": sample_id,
            "scaled_w": width,
            "scaled_h": height,
            "preview_w": preview_w,
            "preview_h": preview_h,
            "scale_x": round(preview_w / width, 6),
            "scale_y": round(preview_h / height, 6),
        }

    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one, plan) for plan in plans]
        for done, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if done % 40 == 0 or done == len(plans):
                print(f"[{done}/{len(plans)}]")
    rows.sort(key=lambda row: (row["style"], int(row["sample_id"]) if row["sample_id"].isdigit() else row["sample_id"]))
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    uniform = sum(abs(row["scale_x"] - row["scale_y"]) < 1e-3 for row in rows)
    print(f"wrote {OUT.name}  uniform scale {uniform}/{len(rows)}")


if __name__ == "__main__":
    main()
