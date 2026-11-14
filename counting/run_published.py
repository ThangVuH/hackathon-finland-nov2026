"""Run the published CubiCasa model on the preview plans.

The network sees each plan at the F1_scaled resolution it was trained on.
Windows and doors are the polygons produced by the official post-processing,
not connected components of the segmentation.
"""

from __future__ import annotations

import csv
import faulthandler
import gc
import importlib.util
import sys
import time
import types
from pathlib import Path

faulthandler.enable()

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "CubiCasa5k"
sys.path.insert(0, str(VENDOR))

# The package init imports the dataset loader, which needs lmdb. Inference does not.
loaders = types.ModuleType("floortrans.loaders")
loaders.__path__ = [str(VENDOR / "floortrans" / "loaders")]
sys.modules["floortrans.loaders"] = loaders
svg_utils = types.ModuleType("floortrans.loaders.svg_utils")
sys.modules["floortrans.loaders.svg_utils"] = svg_utils
loaders.svg_utils = svg_utils
spec = importlib.util.spec_from_file_location(
    "floortrans.loaders.augmentations",
    VENDOR / "floortrans" / "loaders" / "augmentations.py",
)
augmentations = importlib.util.module_from_spec(spec)
sys.modules["floortrans.loaders.augmentations"] = augmentations
spec.loader.exec_module(augmentations)
RotateNTurns = augmentations.RotateNTurns

from floortrans.models.hg_furukawa_original import hg_furukawa_original  # noqa: E402
from floortrans.post_prosessing import get_polygons, split_prediction  # noqa: E402

from count_metrics import match_symbols, summarize  # noqa: E402
from export_yolo import PREVIEW, boxes_for, load_scales  # noqa: E402

WEIGHTS = ROOT / "weights" / "model_best_val_loss_var.pkl"
SPLIT_CSV = ROOT / "preview_cubicasa_split.csv"
EVAL = ROOT / "eval_split.csv"
OUT = ROOT / "published_counts.csv"
SENTINEL = ROOT / "published_current.txt"
SPLIT = [21, 12, 11]
N_CLASSES = 44
WINDOW = 1
DOOR = 2
ROTATIONS = [(0, 0), (1, -1), (2, 2), (-1, 1)]


def load_model() -> torch.nn.Module:
    checkpoint = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    model = hg_furukawa_original(n_classes=51)
    model.conv4_ = torch.nn.Conv2d(256, N_CLASSES, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(N_CLASSES, N_CLASSES, kernel_size=4, stride=4)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model


def load_image(style: str, sample_id: str, scaled_w: int, scaled_h: int) -> torch.Tensor:
    image = Image.open(PREVIEW / f"{style}-{sample_id}.png").convert("RGB")
    image = image.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
    array = np.moveaxis(np.asarray(image, dtype=np.float32), -1, 0)
    return torch.from_numpy(2 * (array / 255.0) - 1).unsqueeze(0)


def predict(model: torch.nn.Module, image: torch.Tensor) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, width = image.shape[2], image.shape[3]
    rotator = RotateNTurns()
    total = None
    with torch.no_grad():
        for forward, back in ROTATIONS:
            rotated = rotator(image, "tensor", forward)
            prediction = model(rotated)
            prediction = rotator(prediction, "tensor", back)
            prediction = rotator(prediction, "points", back)
            prediction = F.interpolate(prediction, size=(height, width), mode="bilinear", align_corners=True)
            total = prediction if total is None else total + prediction
    averaged = total / len(ROTATIONS)
    return split_prediction(averaged, (height, width), SPLIT)


def count_openings(heatmaps, rooms, icons) -> tuple[dict[str, int], dict[str, list[list[float]]]]:
    polygons, types, _rooms, _room_types = get_polygons((heatmaps, rooms, icons), 0.4, [WINDOW, DOOR])
    boxes = {"window": [], "door": []}
    names = {WINDOW: "window", DOOR: "door"}
    for polygon, kind in zip(polygons, types):
        label = names.get(int(kind["class"])) if kind["type"] == "icon" else None
        if label is None:
            continue
        xs = polygon[:, 0]
        ys = polygon[:, 1]
        boxes[label].append([float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())])
    return {label: len(found) for label, found in boxes.items()}, boxes


def to_preview(boxes: list[list[float]], scale_x: float, scale_y: float) -> list[list[float]]:
    return [[x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y] for x0, y0, x1, y1 in boxes]


def answers() -> dict[tuple[str, str, str], int]:
    found = {}
    with EVAL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            found[(row["style"], row["sample_id"], row["label"])] = int(row["answer"])
    return found


