"""Read a text DXF into drawing objects.

Layers are kept as the object kind. A door drawn as a leaf plus a swing
stays two objects. Collapsing them would be a counting rule, and that rule
is not checked here.
"""

from __future__ import annotations

from pathlib import Path

from drawing_objects import DrawingObject


def _pairs(text: str):
    lines = text.splitlines()
    index = 0
    while index + 1 < len(lines):
        yield lines[index].strip(), lines[index + 1].strip()
        index += 2


def _float(value: str) -> float:
    return float(value)


def read_dxf(path: Path) -> list[DrawingObject]:
    raw = path.read_text(encoding="utf-8")
    section = ""
    objects: list[DrawingObject] = []
    entity = ""
    layer = ""
    text = ""
    points: list[tuple[float, float]] = []
    pending_x: float | None = None
    closed = False
    radius = 0.0

    def flush() -> None:
        nonlocal entity, layer, text, points, pending_x, closed, radius
        if entity and layer:
            if entity in ("CIRCLE", "ARC") and points and radius:
                cx, cy = points[0]
                points = [(cx - radius, cy - radius), (cx + radius, cy + radius)]
            objects.append(
                DrawingObject(
                    source="dxf",
                    kind=layer.lower(),
                    name=entity.lower(),
                    text=text,
                    points=tuple(points),
                    closed=closed,
                    storey="",
                )
            )
        entity = ""
        layer = ""
        text = ""
        points = []
        pending_x = None
        closed = False
        radius = 0.0

    for code, value in _pairs(raw):
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
        if not entity:
            continue
        if code == "8":
            layer = value
        elif code == "1":
            text = value
        elif code == "70" and entity == "LWPOLYLINE":
            closed = bool(int(value) & 1)
        elif code == "40" and entity in ("CIRCLE", "ARC"):
            radius = _float(value)
        elif code == "10":
            pending_x = _float(value)
        elif code == "20" and pending_x is not None:
            points.append((pending_x, _float(value)))
            pending_x = None
    flush()
    return objects
