"""Length and volume on molio. Definition only.

This file was already used for areas. There is no held-out IFC file.
The names are taken from the question before the score:

- total length of walls: BaseQuantities.Length on IfcWall and IfcWallStandardCase
- total net volume of walls or slabs: BaseQuantities.NetVolume

Other quantity names are listed and not tried.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import ifcopenshell

from audit_ifc_one import _close, _storey
from drawing_objects import dataset_root
from export_yolo import questions_path

FILE = "bsc-molio_molio-with-uris.ifc"
OUT = Path(__file__).resolve().parent / "ifc_measure.txt"
LENGTH = re.compile(r"^What is the total length of all walls on '(.+)', in metres\?$")
VOLUME = re.compile(r"^What is the total net volume of all (walls|slabs) on '(.+)', in m³\?$")
PREFIX = {"MILLI": 1e-3, "CENTI": 1e-2, "DECI": 1e-1, None: 1.0, "": 1.0}
WALLS = ("IfcWall", "IfcWallStandardCase")


def _scale(model) -> dict[str, float]:
    found = {"LENGTHUNIT": 1.0, "AREAUNIT": 1.0, "VOLUMEUNIT": 1.0}
    for assignment in model.by_type("IfcUnitAssignment"):
        for unit in assignment.Units:
            if not unit.is_a("IfcSIUnit"):
                continue
            factor = PREFIX.get(unit.Prefix, 1.0)
            if unit.UnitType == "LENGTHUNIT":
                found["LENGTHUNIT"] = factor
            elif unit.UnitType == "AREAUNIT":
                found["AREAUNIT"] = factor ** 2
            elif unit.UnitType == "VOLUMEUNIT":
                found["VOLUMEUNIT"] = factor ** 3
    return found


def _quantities(element) -> list[tuple[str, str, str, float]]:
    found = []
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcElementQuantity"):
            continue
        for quantity in definition.Quantities or []:
            kind = ""
            value = None
            if quantity.is_a("IfcQuantityLength"):
                kind, value = "length", quantity.LengthValue
            elif quantity.is_a("IfcQuantityArea"):
                kind, value = "area", quantity.AreaValue
            elif quantity.is_a("IfcQuantityVolume"):
                kind, value = "volume", quantity.VolumeValue
            if kind:
                found.append((definition.Name or "", quantity.Name or "", kind, float(value)))
    return found


def main() -> None:
    model = ifcopenshell.open(str(dataset_root() / "ifc_models" / FILE))
    scale = _scale(model)
    names: Counter = Counter()
    by_storey: dict[tuple[str, str], float] = {}
    for kind in ("IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcCurtainWall"):
        for element in model.by_type(kind):
            storey = _storey(element)
            for set_name, quantity_name, quantity_kind, value in _quantities(element):
                names[(kind, set_name, quantity_name, quantity_kind)] += 1
                factor = scale[{"length": "LENGTHUNIT", "area": "AREAUNIT", "volume": "VOLUMEUNIT"}[quantity_kind]]
                key = (kind, storey, set_name, quantity_name)
                by_storey[key] = by_storey.get(key, 0.0) + value * factor
    lines = [
        "Development audit. Molio was already opened for areas. Not a held-out score.",
        f"units length x{scale['LENGTHUNIT']}  area x{scale['AREAUNIT']}  volume x{scale['VOLUMEUNIT']}",
        "quantity names present:",
    ]
    for key, count in sorted(names.items()):
        lines.append(f"  {count:5}  {key[0]}  {key[1]}.{key[2]}  {key[3]}")

    def total(kinds: tuple[str, ...], storey: str, quantity: str) -> float | None:
        present = False
        value = 0.0
        for kind in kinds:
            found = by_storey.get((kind, storey, "BaseQuantities", quantity))
            if found is None:
                continue
            present = True
            value += found
        return value if present else None

    length_hits = length_n = volume_hits = volume_n = 0
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).endswith(FILE):
            continue
        length = LENGTH.match(row["question"])
        volume = VOLUME.match(row["question"])
        answer = float(row["answer"])
        if length:
            length_n += 1
            predicted = total(WALLS, length.group(1), "Length")
            length_hits += int(predicted is not None and _close(predicted, answer))
        elif volume:
            volume_n += 1
            kinds = WALLS if volume.group(1) == "walls" else ("IfcSlab",)
            predicted = total(kinds, volume.group(2), "NetVolume")
            volume_hits += int(predicted is not None and _close(predicted, answer))
    lines.append(f"wall length, BaseQuantities.Length: {length_hits}/{length_n}")
    lines.append(f"net volume, BaseQuantities.NetVolume: {volume_hits}/{volume_n}")
    lines.append("PDF renders of this model are not answered from the IFC.")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
