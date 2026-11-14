"""Area decision order, fixed before the next file is opened.

1. Qto_SpaceBaseQuantities.NetFloorArea, or BaseQuantities.NetFloorArea.
2. Otherwise one area chosen by name and by an area unit. The names, in
   order, are NetFloorArea, NetArea, Area. A custom name is used only when
   it is the single area-unit property. Several custom names are not ranked
   by which one matches an answer. 120_Pindala is not a preferred name.
3. Otherwise the area is computed from the geometry.

Length and volume are not this order. This file is the plumbing model,
which had not been opened for a quantity decision.
"""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell

from drawing_objects import dataset_root
from export_yolo import questions_path

FILE = "bsc-clinic_clinic-plumbing.ifc"
OUT = Path(__file__).resolve().parent / "ifc_area_order.txt"
STEP1_SETS = ("Qto_SpaceBaseQuantities", "BaseQuantities")
STEP2_NAMES = ("NetFloorArea", "NetArea", "Area")


def _area_quantities(element) -> list[tuple[str, str, float]]:
    found = []
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcElementQuantity"):
            continue
        for quantity in definition.Quantities or []:
            if quantity.is_a("IfcQuantityArea"):
                found.append((definition.Name or "", quantity.Name or "", float(quantity.AreaValue)))
    return found


def _area_properties(element) -> list[tuple[str, str]]:
    found = []
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if not definition.is_a("IfcPropertySet"):
            continue
        for prop in definition.HasProperties or []:
            name = getattr(prop, "Name", "") or ""
            folded = name.casefold()
            if "area" in folded or "pindala" in folded or "flache" in folded or "fläche" in folded:
                found.append((definition.Name or "", name))
    return found


def _choose(element) -> str:
    quantities = _area_quantities(element)
    for set_name in STEP1_SETS:
        for _set_name, quantity_name, _value in quantities:
            if _set_name == set_name and quantity_name == "NetFloorArea":
                return f"1 {set_name}.NetFloorArea"
    for wanted in STEP2_NAMES:
        hits = [item for item in quantities if item[1] == wanted]
        if len(hits) == 1:
            return f"2 {hits[0][0]}.{hits[0][1]}"
    names = sorted({name for _set_name, name in _area_properties(element)})
    if len(names) == 1:
        return f"2 custom {names[0]}"
    if names:
        return "2 several custom names, left unset"
    return "3 geometry"


def main() -> None:
    questions = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if str(row["path"]).endswith(FILE):
            questions.append(f"{row['type']}  {row['question']}")
    model = ifcopenshell.open(str(dataset_root() / "ifc_models" / FILE))
    spaces = model.by_type("IfcSpace")
    chosen: dict[str, int] = {}
    for space in spaces:
        step = _choose(space)
        chosen[step] = chosen.get(step, 0) + 1
    lines = [
        "Decision order fixed before this file was opened for quantities.",
        "1 Qto_SpaceBaseQuantities.NetFloorArea or BaseQuantities.NetFloorArea.",
        "2 else NetFloorArea, NetArea, or Area, or the single area-named property.",
        "3 else geometry. Several custom names are not ranked.",
        "120_Pindala is not a preferred name.",
        "",
        f"file {FILE}",
        f"spaces {len(spaces)}",
        "questions on this file:",
    ]
    lines.extend(f"  {item}" for item in questions)
    lines.append("order result, not compared with an answer:")
    if not chosen:
        lines.append("  no space, so the area order does not apply")
    for step, count in sorted(chosen.items()):
        lines.append(f"  {count}  {step}")
    lines.append("")
    lines.append("Length and volume are a separate audit. They are not scored here.")
    lines.append("In the preview they are not on this plumbing model.")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
