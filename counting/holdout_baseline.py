"""Constant for the 15, taken from the 50. Does not change a solver.

The rule is the one already used on the revision table: the most frequent
answer of a sentence that appears at least twice on the 50, otherwise the
most frequent answer of that template on the 50. A tie keeps the smaller
value. A hit is an equal answer, not a 2% band.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from export_yolo import questions_path
from route_question import route
from swiss_holdout_once import _canonical, _stems

ROOT = Path(__file__).resolve().parent
ORDER = (
    "label_count",
    "room_area",
    "labelled_area",
    "indoor_total",
    "apartment_count",
    "door",
)


def _mode(values: list[float]) -> float:
    counts = Counter(values)
    best = max(counts.values())
    return min(value for value, count in counts.items() if count == best)


def _rows(stems: set[str]) -> dict[str, list[tuple[str, float]]]:
    found: dict[str, list[tuple[str, float]]] = defaultdict(list)
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
        template = route(question)[0]
        if not _canonical(template, question):
            continue
        found[template].append((question, float(row["answer"])))
    return found


def main() -> None:
    train = _rows(_stems("train"))
    hold = _rows(_stems("holdout"))
    lines = [
        "Holdout baseline. The constant is computed on the 50 only, then applied to the 15.",
        "Rule fixed with the revision table: repeated sentence mode, otherwise the template mode. A tie keeps the smaller.",
        "A baseline hit is an equal value. Areas do not use the 2% band in this column.",
        "",
        f"{'template':22} {'sentence':>10} {'one mode':>10}  template mode",
    ]
    for template in ORDER:
        train_rows = train[template]
        by_sentence: dict[str, list[float]] = defaultdict(list)
        for question, answer in train_rows:
            by_sentence[question].append(answer)
        template_mode = _mode([answer for _question, answer in train_rows])
        sentence_mode = {
            question: _mode(answers) if len(answers) >= 2 else template_mode
            for question, answers in by_sentence.items()
        }
        hits = template_hits = 0
        for question, answer in hold[template]:
            if answer == sentence_mode.get(question, template_mode):
                hits += 1
            if answer == template_mode:
                template_hits += 1
        total = len(hold[template])
        lines.append(
            f"{template:22} {hits:>4}/{total:<5} {template_hits:>4}/{total:<5} {template_mode}"
        )
    text = "\n".join(lines) + "\n"
    (ROOT / "holdout_baseline.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
