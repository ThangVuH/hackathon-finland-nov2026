"""Text templates on the Swiss training buildings.

Each full question is its own definition. The two totals that share the
words "net area" are not one rule. The 15 holdout buildings are not read.

Definition reads DXF room text. Inference reads PDF text. A room is a code
line, the name on the line before it, and an area line after it when present.
A label count is the number of those names. A room area is the area after
that code. A labelled total sums areas of that name. An apartment area sums
areas from its unit line (App. / Whg.) until the next unit line.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf
from read_pdf import pdf_lines

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "swiss_text.txt"
CODE = re.compile(r"^[A-Za-z]*\d+\.\d+$")
DIGIT_CODE = re.compile(r"^\d+\.\d+$")
AREA = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m²$")
UNIT = re.compile(r"^(?:App\.|Whg\.|Wohnung|Appartamento)\s+(\S+)")
def normalize_apostrophes(text: str) -> str:
    """Curly apostrophes are the same mark as the straight one. Not a new rule."""
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201a", "'")


LABEL = re.compile(r"^How many rooms labelled '(.*)' are there on this floor\?$")
ROOM = re.compile(r"^What is the net floor area of room ([A-Za-z]*\d+\.\d+) \('(.*)'\) in m²\?$")
NAMED = re.compile(r"^What is the total net area in m² of all rooms labelled '(.*)' on this floor\?$")
APT = re.compile(
    r"^What is the net floor area of apartment ([A-Z]+) in m², summing all its rooms except "
    r"balconies, loggias, terraces and other outdoor spaces\?$"
)
GLOBAL = (
    "What is the total net floor area in m² of all numbered indoor rooms on this floor "
    "(excluding balconies, loggias, terraces and other outdoor spaces, shafts and voids)?"
)
WITHIN = 0.02
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


def _train() -> set[str]:
    rows = csv.DictReader((ROOT / "swiss_split.csv").open(encoding="utf-8"))
    return {row["stem"] for row in rows if row["split"] == "train"}


def _rooms(lines: list[str]) -> tuple[list[tuple[str, str, float | None]], list[tuple[str, list[tuple[str, float]]]]]:
    rooms: list[tuple[str, str, float | None]] = []
    units: list[tuple[str, list[tuple[str, float]]]] = []
    current = ""
    bucket: list[tuple[str, float]] = []
    index = 0
    while index < len(lines):
        unit = UNIT.match(lines[index])
        if unit:
            if current:
                units.append((current, bucket))
            current = unit.group(1).rstrip(".")
            bucket = []
            index += 1
            continue
        name = ""
        if index + 1 < len(lines) and CODE.match(lines[index + 1]) and not CODE.match(lines[index]):
            name = lines[index]
            index += 1
        if index < len(lines) and CODE.match(lines[index]):
            code = lines[index]
            index += 1
            area = None
            match = AREA.match(lines[index]) if index < len(lines) else None
            if match:
                area = float(match.group(1).replace(",", "."))
                index += 1
            rooms.append((name, code, area))
            if current and area is not None and not any(word in name.casefold() for word in OUTDOOR):
                bucket.append((name, area))
            continue
        index += 1
    if current:
        units.append((current, bucket))
    return rooms, units


def _lines(kind: str, path: Path) -> list[str]:
    if kind == "dxf":
        return [item.text for item in read_dxf(path) if item.kind == "room_text" and item.text]
    return pdf_lines(path)


def _close(predicted: float, answer: float) -> bool:
    if answer == 0:
        return predicted == 0
    return abs(predicted - answer) <= WITHIN * abs(answer)


def _rate(hits: int, total: int) -> str:
    return f"{hits}/{total}"


def _indoor_sum(lines: list[str]) -> float:
    """The already frozen total: a printed area whose previous line is a code."""
    total = 0.0
    for index, line in enumerate(lines):
        match = AREA.match(line)
        if match is None or index < 2 or not DIGIT_CODE.match(lines[index - 1]):
            continue
        name = lines[index - 2]
        if any(marker in name.casefold() for marker in OUTDOOR):
            continue
        total += float(match.group(1).replace(",", "."))
    return total


def main() -> None:
    train = _train()
    data = dataset_root() / "swiss_dwellings"
    families = {
        "label count": [0, 0, 0],
        "room area": [0, 0, 0],
        "labelled total": [0, 0, 0],
        "apartment area": [0, 0, 0],
        "global indoor total": [0, 0, 0],
    }
    answers: dict[str, list[float]] = defaultdict(list)
    by_question: dict[str, list[tuple[bool, bool, float]]] = defaultdict(list)
    cache: dict[str, tuple] = {}
    pending: list[tuple[str, str, float]] = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        question = normalize_apostrophes(row["question"])
        if stem not in train:
            continue
        if (
            LABEL.match(question) is None
            and ROOM.match(question) is None
            and NAMED.match(question) is None
            and APT.match(question) is None
            and question != GLOBAL
        ):
            continue
        pending.append((stem, question, float(row["answer"])))
    for stem in {item[0] for item in pending}:
        dxf_text = _lines("dxf", data / f"{stem}.dxf")
        pdf_text = _lines("pdf", data / f"{stem}.pdf")
        cache[stem] = (_rooms(dxf_text), _rooms(pdf_text), dxf_text, pdf_text)
    for stem, question, answer in pending:
        (dxf_rooms, dxf_units), (pdf_rooms, pdf_units), dxf_lines, pdf_lines_here = cache[stem]
        kind = "global indoor total"
        dxf_hit = pdf_hit = False
        if LABEL.match(question):
            kind = "label count"
            label = LABEL.match(question).group(1)
            dxf_hit = sum(name == label for name, _code, _area in dxf_rooms) == answer
            pdf_hit = sum(name == label for name, _code, _area in pdf_rooms) == answer
        elif ROOM.match(question):
            kind = "room area"
            code = ROOM.match(question).group(1)
            dxf_value = next((area for _name, found, area in dxf_rooms if found == code and area is not None), None)
            pdf_value = next((area for _name, found, area in pdf_rooms if found == code and area is not None), None)
            dxf_hit = dxf_value is not None and _close(dxf_value, answer)
            pdf_hit = pdf_value is not None and _close(pdf_value, answer)
        elif NAMED.match(question):
            kind = "labelled total"
            label = NAMED.match(question).group(1)
            dxf_value = sum(area for name, _code, area in dxf_rooms if name == label and area is not None)
            pdf_value = sum(area for name, _code, area in pdf_rooms if name == label and area is not None)
            dxf_hit = _close(dxf_value, answer)
            pdf_hit = _close(pdf_value, answer)
        elif APT.match(question):
            kind = "apartment area"
            letter = APT.match(question).group(1)
            dxf_value = next((sum(area for _name, area in bucket) for mark, bucket in dxf_units if mark == letter), None)
            pdf_value = next((sum(area for _name, area in bucket) for mark, bucket in pdf_units if mark == letter), None)
            dxf_hit = dxf_value is not None and _close(dxf_value, answer)
            pdf_hit = pdf_value is not None and _close(pdf_value, answer)
        else:
            dxf_hit = _close(_indoor_sum(dxf_lines), answer)
            pdf_hit = _close(_indoor_sum(pdf_lines_here), answer)
        families[kind][0] += int(dxf_hit)
        families[kind][1] += int(pdf_hit)
        families[kind][2] += 1
        answers[kind].append(answer)
        by_question[question].append((dxf_hit, pdf_hit, answer))
    lines = [
        "Train buildings only. Holdout answers were not read.",
        "Definition = DXF text. Inference = PDF text. Baseline = most frequent training answer.",
        "",
        f"{'template':22} {'n':>5}  {'definition':>12}  {'inference':>12}  baseline",
    ]
    for name, (dxf_hits, pdf_hits, total) in families.items():
        values = answers[name]
        if not values:
            continue
        counts = Counter(values)
        best = max(counts.values())
        lines.append(
            f"{name:22} {total:5}  {_rate(dxf_hits, total):>12}  {_rate(pdf_hits, total):>12}  {_rate(best, total)}"
        )
    lines.append("")
    lines.append("Same sentence, asked more than once. Room-area sentences name one room, so they stay in the family row.")
    ranked = sorted(by_question.items(), key=lambda item: -len(item[1]))
    for question, rows in ranked:
        if len(rows) < 2:
            continue
        values = [answer for _dxf, _pdf, answer in rows]
        best = max(Counter(values).values())
        dxf_hits = sum(dxf for dxf, _pdf, _answer in rows)
        pdf_hits = sum(pdf for _dxf, pdf, _answer in rows)
        lines.append(
            f"  n={len(rows):3}  definition {_rate(dxf_hits, len(rows))}  "
            f"inference {_rate(pdf_hits, len(rows))}  baseline {_rate(best, len(rows))}"
        )
        lines.append(f"    {question}")
    lines.append("")
    lines.append("The global indoor total uses the already frozen text sum. It is not the labelled-room sum.")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
