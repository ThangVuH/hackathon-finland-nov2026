"""Scores for a count detector.

Two levels are reported together. Symbol precision and recall say whether
each window or door was found. Plan exactness says whether the total matches,
which is the challenge rule. The error histogram shows how often a miss is
only one symbol.
"""

from __future__ import annotations

from collections import Counter, defaultdict


def iou(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = width * height
    if inter == 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (area_a + area_b - inter)


def match_symbols(predicted: list[list[float]], gold: list[list[float]], threshold: float = 0.5) -> tuple[int, int, int]:
    """Greedy one-to-one match. Returns true positives, false positives, false negatives."""
    used = set()
    true_positives = 0
    for box in predicted:
        best_index = None
        best_iou = threshold
        for index, truth in enumerate(gold):
            if index in used:
                continue
            overlap = iou(box, truth)
            if overlap >= best_iou:
                best_iou = overlap
                best_index = index
        if best_index is not None:
            used.add(best_index)
            true_positives += 1
    return true_positives, len(predicted) - true_positives, len(gold) - true_positives


def error_bin(delta: int) -> str:
    if delta == 0:
        return "0"
    if abs(delta) == 1:
        return "±1"
    return "±2 ou plus"


def summarize(rows: list[dict]) -> str:
    """Each row has label, answer, predicted, and optional tp, fp, fn."""
    lines = []
    by_label = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row)
    for label in sorted(by_label):
        group = by_label[label]
        exact = sum(int(row["predicted"]) == int(row["answer"]) for row in group)
        bins = Counter(error_bin(int(row["predicted"]) - int(row["answer"])) for row in group)
        lines.append(
            f"{label}: plans exacts {exact}/{len(group)} ({exact / len(group):.1%})"
        )
        lines.append(
            "  écarts  "
            + "  ".join(f"{name} {bins.get(name, 0)}" for name in ("0", "±1", "±2 ou plus"))
        )
        if any("tp" in row for row in group):
            tp = sum(row.get("tp", 0) for row in group)
            fp = sum(row.get("fp", 0) for row in group)
            fn = sum(row.get("fn", 0) for row in group)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            lines.append(f"  symboles  précision {precision:.1%}  rappel {recall:.1%}  (tp {tp} fp {fp} fn {fn})")
    return "\n".join(lines)
