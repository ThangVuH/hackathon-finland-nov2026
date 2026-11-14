"""The same area procedure on a second file, molio.

Esplanades used a custom property, AR_Ruum / 120_Pindala. That name is not
used here. This file is asked for its own quantities. The choice, fixed
from the names before the score, is BaseQuantities.NetFloorArea, converted
by the declared area unit. Misses are counted and not repaired.
"""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell

from audit_ifc_one import ROOM, STOREY, _close, _storey
from drawing_objects import dataset_root
from export_yolo import questions_path

FILE = "bsc-molio_molio-with-uris.ifc"
OUT = Path(__file__).resolve().parent / "ifc_second_file.txt"
PREFIX = {"MILLI": 1e-3, "CENTI": 1e-2, "DECI": 1e-1, None: 1.0, "": 1.0}


def _area_scale(model) -> tuple[float, str]:
    length_prefix = None
    area_prefix = None
    area_name = ""
    for assignment in model.by_type("IfcUnitAssignment"):
        for unit in assignment.Units:
            if not unit.is_a("IfcSIUnit"):
                continue
            if unit.UnitType == "LENGTHUNIT":
                length_prefix = unit.Prefix
            elif unit.UnitType == "AREAUNIT":
                area_prefix = unit.Prefix
                area_name = unit.Name or ""
    if area_name:
        factor = PREFIX.get(area_prefix, 1.0) ** 2
        return factor, f"area {area_prefix or ''} {area_name}"
    factor = PREFIX.get(length_prefix, 1.0) ** 2
    return factor, f"no area unit; length {length_prefix or 'NONE'} squared"


def _net_area(element, scale: float) -> float | None:
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcElementQuantity") or definition.Name != "BaseQuantities":
            continue
        for quantity in definition.Quantities:
            if quantity.is_a("IfcQuantityArea") and quantity.Name == "NetFloorArea":
                return float(quantity.AreaValue) * scale
    return None


def main() -> None:
    model = ifcopenshell.open(str(dataset_root() / "ifc_models" / FILE))
    scale, unit_text = _area_scale(model)
    spaces = []
    for space in model.by_type("IfcSpace"):
        spaces.append(
            {
                "label": f"{space.LongName or ''} ({space.Name or ''})",
                "storey": _storey(space),
                "area": _net_area(space, scale),
            }
        )
    by_key: dict[tuple[str, str], list[dict]] = {}
    for space in spaces:
        by_key.setdefault((space["label"], space["storey"]), []).append(space)
    room_n = room_hits = ambiguous = missing = 0
    total_n = total_hits = 0
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
            if len(matches) != 1 or matches[0]["area"] is None:
                ambiguous += int(len(matches) != 1)
                missing += int(len(matches) == 1 and matches[0]["area"] is None)
                continue
            room_hits += int(_close(matches[0]["area"], answer))
        elif storey:
            total_n += 1
            group = [space for space in spaces if space["storey"] == storey.group(1)]
            values = [space["area"] for space in group if space["area"] is not None]
            if group and len(values) == len(group):
                total_hits += int(_close(sum(values), answer))
    present = sum(space["area"] is not None for space in spaces)
    text = "\n".join(
        [
            f"Second file only: {FILE}. The esplanades property name is not used.",
            "Chosen before the score, from the quantity name: BaseQuantities.NetFloorArea.",
            f"unit: {unit_text}  scale {scale}",
            f"spaces {len(spaces)}  with NetFloorArea {present}",
            f"room net area: {room_hits}/{room_n}",
            f"label mismatches {ambiguous}  missing quantity on a matched room {missing}",
            f"storey sum of the same quantity: {total_hits}/{total_n}",
            "Misses are not repaired on this file.",
            "",
        ]
    )
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
