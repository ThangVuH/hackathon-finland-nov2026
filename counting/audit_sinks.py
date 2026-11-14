"""Check whether one SVG sink icon matches the preview sink answer.

A double-bowl sink must count as one. Every furniture class that contains
'Sink' is counted once, at the group that carries the class.
"""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SVG_ROOT = ROOT / "svg"
QUESTIONS = ROOT.parent / "junction-dataset-preview" / "questions.jsonl"
SINK_QUESTION = (
    "How many sinks and wash basins (kitchen and bathroom combined; "
    "a double-bowl sink counts as one) are drawn on this floor plan?"
)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def answers() -> dict[tuple[str, str], int]:
    found = {}
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row["question"] != SINK_QUESTION:
            continue
        style, sample_id = Path(row["path"]).stem.rsplit("-", 1)
        found[(style, sample_id)] = int(row["answer"])
    return found


def sink_classes(path: Path) -> Counter:
    counts: Counter = Counter()
    for element in ET.parse(path).iter():
        if local(element.tag) != "g":
            continue
        tokens = (element.get("class") or "").split()
        sink_tokens = [token for token in tokens if "Sink" in token or token == "WaterTap"]
        if not sink_tokens:
            continue
        # Nested marks (Name, BoundaryPolygon) do not carry the sink class.
        counts[" ".join(tokens)] += 1
    return counts


def main() -> None:
    target = answers()
    vocabulary: Counter = Counter()
    rows = []
    for (style, sample_id), answer in sorted(target.items()):
        counts = sink_classes(SVG_ROOT / style / sample_id / "model.svg")
        vocabulary.update(counts)
        predicted = sum(counts.values())
        rows.append((predicted == answer, predicted - answer, style, sample_id, answer, predicted))
    exact = sum(row[0] for row in rows)
    print(f"sinks exact {exact}/{len(rows)}")
    print("delta", dict(sorted(Counter(row[1] for row in rows).items())))
    print("classes")
    for key, value in vocabulary.most_common():
        print(f"  {value:5d}  {key}")
    misses = [row for row in rows if not row[0]]
    print("mismatches", len(misses))
    for row in misses[:12]:
        print(" ", row[2], row[3], "answer", row[4], "svg", row[5], "delta", row[1])
    out = ROOT / "audit_sinks.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["style", "sample_id", "answer", "svg_count", "delta", "exact"])
        for exact_flag, delta, style, sample_id, answer, predicted in rows:
            writer.writerow([style, sample_id, answer, predicted, delta, int(exact_flag)])


if __name__ == "__main__":
    main()
