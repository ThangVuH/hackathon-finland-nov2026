"""Compare CubiCasa SVG symbol counts with the preview answers.

Windows and doors are counted from class tokens on SVG groups. A short
size check says whether the SVG coordinate system can lie on the preview PNG.
A few overlays make that check visible.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SVG_ROOT = ROOT / "svg"
PREVIEW = ROOT.parent / "junction-dataset-preview" / "data" / "cubicasa5k"
EVAL = ROOT / "eval_split.csv"
OUT = ROOT / "audit_counts.csv"
OVERLAYS = ROOT / "overlays"

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def tokens(element: ET.Element) -> list[str]:
    return (element.get("class") or "").split()


def parse_matrix(transform: str | None) -> tuple[float, float, float, float, float, float]:
    if not transform or "matrix" not in transform:
        return IDENTITY
    body = transform[transform.find("(") + 1 : transform.find(")")]
    values = [float(part) for part in body.replace(",", " ").split()]
    return tuple(values)  # type: ignore[return-value]


def multiply(outer, inner):
    a1, b1, c1, d1, e1, f1 = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def apply(matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def polygon_points(element: ET.Element, matrix) -> list[tuple[float, float]]:
    raw = element.get("points") or ""
    numbers = [float(part) for part in raw.replace(",", " ").split() if part]
    points = []
    for index in range(0, len(numbers) - 1, 2):
        points.append(apply(matrix, numbers[index], numbers[index + 1]))
    return points


def icon_points(element: ET.Element, matrix, kind: str) -> list[tuple[float, float]]:
    """Opening geometry only. The door swing arc is a path and is left out.

    ``matrix`` already includes ``element``'s own transform.
    """
    found: list[tuple[float, float]] = []

    def visit(node: ET.Element, current, inside_threshold: bool, at_icon: bool) -> bool:
        if not at_icon:
            current = multiply(current, parse_matrix(node.get("transform")))
        inside_threshold = inside_threshold or (
            local(node.tag) == "g" and "Threshold" in tokens(node)
        )
        take = kind == "window" or inside_threshold
        if take and local(node.tag) == "polygon" and node.get("points"):
            found.extend(polygon_points(node, current))
            return True
        for child in list(node):
            if visit(child, current, inside_threshold, False):
                return True
        return False

    visit(element, matrix, False, True)
    return found


def walk(element: ET.Element, matrix, icons: list[dict], vocabulary: Counter):
    matrix = multiply(matrix, parse_matrix(element.get("transform")))
    kind = None
    element_tokens = tokens(element)
    if local(element.tag) == "g":
        if "Window" in element_tokens:
            kind = "window"
        elif "Door" in element_tokens:
            kind = "door"
        if kind:
            vocabulary[kind + ":" + " ".join(element_tokens)] += 1
            points = icon_points(element, matrix, kind)
            if points:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                icons.append(
                    {
                        "kind": kind,
                        "x0": min(xs),
                        "y0": min(ys),
                        "x1": max(xs),
                        "y1": max(ys),
                    }
                )
            else:
                icons.append({"kind": kind, "x0": None, "y0": None, "x1": None, "y1": None})
            return
        for token in element_tokens:
            if token in {"Toilet", "Sink", "Shower", "Bathtub", "SaunaBench", "SaunaStove"}:
                vocabulary["furniture:" + token] += 1
    for child in list(element):
        walk(child, matrix, icons, vocabulary)


def read_svg(path: Path) -> tuple[list[dict], Counter, float, float]:
    root = ET.parse(path).getroot()
    width = float(root.get("width"))
    height = float(root.get("height"))
    icons: list[dict] = []
    vocabulary: Counter = Counter()
    walk(root, IDENTITY, icons, vocabulary)
    return icons, vocabulary, width, height


def load_eval() -> dict[tuple[str, str, str], dict]:
    rows = {}
    with EVAL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[(row["style"], row["sample_id"], row["label"])] = row
    return rows


def load_scales() -> dict[tuple[str, str], tuple[float, float]]:
    path = ROOT / "scaled_size.csv"
    scales = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scales[(row["style"], row["sample_id"])] = (float(row["scale_x"]), float(row["scale_y"]))
    return scales


SCALES = load_scales()


def draw_overlay(style: str, sample_id: str, icons: list[dict], svg_w: float, svg_h: float) -> None:
    image_path = PREVIEW / f"{style}-{sample_id}.png"
    image = Image.open(image_path).convert("RGB")
    # Symbol coordinates live in F1_scaled.png, not in the SVG viewBox.
    scale_x, scale_y = SCALES[(style, sample_id)]
    del svg_w, svg_h
    draw = ImageDraw.Draw(image)
    colors = {"window": (220, 40, 40), "door": (20, 90, 220)}
    for icon in icons:
        if icon["x0"] is None:
            continue
        box = [
            icon["x0"] * scale_x,
            icon["y0"] * scale_y,
            icon["x1"] * scale_x,
            icon["y1"] * scale_y,
        ]
        draw.rectangle(box, outline=colors[icon["kind"]], width=max(2, image.width // 400))
    OVERLAYS.mkdir(parents=True, exist_ok=True)
    image.save(OVERLAYS / f"{style}-{sample_id}.jpg", quality=85)


def main() -> None:
    answers = load_eval()
    vocabulary: Counter = Counter()
    rows = []
    aspect_close = 0
    aspect_seen = 0
    overlays_drawn = set()
    for svg_path in sorted(SVG_ROOT.glob("*/*/model.svg")):
        style, sample_id = svg_path.parts[-3], svg_path.parts[-2]
        icons, local_vocab, svg_w, svg_h = read_svg(svg_path)
        vocabulary.update(local_vocab)
        counts = Counter(icon["kind"] for icon in icons)
        with Image.open(PREVIEW / f"{style}-{sample_id}.png") as image:
            png_w, png_h = image.size
        aspect_seen += 1
        ratio = (svg_w / svg_h) / (png_w / png_h)
        if abs(ratio - 1) <= 0.02:
            aspect_close += 1
        for label in ("window", "door"):
            answer_row = answers.get((style, sample_id, label))
            if answer_row is None:
                continue
            predicted = counts[label]
            answer = int(answer_row["answer"])
            rows.append(
                {
                    "style": style,
                    "sample_id": sample_id,
                    "split": answer_row["split"],
                    "label": label,
                    "answer": answer,
                    "svg_count": predicted,
                    "exact": int(predicted == answer),
                    "abs_error": abs(predicted - answer),
                    "svg_w": round(svg_w, 1),
                    "svg_h": round(svg_h, 1),
                    "png_w": png_w,
                    "png_h": png_h,
                    "aspect_ratio": round(ratio, 4),
                }
            )
        if style not in overlays_drawn and counts["window"]:
            draw_overlay(style, sample_id, icons, svg_w, svg_h)
            overlays_drawn.add(style)

    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"plans parsed {aspect_seen}  aspect within 2% {aspect_close}")
    for label in ("window", "door"):
        subset = [row for row in rows if row["label"] == label]
        exact = sum(row["exact"] for row in subset)
        print(
            f"{label:6} n={len(subset):3d}  exact={exact}/{len(subset)}"
            f" ({exact / len(subset):.1%})  "
            f"mean |err|={sum(row['abs_error'] for row in subset) / len(subset):.2f}"
        )
        delta = Counter(row["svg_count"] - row["answer"] for row in subset)
        print("  svg-answer", dict(sorted(delta.items())))
    print("vocabulary")
    for key, value in vocabulary.most_common(30):
        print(f"  {value:5d}  {key}")
    print("overlays", sorted(overlays_drawn))


if __name__ == "__main__":
    main()
