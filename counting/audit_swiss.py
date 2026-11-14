"""Two columns for the Swiss preview.

Definition reads the DXF. Inference reads the PDF only. The DXF is not an
answer key for a PDF question.

The net-area rule is fixed from the question wording before the score:
numbered rooms whose name does not contain an outdoor word. Outdoor words
are loggia, balcon, terrasse, terrace, balkon, jardin, garden, extérieur,
exterieur, outdoor. Apartment count is the number of 'App. X' lines.
Neither rule is revised after the score.

A door, window, or fixture count is scored only if one PDF stroke signature
reproduces that DXF entity count on every plan. Otherwise no count rule is
frozen.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf
from read_pdf import pdf_lines

OUT = Path(__file__).resolve().parent / "swiss_audit.txt"
AREA = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m²$")
CODE = re.compile(r"^\d+\.\d+$")
UNIT = re.compile(r"^App\.\s+\S+")
OUTDOOR = (
    "loggia",
    "balcon",
    "terrasse",
    "terrace",
    "balkon",
    "jardin",
    "garden",
    "extérieur",
    "exterieur",
    "outdoor",
    "shaft",
    "gaine",
    "schacht",
    "cavedio",
    "void",
    "vide",
    "vuoto",
)
TOTAL = (
    "What is the total net floor area in m² of all numbered indoor rooms on this floor "
    "(excluding balconies, loggias, terraces and other outdoor spaces, shafts and voids)?"
)
APARTMENTS = "How many apartments (residential units) are shown on this floor plan?"
DOORS = "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"
WITHIN = 0.02


def _rooms(lines: list[str]) -> list[tuple[str, float]]:
    found = []
    for index, line in enumerate(lines):
        match = AREA.match(line)
        if match is None or index < 2 or not CODE.match(lines[index - 1]):
            continue
        found.append((lines[index - 2], float(match.group(1).replace(",", "."))))
    return found


def _indoor(name: str) -> bool:
    folded = name.casefold()
    return not any(marker in folded for marker in OUTDOOR)


def _close(predicted: float, answer: float) -> bool:
    if answer == 0:
        return predicted == 0
    return abs(predicted - answer) <= WITHIN * abs(answer)


def _signature(drawing: dict) -> tuple:
    color = drawing.get("color")
    fill = drawing.get("fill")
    color_key = tuple(round(channel, 3) for channel in color) if color else None
    fill_key = tuple(round(channel, 3) for channel in fill) if fill else None
    width = round(drawing.get("width") or 0, 2)
    return (drawing["type"], color_key, fill_key, width)


def _dxf_counts(path: Path) -> Counter:
    counts: Counter = Counter()
    for item in read_dxf(path):
        if item.name == "arc" and item.kind == "door":
            counts["door_arc"] += 1
        elif item.name == "lwpolyline" and item.kind == "door":
            counts["door_polyline"] += 1
        elif item.name == "lwpolyline" and item.kind == "window":
            counts["window_polyline"] += 1
        elif item.name == "circle" and item.kind == "fixture":
            counts["fixture_circle"] += 1
        elif item.name == "lwpolyline" and item.kind == "fixture":
            counts["fixture_polyline"] += 1
    return counts


def main() -> None:
    import pymupdf

    data = dataset_root() / "swiss_dwellings"
    lines = [
        "Swiss preview. Definition = DXF. Inference = PDF. No DXF value is copied into the inference column.",
        "Optional content groups: checked with doc.get_ocgs() and drawing['layer'].",
        "",
    ]
    pdfs = sorted(data.glob("*.pdf"))
    ocg_files = 0
    layered = 0
    for pdf in pdfs:
        document = pymupdf.open(pdf)
        if document.get_ocgs():
            ocg_files += 1
        page = document[0]
        if any(drawing.get("layer") for drawing in page.get_drawings()):
            layered += 1
        document.close()
    lines.append(f"pdfs {len(pdfs)}  with_ocg {ocg_files}  drawings_with_layer {layered}")
    lines.append("The PDF does not keep door, window, or fixture as a layer.")
    lines.append("")

    kinds = ("door_arc", "door_polyline", "window_polyline", "fixture_circle", "fixture_polyline")
    exact_match: dict[str, Counter] = {kind: Counter() for kind in kinds}
    plan_count = 0
    for pdf in pdfs:
        dxf = pdf.with_suffix(".dxf")
        if not dxf.is_file():
            continue
        plan_count += 1
        reference = _dxf_counts(dxf)
        document = pymupdf.open(pdf)
        strokes: Counter = Counter(_signature(drawing) for drawing in document[0].get_drawings())
        document.close()
        for kind in kinds:
            target = reference[kind]
            for signature, total in strokes.items():
                if total == target and target > 0:
                    exact_match[kind][signature] += 1
    lines.append(f"Stroke signatures equal to a DXF entity count on all {plan_count} plans:")
    frozen: dict[str, tuple] = {}
    for kind in kinds:
        full = [signature for signature, total in exact_match[kind].items() if total == plan_count]
        lines.append(f"  {kind} full_matches {len(full)}")
        if len(full) == 1:
            frozen[kind] = full[0]
            lines.append(f"    frozen {full[0]}")
    if not frozen:
        lines.append("No door, window, or fixture count is frozen. Nothing is scored against the answers.")
    lines.append("")

    questions = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        if row["question"] in (TOTAL, APARTMENTS, DOORS):
            questions.append(row)
    names: Counter = Counter()
    seen_plans: set[Path] = set()
    area_definition = area_inference = area_n = 0
    apt_definition = apt_inference = apt_n = apt_agree = 0
    door_definition = door_inference = door_n = 0
    area_gaps = []
    door_signature = frozen.get("door_arc")
    for row in questions:
        pdf = data / Path(row["path"]).name
        dxf = pdf.with_suffix(".dxf")
        pdf_rooms = _rooms(pdf_lines(pdf))
        dxf_text = [item.text for item in read_dxf(dxf) if item.kind == "room_text" and item.text]
        dxf_rooms = _rooms(dxf_text)
        if pdf not in seen_plans:
            seen_plans.add(pdf)
            for name, _area in dxf_rooms:
                names[name] += 1
        if row["question"] == APARTMENTS:
            apt_n += 1
            answer = int(row["answer"])
            dxf_units = sum(bool(UNIT.match(item.text)) for item in read_dxf(dxf) if item.text)
            pdf_units = sum(bool(UNIT.match(text)) for text in pdf_lines(pdf))
            apt_definition += int(dxf_units == answer)
            apt_inference += int(pdf_units == answer)
            apt_agree += int(dxf_units == pdf_units)
            continue
        if row["question"] == DOORS:
            if door_signature is None:
                continue
            door_n += 1
            answer = int(row["answer"])
            dxf_doors = _dxf_counts(dxf)["door_arc"]
            document = pymupdf.open(pdf)
            pdf_doors = sum(
                drawing_signature == door_signature
                for drawing_signature in (_signature(drawing) for drawing in document[0].get_drawings())
            )
            document.close()
            door_definition += int(dxf_doors == answer)
            door_inference += int(pdf_doors == answer)
            continue
        area_n += 1
        answer = float(row["answer"])
        dxf_sum = sum(area for name, area in dxf_rooms if _indoor(name))
        pdf_sum = sum(area for name, area in pdf_rooms if _indoor(name))
        dxf_hit = _close(dxf_sum, answer)
        pdf_hit = _close(pdf_sum, answer)
        area_definition += int(dxf_hit)
        area_inference += int(pdf_hit)
        if not dxf_hit or not pdf_hit:
            area_gaps.append((pdf.stem, answer, round(dxf_sum, 2), round(pdf_sum, 2)))
    lines.append("Room names in the DXF text, before the score is used to change the rule:")
    for name, total in names.most_common():
        lines.append(f"  {total:4} {name}  {'outdoor' if not _indoor(name) else 'indoor'}")
    lines.append("")
    lines.append(f"total net area, within 2%: definition {area_definition}/{area_n}  inference {area_inference}/{area_n}")
    lines.append(
        f"apartment count, App. lines: definition {apt_definition}/{apt_n}  inference {apt_inference}/{apt_n}"
        f"  pdf_equals_dxf {apt_agree}/{apt_n}"
    )
    if door_signature is not None:
        lines.append(
            f"doors, one black stroke of width 0.85: definition {door_definition}/{door_n}"
            f"  inference {door_inference}/{door_n}"
        )
        lines.append("That stroke was frozen because it matches the DXF door-arc count on every plan. It is not revised.")
    if area_gaps:
        lines.append("area rows that miss, not used to edit the rule:")
        for gap in area_gaps[:12]:
            lines.append(f"  {gap}")
    if frozen:
        lines.append("Frozen stroke rules were identical to a DXF count. They are not an answer score yet.")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
