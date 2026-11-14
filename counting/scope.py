"""Decide whether a drawing is a floor plan this detector may count.

IFC, CAD, PDF sheets and known archive sources are refused. Guessing a count
there would look like an answer and would be wrong for a reason the model
cannot see.

The decision is based on the filename, not on pixels. A held-out CubiCasa plan
(high_quality_architectural-10491) is a yellowed sheet with almost no white
pixels, and the product samples are grayscale. A brightness check refuses
those floor plans along with the archive scans it was meant to catch.
"""

from __future__ import annotations

from pathlib import Path

VECTOR_EXTENSIONS = {".ifc", ".dwg", ".dxf"}
SHEET_EXTENSIONS = {".pdf"}
SOURCE_MARKERS = (
    "/habs/",
    "/finna/",
    "/europeana/",
    "/wikimedia/",
    "/ifc_models/",
    "/ifc-models/",
    "ifc_models",
    "ifc-models",
)
NAME_MARKERS = ("_sheet_", "-sheet-", "_sheet.", "-sheet.", "planche")


def _path_text(filename: str) -> str:
    return filename.replace("\\", "/").lower()


def name_reason(filename: str) -> str | None:
    text = _path_text(filename or "drawing.png")
    extension = Path(text).suffix
    if extension in VECTOR_EXTENSIONS:
        return "IFC or CAD file. The checker reads a floor-plan image, and it will not invent a count for this file."
    if extension in SHEET_EXTENSIONS:
        return "Drawing sheet (PDF). The checker reads one floor plan, not a title-block sheet, and it will not invent a count."
    padded = f"/{text}"
    if any(marker in padded for marker in SOURCE_MARKERS):
        return "Archive scan or IFC export. Outside the floor plans this detector was trained on, so no count is returned."
    leaf = Path(text).name
    if any(marker in leaf for marker in NAME_MARKERS):
        return "This filename is an archive sheet. The checker does not count photographed drawing sheets."
    return None


def assess(filename: str, image=None) -> str | None:
    del image
    return name_reason(filename)
