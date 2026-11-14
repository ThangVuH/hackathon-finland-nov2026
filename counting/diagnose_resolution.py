"""Second inference configuration, on plans the published model already saw.

The run that produced published_counts_test.csv resizes each preview up or
down to F1_scaled.png. The repository builds its training and evaluation
database from F1_original.png, which is the preview image, at its own size.
This script measures that resolution on a few of those seen plans. It also
runs the real F1_scaled.png when one is downloaded, because a bilinear resize
of the preview is not that file.

Nothing here is chosen from the 27 held-out plans, and this script does not
write published_counts.csv.
"""

from __future__ import annotations

import csv
import statistics
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

import fetch_scales
import fetch_svgs
from audit_svg import SVG_ROOT, read_svg
from count_metrics import match_symbols
from export_yolo import PREVIEW, boxes_for, load_scales
from run_published import answers, count_openings, load_model, predict

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "diagnostics"
SEEN = [
    ("colorful", "34"),
    ("colorful", "6327"),
    ("high_quality", "10306"),
    ("colorful", "2002"),
    ("high_quality", "108"),
    ("high_quality", "11377"),
]
FILE_SCALED = {("colorful", "34"), ("colorful", "6327")}
FIELDS = [
    "config",
    "style",
    "sample_id",
    "input_w",
    "input_h",
    "window_pred",
    "window_svg",
    "window_answer",
    "door_pred",
    "door_svg",
    "door_answer",
    "window_tp",
    "window_fp",
    "window_fn",
    "door_tp",
    "door_fp",
    "door_fn",
    "window_fragmented",
    "window_missed",
    "window_extra",
    "door_fragmented",
    "door_missed",
    "door_extra",
    "window_median_dist",
    "door_median_dist",
    "seconds",
]


def load_tensor(path: Path) -> torch.Tensor:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        array = np.moveaxis(np.asarray(rgb, dtype=np.float32), -1, 0)
    return torch.from_numpy(2 * (array / 255.0) - 1).unsqueeze(0)


def fetch_scaled(style: str, sample_id: str) -> Path | None:
    destination = ROOT / "cache" / "samples" / style / sample_id / "F1_scaled.png"
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    suffix = f"{style}/{sample_id}/F1_scaled.png"
    for name, method, comp, _uncomp, offset in fetch_svgs.load_directory():
        if name.replace("\\", "/").endswith(suffix):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(fetch_scales.extract_png(method, comp, offset))
            return destination
    return None


def gold_boxes(style: str, sample_id: str, scale_x: float, scale_y: float) -> dict[str, list[list[float]]]:
    found = {"window": [], "door": []}
    for class_id, x0, y0, x1, y1 in boxes_for(style, sample_id, scale_x, scale_y):
        found["window" if class_id == 0 else "door"].append([x0, y0, x1, y1])
    return found


def centers_inside(predicted: list[list[float]], gold: list[list[float]]) -> tuple[int, int, int]:
    used = set()
    fragmented = 0
    missed = 0
    for box in gold:
        inside = []
        for index, pred in enumerate(predicted):
            center_x = (pred[0] + pred[2]) / 2
            center_y = (pred[1] + pred[3]) / 2
            if box[0] <= center_x <= box[2] and box[1] <= center_y <= box[3]:
                inside.append(index)
        if not inside:
            missed += 1
        elif len(inside) > 1:
            fragmented += 1
        used.update(inside)
    return fragmented, missed, len(predicted) - len(used)


def median_distance(predicted: list[list[float]], gold: list[list[float]]) -> str:
    if not predicted or not gold:
        return ""
    distances = []
    for pred in predicted:
        center = ((pred[0] + pred[2]) / 2, (pred[1] + pred[3]) / 2)
        distances.append(
            min(
                ((center[0] - (box[0] + box[2]) / 2) ** 2 + (center[1] - (box[1] + box[3]) / 2) ** 2) ** 0.5
                for box in gold
            )
        )
    return f"{statistics.median(distances):.1f}"


