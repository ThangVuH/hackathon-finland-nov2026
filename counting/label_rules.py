"""Boxes for the detector, in SVG coordinates.

The class map is the definition that reproduces the preview answers.
A double sink is one box. A shower screen is not a shower. A utility
room is not a kitchen. A sauna stove is a best-effort stand-in for the
sauna question, whose definition is not fully reproduced.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from audit_svg import (
    IDENTITY,
    SVG_ROOT,
    apply,
    icon_points,
    local,
    multiply,
    parse_matrix,
    polygon_points,
    tokens,
)

SINK = {"Sink", "RoundSink", "SideSink", "CornerSink", "DoubleSink", "DoubleSinkRight"}
TOILET = {"Toilet"}
SHOWER = {"Shower", "Bathtub", "BathtubRound"}
STOVE = {"SaunaStove"}

CLASS_ID = {
    "window": 0,
    "door": 1,
    "sink": 2,
    "toilet": 3,
    "shower": 4,
    "kitchen": 5,
    "sauna_stove": 6,
}


def icon_kind(element_tokens: list[str]) -> str | None:
    if "FixedFurniture" not in element_tokens:
        if "Window" in element_tokens:
            return "window"
        if "Door" in element_tokens:
            return "door"
        return None
    for token in element_tokens:
        if token in SINK:
            return "sink"
        if token in TOILET:
            return "toilet"
        if token in SHOWER:
            return "shower"
        if token in STOVE:
            return "sauna_stove"
    return None


def _add(boxes: list[tuple[str, float, float, float, float]], kind: str, points: list[tuple[float, float]]) -> None:
    if len(points) < 2:
        return
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    boxes.append((kind, x0, y0, x1, y1))


def _shape_points(element: ET.Element, matrix) -> list[tuple[float, float]]:
    matrix = multiply(matrix, parse_matrix(element.get("transform")))
    found: list[tuple[float, float]] = []
    tag = local(element.tag)

    def number(name: str) -> float:
        return float(element.get(name) or 0)

    if tag in ("polygon", "polyline") and element.get("points"):
        found.extend(polygon_points(element, matrix))
    elif tag == "rect":
        x, y = number("x"), number("y")
        found.append(apply(matrix, x, y))
        found.append(apply(matrix, x + number("width"), y + number("height")))
    elif tag in ("circle", "ellipse"):
        cx, cy = number("cx"), number("cy")
        rx = float(element.get("r") or element.get("rx") or 0)
        ry = float(element.get("ry") or element.get("r") or 0)
        found.append(apply(matrix, cx - rx, cy - ry))
        found.append(apply(matrix, cx + rx, cy + ry))
    elif tag == "line":
        found.append(apply(matrix, number("x1"), number("y1")))
        found.append(apply(matrix, number("x2"), number("y2")))
    for child in list(element):
        found.extend(_shape_points(child, matrix))
    return found


def _furniture_points(element: ET.Element, matrix) -> list[tuple[float, float]]:
    """`matrix` already includes `element`'s own transform."""
    points: list[tuple[float, float]] = []
    for child in list(element):
        points.extend(_shape_points(child, matrix))
    return points


def boxes_in(path: Path) -> list[tuple[str, float, float, float, float]]:
    boxes: list[tuple[str, float, float, float, float]] = []

    def walk(element: ET.Element, matrix) -> None:
        matrix = multiply(matrix, parse_matrix(element.get("transform")))
        if local(element.tag) != "g":
            for child in list(element):
                walk(child, matrix)
            return
        element_tokens = tokens(element)
        kind = icon_kind(element_tokens)
        if kind in ("window", "door"):
            _add(boxes, kind, icon_points(element, matrix, kind))
            return
        if kind in ("sink", "toilet", "shower", "sauna_stove"):
            _add(boxes, kind, _furniture_points(element, matrix))
            return
        if "Space" in element_tokens and "Kitchen" in element_tokens:
            for child in list(element):
                if local(child.tag) == "polygon" and child.get("points"):
                    _add(boxes, "kitchen", polygon_points(child, matrix))
                    break
        for child in list(element):
            walk(child, matrix)

    walk(ET.parse(path).getroot(), IDENTITY)
    return boxes


def count_floors(path: Path) -> int:
    total = 0
    for element in ET.parse(path).iter():
        if local(element.tag) == "g" and "Floorplan" in tokens(element):
            total += 1
    return total


def svg_path(style: str, sample_id: str) -> Path:
    return SVG_ROOT / style / sample_id / "model.svg"
