"""Area conventions on one IFC file only.

The file is bsc-esplanades. Other models, PDF renders, and the Estonian
duplicates are not scored. Two conventions are fixed before the score:

- the space property AR_Ruum / 120_Pindala, comma accepted as a decimal mark
- the convex area of the space mesh vertices at the lowest height

Qto net and gross areas are recorded if they exist. A miss is not repaired
with a third rule. resbim-388 is checked only for whether it has products
and whether the preview asks it anything.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
from shapely.geometry import MultiPoint

from drawing_objects import dataset_root
from export_yolo import questions_path

FILE = "bsc-esplanades_1807-ep-ar-v18.ifc"
ROOM = re.compile(r"What is the net floor area of the room '(.+)' on '(.+)', in m²\?")
STOREY = re.compile(r"What is the total net floor area of all rooms \(spaces\) on '(.+)', in m²\?")
WITHIN = 0.02
OUT = Path(__file__).resolve().parent / "ifc_one_file_audit.txt"


def _close(predicted: float, answer: float) -> bool:
    if answer == 0:
        return abs(predicted) <= 1e-6
    return abs(predicted - answer) <= WITHIN * abs(answer)


def _storey(element) -> str:
    """Doors are contained in a storey. Spaces are aggregated by one."""
    import ifcopenshell.util.element as element_util

    current = element
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if current.is_a("IfcBuildingStorey"):
            return str(current.Name or "")
        container = element_util.get_container(current)
        if container is not None:
            current = container
            continue
        parents = getattr(current, "Decomposes", None) or []
        current = parents[0].RelatingObject if parents else None
    return ""


def _property_area(element) -> float | None:
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcPropertySet") or definition.Name != "AR_Ruum":
            continue
        for prop in definition.HasProperties:
            if prop.Name != "120_Pindala":
                continue
            raw = str(prop.NominalValue.wrappedValue).replace(",", ".").replace(" ", "")
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _qto_areas(element) -> dict[str, float]:
    found = {}
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcElementQuantity"):
            continue
        for quantity in definition.Quantities:
            if quantity.is_a("IfcQuantityArea"):
                found[f"{definition.Name}.{quantity.Name}"] = float(quantity.AreaValue)
    return found


def _footprint(element, settings) -> float | None:
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
    except Exception:
        return None
    verts = shape.geometry.verts
    if len(verts) < 9:
        return None
    triples = list(zip(verts[0::3], verts[1::3], verts[2::3]))
    lowest = min(point[2] for point in triples)
    flat = [(point[0], point[1]) for point in triples if abs(point[2] - lowest) < 1e-3]
    if len(flat) < 3:
        return None
    hull = MultiPoint(flat).convex_hull
    if hull.geom_type == "Polygon":
        return float(hull.area)
    return None


def main() -> None:
    path = dataset_root() / "ifc_models" / FILE
    model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    length_unit = []
    for assignment in model.by_type("IfcUnitAssignment"):
        for unit in assignment.Units:
            if unit.is_a("IfcSIUnit") and unit.UnitType == "LENGTHUNIT":
                length_unit.append(f"{unit.Prefix or ''} {unit.Name}")
    spaces = []
    qto_names: set[str] = set()
    for space in model.by_type("IfcSpace"):
        label = f"{space.LongName or ''} ({space.Name or ''})"
        qtos = _qto_areas(space)
        qto_names.update(qtos)
        spaces.append(
            {
                "label": label,
                "storey": _storey(space),
                "property": _property_area(space),
                "footprint": _footprint(space, settings),
            }
        )
    by_key: dict[tuple[str, str], list[dict]] = {}
    for space in spaces:
        by_key.setdefault((space["label"], space["storey"]), []).append(space)

    room_n = prop_hits = foot_hits = 0
    total_n = total_prop = total_foot = 0
    missing_property = ambiguous = 0
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).endswith(FILE):
            continue
        room = ROOM.fullmatch(row["question"])
        storey = STOREY.fullmatch(row["question"])
        answer = float(row["answer"])
        if room:
            room_n += 1
            matches = by_key.get((room.group(1), room.group(2)), [])
            if len(matches) != 1:
                ambiguous += 1
                continue
            chosen = matches[0]
            if chosen["property"] is None:
                missing_property += 1
            else:
                prop_hits += int(_close(chosen["property"], answer))
            if chosen["footprint"] is not None:
                foot_hits += int(_close(chosen["footprint"], answer))
        elif storey:
            total_n += 1
            group = [space for space in spaces if space["storey"] == storey.group(1)]
            prop_values = [space["property"] for space in group if space["property"] is not None]
            foot_values = [space["footprint"] for space in group if space["footprint"] is not None]
            if len(prop_values) == len(group) and group:
                total_prop += int(_close(sum(prop_values), answer))
            if len(foot_values) == len(group) and group:
                total_foot += int(_close(sum(foot_values), answer))

    resbim = dataset_root() / "ifc_models" / "resbim-388_model.ifc"
    resbim_model = ifcopenshell.open(str(resbim))
    empty_counts = {
        kind: len(resbim_model.by_type(kind))
        for kind in ("IfcDoor", "IfcWindow", "IfcSpace", "IfcWall", "IfcBuildingStorey")
    }
    asked = 0
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if line and "resbim-388" in line:
            asked += 1
    text = "\n".join(
        [
            f"One file only: {FILE}. PDF renders and other IFC models are not scored.",
            f"length unit: {', '.join(length_unit) or 'unspecified'}",
            f"spaces {len(spaces)}",
            f"Qto area quantities found: {', '.join(sorted(qto_names)) or 'none'}",
            f"room net area, property 120_Pindala: {prop_hits}/{room_n}",
            f"room net area, convex lowest footprint: {foot_hits}/{room_n}",
            f"ambiguous or missing label matches: {ambiguous}",
            f"spaces missing 120_Pindala among matched rooms: {missing_property}",
            f"storey total, same property sum: {total_prop}/{total_n}",
            f"storey total, same footprint sum: {total_foot}/{total_n}",
            "No third convention is tried on the misses.",
            f"resbim-388 products {empty_counts}",
            f"resbim-388 preview questions {asked}. It cannot test a 'none' answer until a question asks one.",
            "",
        ]
    )
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
