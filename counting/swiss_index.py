"""Rooms as polygons, labels, and the objects inside them.

Train buildings only. The 15 holdout plans are not read.

First check: a missing printed area is not an area text sitting near the
label. The radius is the largest name-to-area distance among triples the
line reader already paired.

Second check: on rooms that do have a printed area, the smallest
ROOM_OUTLINE polygon that contains the label is compared with that printed
area. This does not apply the inclusion rule.

Door candidate, fixed from the gap (the answer never exceeds the arc count):
count door arcs whose swing midpoint is not inside a room named as outdoor,
shaft, or void. The outdoor words are the list already frozen.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

from shapely.geometry import Point, Polygon

from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf
from swiss_text import AREA, CODE, OUTDOOR, ROOM, _train

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "swiss_index.txt"
DOORS = "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"


def _shoelace(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2


def _rings(path: Path) -> list[tuple[Polygon, float]]:
    rings = []
    for item in read_dxf(path):
        if item.kind != "room_outline" or item.name != "lwpolyline" or len(item.points) < 3:
            continue
        area = _shoelace(item.points)
        if area <= 1e-6:
            continue
        polygon = Polygon(item.points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        rings.append((polygon, area))
    return rings


def _texts(path: Path) -> list[tuple[str, Point]]:
    found = []
    for item in read_dxf(path):
        if item.kind == "room_text" and item.name == "text" and item.text and item.points:
            found.append((item.text, Point(item.points[0])))
    return found


def _arcs(path: Path) -> list[Point]:
    """Swing midpoint. The hinge is on the wall, so the centre is not used."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    entity = ""
    layer = ""
    cx = cy = radius = start = end = None
    points: list[Point] = []

    def flush() -> None:
        nonlocal entity, layer, cx, cy, radius, start, end
        if entity == "ARC" and layer == "DOOR" and None not in (cx, cy, radius, start, end):
            sweep = (end - start) % 360
            mid = math.radians(start + sweep / 2)
            points.append(Point(cx + radius * math.cos(mid), cy + radius * math.sin(mid)))
        entity = ""
        layer = ""
        cx = cy = radius = start = end = None

    section = ""
    index = 0
    while index + 1 < len(lines):
        code, value = lines[index].strip(), lines[index + 1].strip()
        index += 2
        if code == "0" and value == "SECTION":
            section = ""
            continue
        if code == "2" and section == "" and value in ("HEADER", "CLASSES", "TABLES", "BLOCKS", "ENTITIES", "OBJECTS"):
            section = value
            continue
        if code == "0" and value == "ENDSEC":
            if section == "ENTITIES":
                flush()
            section = ""
            continue
        if section != "ENTITIES":
            continue
        if code == "0":
            flush()
            entity = value
            continue
        if entity != "ARC":
            continue
        if code == "8":
            layer = value
        elif code == "10":
            cx = float(value)
        elif code == "20":
            cy = float(value)
        elif code == "40":
            radius = float(value)
        elif code == "50":
            start = float(value)
        elif code == "51":
            end = float(value)
    flush()
    return points


def _smallest(rings: list[tuple[Polygon, float]], point: Point) -> tuple[Polygon, float] | None:
    found = [(polygon, area) for polygon, area in rings if polygon.contains(point)]
    if not found:
        return None
    return min(found, key=lambda item: item[1])


def _excluded(name: str) -> bool:
    folded = name.casefold()
    return any(marker in folded for marker in OUTDOOR)


def _paired(texts: list[tuple[str, Point]]):
    """Line order. Returns paired triples and rooms whose code has no area line."""
    paired = []
    missing = []
    used_areas: set[int] = set()
    index = 0
    while index < len(texts):
        name = ""
        name_at = None
        if index + 1 < len(texts) and CODE.match(texts[index + 1][0]) and not CODE.match(texts[index][0]):
            if AREA.match(texts[index][0]) or texts[index][0].startswith(("App.", "Whg.", "Wohnung", "Appartamento")):
                index += 1
                continue
            name, name_at = texts[index]
            index += 1
        if index < len(texts) and CODE.match(texts[index][0]):
            code, code_at = texts[index]
            index += 1
            if index < len(texts) and AREA.match(texts[index][0]):
                value = float(AREA.match(texts[index][0]).group(1).replace(",", "."))
                paired.append((name, name_at, code, code_at, value, texts[index][1]))
                used_areas.add(index)
                index += 1
            else:
                missing.append((name, name_at, code, code_at))
            continue
        index += 1
    return paired, missing, used_areas


