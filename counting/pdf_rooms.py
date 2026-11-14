"""PDF inference for room outlines. Train buildings only.

The stroke is chosen the way the door arc was chosen: the signature whose
closed paths equal the DXF room-polygon count on the most plans. Area is not
used to choose it.

A closed path of that stroke is a room. Its area in square metres is the PDF
area times one factor for the plan. The factor is the median of printed area
over PDF area, on rooms that have a printed area. The written scale, such as
1:200, is only a cross-check. If the two factors differ by more than 2%, the
plan is low confidence.

Inference is scored against the DXF polygon of the same room code, within 2%.
The 15 holdout buildings are not read.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf
from shapely.geometry import Point, Polygon

from drawing_objects import dataset_root
from read_dxf import read_dxf
from swiss_index import _paired, _shoelace, _smallest, _texts
from swiss_text import _train

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "pdf_rooms.txt"
SCALE = re.compile(r"1\s*:\s*(\d+)")
NUMBER = re.compile(r"^(\d+(?:[.,]\d+)?)$")
CODE = re.compile(r"^[A-Za-z]*\d+\.\d+$")
WITHIN = 0.02


def _signature(drawing: dict) -> tuple:
    color = drawing.get("color") or drawing.get("fill")
    return (
        drawing.get("type"),
        tuple(round(channel, 3) for channel in color) if color else None,
        round(float(drawing.get("width") or 0), 2),
    )


def _ring(drawing: dict) -> list[tuple[float, float]] | None:
    if any(item[0] == "re" for item in drawing.get("items", [])):
        rect = next(item[1] for item in drawing["items"] if item[0] == "re")
        return [(rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x1, rect.y1), (rect.x0, rect.y1)]
    points: list[tuple[float, float]] = []
    for item in drawing.get("items", []):
        if item[0] != "l":
            return None
        start = (item[1].x, item[1].y)
        end = (item[2].x, item[2].y)
        if not points:
            points.append(start)
        points.append(end)
    if len(points) < 4:
        return None
    if (points[0][0] - points[-1][0]) ** 2 + (points[0][1] - points[-1][1]) ** 2 > 1.5 ** 2:
        return None
    return points[:-1]


def _dxf_rooms(path: Path) -> dict[str, float]:
    texts = _texts(path)
    paired, missing, _used = _paired(texts)
    rings = [
        (polygon, area)
        for item in read_dxf(path)
        if item.kind == "room_outline" and item.name == "lwpolyline" and len(item.points) >= 3
        for polygon, area in [_as_polygon(item.points)]
        if polygon is not None
    ]
    rooms = {}
    rows = [(name, name_at, code, code_at, printed) for name, name_at, code, code_at, printed, _area in paired]
    rows += [(name, name_at, code, code_at, None) for name, name_at, code, code_at in missing]
    for _name, name_at, code, code_at, printed in rows:
        anchor = name_at or code_at
        found = _smallest(rings, anchor) if anchor is not None else None
        if found is None:
            continue
        rooms[code] = found[1]
    return rooms


def _as_polygon(points) -> tuple[Polygon | None, float]:
    area = _shoelace(points)
    if area <= 1e-6:
        return None, 0.0
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or polygon.geom_type != "Polygon":
        return None, 0.0
    return polygon, area


def _pdf_polygons(page) -> dict[tuple, list[Polygon]]:
    grouped: dict[tuple, list[Polygon]] = defaultdict(list)
    for drawing in page.get_drawings():
        points = _ring(drawing)
        if points is None:
            continue
        polygon, _area = _as_polygon(tuple(points))
        if polygon is not None:
            grouped[_signature(drawing)].append(polygon)
    return grouped


def _words(page) -> list[tuple[str, Point]]:
    found = []
    for word in page.get_text("words"):
        x0, y0, x1, y1, text = word[:5]
        found.append((text, Point((x0 + x1) / 2, (y0 + y1) / 2)))
    return found


def _page_scale(words: list[tuple[str, Point]]) -> float | None:
    """Square points per square metre, from a written 1:N and 72 points per inch."""
    match = SCALE.search(" ".join(text for text, _point in words))
    if match is None:
        return None
    points_per_metre = (1000 / int(match.group(1))) / 25.4 * 72
    return 1 / points_per_metre ** 2


def main() -> None:
    train = sorted(_train())
    data = dataset_root() / "swiss_dwellings"
    count_hits: Counter = Counter()
    pages = {}
    for stem in train:
        dxf_n = sum(
            1
            for item in read_dxf(data / f"{stem}.dxf")
            if item.kind == "room_outline" and item.name == "lwpolyline" and len(item.points) >= 3
        )
        document = pymupdf.open(data / f"{stem}.pdf")
        grouped = _pdf_polygons(document[0])
        pages[stem] = (document[0].rect, grouped, _words(document[0]), dxf_n)
        document.close()
        for signature, polygons in grouped.items():
            if len(polygons) == dxf_n and dxf_n:
                count_hits[signature] += 1
    signature = count_hits.most_common(1)[0][0] if count_hits else None
    matched = count_hits[signature] if signature else 0
    compared = calibrated = text_only = disagree = 0
    hits = printed_hits = printed_n = missing_hits = missing_n = 0
    same_hits = same_n = other_hits = other_n = 0
    example = None
    for stem in train:
        _rect, grouped, words, dxf_n = pages[stem]
        same_count = len(grouped.get(signature, [])) == dxf_n if signature else False
        if signature is None or len(grouped.get(signature, [])) == 0:
            continue
        polygons = grouped[signature]
        dxf_rooms = _dxf_rooms(data / f"{stem}.dxf")
        ratios = []
        coded: list[tuple[str, float, bool]] = []
        for polygon in polygons:
            code = next((text for text, point in words if CODE.match(text) and polygon.contains(point)), None)
            printed = None
            for index, (text, point) in enumerate(words):
                match = NUMBER.match(text)
                if match is None or not polygon.contains(point):
                    continue
                follower = words[index + 1][0] if index + 1 < len(words) else ""
                if "m" not in follower.casefold() and "²" not in follower:
                    continue
                printed = float(match.group(1).replace(",", "."))
                break
            if printed and polygon.area:
                ratios.append(printed / polygon.area)
            if code is not None:
                coded.append((code, polygon.area, printed is not None))
        written = _page_scale(words)
        factor = None
        if ratios:
            ordered = sorted(ratios)
            factor = ordered[len(ordered) // 2]
            calibrated += 1
            if written and abs(factor - written) > WITHIN * abs(written):
                disagree += 1
            if stem == "site1000_bldg2082_floor9385":
                example = (factor, written, len(ratios))
        elif written:
            factor = written
            text_only += 1
        if factor is None:
            continue
        for code, area, had_print in coded:
            target = dxf_rooms.get(code)
            if target is None:
                continue
            compared += 1
            ok = abs(area * factor - target) <= WITHIN * abs(target) if target else area * factor == 0
            hits += int(ok)
            if had_print:
                printed_n += 1
                printed_hits += int(ok)
            else:
                missing_n += 1
                missing_hits += int(ok)
            if same_count:
                same_n += 1
                same_hits += int(ok)
            else:
                other_n += 1
                other_hits += int(ok)
    lines = [
        "Train buildings only. The stroke is chosen by count, not by area.",
        "Holdout answers were not read.",
        f"closed paths equal DXF room polygons: {matched}/{len(train)}  signature {signature}",
        "other signatures at the top:",
    ]
    for key, count in count_hits.most_common(5):
        lines.append(f"  {count}/{len(train)}  {key}")
    lines.extend(
        [
            f"plans calibrated from a printed area: {calibrated}",
            f"plans with only the written scale: {text_only}",
            f"plans where printed factor and 1:N differ by more than 2%: {disagree}",
            f"PDF area against the DXF polygon, within 2%: {hits}/{compared}",
            f"  rooms that had a printed area: {printed_hits}/{printed_n}",
            f"  rooms with no printed area: {missing_hits}/{missing_n}",
            f"  on plans whose stroke count matches: {same_hits}/{same_n}",
            f"  on the other plans: {other_hits}/{other_n}",
            f"example site1000 factor, written factor, printed rooms: {example}",
            "A disagreement of the two scales is a low-confidence flag. It does not change the factor.",
        ]
    )
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
