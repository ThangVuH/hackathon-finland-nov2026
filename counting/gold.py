"""English preview questions. Finnish duplicates are the same answer and are left out."""

from __future__ import annotations

import json
from pathlib import Path

from export_yolo import questions_path

QUESTIONS = {
    "window": "How many windows are shown on this floor plan?",
    "door": (
        "How many doors are shown on this floor plan? Count doorways fitted with a door; "
        "open doorways without a door leaf do not count."
    ),
    "sink": (
        "How many sinks and wash basins (kitchen and bathroom combined; "
        "a double-bowl sink counts as one) are drawn on this floor plan?"
    ),
    "toilet": "How many toilet bowls (WC seats) are drawn on this floor plan?",
    "shower": "How many showers and bathtubs are drawn on this floor plan in total?",
    "kitchen": (
        "How many kitchens (including kitchenettes, open kitchens and utility kitchens) "
        "are on this floor plan?"
    ),
    "floor": "How many floors (storeys) does this floor plan show?",
    "sauna": "How many saunas are on this floor plan?",
}


def load_answers() -> dict[tuple[str, str, str], int]:
    wanted = {text: kind for kind, text in QUESTIONS.items()}
    found: dict[tuple[str, str, str], int] = {}
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        kind = wanted.get(row["question"])
        if kind is None or not str(row["path"]).startswith("data/cubicasa5k/"):
            continue
        style, sample_id = Path(row["path"]).stem.rsplit("-", 1)
        found[(style, sample_id, kind)] = int(row["answer"])
    return found
