"""Two apartment rules, fixed before the score. Train buildings only.

The span between two unit labels scored 10/86 and is not tried again.
Both candidates use the UNIT_OUTLINE layer.

1. Area of the outline that contains the unit label (App. / Whg. / Wohnung / Appartamento).
2. Sum of room areas whose label sits inside that same outline.
   A room area is the printed area, or the room polygon if no area is printed.

No third rule. The 15 holdout buildings are not read.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from shapely.geometry import Point, Polygon

from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf
from swiss_index import _paired, _rings, _shoelace, _texts
from swiss_text import APT, UNIT, _close, _train

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "swiss_unit.txt"


def _units(path: Path) -> list[tuple[Polygon, float]]:
    found = []
    for item in read_dxf(path):
        if item.kind != "unit_outline" or item.name != "lwpolyline" or len(item.points) < 3:
            continue
        area = _shoelace(item.points)
        if area <= 1e-6:
            continue
        polygon = Polygon(item.points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        found.append((polygon, area))
    return found


def _containing(polygons: list[tuple[Polygon, float]], point: Point) -> tuple[Polygon, float] | None:
    hits = [(polygon, area) for polygon, area in polygons if polygon.contains(point)]
    if not hits:
        return None
    return min(hits, key=lambda item: item[1])


def main() -> None:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    questions = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        match = APT.match(row["question"])
        if stem in train and match:
            questions.append((stem, match.group(1), float(row["answer"])))
    outline_hits = sum_hits = 0
    answers = []
    for stem, letter, answer in questions:
        path = data / f"{stem}.dxf"
        texts = _texts(path)
        units = _units(path)
        label = None
        for text, point in texts:
            match = UNIT.match(text)
            if match and match.group(1).rstrip(".") == letter:
                label = point
                break
        chosen = _containing(units, label) if label is not None else None
        outline_hits += int(chosen is not None and _close(chosen[1], answer))
        room_sum = None
        if chosen is not None:
            paired, missing, _used = _paired(texts)
            rings = _rings(path)
            total = 0.0
            present = False
            for name, name_at, _code, code_at, printed, _area_at in list(paired) + [
                (name, name_at, code, code_at, None, None) for name, name_at, code, code_at in missing
            ]:
                anchor = name_at or code_at
                if anchor is None or not chosen[0].contains(anchor):
                    continue
                if printed is None:
                    room = _containing(rings, anchor)
                    if room is None:
                        continue
                    value = room[1]
                else:
                    value = printed
                total += value
                present = True
            if present:
                room_sum = total
        sum_hits += int(room_sum is not None and _close(room_sum, answer))
        answers.append(answer)
    total = len(questions)
    baseline = max(Counter(answers).values()) if answers else 0
    lines = [
        "Train buildings only. Two candidates, then stop. Holdout answers were not read.",
        f"questions {total}  baseline {baseline}/{total}",
        f"1 outline containing the unit label: {outline_hits}/{total}",
        f"2 sum of room areas inside that outline: {sum_hits}/{total}",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
