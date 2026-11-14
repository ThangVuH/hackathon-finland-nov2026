"""One Swiss reading. The 50 are the rehearsal. The 15 are consumed only if that rehearsal passes.

Predictions are written before any answer is read. A crash writes a note and
does not consume the holdout reading. The consumed mark is written only after
the holdout scores have been saved.

    py -3.13 swiss_holdout_once.py --revision
    py -3.13 swiss_holdout_once.py --holdout
"""

from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import questions_path
from pdf_questions import _factor, _label, _plan
from read_pdf import pdf_lines
from route_question import route
from swiss_doors import _strokes
from swiss_index import _smallest
from swiss_text import GLOBAL, LABEL, NAMED, ROOM, UNIT, _close, _rooms as text_rooms

ROOT = Path(__file__).resolve().parent
DONE = ROOT / "swiss_holdout_done.txt"
LOCK = ROOT / "swiss_holdout_lock.txt"
CHECK = ROOT / "swiss_revision_check.txt"
PREDICTIONS = ROOT / "predictions"
ADDED = {
    "How many rooms labelled 'Cage d'escalier' are there on this floor?",
    "What is the net floor area of room U1.09 ('Küche') in m²?",
    "What is the net floor area of room U1.15 ('Korridor') in m²?",
}
PREVIOUS = {
    "label_count": (303, 303),
    "room_area": (97, 98),
    "labelled_area": (42, 50),
    "indoor_total": (37, 50),
    "apartment_count": (50, 50),
    "door": (29, 50),
}


def _stems(split: str) -> set[str]:
    rows = csv.DictReader((ROOT / "swiss_split.csv").open(encoding="utf-8"))
    found = {row["stem"] for row in rows if row["split"] == split}
    expected = 50 if split == "train" else 15
    if len(found) != expected:
        raise SystemExit(f"expected {expected} {split} buildings, found {len(found)}")
    return found


def _canonical(template: str, question: str) -> bool:
    if template == "label_count":
        return LABEL.match(question) is not None
    if template == "room_area":
        return ROOM.match(question) is not None
    if template == "labelled_area":
        return NAMED.match(question) is not None
    if template == "indoor_total":
        return question == GLOBAL
    if template == "door":
        return question.startswith("How many doors (interior")
    if template == "apartment_count":
        return question.startswith("How many apartments")
    return False


def _predict(stems: set[str]) -> list[dict]:
    data = dataset_root() / "swiss_dwellings"
    cache = {}
    records = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        question = row["question"]
        if stem not in stems or not question.startswith(("How", "What")):
            continue
        template, params, _proof = route(question)
        if not _canonical(template, question):
            continue
        if stem not in cache:
            words, polygons, printed, written, _dxf = _plan(data / f"{stem}.pdf", data / f"{stem}.dxf")
            lines = pdf_lines(data / f"{stem}.pdf")
            rooms, _units = text_rooms(lines)
            cache[stem] = (words, polygons, _factor(printed, written), rooms, _strokes(data / f"{stem}.pdf"), lines)
        words, polygons, factor, rooms, strokes, lines = cache[stem]
        predicted = None
        if template == "label_count":
            predicted = sum(name == params[0] for name, _code, _area in rooms)
        elif template == "room_area" and factor is not None and params:
            point = next((point for text, point in words if text == params[0]), None)
            chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point) if point else None
            predicted = None if chosen is None else chosen[1] * factor
        elif template == "labelled_area" and factor is not None and params:
            seen: set[int] = set()
            total = 0.0
            for text, point in words:
                if text != params[0]:
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
            predicted = sum(bool(UNIT.match(item)) for item in lines)
        elif template == "door":
            predicted = strokes
        records.append(
            {
                "stem": stem,
                "question": question,
                "template": template,
                "predicted": predicted,
            }
        )
    return records


def _write_predictions(records: list[dict], split: str) -> Path:
    PREDICTIONS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = PREDICTIONS / f"swiss-{split}-{stamp}.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def _answers(stems: set[str]) -> dict[tuple[str, str], float]:
    found = {}
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        stem = Path(str(row["path"])).stem
        if stem in stems:
            found[(stem, row["question"])] = float(row["answer"])
    return found


