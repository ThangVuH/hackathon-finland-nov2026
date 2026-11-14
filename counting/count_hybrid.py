"""Third configuration: polygons, plus an uncovered segmentation component.

A window or door component is added only when no polygon of the same class
contains its center and none overlaps at least a third of its rectangle.
Components under 20 pixels are dropped. Both numbers were fixed before any
look at the 27 held-out plans.

``seen`` measures plans the published model has already seen.
``test`` is the single run on the 27. Neither run writes published_counts.csv.
"""

from __future__ import annotations

import csv
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from count_metrics import iou, match_symbols, summarize
from export_yolo import PREVIEW, boxes_for, load_scales
from run_published import answers, count_openings, load_image, load_model, plans_for, predict

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "diagnostics"
MIN_AREA = 20
COVER_RATIO = 0.3
WINDOW = 1
DOOR = 2
LABELS = ("window", "door")
CLASS_NAME = {
    0: "vide",
    1: "fenetre",
    2: "porte",
    3: "placard",
    4: "appareil",
    5: "toilettes",
    6: "lavabo",
    7: "sauna",
    8: "cheminee",
    9: "baignoire",
    10: "conduit",
}
FIELDS = [
    "style",
    "sample_id",
    "cubicasa_split",
    "seconds",
    "window_polygon",
    "window_added",
    "window_hybrid",
    "window_answer",
    "window_svg",
    "door_polygon",
    "door_added",
    "door_hybrid",
    "door_answer",
    "door_svg",
    "window_fp",
    "window_fp_door",
    "window_fp_near_door",
    "window_fp_other",
    "window_fp_rest",
    "error",
]
FP_FIELDS = ["style", "sample_id", "source", "dominant", "dominant_share", "door_distance"]


def box_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def is_covered(component: list[float], polygons: list[list[float]]) -> bool:
    center_x = (component[0] + component[2]) / 2
    center_y = (component[1] + component[3]) / 2
    area = box_area(component)
    if area <= 0:
        return True
    for polygon in polygons:
        inside = polygon[0] <= center_x <= polygon[2] and polygon[1] <= center_y <= polygon[3]
        if inside or intersection(component, polygon) / area >= COVER_RATIO:
            return True
    return False


def component_boxes(mask: np.ndarray) -> list[list[float]]:
    labels, count = ndimage.label(mask)
    found = []
    for index in range(1, int(count) + 1):
        ys, xs = np.where(labels == index)
        if len(xs) < MIN_AREA:
            continue
        found.append([float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)])
    return found


def add_uncovered(polygons: list[list[float]], icon_map: np.ndarray, class_id: int) -> tuple[list[list[float]], list[list[float]]]:
    extra = [box for box in component_boxes(icon_map == class_id) if not is_covered(box, polygons)]
    return polygons + extra, extra


def scale_boxes(boxes: list[list[float]], scale_x: float, scale_y: float) -> list[list[float]]:
    return [[x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y] for x0, y0, x1, y1 in boxes]


def point_box_distance(x: float, y: float, box: list[float]) -> float:
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    return (dx * dx + dy * dy) ** 0.5


def unmatched(predicted: list[list[float]], gold: list[list[float]]) -> list[list[float]]:
    used = set()
    kept = []
    for box in predicted:
        best_index = None
        best_overlap = 0.5
        for index, truth in enumerate(gold):
            if index in used:
                continue
            overlap = iou(box, truth)
            if overlap >= best_overlap:
                best_overlap = overlap
                best_index = index
        if best_index is None:
            kept.append(box)
        else:
            used.add(best_index)
    return kept


