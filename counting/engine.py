"""Window and door boxes from the trained detector, on any floor-plan image.

Tiles match the training setup. Coordinates leave this module on the
0-1000 scale the drawing canvas expects.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from arbitrate import to_milli

ROOT = Path(__file__).resolve().parent
# The live window-door weights were trained with 21 of the 27 test plans.
# epoch22 is the checkpoint chosen on validation, then scored once.
WEIGHTS = ROOT / "runs" / "multiclass" / "weights" / "epoch22.pt"
THRESHOLD_PATH = ROOT / "detector_threshold.txt"
# Frozen in exact_selection.txt. The old single 0.40 cutoff is not applied here.
CUTOFF = {
    "window": 0.30,
    "door": 0.45,
    "sink": 0.60,
    "toilet": 0.45,
    "shower": 0.15,
    "sauna_stove": 0.15,
}
LABELS = {
    "window": "Window",
    "door": "Door",
    "sink": "Sink",
    "toilet": "Toilet",
    "shower": "Shower",
    "sauna_stove": "Sauna stove",
}
_model = None


def load_threshold() -> float:
    if THRESHOLD_PATH.exists():
        try:
            return float(THRESHOLD_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return 0.25


def save_threshold(threshold: float) -> None:
    THRESHOLD_PATH.write_text(f"{threshold:.2f}\n", encoding="utf-8")


def get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(str(WEIGHTS))
    return _model


def predict_tiles(image: Image.Image) -> list[tuple[str, float, list[float]]]:
    """Raw boxes in pixels, before the confidence cutoff. Includes weak scores."""
    from evaluate_counts import CONF_GRID, MAX_DET, NAMES
    from export_yolo import TILE, tile_origins

    width, height = image.size
    found: list[tuple[str, float, list[float]]] = []
    model = get_model()
    floor = min(CONF_GRID)
    for origin_x, origin_y, tile_w, tile_h in tile_origins(width, height):
        crop = image.crop((origin_x, origin_y, origin_x + tile_w, origin_y + tile_h))
        result = model.predict(
            crop, imgsz=TILE, conf=floor, iou=0.5, max_det=MAX_DET, verbose=False, device="cpu"
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue
        for box, score, class_id in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
        ):
            x0, y0, x1, y1 = box
            found.append(
                (
                    NAMES[int(class_id)],
                    float(score),
                    [x0 + origin_x, y0 + origin_y, x1 + origin_x, y1 + origin_y],
                )
            )
    return found


def keep(
    detections: list[tuple[str, float, list[float]]],
    width: int,
    height: int,
    kinds: tuple[str, ...] | None = None,
) -> dict:
    from evaluate_counts import nms

    wanted = kinds or ("window", "door")
    grouped: dict[str, list[list[float]]] = {name: [] for name in wanted}
    scores: dict[str, list[float]] = {name: [] for name in wanted}
    rejected = 0.0
    for name, score, box in detections:
        if name not in grouped:
            continue
        if score < CUTOFF[name]:
            rejected = max(rejected, score)
            continue
        grouped[name].append(box)
        scores[name].append(score)

    items = []
    kept_scores = []
    for name in wanted:
        chosen = nms(grouped[name], scores[name])
        for index in chosen:
            milli = to_milli(grouped[name][index], width, height)
            if milli["xmax"] - milli["xmin"] < 1 or milli["ymax"] - milli["ymin"] < 1:
                continue
            items.append(
                {
                    **milli,
                    "kind": name,
                    "label": LABELS[name],
                    "score": round(scores[name][index], 4),
                }
            )
            kept_scores.append(scores[name][index])
    confidence = sum(kept_scores) / len(kept_scores) if kept_scores else max(0.0, 1.0 - rejected)
    return {"confidence": round(confidence, 4), "items": items}


def detect_openings(image: Image.Image, kinds: tuple[str, ...] | None = None) -> dict:
    width, height = image.size
    return keep(predict_tiles(image), width, height, kinds)