def main() -> None:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    asked: dict[str, list[tuple[str, str]]] = {}
    door_answers: dict[str, int] = {}
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        if stem not in train:
            continue
        room = ROOM.match(row["question"])
        if room:
            asked.setdefault(stem, []).append((room.group(1), room.group(2)))
        if row["question"] == DOORS:
            door_answers[stem] = int(row["answer"])

    pair_distances = []
    missing_near = missing_far = missing_n = 0
    unpaired_areas = 0
    ratios = []
    no_polygon = 0
    door_hits = door_n = dropped = 0
    plans = []
    for stem in sorted(train):
        path = data / f"{stem}.dxf"
        texts = _texts(path)
        paired, missing, used = _paired(texts)
        area_indexes = {index for index, (text, _point) in enumerate(texts) if AREA.match(text)}
        unpaired = [texts[index][1] for index in area_indexes - used]
        unpaired_areas += len(unpaired)
        for name, name_at, _code, _code_at, _value, area_at in paired:
            if name_at is not None:
                pair_distances.append(name_at.distance(area_at))
        plans.append((stem, path, paired, missing, unpaired))
    radius = max(pair_distances) if pair_distances else 0.0
    for stem, path, paired, missing, unpaired in plans:
        for _name, name_at, _code, code_at in missing:
            missing_n += 1
            anchor = name_at or code_at
            if anchor is None or not unpaired:
                missing_far += 1
                continue
            nearest = min(anchor.distance(point) for point in unpaired)
            if nearest <= radius:
                missing_near += 1
            else:
                missing_far += 1
        rings = _rings(path)
        by_code = {code: (name, name_at, code_at, value) for name, name_at, code, code_at, value, _area_at in paired}
        for code, _label in asked.get(stem, []):
            room = by_code.get(code)
            if room is None:
                continue
            name, name_at, code_at, printed = room
            anchor = name_at or code_at
            found = _smallest(rings, anchor) if anchor is not None else None
            if found is None:
                no_polygon += 1
                continue
            _polygon, area = found
            if printed:
                ratios.append(area / printed)
        names_at = []
        for name, name_at, _code, _code_at, _value, _area_at in paired:
            if name and name_at is not None:
                names_at.append((name, name_at))
        for name, name_at, _code, code_at in missing:
            if name and name_at is not None:
                names_at.append((name, name_at))
        excluded_rings = []
        for name, point in names_at:
            if not _excluded(name):
                continue
            found = _smallest(rings, point)
            if found is not None:
                excluded_rings.append(found[0])
        kept = 0
        for point in _arcs(path):
            if any(polygon.contains(point) for polygon in excluded_rings):
                dropped += 1
                continue
            kept += 1
        if stem in door_answers:
            door_n += 1
            door_hits += int(kept == door_answers[stem])

    radius = max(pair_distances) if pair_distances else 0.0
    ordered = sorted(pair_distances)
    median = ordered[len(ordered) // 2] if ordered else 0.0
    ratio_ordered = sorted(ratios)
    ratio_median = ratio_ordered[len(ratio_ordered) // 2] if ratio_ordered else 0.0
    close = sum(1 for ratio in ratios if abs(ratio - 1) <= 0.02)
    lines = [
        "Train buildings only. Holdout answers were not read.",
        f"paired name-to-area distances: n={len(pair_distances)}  median {median:.3f} m  max {radius:.3f} m",
        f"area texts not consumed by a triple: {unpaired_areas}",
        f"rooms with a code and no area line: {missing_n}",
        f"  nearest unused area text inside that max radius: {missing_near}",
        f"  no unused area text that close: {missing_far}",
        f"printed rooms asked by a question, polygon over printed area: n={len(ratios)}  no polygon {no_polygon}",
        f"  median ratio {ratio_median:.4f}  within 2% of 1: {close}/{len(ratios)}",
        "  ratio counts:",
    ]
    buckets = Counter(round(ratio, 2) for ratio in ratios)
    for key, count in sorted(buckets.items()):
        lines.append(f"    {key:.2f}  {count}")
    lines.append(
        f"door candidate, arcs whose swing is not in an excluded room: {door_hits}/{door_n}  "
        f"arcs dropped {dropped}"
    )
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