def false_positive_source(
    box: list[list[float]],
    doors: list[list[float]],
    icon_map: np.ndarray,
    scale_x: float,
    scale_y: float,
) -> tuple[str, str, float, float]:
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    door_distance = min((point_box_distance(center_x, center_y, door) for door in doors), default=-1.0)
    overlaps_door = any(intersection(box, door) > 0 for door in doors)
    near_span = 0.0
    for door in doors:
        if point_box_distance(center_x, center_y, door) == door_distance:
            near_span = max(door[2] - door[0], door[3] - door[1])
            break
    x0 = max(0, int(box[0] / scale_x))
    y0 = max(0, int(box[1] / scale_y))
    x1 = min(icon_map.shape[1], max(x0 + 1, int(box[2] / scale_x)))
    y1 = min(icon_map.shape[0], max(y0 + 1, int(box[3] / scale_y)))
    crop = icon_map[y0:y1, x0:x1]
    counts = np.bincount(crop.ravel(), minlength=11) if crop.size else np.zeros(11, dtype=int)
    dominant = int(np.argmax(counts))
    share = float(counts[dominant] / counts.sum()) if counts.sum() else 0.0
    if overlaps_door:
        source = "porte"
    elif door_distance >= 0 and door_distance <= max(near_span, 8.0):
        source = "pres_porte"
    elif dominant not in (0, 1) and share >= 0.25:
        source = "autre"
    else:
        source = "reste"
    return source, CLASS_NAME.get(dominant, str(dominant)), round(share, 3), round(door_distance, 1)


def check_cover() -> None:
    polygons = [[0.0, 0.0, 10.0, 10.0]]
    if not is_covered([1.0, 1.0, 4.0, 4.0], polygons):
        raise RuntimeError("center")
    if is_covered([20.0, 20.0, 30.0, 30.0], polygons):
        raise RuntimeError("far")
    partial = [8.0, 0.0, 14.0, 10.0]
    if not is_covered(partial, polygons):
        raise RuntimeError("overlap")


