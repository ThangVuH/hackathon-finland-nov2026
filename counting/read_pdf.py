"""Read text from a one-page plan PDF.

Strokes are not given a class. On the Swiss sheets the same gray is used
for several symbols, so a color is not a door or a window.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from drawing_objects import DrawingObject


def pdf_lines(path: Path) -> list[str]:
    """Layout order, which is the order of the room annotation."""
    document = pymupdf.open(path)
    try:
        lines: list[str] = []
        for page in document:
            lines.extend(line.strip() for line in page.get_text("text").splitlines() if line.strip())
        return lines
    finally:
        document.close()


def read_pdf(path: Path) -> list[DrawingObject]:
    document = pymupdf.open(path)
    objects: list[DrawingObject] = []
    try:
        for page in document:
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    text = "".join(span["text"] for span in line.get("spans", [])).strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = line["bbox"]
                    objects.append(
                        DrawingObject(
                            source="pdf",
                            kind="text",
                            name="text",
                            text=text,
                            points=((x0, y0), (x1, y1)),
                            closed=False,
                            storey="",
                        )
                    )
    finally:
        document.close()
    return objects
