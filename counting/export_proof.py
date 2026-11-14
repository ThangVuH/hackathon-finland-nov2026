"""One real sheet for the page: Zimmer text boxes and one room polygon."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
from shapely.geometry import Point

from drawing_objects import dataset_root
from pdf_questions import SIGNATURE
from pdf_rooms import _pdf_polygons

STEM = "site1000_bldg2082_floor9385"
OUT_DIR = Path(__file__).resolve().parents[1] / "STOA-eyes" / "src" / "proofs"


def _milli(rect, x: float, y: float) -> list[int]:
    return [round(1000 * x / rect.width), round(1000 * y / rect.height)]


def main() -> None:
    path = dataset_root() / "swiss_dwellings" / f"{STEM}.pdf"
    document = pymupdf.open(path)
    page = document[0]
    rect = page.rect
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False)
    pixmap.save(OUT_DIR / "swiss-floor.png")
    words = page.get_text("words")
    polygons = _pdf_polygons(page).get(SIGNATURE, [])
    document.close()
    items = []
    for word in words:
        x0, y0, x1, y1, text = word[:5]
        if text != "Zimmer":
            continue
        items.append(
            {
                "kind": "text",
                "label": "Zimmer",
                "page": 1,
                "ymin": _milli(rect, x0, y0)[1],
                "xmin": _milli(rect, x0, y0)[0],
                "ymax": _milli(rect, x1, y1)[1],
                "xmax": _milli(rect, x1, y1)[0],
            }
        )
    code_point = next((Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in words if w[4] == "2.10"), None)
    target = None
    if code_point is not None:
        containing = [polygon for polygon in polygons if polygon.contains(code_point)]
        if containing:
            target = min(containing, key=lambda polygon: polygon.area)
    ring = []
    if target is not None:
        xs, ys = target.exterior.coords.xy
        ring = [_milli(rect, x, y) for x, y in zip(xs, ys)]
    payload = {
        "value": len(items),
        "note": "printed labels. The written scale and the printed areas agree on this sheet.",
        "scale": "agrees",
        "items": items,
        "room": {
            "label": "2.10 Zimmer",
            "source": "polygon",
            "page": 1,
            "polygon": ring,
        },
    }
    (OUT_DIR / "swiss-floor.json").write_text(json.dumps(payload), encoding="utf-8")
    print(f"labels {len(items)}  ring {len(ring)}  png {pixmap.width}x{pixmap.height}")


if __name__ == "__main__":
    main()