def _hit(template: str, predicted, answer: float) -> bool:
    if predicted is None:
        return False
    if template in ("label_count", "apartment_count", "door"):
        return predicted == answer
    return _close(predicted, answer)


def _summarize(records: list[dict], answers: dict[tuple[str, str], float]) -> tuple[str, bool]:
    groups: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    added = []
    for record in records:
        question = record["question"]
        template = record["template"]
        answer = answers[(record["stem"], question)]
        hit = _hit(template, record["predicted"], answer)
        fresh = question in ADDED
        groups[template].append((hit, fresh))
        if fresh:
            added.append((template, hit, question))
    lines = []
    ok = True
    fresh_questions = {question for _template, _hit, question in added}
    if fresh_questions != ADDED:
        ok = False
        lines.append("FAIL new sentences are not exactly the three pattern fixes")
        for question in sorted(fresh_questions - ADDED):
            lines.append(f"  unexpected {question}")
        for question in sorted(ADDED - fresh_questions):
            lines.append(f"  missing {question}")
    for template, expected in PREVIOUS.items():
        rows = groups.get(template, [])
        previous = [hit for hit, fresh in rows if not fresh]
        extra = [hit for hit, fresh in rows if fresh]
        hits = sum(previous)
        total = len(previous)
        mark = "ok" if (hits, total) == expected else "FAIL"
        if mark == "FAIL":
            ok = False
        lines.append(f"{template:22} previous {hits}/{total}  expected {expected[0]}/{expected[1]}  {mark}  added {sum(extra)}/{len(extra)}")
    lines.append("added sentences:")
    for template, hit, question in added:
        lines.append(f"  {template}  {'hit' if hit else 'miss'}  {question}")
    return "\n".join(lines) + "\n", ok


def _holdout_table(records: list[dict], answers: dict[tuple[str, str], float]) -> str:
    hits: dict[str, int] = defaultdict(int)
    totals: dict[str, int] = defaultdict(int)
    for record in records:
        template = record["template"]
        totals[template] += 1
        if _hit(template, record["predicted"], answers[(record["stem"], record["question"])]):
            hits[template] += 1
    lines = [f"{template:22} {hits[template]}/{totals[template]}" for template in sorted(totals)]
    return "\n".join(lines) + "\n"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _revision() -> None:
    stems = _stems("train")
    path = _write_predictions(_predict(stems), "train")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    text, ok = _summarize(records, _answers(stems))
    header = f"{'PASS' if ok else 'FAIL'} predictions {path.name}\n"
    CHECK.write_text(header + text, encoding="utf-8")
    print(header + text, end="")
    if not ok:
        raise SystemExit(2)


def _holdout() -> None:
    if DONE.exists():
        raise SystemExit("The 15 already have a finished reading. Refusing a second pass.")
    if not CHECK.is_file() or not CHECK.read_text(encoding="utf-8").startswith("PASS"):
        raise SystemExit("The revision check has not passed. Refusing the 15.")
    if LOCK.exists():
        pid = 0
        try:
            pid = int(LOCK.read_text(encoding="utf-8").strip().split()[0])
        except ValueError:
            pid = 0
        if _alive(pid):
            raise SystemExit(f"A reading is already running, pid {pid}.")
        (ROOT / "swiss_holdout_crash.txt").write_text(
            f"Previous attempt pid {pid} did not finish. The reading was not consumed.\n",
            encoding="utf-8",
        )
        LOCK.unlink(missing_ok=True)
    stems = _stems("holdout")
    LOCK.write_text(f"{os.getpid()} started\n", encoding="utf-8")
    try:
        path = _write_predictions(_predict(stems), "holdout")
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        text = _holdout_table(records, _answers(stems))
        body = f"predictions {path.name}\n{text}"
        (ROOT / "swiss_holdout.txt").write_text(body, encoding="utf-8")
        DONE.write_text(body, encoding="utf-8")
        LOCK.unlink(missing_ok=True)
        print(body, end="")
    except Exception:
        (ROOT / "swiss_holdout_crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
        LOCK.unlink(missing_ok=True)
        raise


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--revision":
        _revision()
        return
    if mode == "--holdout":
        _holdout()
        return
    raise SystemExit("Use --revision or --holdout.")


if __name__ == "__main__":
    main()
