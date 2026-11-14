"""Read IFC products into the common object list.

ifcopenshell assigns each product to its building storey. Without that
library, the file is only counted by entity type: no storey, no geometry.
Neither result is compared with a question.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from drawing_objects import DrawingObject

PRODUCTS = (
    "IfcDoor",
    "IfcWindow",
    "IfcSpace",
    "IfcWall",
    "IfcWallStandardCase",
    "IfcSlab",
    "IfcColumn",
    "IfcBeam",
    "IfcStair",
    "IfcSanitaryTerminal",
    "IfcFlowTerminal",
    "IfcBuildingStorey",
)
_TYPE = re.compile(r"=\s*([A-Z0-9]+)\(")


def _storey_name(element, element_util) -> str:
    container = element_util.get_container(element)
    seen: set[int] = set()
    while container is not None and id(container) not in seen:
        seen.add(id(container))
        if container.is_a("IfcBuildingStorey"):
            return str(getattr(container, "Name", "") or "")
        container = element_util.get_container(container)
    return ""


def read_ifc(path: Path) -> tuple[list[DrawingObject], str]:
    if path.stat().st_size == 0:
        return [], "empty file"
    try:
        import ifcopenshell
        import ifcopenshell.util.element as element_util
    except ImportError:
        return _scan(path), "type scan only; ifcopenshell is not installed"
    model = ifcopenshell.open(str(path))
    objects: list[DrawingObject] = []
    for ifc_type in PRODUCTS:
        try:
            elements = model.by_type(ifc_type)
        except RuntimeError:
            continue
        for element in elements:
            storey = ""
            if ifc_type != "IfcBuildingStorey":
                try:
                    storey = _storey_name(element, element_util)
                except Exception:
                    storey = ""
            objects.append(
                DrawingObject(
                    source="ifc",
                    kind=element.is_a(),
                    name=str(getattr(element, "Name", "") or ""),
                    text=str(getattr(element, "ObjectType", "") or ""),
                    points=(),
                    closed=False,
                    storey=storey,
                )
            )
    return objects, "ifcopenshell"


def _scan(path: Path) -> list[DrawingObject]:
    counts: Counter[str] = Counter()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = _TYPE.search(line)
            if match and match.group(1) in {name.upper() for name in PRODUCTS}:
                counts[match.group(1)] += 1
    wanted = {name.upper(): name for name in PRODUCTS}
    return [
        DrawingObject(
            source="ifc",
            kind=wanted[name],
            name="",
            text=str(total),
            points=(),
            closed=False,
            storey="",
        )
        for name, total in sorted(counts.items())
    ]
