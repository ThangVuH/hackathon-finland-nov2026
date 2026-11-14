"""Per-question PDF area. Train buildings only.

The stroke stays the gray closed path chosen by count. No other signature
is tried.

On plans where the printed-area factor and the written scale differ by more
than 2%, both factors are compared with the DXF polygon. That comparison
does not read the answers. The winner is the factor used afterwards.

A question is then answered from the PDF alone: the centre of the room
label, the closed path that contains it, and that factor. The 15 holdout
buildings are not read.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pymupdf

from drawing_objects import dataset_root
from export_yolo import questions_path
from pdf_rooms import CODE, WITHIN, _dxf_rooms, _page_scale, _pdf_polygons, _words
from swiss_index import _smallest
from swiss_text import GLOBAL, NAMED, OUTDOOR, ROOM, _close, _train

# Chosen on the 18 disagreeing plans against DXF polygons, before the answers.
# Printed factor 0/371, written scale 371/371.
RULE = "written"


def _excluded(name: str) -> bool:
    folded = name.casefold()
    return any(marker in folded for marker in OUTDOOR)


def _label(words, polygon) -> tuple[str, str]:
    inside = [(text, point) for text, point in words if polygon.contains(point)]
    inside.sort(key=lambda item: (round(item[1].y, 1), item[1].x))
    name = ""
    code = ""
    for text, _point in inside:
        if CODE.match(text) and not code:
            code = text
        elif text and not name and "²" not in text and not text.casefold().endswith("m2"):
            name = text
    return name, code


def _plan(path_pdf: Path, path_dxf: Path):
    document = pymupdf.open(path_pdf)
    page = document[0]
    grouped = _pdf_polygons(page)
    words = _words(page)
    document.close()
    polygons = grouped.get(SIGNATURE, [])
    ratios = []
    for polygon in polygons:
        for index, (text, point) in enumerate(words):
            if not text[:1].isdigit() or not polygon.contains(point):
                continue
            follower = words[index + 1][0] if index + 1 < len(words) else ""
            if "m" not in follower.casefold() and "²" not in follower:
                continue
            try:
                printed = float(text.replace(",", "."))
            except ValueError:
                continue
            if polygon.area:
                ratios.append(printed / polygon.area)
            break
    printed = sorted(ratios)[len(ratios) // 2] if ratios else None
    written = _page_scale(words)
    dxf = _dxf_rooms(path_dxf)
    return words, polygons, printed, written, dxf


def _factor(printed: float | None, written: float | None) -> float | None:
    if printed is not None and written is not None and abs(printed - written) > WITHIN * abs(written):
        return printed if RULE == "printed" else written
    if printed is not None:
        return printed
    return written


def _rooms(words, polygons, factor: float) -> list[tuple[str, str, float]]:
    found = []
    for polygon in polygons:
        name, code = _label(words, polygon)
        if not code:
            continue
        found.append((name, code, polygon.area * factor))
    return found


def main() -> None:
    global RULE
    train = sorted(_train())
    data = dataset_root() / "swiss_dwellings"
    cached = {}
    printed_hits = written_hits = compared = disagree_plans = 0
    for stem in train:
        words, polygons, printed, written, dxf = _plan(data / f"{stem}.pdf", data / f"{stem}.dxf")
        cached[stem] = (words, polygons, printed, written)
        if printed is None or written is None or abs(printed - written) <= WITHIN * abs(written):
            continue
        disagree_plans += 1
        for polygon in polygons:
            _name, code = _label(words, polygon)
            target = dxf.get(code)
            if not code or target is None:
                continue
            compared += 1
            printed_hits += int(_close(polygon.area * printed, target))
            written_hits += int(_close(polygon.area * written, target))
    RULE = "printed" if printed_hits >= written_hits else "written"
    # Answers are read only after RULE is fixed.
    families = {
        "room area": [0, 0],
        "labelled total": [0, 0],
        "global indoor total": [0, 0],
    }
    answers: dict[str, list[float]] = {name: [] for name in families}
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        if stem not in cached:
            continue
        question = row["question"]
        room = ROOM.match(question)
        named = NAMED.match(question)
        kind = "room area" if room else "labelled total" if named else "global indoor total" if question == GLOBAL else ""
        if not kind:
            continue
        words, polygons, printed, written = cached[stem]
        factor = _factor(printed, written)
        predicted = None
        if factor is not None:
            rooms = _rooms(words, polygons, factor)
            if room:
                code = room.group(1)
                point = next((point for text, point in words if text == code), None)
                chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point) if point is not None else None
                predicted = None if chosen is None else chosen[1] * factor
            elif named:
                label = named.group(1)
                seen: set[int] = set()
                total = 0.0
                for text, point in words:
                    if text != label:
                        continue
                    chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point)
                    if chosen is None or id(chosen[0]) in seen:
                        continue
                    seen.add(id(chosen[0]))
                    total += chosen[1] * factor
                predicted = total
            else:
                seen = set()
                total = 0.0
                for text, point in words:
                    if not CODE.match(text):
                        continue
                    chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point)
                    if chosen is None or id(chosen[0]) in seen:
                        continue
                    name, _code = _label(words, chosen[0])
                    if _excluded(name):
                        continue
                    seen.add(id(chosen[0]))
                    total += chosen[1] * factor
                predicted = total
        answer = float(row["answer"])
        families[kind][1] += 1
        families[kind][0] += int(predicted is not None and _close(predicted, answer))
        answers[kind].append(answer)
    lines = [
        "Train buildings only. Holdout answers were not read.",
        f"plans where the two factors differ: {disagree_plans}",
        f"on those plans, against the DXF polygon, before any answer was read:",
        f"  printed-area factor {printed_hits}/{compared}",
        f"  written scale {written_hits}/{compared}",
        f"rule: when they differ, use the {RULE} factor.",
        "",
        f"{'template':22} {'n':>5}  {'inference':>12}  baseline",
    ]
    for name, (hits, total) in families.items():
        best = max(Counter(answers[name]).values()) if answers[name] else 0
        lines.append(f"{name:22} {total:5}  {f'{hits}/{total}':>12}  {best}/{total}")
    text = "\n".join(lines) + "\n"
    out = Path(__file__).resolve().parent / "pdf_questions.txt"
    out.write_text(text, encoding="utf-8")
    print(text, end="")


# The count search already selected this signature. It is not chosen again.
SIGNATURE = ("fs", (0.541, 0.541, 0.541), 0.37)


if __name__ == "__main__":
    main()
