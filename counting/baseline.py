"""Constant baseline and definition ceiling.

The constant for each template is the most frequent answer on the training
plans only. Scored on the test plans, that constant contains no test answer.
A tie keeps the smaller answer. The ceiling is the SVG rule against the
answer. It is not a detector score.

Non-modal plans are those whose answer is not that training constant. The
constant is exact on none of them, by construction. That slice is where a
detector has to add something.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from math import comb

from export_yolo import ROOT, load_splits
from gold import QUESTIONS, load_answers
from label_rules import CLASS_ID, boxes_in, count_floors, svg_path

OUT = ROOT / "baseline_report.txt"
PUBLIC = ROOT / "published_counts_test.csv"
PREDICTED = {
    "window": "window",
    "door": "door",
    "sink": "sink",
    "toilet": "toilet",
    "shower": "shower",
    "kitchen": "kitchen",
    "sauna": "sauna_stove",
}


def _mode(values: list[int]) -> tuple[int, int]:
    counts = Counter(values)
    best_count = max(counts.values())
    modes = sorted(answer for answer, count in counts.items() if count == best_count)
    return modes[0], best_count


def _rate(exact: int, total: int) -> str:
    return f"{exact}/{total}"


def _one_sided(observed: int, total: int, probability: float) -> float:
    """Probability of a count at least this far from the training rate, one side."""
    if total == 0:
        return 1.0
    probability = min(1.0, max(0.0, probability))
    expected = probability * total
    if observed >= expected:
        start, stop = observed, total
    else:
        start, stop = 0, observed
    tail = 0.0
    for count in range(start, stop + 1):
        tail += comb(total, count) * probability**count * (1 - probability) ** (total - count)
    return tail


def train_modes() -> dict[str, int]:
    splits = load_splits()
    grouped: dict[str, list[int]] = defaultdict(list)
    for (style, sample_id, kind), answer in load_answers().items():
        if splits.get((style, sample_id)) == "train":
            grouped[kind].append(answer)
    return {kind: _mode(values)[0] for kind, values in grouped.items()}


def definition_counts() -> dict[str, Counter]:
    predicted: dict[str, Counter] = defaultdict(Counter)
    for (style, sample_id) in load_splits():
        path = svg_path(style, sample_id)
        counts = Counter(kind for kind, *_box in boxes_in(path))
        for kind, total in counts.items():
            predicted[kind][(style, sample_id)] = total
        predicted["floor"][(style, sample_id)] = count_floors(path)
    return predicted


def _label_lines() -> list[str]:
    lines = ["Boxes in the exported tiles. A plan is counted once per class."]
    label_root = ROOT / "yolo-multiclass" / "labels"
    for split in ("train", "val", "test"):
        boxes: Counter[str] = Counter()
        plans: dict[str, set[str]] = defaultdict(set)
        all_plans: set[str] = set()
        for label in (label_root / split).glob("*.txt"):
            plan = label.stem.split("_x")[0]
            all_plans.add(plan)
            for line in label.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                class_id = line.split()[0]
                boxes[class_id] += 1
                plans[class_id].add(plan)
        lines.append(f"  {split} plans {len(all_plans)}")
        for name, index in sorted(CLASS_ID.items(), key=lambda item: item[1]):
            class_id = str(index)
            lines.append(
                f"    {name} boxes {boxes[class_id]}  plans {len(plans[class_id])}/{len(all_plans)}"
            )
    return lines


def main() -> None:
    answers = load_answers()
    splits = load_splits()
    predicted = definition_counts()
    modes = train_modes()
    by_split: dict[str, dict[str, list[tuple[tuple[str, str], int]]]] = {
        "train": defaultdict(list),
        "val": defaultdict(list),
        "test": defaultdict(list),
    }
    for (style, sample_id, kind), answer in answers.items():
        split = splits.get((style, sample_id))
        if split in by_split:
            by_split[split][kind].append(((style, sample_id), answer))

    lines = [
        "The constant is the most frequent training answer. A tie keeps the smaller answer.",
        "Test and validation use that frozen constant. They do not choose it.",
        "Ceiling = SVG rule. Non-modal = answer different from the training constant.",
        "The constant scores 0 on every non-modal plan.",
        "",
    ]
    lines.extend(_label_lines())
    lines.append("")
    for kind in QUESTIONS:
        mode = modes[kind]
        train_rows = by_split["train"][kind]
        train_hits = sum(answer == mode for _key, answer in train_rows)
        lines.append(
            f"{kind:8} train_mode {mode}  train_share {_rate(train_hits, len(train_rows))}"
        )
        source = "floor" if kind == "floor" else PREDICTED[kind]
        for split in ("val", "test"):
            rows = by_split[split][kind]
            hits = sum(answer == mode for _key, answer in rows)
            nonmodal = [(key, answer) for key, answer in rows if answer != mode]
            ceiling_all = sum(predicted[source].get(key, 0) == answer for key, answer in rows)
            ceiling_hits = sum(predicted[source].get(key, 0) == answer for key, answer in nonmodal)
            lines.append(
                f"         {split:4} constant {_rate(hits, len(rows))}"
                f"  definition {_rate(ceiling_all, len(rows))}"
                f"  nonmodal {len(nonmodal)}"
                f"  definition_on_nonmodal {_rate(ceiling_hits, len(nonmodal))}"
            )
        if kind == "sauna":
            zeros = sum(answer == 0 for _key, answer in train_rows)
            lines.append(f"         train answers equal to 0: {_rate(zeros, len(train_rows))} (not the mode)")
        if kind == "kitchen":
            val_non = sum(answer != mode for _key, answer in by_split["val"][kind])
            test_non = sum(answer != mode for _key, answer in by_split["test"][kind])
            lines.append("         UNMEASURABLE. Not in any global detector score.")
            lines.append(
                f"         test nonmodal {test_non}/{len(by_split['test'][kind])},"
                f" val nonmodal {val_non}/{len(by_split['val'][kind])}."
            )

    lines.append("")
    lines.append("LIMIT. The official test is not an exchangeable draw from the training answers.")
    lines.append("Eight templates were looked at. One tail near 1% can still be chance.")
    lines.append("Validation thresholds can transfer worse, and a train or validation score is optimistic.")
    lines.append("nonmodal counts. expected = training nonmodal rate times the split size. tail = one-sided binomial.")
    for kind in QUESTIONS:
        train_rows = by_split["train"][kind]
        mode = modes[kind]
        train_non = sum(answer != mode for _key, answer in train_rows)
        probability = train_non / len(train_rows) if train_rows else 0.0
        lines.append(f"  {kind:8} train_nonmodal {_rate(train_non, len(train_rows))}")
        for split in ("val", "test"):
            rows = by_split[split][kind]
            observed = sum(answer != mode for _key, answer in rows)
            expected = probability * len(rows)
            tail = _one_sided(observed, len(rows), probability)
            lines.append(
                f"           {split:4} {observed}/{len(rows)}  expected {expected:.1f}  tail {tail:.3f}"
            )

    lines.append("")
    lines.append("Public model on the 27, against the training constant, not against the test mode.")
    public_rows = list(csv.DictReader(PUBLIC.open(encoding="utf-8")))
    for label, column in (("window", "window_answer"), ("door", "door_answer")):
        usable = [row for row in public_rows if row[column] != ""]
        mode = modes[label]
        constant_hits = sum(int(row[column]) == mode for row in usable)
        model_hits = sum(int(row[label] or 0) == int(row[column]) for row in usable)
        nonmodal = [row for row in usable if int(row[column]) != mode]
        model_non = sum(int(row[label] or 0) == int(row[column]) for row in nonmodal)
        lines.append(
            f"  {label:6} constant {_rate(constant_hits, len(usable))}"
            f"  model {_rate(model_hits, len(usable))}"
            f"  model_on_nonmodal {_rate(model_non, len(nonmodal))}"
        )
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")
    for kind, source in PREDICTED.items():
        if kind == "sauna":
            continue
        rows = [
            (key, answer)
            for split in by_split.values()
            for key, answer in split[kind]
        ]
        exact = sum(predicted[source].get(key, 0) == answer for key, answer in rows)
        if exact != len(rows):
            raise SystemExit(f"{kind} definition is {exact}/{len(rows)}, expected a full match")
    floor_rows = [item for split in by_split.values() for item in split["floor"]]
    floor_exact = sum(predicted["floor"].get(key, 0) == answer for key, answer in floor_rows)
    if floor_exact != len(floor_rows):
        raise SystemExit(f"floor definition is {floor_exact}/{len(floor_rows)}, expected a full match")


if __name__ == "__main__":
    main()
