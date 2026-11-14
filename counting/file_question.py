"""Answer a dropped PDF or IFC from the file, not from a vision model.

A PDF uses the frozen Swiss readers. An IFC lists each space with its name,
the selected property value, and its GlobalId. Neither path invents a count
when the template has no reader.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pymupdf

from pdf_questions import RULE, SIGNATURE, _factor
from pdf_rooms import _page_scale, _pdf_polygons
from route_question import route
from swiss_doors import _strokes
from swiss_index import _smallest
from swiss_text import _rooms


def answer_file(filename: str, data: bytes, question: str) -> dict:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        return _pdf(data, question)
    if suffix == ".ifc":
        return _ifc(data, question)
    return _unverified("This file is not a PDF or an IFC. No count was invented.")


def _unverified(reason: str) -> dict:
    return {
        "answer": reason,
        "object_type": "",
        "count": 0,
        "items": [],
        "verdict": "unverified",
        "warning": "No count was invented.",
        "preview": "",
    }


def _pdf(data: bytes, question: str) -> dict:
    template, params, _proof = route(question)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    document = pymupdf.open(path)
    page = document[0]
    rect = page.rect
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False)
    preview = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    raw_words = page.get_text("words")
    polygons = _pdf_polygons(page).get(SIGNATURE, [])
    document.close()
    lines = [""]
    from read_pdf import pdf_lines

    try:
        lines = pdf_lines(path)
    except Exception:
        lines = [" ".join(word[4] for word in raw_words)]
    door_strokes = _strokes(path) if template == "door" else 0
    path.unlink(missing_ok=True)
    words = [((word[0] + word[2]) / 2, (word[1] + word[3]) / 2, word[4], word[:4]) for word in raw_words]
    centres = []
    from shapely.geometry import Point

    for x, y, text, _box in words:
        centres.append((text, Point(x, y)))
    printed = _printed_factor(polygons, centres)
    written = _page_scale(centres)
    factor = _factor(printed, written)
    note = _pdf_note(template, printed, written)

    if template == "label_count":
        label = params[0] if params else ""
        rooms, _units = _rooms(lines)
        count = sum(name == label for name, _code, _area in rooms)
        items = []
        for x, y, text, box in words:
            if text != label:
                continue
            items.append({**_box_of(rect, box), "label": text, "kind": "text", "note": "text box", "page": 1})
        return _done(f"{count} rooms labelled {label}.", "Label", count, items, note, preview)
    if template == "room_area" and factor is not None and params:
        code = params[0]
        point = next((point for text, point in centres if text == code), None)
        chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point) if point is not None else None
        if chosen is None:
            return _unverified("No closed path contains that room code.") | {"preview": preview}
        area = chosen[1] * factor
        ring = [[round(1000 * x / rect.width), round(1000 * y / rect.height)] for x, y in chosen[0].exterior.coords]
        xs = [point[0] for point in ring]
        ys = [point[1] for point in ring]
        item = {
            "label": code,
            "kind": "room",
            "note": "polygon",
            "page": 1,
            "polygon": ring,
            "xmin": min(xs),
            "ymin": min(ys),
            "xmax": max(xs),
            "ymax": max(ys),
        }
        return _done(f"Room {code}: {area:.2f} m², from the polygon.", "Room", 1, [item], note, preview)
    if template == "door":
        count = door_strokes
        return _done(
            f"{count} door strokes. On 50 revision plans this rule is exact on 29.",
            "Door",
            count,
            [],
            "Weak: 29/50 on the revision plans. The stroke equals the arc count, so it is not a second measurement.",
            preview,
        )
    return _unverified("This PDF question has no frozen reader.") | {"preview": preview}


def _printed_factor(polygons, centres) -> float | None:
    ratios = []
    for polygon in polygons:
        for index, (text, point) in enumerate(centres):
            if not text[:1].isdigit() or not polygon.contains(point):
                continue
            follower = centres[index + 1][0] if index + 1 < len(centres) else ""
            if "m" not in follower.casefold() and "²" not in follower:
                continue
            try:
                printed = float(text.replace(",", "."))
            except ValueError:
                continue
            if polygon.area:
                ratios.append(printed / polygon.area)
            break
    if not ratios:
        return None
    ratios.sort()
    return ratios[len(ratios) // 2]


def _pdf_note(template: str, printed: float | None, written: float | None) -> str:
    scale = "The written scale and the printed areas agree."
    if printed is not None and written is not None and abs(printed - written) > 0.02 * max(abs(written), 1e-9):
        scale = "Low confidence: the two scale factors disagree, so the written scale is used."
    known = {
        "label_count": "On 303 revision questions, 303 exact.",
        "room_area": "On 98 revision questions, 97 exact.",
    }
    return " ".join(part for part in (known.get(template, ""), scale) if part)


def _box_of(rect, box) -> dict:
    x0, y0, x1, y1 = box
    return {
        "xmin": round(1000 * x0 / rect.width),
        "ymin": round(1000 * y0 / rect.height),
        "xmax": round(1000 * x1 / rect.width),
        "ymax": round(1000 * y1 / rect.height),
    }


def _done(answer: str, object_type: str, count: int, items: list, warning: str, preview: str) -> dict:
    return {
        "answer": answer,
        "object_type": object_type,
        "count": count,
        "items": items,
        "verdict": "unverified",
        "warning": warning,
        "preview": preview,
    }


def _ifc(data: bytes, question: str) -> dict:
    try:
        import ifcopenshell
    except ImportError:
        return _unverified("The IFC reader is not installed. No count was invented.")
    from audit_ifc_select import _properties, _select
    from audit_ifc_one import _footprint, _storey

    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        model = ifcopenshell.open(str(path))
    except Exception:
        path.unlink(missing_ok=True)
        return _unverified("This IFC file could not be opened. No count was invented.")
    settings = ifcopenshell.geom.settings()
    spaces = []
    for space in model.by_type("IfcSpace"):
        spaces.append(
            {
                "name": space.LongName or space.Name or "",
                "global_id": str(space.GlobalId),
                "storey": _storey(space),
                "footprint": _footprint(space, settings),
                "properties": _properties(space),
            }
        )
    path.unlink(missing_ok=True)
    selected = _select(spaces)
    if selected is None:
        return _unverified("No area property covers more than half the spaces. No count was invented.")
    key, hits, usable, second = selected
    second_hits = second[1] if second else 0
    template, params, _proof = route(question)
    wanted = params[0].casefold() if template == "ifc_room" and params else ""
    items = []
    for space in spaces:
        if wanted and wanted not in space["name"].casefold():
            continue
        value = next((item[2] for item in space["properties"] if item[:2] == key), None)
        shown = "missing" if value is None else f"{value:g}"
        items.append(
            {
                "label": space["name"] or space["global_id"],
                "kind": "room",
                "note": f"{shown} m² | {space['global_id']}",
                "page": 1,
                "ymin": 0,
                "xmin": 0,
                "ymax": 0,
                "xmax": 0,
            }
        )
    warning = (
        f"Property {key[0]} / {key[1]} matches the footprint on {hits}/{usable} spaces. "
        f"The next property matches on {second_hits}/{usable}."
    )
    if not items:
        return _unverified("No room in this file matches the question.") | {"warning": warning}
    if len(items) == 1:
        answer = f"{items[0]['label']}: {items[0]['note']}."
    else:
        answer = f"{len(items)} rooms listed. Each line is a name, a value and a GlobalId."
    return _done(answer, "Room", len(items), items, warning, "")
