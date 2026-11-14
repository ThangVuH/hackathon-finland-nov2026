"""Export detector boxes as a tiled YOLO dataset.

The 27 official CubiCasa test plans are held out of train and validation.
Symbol coordinates are converted from SVG space to the preview image.
Plans larger than the tile are cut into overlapping tiles so a thin window
is not reduced to a couple of pixels. A box is assigned to the tile that
contains its center.
"""

from __future__ import annotations

import csv
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from audit_svg import SVG_ROOT
from label_rules import CLASS_ID, boxes_in

ROOT = Path(__file__).resolve().parent
SCALES = ROOT / "scaled_size.csv"
OFFICIAL = ROOT / "preview_cubicasa_split.csv"
SPLIT_CSV = ROOT / "detector_split.csv"
OUT = ROOT / "yolo-multiclass"
TILE = 640
OVERLAP = 128
VAL_FRACTION = 0.15
SEED = 13


def preview_dir() -> Path:
    candidates = [
        ROOT.parent / "junction-dataset-preview" / "data" / "cubicasa5k",
        ROOT.parent.parent / "stoa-preview" / "junction-dataset-preview" / "data" / "cubicasa5k",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("CubiCasa preview images were not found next to the repo.")


PREVIEW = preview_dir()


def questions_path() -> Path:
    candidates = [
        ROOT.parent / "junction-dataset-preview" / "questions.jsonl",
        ROOT.parent.parent / "stoa-preview" / "junction-dataset-preview" / "questions.jsonl",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("questions.jsonl was not found next to the repo.")


def write_detector_split() -> dict[tuple[str, str], str]:
    """Train and val exclude the official CubiCasa test plans."""
    official = {}
    with OFFICIAL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            official[(row["style"], row["sample_id"])] = row["cubicasa_split"]
    rest: dict[str, list[str]] = defaultdict(list)
    test: list[tuple[str, str]] = []
    for style_dir in sorted(path for path in SVG_ROOT.iterdir() if path.is_dir()):
        for sample_dir in sorted(path for path in style_dir.iterdir() if path.is_dir()):
            key = (style_dir.name, sample_dir.name)
            if official.get(key) == "test":
                test.append(key)
            else:
                rest[key[0]].append(key[1])
    rng = random.Random(SEED)
    splits: dict[tuple[str, str], str] = {key: "test" for key in test}
    for style, sample_ids in sorted(rest.items()):
        ordered = sorted(sample_ids)
        rng.shuffle(ordered)
        n_val = max(1, round(len(ordered) * VAL_FRACTION))
        if n_val >= len(ordered):
            n_val = 1
        held = set(ordered[:n_val])
        for sample_id in sample_ids:
            splits[(style, sample_id)] = "val" if sample_id in held else "train"
    with SPLIT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["style", "sample_id", "split"])
        for (style, sample_id), split in sorted(splits.items()):
            writer.writerow([style, sample_id, split])
    return splits


def load_splits() -> dict[tuple[str, str], str]:
    if not SPLIT_CSV.exists():
        return write_detector_split()
    splits = {}
    with SPLIT_CSV.open(encoding="utf-8") as handle:
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
    boxes = []
    for kind, x0, y0, x1, y1 in boxes_in(SVG_ROOT / style / sample_id / "model.svg"):
        left = min(x0, x1) * scale_x
        right = max(x0, x1) * scale_x
        top = min(y0, y1) * scale_y
        bottom = max(y0, y1) * scale_y
        if right - left < 1 or bottom - top < 1:
            continue
        boxes.append((CLASS_ID[kind], left, top, right, bottom))
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
    splits = write_detector_split()
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
        + "".join(f"  {index}: {name}\n" for name, index in sorted(CLASS_ID.items(), key=lambda item: item[1]))
    )
    (OUT / "dataset.yaml").write_text(yaml, encoding="utf-8")
    print("samples", dict(counts))


if __name__ == "__main__":
    main()
