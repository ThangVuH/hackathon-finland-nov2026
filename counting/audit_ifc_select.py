"""Revised area order, written after Esplanades had already been scored.

The name order does not select 120_Pindala, so on that file it would fall
through to geometry. There is no held-out IFC file. This score is a
development score.

Selector, fixed here and not chosen by the answer: among numeric properties
of IfcSpace, keep the one whose value is within 2% of the geometric
footprint on the most spaces. It has to cover more than half the spaces
that have a footprint. Ties keep the earlier name.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom

from audit_ifc_one import FILE, ROOM, STOREY, _close, _footprint, _storey
from drawing_objects import dataset_root
from export_yolo import questions_path

OUT = Path(__file__).resolve().parent / "ifc_select.txt"
WITHIN = 0.02


def _number(value) -> float | None:
    if value is None:
        return None
    raw = getattr(value, "wrappedValue", value)
    try:
        return float(str(raw).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def _properties(element) -> list[tuple[str, str, float]]:
    found = []
    for relation in getattr(element, "IsDefinedBy", []):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = relation.RelatingPropertyDefinition
        if definition.is_a("IfcElementQuantity"):
            for quantity in definition.Quantities or []:
                value = None
                if quantity.is_a("IfcQuantityArea"):
                    value = quantity.AreaValue
                elif quantity.is_a("IfcQuantityLength"):
                    value = quantity.LengthValue
                elif quantity.is_a("IfcQuantityVolume"):
                    value = quantity.VolumeValue
                number = _number(value)
                if number is not None:
                    found.append((definition.Name or "", quantity.Name or "", number))
            continue
        if not definition.is_a("IfcPropertySet"):
            continue
        for prop in definition.HasProperties or []:
            if not prop.is_a("IfcPropertySingleValue"):
                continue
            number = _number(getattr(prop, "NominalValue", None))
            if number is not None:
                found.append((definition.Name or "", prop.Name or "", number))
    return found


def _select(spaces: list[dict]) -> tuple[tuple[str, str], int, int] | None:
    usable = [space for space in spaces if space["footprint"] not in (None, 0)]
    if not usable:
        return None
    hits: dict[tuple[str, str], int] = defaultdict(int)
    for space in usable:
        for set_name, prop_name, value in space["properties"]:
            if abs(value - space["footprint"]) <= WITHIN * abs(space["footprint"]):
                hits[(set_name, prop_name)] += 1
    if not hits:
        return None
    ranking = sorted(hits.items(), key=lambda item: (-item[1], item[0]))
    best_key, best = ranking[0]
    second = ranking[1] if len(ranking) > 1 else None
    if best * 2 <= len(usable):
        return None
    return best_key, best, len(usable), second


def _score(path_name: str, chosen: tuple[str, str] | None, spaces: list[dict]) -> list[str]:
    by_key: dict[tuple[str, str], list[dict]] = {}
    for space in spaces:
        by_key.setdefault((space["label"], space["storey"]), []).append(space)
    room_n = room_hits = ambiguous = missing = 0
    total_n = total_hits = 0
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).endswith(path_name) or not row["question"].startswith("What"):
            continue
        room = ROOM.fullmatch(row["question"])
        storey = STOREY.fullmatch(row["question"])
        answer = float(row["answer"])
        if room:
            room_n += 1
            matches = by_key.get((room.group(1), room.group(2)), [])
            if len(matches) != 1 or chosen is None:
                ambiguous += 1
                continue
            value = next((item[2] for item in matches[0]["properties"] if item[:2] == chosen), None)
            if value is None:
                missing += 1
                continue
            room_hits += int(_close(value, answer))
        elif storey:
            total_n += 1
            if chosen is None:
                continue
            total = 0.0
            present = False
            for space in spaces:
                if space["storey"] != storey.group(1):
                    continue
                value = next((item[2] for item in space["properties"] if item[:2] == chosen), None)
                if value is None:
                    continue
                present = True
                total += value
            if present:
                total_hits += int(_close(total, answer))
    return [
        f"room questions {room_hits}/{room_n}  missing {missing}  ambiguous {ambiguous}",
        f"storey sums {total_hits}/{total_n}",
    ]


def _file(path_name: str) -> list[str]:
    model = ifcopenshell.open(str(dataset_root() / "ifc_models" / path_name))
    settings = ifcopenshell.geom.settings()
    spaces = []
    for space in model.by_type("IfcSpace"):
        spaces.append(
            {
                "label": f"{space.LongName or ''} ({space.Name or ''})",
                "storey": _storey(space),
                "footprint": _footprint(space, settings),
                "properties": _properties(space),
            }
        )
    chosen_row = _select(spaces)
    usable = sum(1 for space in spaces if space["footprint"] not in (None, 0))
    lines = [f"file {path_name}", f"spaces {len(spaces)}  with footprint {usable}"]
    chosen = None
    if chosen_row is None:
        lines.append("selector: no property matches the footprint on more than half the spaces")
    else:
        chosen, hits, total, second = chosen_row
        lines.append(f"selector: {chosen[0]} / {chosen[1]}  matches footprint {hits}/{total}")
        if second is None:
            lines.append("second property: none")
        else:
            (set_name, prop_name), second_hits = second
            lines.append(f"second: {set_name} / {prop_name}  matches footprint {second_hits}/{total}")
            if second_hits * 2 > total:
                lines.append("margin: the second property also clears half. Low confidence. Fall back to geometry.")
            else:
                lines.append("margin: only the first property clears half.")
    lines.extend(_score(path_name, chosen, spaces))
    return lines


def main() -> None:
    lines = [
        "Development scores. No IFC file was held out.",
        "The selector was written after Esplanades. It compares properties to geometry, not to answers.",
        "",
    ]
    lines.extend(_file(FILE))
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