def draw_overlay(image_path: Path, gold: dict[str, list], predicted: dict[str, list], destination: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    strokes = (
        (gold["window"], (0, 150, 0)),
        (gold["door"], (0, 70, 190)),
        (predicted["window"], (210, 30, 30)),
        (predicted["door"], (220, 130, 0)),
    )
    for boxes, color in strokes:
        for box in boxes:
            draw.rectangle([box[0], box[1], box[2], box[3]], outline=color, width=2)
    image.thumbnail((1400, 1400))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def one(
    model,
    config: str,
    style: str,
    sample_id: str,
    image_path: Path,
    pred_scale: tuple[float, float],
    gold_scale: tuple[float, float],
    overlay_path: Path,
    gold_answers: dict,
) -> dict:
    tensor = load_tensor(image_path)
    tick = time.perf_counter()
    heatmaps, rooms, icons = predict(model, tensor)
    totals, boxes = count_openings(heatmaps, rooms, icons)
    elapsed = time.perf_counter() - tick
    scale_x, scale_y = pred_scale
    predicted = {
        "window": [[x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y] for x0, y0, x1, y1 in boxes["window"]],
        "door": [[x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y] for x0, y0, x1, y1 in boxes["door"]],
    }
    reference = gold_boxes(style, sample_id, gold_scale[0], gold_scale[1])
    record = {
        "config": config,
        "style": style,
        "sample_id": sample_id,
        "input_w": tensor.shape[3],
        "input_h": tensor.shape[2],
        "seconds": round(elapsed, 1),
    }
    for label in ("window", "door"):
        true_positives, false_positives, false_negatives = match_symbols(predicted[label], reference[label])
        fragmented, missed, extra = centers_inside(predicted[label], reference[label])
        record[f"{label}_pred"] = totals[label]
        record[f"{label}_svg"] = len(reference[label])
        answer = gold_answers.get((style, sample_id, label))
        record[f"{label}_answer"] = "" if answer is None else answer
        record[f"{label}_tp"] = true_positives
        record[f"{label}_fp"] = false_positives
        record[f"{label}_fn"] = false_negatives
        record[f"{label}_fragmented"] = fragmented
        record[f"{label}_missed"] = missed
        record[f"{label}_extra"] = extra
        record[f"{label}_median_dist"] = median_distance(predicted[label], reference[label])
    overlay_name = OUT_DIR / "overlays" / config / f"{style}-{sample_id}.png"
    draw_overlay(overlay_path, reference, predicted, overlay_name)
    print(
        f"  {config} {record['input_w']}x{record['input_h']} "
        f"fenetres {totals['window']}/{len(reference['window'])} "
        f"portes {totals['door']}/{len(reference['door'])} {elapsed:.0f}s",
        flush=True,
    )
    return record


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    scales = load_scales()
    gold_answers = answers()
    model = load_model()
    rows = []
    out = OUT_DIR / "seen_native.csv"
    for style, sample_id in SEEN:
        preview_w, preview_h, scale_x, scale_y = scales[(style, sample_id)]
        icons, _vocabulary, _width, _height = read_svg(SVG_ROOT / style / sample_id / "model.svg")
        raw = Counter(icon["kind"] for icon in icons if icon["x0"] is not None)
        print(
            f"{style}-{sample_id} apercu {preview_w}x{preview_h} "
            f"chaine actuelle {round(preview_w / scale_x)}x{round(preview_h / scale_y)} "
            f"svg fenetres {raw['window']} portes {raw['door']}",
            flush=True,
        )
        preview = PREVIEW / f"{style}-{sample_id}.png"
        rows.append(
            one(
                model,
                "native",
                style,
                sample_id,
                preview,
                (1.0, 1.0),
                (scale_x, scale_y),
                preview,
                gold_answers,
            )
        )
        write_rows(out, rows)
        if (style, sample_id) not in FILE_SCALED:
            continue
        scaled_path = fetch_scaled(style, sample_id)
        if scaled_path is None:
            print("  fichier F1_scaled introuvable", flush=True)
            continue
        rows.append(
            one(
                model,
                "fichier_scaled",
                style,
                sample_id,
                scaled_path,
                (scale_x, scale_y),
                (scale_x, scale_y),
                preview,
                gold_answers,
            )
        )
        write_rows(out, rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
