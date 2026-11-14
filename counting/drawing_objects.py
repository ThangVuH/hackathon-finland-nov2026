"""Objects read from a deposited file.

`kind` is the file's own class: a DXF layer, a PDF text line, or an IFC
entity. It is not a checked answer definition. A PDF question is read from
the PDF. The DXF twin is a separate file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DrawingObject:
    source: str
    kind: str
    name: str
    text: str
    points: tuple[tuple[float, float], ...]
    closed: bool
    storey: str


def dataset_root() -> Path:
    candidates = [
        ROOT.parent / "junction-dataset-preview" / "data",
        ROOT.parent.parent / "stoa-preview" / "junction-dataset-preview" / "data",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Preview data directory was not found next to the repo.")
