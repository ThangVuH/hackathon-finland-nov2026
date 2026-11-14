"""Describe the local Swiss and IFC files. This is not a score.

PDF questions stay on the PDF reader. DXF questions would stay on the DXF
reader. The two are not compared with the preview answers here.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from drawing_objects import dataset_root
from read_dxf import read_dxf
from read_ifc import read_ifc
from read_pdf import pdf_lines

OUT = Path(__file__).resolve().parent / "file_read_report.txt"
AREA = re.compile(r"^\d+(?:[.,]\d+)?\s*m²$")
CODE = re.compile(r"^\d+\.\d+$")
UNIT = re.compile(r"^App\.\s+\S+")


def _annotation(lines: list[str]) -> tuple[int, int, int]:
    rooms = 0
    orphans = 0
    units = 0
    for index, line in enumerate(lines):
        if UNIT.match(line):
            units += 1
        if not AREA.match(line):
            continue
        if index >= 2 and CODE.match(lines[index - 1]) and lines[index - 2] and not AREA.match(lines[index - 2]):
            rooms += 1
        else:
            orphans += 1
    return rooms, orphans, units


def main() -> None:
    data = dataset_root()
    lines = [
        "File reading only. No comparison with preview answers.",
        "A PDF question is not answered from its DXF twin.",
        "An IFC PDF render is not answered from the IFC.",
        "",
    ]
    swiss = data / "swiss_dwellings"
    dxf_layers: Counter[str] = Counter()
    dxf_entities: Counter[tuple[str, str]] = Counter()
    dxf_rooms = dxf_orphans = dxf_units = 0
    pdf_rooms = pdf_orphans = pdf_units = 0
    paired = 0
    for dxf in sorted(swiss.glob("*.dxf")):
        objects = read_dxf(dxf)
        for item in objects:
            dxf_layers[item.kind] += 1
            dxf_entities[(item.kind, item.name)] += 1
        rooms, orphans, units = _annotation([item.text for item in objects if item.kind == "room_text" and item.text])
        dxf_rooms += rooms
        dxf_orphans += orphans
        dxf_units += units
        pdf = dxf.with_suffix(".pdf")
        if pdf.is_file():
            paired += 1
            rooms, orphans, units = _annotation(pdf_lines(pdf))
            pdf_rooms += rooms
            pdf_orphans += orphans
            pdf_units += units
    dxf_count = len(list(swiss.glob("*.dxf")))
    lines.append(f"swiss dxf files {dxf_count}  paired pdf {paired}")
    lines.append("dxf entities by layer")
    for layer, total in dxf_layers.most_common():
        lines.append(f"  {layer} {total}")
    lines.append("dxf entities by layer and type")
    for (layer, name), total in sorted(dxf_entities.items()):
        lines.append(f"  {layer} {name} {total}")
    lines.append(
        f"room lines parsed as name + number + area: dxf {dxf_rooms} (orphans {dxf_orphans}),"
        f" pdf {pdf_rooms} (orphans {pdf_orphans})"
    )
    lines.append(f"lines matching 'App. X': dxf {dxf_units}, pdf {pdf_units}")
    lines.append("Fixture circles and door arcs are not toilets, basins, or doors until a rule is checked.")
    lines.append("")
    for family in ("ifc_models", "ifc_bench"):
        lines.append(family)
        for path in sorted((data / family).glob("*.ifc")):
            objects, how = read_ifc(path)
            if how.startswith("type scan"):
                counts = {item.kind: int(item.text) for item in objects}
            else:
                counts = Counter(item.kind for item in objects)
            storeys = sorted({item.storey for item in objects if item.storey})
            summary = ", ".join(f"{kind} {total}" for kind, total in sorted(counts.items())) or "no products"
            lines.append(f"  {path.name} [{how}] storeys {len(storeys)}  {summary}")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