def seen_plans() -> list[tuple[str, str, str]]:
    selected = []
    seen = set()
    with (ROOT / "published_counts.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("cubicasa_split") == "test" or not row.get("sample_id"):
                continue
            key = (row["style"], row["sample_id"])
            if key in seen:
                continue
            seen.add(key)
            selected.append((row["style"], row["sample_id"], row["cubicasa_split"]))
    return selected


def finished(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {(row["style"], row["sample_id"]) for row in csv.DictReader(handle) if not row.get("error")}


def write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def draw_overlay(style: str, sample_id: str, gold: dict, hybrid: dict, destination: Path) -> None:
    with Image.open(PREVIEW / f"{style}-{sample_id}.png") as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    strokes = (
        (gold["window"], (0, 150, 0)),
        (gold["door"], (0, 70, 190)),
        (hybrid["window"], (210, 30, 30)),
        (hybrid["door"], (220, 130, 0)),
    )
    for boxes, color in strokes:
        for box in boxes:
            draw.rectangle(box, outline=color, width=2)
    canvas.thumbnail((1400, 1400))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)


def metric_rows(records: list[dict], predicted_key: str) -> list[dict]:
    rows = []
    for record in records:
        if record.get("error"):
            continue
        for label in LABELS:
            answer = record.get(f"{label}_answer")
            if answer == "" or answer is None:
                continue
            predicted = int(record[f"{label}_{predicted_key}"])
            rows.append({"label": label, "answer": int(answer), "predicted": predicted})
    return rows


def one(model, style: str, sample_id: str, cubi_split: str, scales, gold_answers) -> tuple[dict, list[dict]]:
    preview_w, preview_h, scale_x, scale_y = scales[(style, sample_id)]
    scaled_w = round(preview_w / scale_x)
    scaled_h = round(preview_h / scale_y)
    tick = time.perf_counter()
    heatmaps, rooms, icons = predict(model, load_image(style, sample_id, scaled_w, scaled_h))
    icon_map = np.argmax(icons, axis=0)
    _totals, network_boxes = count_openings(heatmaps, rooms, icons)
    gold = {"window": [], "door": []}
    for class_id, x0, y0, x1, y1 in boxes_for(style, sample_id, scale_x, scale_y):
        gold["window" if class_id == 0 else "door"].append([x0, y0, x1, y1])
    record = {
        "style": style,
        "sample_id": sample_id,
        "cubicasa_split": cubi_split,
        "seconds": round(time.perf_counter() - tick, 1),
        "error": "",
    }
    preview_boxes = {}
    added_any = 0
    for label, class_id in (("window", WINDOW), ("door", DOOR)):
        combined, extra = add_uncovered(network_boxes[label], icon_map, class_id)
        polygons = scale_boxes(network_boxes[label], scale_x, scale_y)
        hybrid = scale_boxes(combined, scale_x, scale_y)
        preview_boxes[label] = hybrid
        answer = gold_answers.get((style, sample_id, label))
        record[f"{label}_polygon"] = len(polygons)
        record[f"{label}_added"] = len(extra)
        record[f"{label}_hybrid"] = len(hybrid)
        record[f"{label}_answer"] = "" if answer is None else answer
        record[f"{label}_svg"] = len(gold[label])
        added_any += len(extra)
    false_rows = []
    missed = unmatched(scale_boxes(network_boxes["window"], scale_x, scale_y), gold["window"])
    sources = Counter()
    for box in missed:
        source, dominant, share, distance = false_positive_source(box, gold["door"], icon_map, scale_x, scale_y)
        sources[source] += 1
        false_rows.append(
            {
                "style": style,
                "sample_id": sample_id,
                "source": source,
                "dominant": dominant,
                "dominant_share": share,
                "door_distance": distance,
            }
        )
    record["window_fp"] = len(missed)
    record["window_fp_door"] = sources["porte"]
    record["window_fp_near_door"] = sources["pres_porte"]
    record["window_fp_other"] = sources["autre"]
    record["window_fp_rest"] = sources["reste"]
    if added_any:
        draw_overlay(
            style,
            sample_id,
            gold,
            preview_boxes,
            OUT_DIR / "overlays" / "hybrid" / f"{style}-{sample_id}.png",
        )
    return record, false_rows


def main() -> None:
    check_cover()
    mode = sys.argv[1] if len(sys.argv) > 1 else "seen"
    if mode == "seen":
        selected = seen_plans()
        out = OUT_DIR / "seen_hybrid.csv"
        fp_out = OUT_DIR / "seen_window_fp.csv"
    elif mode == "test":
        selected = plans_for("test")
        out = OUT_DIR / "test_hybrid.csv"
        fp_out = OUT_DIR / "test_window_fp.csv"
    else:
        raise SystemExit("usage: count_hybrid.py seen|test")
    done = finished(out)
    pending = [item for item in selected if (item[0], item[1]) not in done]
    print(
        f"configuration 3  min {MIN_AREA}px  couverture {COVER_RATIO}  "
        f"{mode} {len(pending)} a calculer, {len(done)} deja faits",
        flush=True,
    )
    scales = load_scales()
    gold_answers = answers()
    model = load_model() if pending else None
    records = load_rows(out)
    false_rows = load_rows(fp_out)
    for index, (style, sample_id, cubi_split) in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {style}-{sample_id} {cubi_split}", flush=True)
        try:
            record, found = one(model, style, sample_id, cubi_split, scales, gold_answers)
        except Exception as error:
            record = {
                "style": style,
                "sample_id": sample_id,
                "cubicasa_split": cubi_split,
                "seconds": 0,
                "error": f"{type(error).__name__}: {error}",
            }
            found = []
            print(f"  echec {record['error']}", flush=True)
        else:
            print(
                f"  polygones f{record['window_polygon']} p{record['door_polygon']}  "
                f"ajouts f{record['window_added']} p{record['door_added']}  "
                f"hybride f{record['window_hybrid']} p{record['door_hybrid']}  "
                f"fp fenetres {record['window_fp']} {record['seconds']}s",
                flush=True,
            )
        records.append(record)
        false_rows.extend(found)
        write_rows(out, records, FIELDS)
        write_rows(fp_out, false_rows, FP_FIELDS)
    print(f"wrote {out.name}")
    print("polygones")
    print(summarize(metric_rows(records, "polygon")))
    print("hybride")
    print(summarize(metric_rows(records, "hybrid")))
    sources = Counter(row["source"] for row in false_rows)
    print("faux positifs fenetres", dict(sources), "total", sum(sources.values()))


if __name__ == "__main__":
    main()
