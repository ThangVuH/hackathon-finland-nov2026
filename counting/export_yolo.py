"""Export window and door boxes as a tiled YOLO dataset.

Symbol coordinates are converted from F1_scaled pixels to the preview image.
Plans larger than the tile are cut into overlapping tiles so a thin window
is not reduced to a couple of pixels. A box is assigned to the tile that
contains its center.
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from pathlib import Path

from PIL import Image

from audit_svg import SVG_ROOT, read_svg

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT.parent / "junction-dataset-preview" / "data" / "cubicasa5k"
EVAL = ROOT / "eval_split.csv"
SCALES = ROOT / "scaled_size.csv"
OUT = ROOT / "yolo"
TILE = 640
OVERLAP = 128
CLASS_ID = {"window": 0, "door": 1}


def load_splits() -> dict[tuple[str, str], str]:
    splits = {}
    with EVAL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            splits[(row["style"], row["sample_id"])] = row["split"]
    return splits


def load_scales() -> dict[tuple[str, str], tuple[int, int, float, float]]:
    scales = {}
    with SCALES.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            preview_w = int(row["preview_w"])
            preview_h = int(row["preview_h"])
            scales[(row["style"], row["sample_id"])] = (
                preview_w,
                preview_h,
                preview_w / int(row["scaled_w"]),
                preview_h / int(row["scaled_h"]),
            )
    return scales


def boxes_for(style: str, sample_id: str, scale_x: float, scale_y: float) -> list[tuple[int, float, float, float, float]]:
    icons, _vocabulary, _width, _height = read_svg(SVG_ROOT / style / sample_id / "model.svg")
    boxes = []
    for icon in icons:
        if icon["x0"] is None:
            continue
        x0 = min(icon["x0"], icon["x1"]) * scale_x
        x1 = max(icon["x0"], icon["x1"]) * scale_x
        y0 = min(icon["y0"], icon["y1"]) * scale_y
        y1 = max(icon["y0"], icon["y1"]) * scale_y
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        boxes.append((CLASS_ID[icon["kind"]], x0, y0, x1, y1))
    return boxes


def axis_origins(length: int) -> list[int]:
    if length <= TILE:
        return [0]
    step = TILE - OVERLAP
    origins = list(range(0, length - TILE + 1, step))
    if origins[-1] != length - TILE:
        origins.append(length - TILE)
    return origins


def tile_origins(width: int, height: int) -> list[tuple[int, int, int, int]]:
    if width <= TILE and height <= TILE:
        return [(0, 0, width, height)]
    return [
        (x, y, min(TILE, width - x), min(TILE, height - y))
        for y in axis_origins(height)
        for x in axis_origins(width)
    ]


def label_line(class_id: int, box, origin, tile_w: int, tile_h: int) -> str | None:
    _class_id, x0, y0, x1, y1 = box
    ox, oy = origin
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    if not (ox <= center_x < ox + tile_w and oy <= center_y < oy + tile_h):
        return None
    left = max(x0, ox) - ox
    top = max(y0, oy) - oy
    right = min(x1, ox + tile_w) - ox
    bottom = min(y1, oy + tile_h) - oy
    if right - left < 1 or bottom - top < 1:
        return None
    return (
        f"{class_id} {(left + right) / 2 / tile_w:.6f} {(top + bottom) / 2 / tile_h:.6f} "
        f"{(right - left) / tile_w:.6f} {(bottom - top) / tile_h:.6f}"
    )


def link_or_copy(source: Path, destination: Path) -> None:
    if destination.exists():
        return
    try:
        os.link(source, destination)
    except OSError:
        destination.write_bytes(source.read_bytes())


def main() -> None:
    splits = load_splits()
    scales = load_scales()
    counts = Counter()
    for split in ("train", "val", "test"):
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    for (style, sample_id), split in sorted(splits.items()):
        preview_w, preview_h, scale_x, scale_y = scales[(style, sample_id)]
        boxes = boxes_for(style, sample_id, scale_x, scale_y)
        source = PREVIEW / f"{style}-{sample_id}.png"
        origins = tile_origins(preview_w, preview_h)
        whole = len(origins) == 1 and origins[0][2] == preview_w and origins[0][3] == preview_h
        if whole:
            image_name = f"{style}-{sample_id}.png"
            link_or_copy(source, OUT / "images" / split / image_name)
            lines = []
            for box in boxes:
                line = label_line(box[0], box, (0, 0), preview_w, preview_h)
                if line:
                    lines.append(line)
            (OUT / "labels" / split / f"{style}-{sample_id}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""),
                encoding="utf-8",
            )
            counts[split] += 1
            continue
        image = Image.open(source)
        for ox, oy, tile_w, tile_h in origins:
            lines = [label_line(box[0], box, (ox, oy), tile_w, tile_h) for box in boxes]
            lines = [line for line in lines if line]
            if not lines:
                continue
            crop = image.crop((ox, oy, ox + tile_w, oy + tile_h))
            stem = f"{style}-{sample_id}_x{ox}_y{oy}"
            crop.save(OUT / "images" / split / f"{stem}.png")
            (OUT / "labels" / split / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            counts[split] += 1
        image.close()

    yaml = (
        f'path: "{OUT.as_posix()}"\n'
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        "  0: window\n"
        "  1: door\n"
    )
    (OUT / "dataset.yaml").write_text(yaml, encoding="utf-8")
    print("samples", dict(counts))


if __name__ == "__main__":
    main()
