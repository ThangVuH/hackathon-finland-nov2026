"""One validation plan at confidence 0.05.

Reports the busiest tile. If that tile reaches max_det, a higher-scoring
box can be dropped before the cutoff is applied.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from ultralytics import YOLO

from evaluate_counts import MAX_DET
from export_yolo import PREVIEW, ROOT, TILE, load_splits, tile_origins

OUT = ROOT / "max_det_check.txt"
PREDICT_CONF = 0.05


def main() -> None:
    weights = sorted((ROOT / "runs" / "multiclass" / "weights").glob("epoch*.pt"))
    if not weights:
        raise SystemExit("no epoch weights")
    chosen = None
    for (style, sample_id), split in load_splits().items():
        if split != "val":
            continue
        path = PREVIEW / f"{style}-{sample_id}.png"
        with Image.open(path) as probe:
            area = probe.size[0] * probe.size[1]
        if chosen is None or area > chosen[0]:
            chosen = (area, style, sample_id)
    _area, style, sample_id = chosen
    image = Image.open(PREVIEW / f"{style}-{sample_id}.png").convert("RGB")
    width, height = image.size
    model = YOLO(str(weights[-1]))
    busiest = 0
    tiles = 0
    for origin_x, origin_y, tile_w, tile_h in tile_origins(width, height):
        crop = image.crop((origin_x, origin_y, origin_x + tile_w, origin_y + tile_h))
        result = model.predict(
            crop, imgsz=TILE, conf=PREDICT_CONF, iou=0.5, max_det=MAX_DET, verbose=False, device="cpu"
        )[0]
        count = 0 if result.boxes is None else len(result.boxes)
        busiest = max(busiest, count)
        tiles += 1
    image.close()
    lines = [
        f"weights {weights[-1].name}",
        f"plan {style}-{sample_id}  {width}x{height}  tiles {tiles}",
        f"confidence {PREDICT_CONF}  max_det {MAX_DET}",
        f"busiest tile {busiest}",
        f"default cap 300 reached: {'yes' if busiest >= 300 else 'no'}",
        f"max_det reached: {'yes' if busiest >= MAX_DET else 'no'}",
        "Cross-tile merge stays after the confidence cutoff, in the selector and in the live keeper.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
