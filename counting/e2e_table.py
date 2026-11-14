"""Question, router, solver, answer. Train buildings and CubiCasa train/val.

The 15 Swiss holdout plans and the 27 CubiCasa test plans are not read.
Inference is empty where no solver exists. Kitchen is not in a total.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import load_splits, questions_path
from label_rules import boxes_in, count_floors, svg_path
from pdf_questions import _factor, _label, _plan
from read_pdf import pdf_lines
from route_question import route
from swiss_doors import _strokes
from swiss_index import _smallest
from swiss_text import GLOBAL, LABEL, NAMED, ROOM, UNIT, _close, _rooms as _text_rooms, _train

CANON = {
    "label_count": LABEL,
    "room_area": ROOM,
    "labelled_area": NAMED,
    "indoor_total": None,
    "apartment_count": None,
    "door": None,
}
DOOR_Q = "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"
COUNT_Q = "How many apartments (residential units) are shown on this floor plan?"

ROOT = Path(__file__).resolve().parent
CLASS = {
    "window": "window",
    "door": "door",
    "sink": "sink",
    "toilet_bowl": "toilet",
    "shower": "shower",
    "kitchen": "kitchen",
    "sauna": "sauna_stove",
    "floor": "floor",
}


def _mode(values: list[float]) -> float:
    counts = Counter(values)
    best = max(counts.values())
    return min(value for value, count in counts.items() if count == best)


def _swiss() -> list[str]:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    cache = {}
    buckets: dict[str, list[tuple[bool, float, str, bool]]] = defaultdict(list)
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        if stem not in train or not row["question"][:1].isascii():
            continue
        if not row["question"].startswith(("How", "What")):
            continue
        template, params, _proof = route(row["question"])
        if stem not in cache:
            words, polygons, printed, written, _dxf = _plan(data / f"{stem}.pdf", data / f"{stem}.dxf")
            lines = pdf_lines(data / f"{stem}.pdf")
            rooms, _units = _text_rooms(lines)
            cache[stem] = (words, polygons, _factor(printed, written), rooms, _strokes(data / f"{stem}.pdf"), lines)
        words, polygons, factor, rooms, strokes, lines = cache[stem]
        answer = float(row["answer"])
        predicted = None
        if template == "label_count":
            label = params[0] if params else ""
            predicted = sum(name == label for name, _code, _area in rooms)
        elif template == "room_area" and factor is not None and params:
            code = params[0]
            point = next((point for text, point in words if text == code), None)
            chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point) if point is not None else None
            predicted = None if chosen is None else chosen[1] * factor
        elif template == "labelled_area" and factor is not None and params:
            label = params[0]
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
        elif template == "indoor_total" and factor is not None:
            from pdf_rooms import CODE
            from swiss_text import OUTDOOR

            seen = set()
            total = 0.0
            for text, point in words:
                if not CODE.match(text):
                    continue
                chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point)
                if chosen is None or id(chosen[0]) in seen:
                    continue
                name, _code = _label(words, chosen[0])
                if any(marker in name.casefold() for marker in OUTDOOR):
                    continue
                seen.add(id(chosen[0]))
                total += chosen[1] * factor
            predicted = total
        elif template == "apartment_count":
            predicted = sum(bool(UNIT.match(line)) for line in lines)
        elif template == "door":
            predicted = strokes
        canon = _canonical(template, row["question"])
        if template == "apartment_area" or template not in ("label_count", "room_area", "labelled_area", "indoor_total", "apartment_count", "door"):
            buckets[template].append((False, answer, row["question"], canon))
            continue
        ok = predicted is not None and (_close(predicted, answer) if template not in ("label_count", "apartment_count", "door") else predicted == answer)
        buckets[template].append((ok, answer, row["question"], canon))
    definition = {
        "label_count": "303/303",
        "room_area": "98/98",
        "labelled_area": "50/50",
        "indoor_total": "47/50",
        "apartment_area": "10/86",
        "door": "29/50",
        "apartment_count": "text",
    }
    lines_out = [
        "Swiss train, English questions. Router then solver. Holdout not read.",
        "Definition is the DXF rule already frozen. Inference reads the PDF.",
        "Baseline: most frequent answer of a sentence that repeats, otherwise the most frequent answer of the template. A tie keeps the smaller.",
        "",
    ]
    lines_out.append(f"{'template':22} {'n':>5}  {'definition':>12}  {'inference':>12}  baseline")
    extras: list[str] = []
    for template, rows in sorted(buckets.items()):
        canon_rows = [row for row in rows if row[3]]
        other = [row for row in rows if not row[3]]
        scored = canon_rows or rows
        total = len(scored)
        if template == "apartment_area" or template not in definition:
            shown = "no solver"
        else:
            hits = sum(ok for ok, _a, _q, _c in scored)
            shown = f"{hits}/{total}"
        base_hits = _baseline(scored)
        ceiling = definition.get(template, "—")
        lines_out.append(f"{template:22} {total:5}  {ceiling:>12}  {shown:>12}  {base_hits}/{total}")
        if canon_rows and other:
            for _ok, _answer, question, _canon in other:
                extras.append(f"{template:16} {question}")
    if extras:
        lines_out.append("")
        lines_out.append("Routed here, but not the frozen sentence. Counted in the table above only when no frozen sentence exists.")
        lines_out.extend(sorted(set(extras)))
    return lines_out


def _canonical(template: str, question: str) -> bool:
    if template == "indoor_total":
        return question == GLOBAL
    if template == "door":
        return question == DOOR_Q
    if template == "apartment_count":
        return question == COUNT_Q
    pattern = CANON.get(template)
    return bool(pattern and pattern.match(question))


def _baseline(rows: list[tuple[bool, float, str, bool]]) -> int:
    grouped: dict[str, list[float]] = defaultdict(list)
    for _ok, answer, question, _canon in rows:
        grouped[question].append(answer)
    flat = [answer for answers in grouped.values() for answer in answers]
    if not flat:
        return 0
    template_mode = _mode(flat)
    hits = 0
    for answers in grouped.values():
        chosen = _mode(answers) if len(answers) >= 2 else template_mode
        hits += sum(answer == chosen for answer in answers)
    return hits


def _cubi() -> list[str]:
    splits = load_splits()
    kept = {key for key, split in splits.items() if split in ("train", "val")}
    train_keys = {key for key, split in splits.items() if split == "train"}
    counts: dict[tuple[str, str], Counter] = {}
    floors: dict[tuple[str, str], int] = {}
    buckets: dict[str, list[tuple[str, bool, float]]] = defaultdict(list)
    train_values: dict[str, list[float]] = defaultdict(list)
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/cubicasa5k/"):
            continue
        if not row["question"].startswith(("How", "What")):
            continue
        stem = Path(row["path"]).stem
        style, sample = stem.rsplit("-", 1)
        key = (style, sample)
        if key not in kept:
            continue
        template = route(row["question"])[0]
        if template not in CLASS:
            continue
        answer = float(row["answer"])
        if key in train_keys:
            train_values[template].append(answer)
        if key not in counts:
            boxes = boxes_in(svg_path(style, sample))
            counts[key] = Counter(kind for kind, *_rest in boxes)
            floors[key] = count_floors(svg_path(style, sample))
        kind = CLASS[template]
        predicted = floors[key] if kind == "floor" else counts[key][kind]
        buckets[template].append(("train" if key in train_keys else "val", predicted == answer, answer))
    lines = ["CubiCasa train and val. The 27 test plans were not read.", "Definition is the SVG. Inference is the single read after the epoch is frozen.", ""]
    lines.append(f"{'template':22} {'n':>5}  {'definition':>12}  {'inference':>12}  baseline")
    for template, rows in sorted(buckets.items()):
        hits = sum(ok for _split, ok, _answer in rows)
        total = len(rows)
        mode = _mode(train_values[template]) if train_values[template] else None
        base = sum(answer == mode for _split, _ok, answer in rows) if mode is not None else 0
        lines.append(f"{template:22} {total:5}  {f'{hits}/{total}':>12}  {'not read':>12}  {base}/{total}")
    return lines


def main() -> None:
    text = "\n".join(_swiss() + ["", ""] + _cubi()) + "\n"
    (ROOT / "e2e_table.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
