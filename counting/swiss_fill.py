"""Area rule frozen after the polygon check, then scored on the training buildings.

The check, already measured: on the 30 rooms with a printed area, the smallest
ROOM_OUTLINE around the label matches that printed area 30/30. No unused area
text sits near a room that lacks a printed area.

Rule: printed area if the line is there, otherwise the smallest outline that
contains the label. Inclusion is unchanged.

- one room: that room
- one label: rooms with that name
- an apartment: rooms from its unit line to the next, outdoor names removed
- all indoor rooms: numbered rooms whose name is not outdoor

Definition is the DXF. The PDF is not given these polygons. The 15 holdout
buildings are not read.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import questions_path
from swiss_index import _rings, _smallest, _texts
from swiss_text import APT, GLOBAL, NAMED, OUTDOOR, ROOM, UNIT, _close, _train
from swiss_index import _paired

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "swiss_fill.txt"


def _excluded(name: str) -> bool:
    folded = name.casefold()
    return any(marker in folded for marker in OUTDOOR)


def _value(printed: float | None, point, rings) -> float | None:
    if printed is not None:
        return printed
    if point is None:
        return None
    found = _smallest(rings, point)
    return None if found is None else found[1]


def main() -> None:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    pending = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        question = row["question"]
        if stem not in train:
            continue
        if ROOM.match(question) or NAMED.match(question) or APT.match(question) or question == GLOBAL:
            pending.append((stem, question, float(row["answer"])))
    cache = {}
    families = {
        "room area": [0, 0],
        "labelled total": [0, 0],
        "apartment area": [0, 0],
        "global indoor total": [0, 0],
    }
    answers: dict[str, list[float]] = defaultdict(list)
    filled = 0
    unfilled = 0
    for stem, question, answer in pending:
        if stem not in cache:
            texts = _texts(data / f"{stem}.dxf")
            paired, missing, _used = _paired(texts)
            rings = _rings(data / f"{stem}.dxf")
            rooms = []
            current = ""
            groups: list[tuple[str, list[float]]] = []
            bucket: list[float] = []
            sequence = []
            for name, name_at, code, code_at, printed, _area_at in paired:
                value = _value(printed, name_at or code_at, rings)
                sequence.append((name, code, value, False))
            for name, name_at, code, code_at in missing:
                value = _value(None, name_at or code_at, rings)
                if value is None:
                    unfilled += 1
                else:
                    filled += 1
                sequence.append((name, code, value, True))
            # Text order is the file order already walked by _paired, but paired and
            # missing were split. Rebuild from the texts so apartment spans stay in order.
            ordered = []
            index = 0
            items = texts
            from swiss_text import AREA, CODE

            while index < len(items):
                text = items[index][0]
                unit = UNIT.match(text)
                if unit:
                    if current:
                        groups.append((current, bucket))
                    current = unit.group(1).rstrip(".")
                    bucket = []
                    index += 1
                    continue
                name = ""
                name_at = None
                if (
                    index + 1 < len(items)
                    and CODE.match(items[index + 1][0])
                    and not CODE.match(text)
                    and AREA.match(text) is None
                    and UNIT.match(text) is None
                ):
                    name, name_at = items[index]
                    index += 1
                if index < len(items) and CODE.match(items[index][0]):
                    code, code_at = items[index]
                    index += 1
                    printed = None
                    if index < len(items) and AREA.match(items[index][0]):
                        printed = float(AREA.match(items[index][0]).group(1).replace(",", "."))
                        index += 1
                    value = _value(printed, name_at or code_at, rings)
                    ordered.append((name, code, value))
                    if current and value is not None and not _excluded(name):
                        bucket.append(value)
                    continue
                index += 1
            if current:
                groups.append((current, bucket))
            cache[stem] = (ordered, groups)
        ordered, groups = cache[stem]
        kind = "global indoor total"
        predicted = None
        if ROOM.match(question):
            kind = "room area"
            code = ROOM.match(question).group(1)
            predicted = next((value for _name, found, value in ordered if found == code), None)
        elif NAMED.match(question):
            kind = "labelled total"
            label = NAMED.match(question).group(1)
            predicted = sum(value for name, _code, value in ordered if name == label and value is not None)
        elif APT.match(question):
            kind = "apartment area"
            letter = APT.match(question).group(1)
            predicted = next((sum(bucket) for mark, bucket in groups if mark == letter), None)
        else:
            predicted = sum(value for name, _code, value in ordered if value is not None and not _excluded(name))
        families[kind][1] += 1
        families[kind][0] += int(predicted is not None and _close(predicted, answer))
        answers[kind].append(answer)
    lines = [
        "Train buildings only. Rule frozen after 30/30 polygon ratios of 1.",
        "Definition only. PDF inference is not this column.",
        f"rooms without a printed area that received a polygon: {filled}  still without an area: {unfilled}",
        "",
        f"{'template':22} {'n':>5}  {'definition':>12}  baseline",
    ]
    for name, (hits, total) in families.items():
        values = answers[name]
        best = max(Counter(values).values()) if values else 0
        lines.append(f"{name:22} {total:5}  {f'{hits}/{total}':>12}  {best}/{total}")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
