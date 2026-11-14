"""Door arcs alone, on the Swiss training buildings.

Arcs and arcs-plus-polylines are different rules. This file scores arcs
only. The difference answer minus arc count is recorded so a constant
offset can be seen. The 15 holdout buildings are not read.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pymupdf

from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "swiss_doors.txt"
DOORS = "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"
# Frozen earlier: this stroke matches the DXF door-arc count on every plan.
STROKE = ("s", (0.0, 0.0, 0.0), None, 0.85)


def _train() -> set[str]:
    rows = csv.DictReader((ROOT / "swiss_split.csv").open(encoding="utf-8"))
    return {row["stem"] for row in rows if row["split"] == "train"}


def _arcs(path: Path) -> int:
    return sum(1 for item in read_dxf(path) if item.kind == "door" and item.name == "arc")


def _strokes(path: Path) -> int:
    document = pymupdf.open(path)
    try:
        page = document[0]
        return sum(1 for drawing in page.get_drawings() if _signature(drawing) == STROKE)
    finally:
        document.close()


def _signature(drawing: dict) -> tuple:
    color = drawing.get("color")
    fill = drawing.get("fill")
    return (
        drawing.get("type"),
        tuple(round(channel, 3) for channel in color) if color else None,
        tuple(round(channel, 3) for channel in fill) if fill else None,
        round(float(drawing.get("width") or 0), 2),
    )


def _door_arcs(path: Path) -> list[tuple[tuple[float, float], float]]:
    arcs = []
    for item in read_dxf(path):
        if item.kind != "door" or item.name != "arc" or len(item.points) < 2:
            continue
        (x0, y0), (x1, y1) = item.points[0], item.points[1]
        centre = (round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2))
        arcs.append((centre, round((x1 - x0) / 2, 2)))
    return arcs


def _polylines(path: Path) -> list[tuple[float, float]]:
    points = []
    for item in read_dxf(path):
        if item.kind == "door" and item.name == "lwpolyline":
            points.extend(item.points)
    return points


def main() -> None:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    answers = []
    gaps = Counter()
    definition = inference = agree = centres_hit = near_leaf = 0
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row["question"] != DOORS:
            continue
        stem = Path(row["path"]).stem
        if stem not in train:
            continue
        answer = int(row["answer"])
        path = data / f"{stem}.dxf"
        arc_rows = _door_arcs(path)
        arcs = len(arc_rows)
        strokes = _strokes(data / f"{stem}.pdf")
        answers.append(answer)
        gaps[answer - arcs] += 1
        definition += int(arcs == answer)
        inference += int(strokes == answer)
        agree += int(arcs == strokes)
        centres_hit += int(len({centre for centre, _radius in arc_rows}) == answer)
        leaves = _polylines(path)
        kept = 0
        for centre, radius in arc_rows:
            if any((px - centre[0]) ** 2 + (py - centre[1]) ** 2 <= radius ** 2 for px, py in leaves):
                kept += 1
        near_leaf += int(kept == answer)
    total = len(answers)
    mode = Counter(answers).most_common(1)[0]
    lines = [
        "Train buildings only. Arcs alone. Holdout answers were not read.",
        f"plans {total}",
        f"definition (DXF arcs) {definition}/{total}",
        f"inference (PDF stroke width 0.85) {inference}/{total}",
        f"PDF strokes equal DXF arcs {agree}/{total}",
        f"baseline, most frequent training answer {mode[0]} = {mode[1]}/{total}",
        "answer minus arc count:",
    ]
    for gap, count in sorted(gaps.items()):
        lines.append(f"  {gap:+d}  {count}")
    lines.append("No plan has a positive difference, so arcs + 1 is not a candidate.")
    lines.append(f"candidate, one count per arc centre: {centres_hit}/{total}")
    lines.append(f"candidate, arc kept only if a door polyline point lies in its circle: {near_leaf}/{total}")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