def plans_for(which: str) -> list[tuple[str, str, str]]:
    selected = []
    with SPLIT_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if which == "all" or row["cubicasa_split"] == which:
                selected.append((row["style"], row["sample_id"], row["cubicasa_split"]))
    return selected


FIELDS = [
    "style",
    "sample_id",
    "cubicasa_split",
    "seconds",
    "window",
    "window_answer",
    "door",
    "door_answer",
    "error",
]


def _write_rows(rows: list[dict]) -> None:
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _begin_plan(style: str, sample_id: str) -> int:
    key = f"{style},{sample_id}"
    crashes = 0
    if SENTINEL.exists():
        text = SENTINEL.read_text(encoding="utf-8").strip()
        if text.startswith(key + ","):
            crashes = int(text.rsplit(",", 1)[-1])
    crashes += 1
    SENTINEL.write_text(f"{key},{crashes}", encoding="utf-8")
    return crashes


def load_rows() -> list[dict]:
    if not OUT.exists():
        return []
    with OUT.open(encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("sample_id")]


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "test"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    selected = plans_for(which)
    if limit:
        selected = selected[:limit]
    done = {(row["style"], row["sample_id"]) for row in load_rows()}
    pending = [item for item in selected if (item[0], item[1]) not in done]
    scales = load_scales()
    gold = answers()
    rows = load_rows()
    metric_rows = []
    started = time.perf_counter()
    model = load_model() if pending else None
    print(f"{len(pending)} plans a calculer, {len(done)} deja enregistres", flush=True)
    for index, (style, sample_id, cubi_split) in enumerate(pending, start=1):
        preview_w, preview_h, scale_x, scale_y = scales[(style, sample_id)]
        scaled_w = round(preview_w / scale_x)
        scaled_h = round(preview_h / scale_y)
        print(f"[{index}/{len(pending)}] {style}-{sample_id} {cubi_split} {scaled_w}x{scaled_h}", flush=True)
        crashes = _begin_plan(style, sample_id)
        if crashes > 2:
            print("  saute: le processus s'est arrete deux fois sur ce plan", flush=True)
            rows.append(
                {
                    "style": style,
                    "sample_id": sample_id,
                    "cubicasa_split": cubi_split,
                    "seconds": 0,
                    "error": "processus interrompu",
                }
            )
            _write_rows(rows)
            SENTINEL.unlink(missing_ok=True)
            continue
        tick = time.perf_counter()
        try:
            heatmaps, rooms, icons = predict(model, load_image(style, sample_id, scaled_w, scaled_h))
            totals, boxes = count_openings(heatmaps, rooms, icons)
        except Exception as error:
            print(f"  echec {type(error).__name__}: {error}", flush=True)
            rows.append(
                {
                    "style": style,
                    "sample_id": sample_id,
                    "cubicasa_split": cubi_split,
                    "seconds": round(time.perf_counter() - tick, 1),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            _write_rows(rows)
            continue
        elapsed = time.perf_counter() - tick
        record = {
            "style": style,
            "sample_id": sample_id,
            "cubicasa_split": cubi_split,
            "seconds": round(elapsed, 1),
        }
        gold_boxes = {"window": [], "door": []}
        for class_id, x0, y0, x1, y1 in boxes_for(style, sample_id, scale_x, scale_y):
            gold_boxes["window" if class_id == 0 else "door"].append([x0, y0, x1, y1])
        for label in ("window", "door"):
            predicted_boxes = to_preview(boxes[label], scale_x, scale_y)
            true_positives, false_positives, false_negatives = match_symbols(
                predicted_boxes, gold_boxes[label]
            )
            record[label] = totals[label]
            key = (style, sample_id, label)
            if key not in gold:
                continue
            record[f"{label}_answer"] = gold[key]
            metric_rows.append(
                {
                    "label": label,
                    "group": cubi_split,
                    "answer": gold[key],
                    "predicted": totals[label],
                    "tp": true_positives,
                    "fp": false_positives,
                    "fn": false_negatives,
                }
            )
        rows.append(record)
        print(
            f"  fenetres {totals['window']} portes {totals['door']} {elapsed:.0f}s",
            flush=True,
        )
        _write_rows(rows)
        SENTINEL.unlink(missing_ok=True)
        del heatmaps, rooms, icons, boxes
        gc.collect()

    _write_rows(rows)
    print(f"wrote {OUT.name} in {time.perf_counter() - started:.0f}s")
    for group in ("test", "val", "train"):
        subset = [row for row in metric_rows if row["group"] == group]
        if not subset:
            continue
        print(group)
        print(summarize(subset))


if __name__ == "__main__":
    main()
