"""Freeze the CubiCasa count evaluation.

One row per plan and per symbol class. Finnish duplicates are omitted.
Plans are split 70/15/15, stratified by drawing style, with a fixed seed.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT.parent / "junction-dataset-preview" / "questions.jsonl"
OUT = ROOT / "eval_split.csv"

CLASSES = {
    "window": "How many windows are shown on this floor plan?",
    "door": "How many doors are shown on this floor plan? Count doorways fitted with a door; open doorways without a door leaf do not count.",
}

SEED = 13
TEST_FRACTION = 0.15
VAL_FRACTION = 0.15


def load_answers() -> dict[tuple[str, str], int]:
    answers = {}
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not row["path"].startswith("data/cubicasa5k/"):
            continue
        for name, question in CLASSES.items():
            if row["question"] == question:
                stem = Path(row["path"]).stem
                style, sample_id = stem.rsplit("-", 1)
                answers[(style, sample_id, name)] = int(row["answer"])
    return answers


def assign_splits(plans: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    by_style: dict[str, list[str]] = defaultdict(list)
    for style, sample_id in plans:
        by_style[style].append(sample_id)
    rng = random.Random(SEED)
    splits = {}
    for style, sample_ids in sorted(by_style.items()):
        ordered = sorted(sample_ids)
        rng.shuffle(ordered)
        count = len(ordered)
        n_test = max(1, round(count * TEST_FRACTION))
        n_val = max(1, round(count * VAL_FRACTION))
        if n_test + n_val >= count:
            n_test, n_val = 1, 1
        for sample_id in ordered[:n_test]:
            splits[(style, sample_id)] = "test"
        for sample_id in ordered[n_test : n_test + n_val]:
            splits[(style, sample_id)] = "val"
        for sample_id in ordered[n_test + n_val :]:
            splits[(style, sample_id)] = "train"
    return splits


def main() -> None:
    answers = load_answers()
    plans = sorted({(style, sample_id) for style, sample_id, _ in answers})
    splits = assign_splits(plans)
    rows = []
    for style, sample_id, name in sorted(answers):
        rows.append(
            {
                "style": style,
                "sample_id": sample_id,
                "plan": f"{style}-{sample_id}",
                "split": splits[(style, sample_id)],
                "label": name,
                "answer": answers[(style, sample_id, name)],
                "image": f"data/cubicasa5k/{style}-{sample_id}.png",
            }
        )
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = defaultdict(int)
    for row in rows:
        summary[f"{row['split']}:{row['label']}"] += 1
        summary[f"plans:{row['split']}"] += 0
    plan_counts = defaultdict(int)
    for (style, sample_id), split in splits.items():
        plan_counts[f"{split}:{style}"] += 1
    print(f"rows {len(rows)} plans {len(plans)} -> {OUT.name}")
    for key in sorted(plan_counts):
        print(f"  {key} {plan_counts[key]}")


if __name__ == "__main__":
    main()
