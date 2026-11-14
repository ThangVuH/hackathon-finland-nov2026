"""Count windows and doors on whole plans and score exact match.

Tiles are predicted separately, then boxes are put back on the plan and
merged. The confidence threshold is chosen on the validation plans and
applied once to the test plans.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw
from ultralytics import YOLO

from count_metrics import match_symbols, summarize
from export_yolo import CLASS_ID, PREVIEW, TILE, boxes_for, load_scales, tile_origins

ROOT = Path(__file__).resolve().parent
EVAL = ROOT / "eval_split.csv"
WEIGHTS = ROOT / "runs" / "window-door" / "weights" / "best.pt"
NAMES = {index: name for name, index in CLASS_ID.items()}
CONF_GRID = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)


def load_answers() -> dict[tuple[str, str, str], tuple[str, int]]:
    answers = {}
    with EVAL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            answers[(row["style"], row["sample_id"], row["label"])] = (row["split"], int(row["answer"]))
    return answers


def intersection(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def nms(boxes: list[list[float]], scores: list[float], iou_threshold: float = 0.5) -> list[int]:
    order = sorted(range(len(boxes)), key=lambda index: scores[index], reverse=True)
    kept: list[int] = []
    while order:
        current = order.pop(0)
        kept.append(current)
        remaining = []
        box = boxes[current]
        area = max(1e-6, (box[2] - box[0]) * (box[3] - box[1]))
        for other in order:
            other_box = boxes[other]
            other_area = max(1e-6, (other_box[2] - other_box[0]) * (other_box[3] - other_box[1]))
            union = area + other_area - intersection(box, other_box)
            if intersection(box, other_box) / union < iou_threshold:
                remaining.append(other)
        order = remaining
    return kept


def predict_plan(model: YOLO, style: str, sample_id: str, scale) -> list[tuple[str, float, list[float]]]:
    preview_w, preview_h, _sx, _sy = scale
    image = Image.open(PREVIEW / f"{style}-{sample_id}.png").convert("RGB")
    collected: list[tuple[str, float, list[float]]] = []
    for ox, oy, tile_w, tile_h in tile_origins(preview_w, preview_h):
        crop = image.crop((ox, oy, ox + tile_w, oy + tile_h))
        result = model.predict(crop, imgsz=TILE, conf=min(CONF_GRID), iou=0.5, verbose=False, device="cpu")[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue
        for box, score, class_id in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
        ):
            x0, y0, x1, y1 = box
            collected.append(
                (
                    NAMES[int(class_id)],
                    float(score),
                    [x0 + ox, y0 + oy, x1 + ox, y1 + oy],
                )
            )
    image.close()
    return collected


def counts_at(detections, threshold: float) -> dict[str, int]:
    kept = defaultdict(list)
    scores = defaultdict(list)
    for name, score, box in detections:
        if score < threshold:
            continue
        kept[name].append(box)
        scores[name].append(score)
    totals = {}
    for name in NAMES.values():
        chosen = nms(kept[name], scores[name])
        totals[name] = len(chosen)
    return totals


def kept_boxes(detections, threshold: float, label: str) -> list[list[float]]:
    grouped = []
    scores = []
    for name, score, box in detections:
        if name == label and score >= threshold:
            grouped.append(box)
            scores.append(score)
    return [grouped[index] for index in nms(grouped, scores)]


def score(plans: dict, answers, scales, threshold: float, split: str) -> list[dict]:
    rows = []
    for (style, sample_id), detections in plans.items():
        preview_w, preview_h, scale_x, scale_y = scales[(style, sample_id)]
        del preview_w, preview_h
        gold = defaultdict(list)
        for class_id, x0, y0, x1, y1 in boxes_for(style, sample_id, scale_x, scale_y):
            gold[NAMES[class_id]].append([x0, y0, x1, y1])
        for label in NAMES.values():
            key = (style, sample_id, label)
            if key not in answers or answers[key][0] != split:
                continue
            predicted_boxes = kept_boxes(detections, threshold, label)
            true_positives, false_positives, false_negatives = match_symbols(
                predicted_boxes, gold[label]
            )
            rows.append(
                {
                    "label": label,
                    "answer": answers[key][1],
                    "predicted": len(predicted_boxes),
                    "tp": true_positives,
                    "fp": false_positives,
                    "fn": false_negatives,
                }
            )
    return rows


def draw_examples(threshold: float, plans, answers) -> None:
    out = ROOT / "overlays" / "predictions"
    out.mkdir(parents=True, exist_ok=True)
    shown = set()
    colors = {"window": (220, 30, 30), "door": (20, 70, 220)}
    for (style, sample_id), detections in plans.items():
        if style in shown or answers.get((style, sample_id, "window"), ("", 0))[0] != "test":
            continue
        image = Image.open(PREVIEW / f"{style}-{sample_id}.png").convert("RGB")
        draw = ImageDraw.Draw(image)
        totals = counts_at(detections, threshold)
        grouped = defaultdict(list)
        grouped_scores = defaultdict(list)
        for name, score, box in detections:
            if score < threshold:
                continue
            grouped[name].append(box)
            grouped_scores[name].append(score)
        for name in grouped:
            for index in nms(grouped[name], grouped_scores[name]):
                draw.rectangle(grouped[name][index], outline=colors[name], width=max(2, image.width // 400))
        image.save(out / f"{style}-{sample_id}.jpg", quality=85)
        shown.add(style)
        del totals
        if len(shown) == 3:
            break


def main() -> None:
    answers = load_answers()
    scales = load_scales()
    model = YOLO(str(WEIGHTS))
    plans = {}
    wanted = {
        (style, sample_id)
        for (style, sample_id, _label), (split, _answer) in answers.items()
        if split in {"val", "test"}
    }
    for index, (style, sample_id) in enumerate(sorted(wanted), start=1):
        plans[(style, sample_id)] = predict_plan(model, style, sample_id, scales[(style, sample_id)])
        if index % 20 == 0 or index == len(wanted):
            print(f"predicted {index}/{len(wanted)}")

    best_threshold = CONF_GRID[0]
    best_exact = -1
    for threshold in CONF_GRID:
        rows = score(plans, answers, scales, threshold, "val")
        exact = sum(int(row["predicted"]) == int(row["answer"]) for row in rows)
        print(f"val conf={threshold:.2f} exact={exact}/{len(rows)}")
        if exact > best_exact:
            best_exact = exact
            best_threshold = threshold

    print(f"chosen conf {best_threshold}")
    for split in ("val", "test"):
        print(split)
        print(summarize(score(plans, answers, scales, best_threshold, split)))
    draw_examples(best_threshold, plans, answers)


if __name__ == "__main__":
    main()
