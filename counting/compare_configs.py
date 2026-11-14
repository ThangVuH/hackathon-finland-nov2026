"""Exact-plan rates for the vision model, the detector, and the checker.

The checker accepts a plan only when both engines report the same total and
their boxes overlap. The curve is that precision against the share of plans
accepted, as the agreement required is relaxed.

Detector boxes are cached in cache/tiles.jsonl. Vision boxes are cached in
cache/vision.jsonl and are requested only when LOVABLE_API_KEY is set.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image

from arbitrate import reliability_score, selective_table
from count_metrics import error_bin
from engine import keep, predict_tiles, save_threshold
from evaluate_counts import CONF_GRID
from export_yolo import PREVIEW
from scope import assess

ROOT = Path(__file__).resolve().parent
EVAL = ROOT / "eval_split.csv"
CACHE = ROOT / "cache"
TILES = CACHE / "tiles.jsonl"
VISION = CACHE / "vision.jsonl"
REPORT = ROOT / "comparison_report.txt"
ROWS = ROOT / "comparison_rows.csv"

QUESTIONS = {
    "window": "How many windows are shown on this floor plan?",
    "door": (
        "How many doors are shown on this floor plan? Count doorways fitted with a door; "
        "open doorways without a door leaf do not count."
    ),
}
VISION_INSTRUCTIONS = (
    "You count elements on a floor plan. Return JSON with keys answer, object_type, count, items. "
    "items is a list of {label, ymin, xmin, ymax, xmax} on a 0-1000 scale, origin top-left. "
    "One item per window or door. A double door is one door. Do not invent elements."
)


def load_rows() -> list[dict]:
    with EVAL.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def by_plan(rows: list[dict], split: str) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["split"] == split:
            grouped[(row["style"], row["sample_id"])].append(row)
    return grouped


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def scope_audit(plans: dict[tuple[str, str], list[dict]]) -> list[str]:
    refused = []
    for style, sample_id in sorted(plans):
        name = f"{style}-{sample_id}.png"
        reason = assess(name)
        if reason:
            refused.append(f"{name}: {reason}")
    return refused


def detection_cache(plans: dict[tuple[str, str], list[dict]]) -> dict[tuple[str, str], tuple[int, int, list]]:
    cached = {}
    for record in load_jsonl(TILES):
        cached[(record["style"], record["sample_id"])] = (
            record["width"],
            record["height"],
            [tuple(item) for item in record["detections"]],
        )
    missing = [key for key in sorted(plans) if key not in cached]
    for index, (style, sample_id) in enumerate(missing, start=1):
        path = PREVIEW / f"{style}-{sample_id}.png"
        print(f"detector {index}/{len(missing)} {style}-{sample_id}", flush=True)
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            detections = predict_tiles(rgb)
        record = {
            "style": style,
            "sample_id": sample_id,
            "width": width,
            "height": height,
            "detections": detections,
        }
        append_jsonl(TILES, record)
        cached[(style, sample_id)] = (width, height, detections)
    return cached


def choose_threshold(plans, cache) -> float:
    best_threshold = CONF_GRID[0]
    best_exact = -1
    for threshold in CONF_GRID:
        exact = 0
        total = 0
        for key, rows in plans.items():
            width, height, detections = cache[key]
            totals = _totals(keep(detections, threshold, width, height)["items"])
            for row in rows:
                total += 1
                exact += int(totals[row["label"]] == int(row["answer"]))
        print(f"val conf={threshold:.2f} exact={exact}/{total}", flush=True)
        if exact > best_exact:
            best_exact = exact
            best_threshold = threshold
    print(f"chosen conf {best_threshold}", flush=True)
    return best_threshold


def _totals(items: list[dict]) -> dict[str, int]:
    totals = {"window": 0, "door": 0}
    for item in items:
        if item["kind"] in totals:
            totals[item["kind"]] += 1
    return totals


def _of_kind(items: list[dict], kind: str) -> list[dict]:
    return [item for item in items if item.get("kind") == kind]


def prepare_vision_image(path: Path) -> str:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        scale = min(1.0, 1800 / max(rgb.size))
        if scale < 1:
            rgb = rgb.resize((round(rgb.width * scale), round(rgb.height * scale)), Image.Resampling.BILINEAR)
        buffer = BytesIO()
        rgb.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def parse_model_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def call_vision(data_url: str, question: str) -> dict:
    key = os.environ["LOVABLE_API_KEY"]
    payload = {
        "model": "openai/gpt-6-astra",
        "messages": [
            {"role": "system", "content": VISION_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    request = urllib.request.Request(
        "https://ai.gateway.lovable.dev/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Lovable-API-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode())
    content = body["choices"][0]["message"]["content"]
    parsed = parse_model_json(content)
    items = []
    for item in parsed.get("items") or []:
        items.append(
            {
                "kind": parsed.get("object_type") or "",
                "label": item.get("label") or "",
                "ymin": item.get("ymin", 0),
                "xmin": item.get("xmin", 0),
                "ymax": item.get("ymax", 0),
                "xmax": item.get("xmax", 0),
            }
        )
    return {"available": True, "count": len(items), "items": items, "answer": parsed.get("answer") or ""}


def vision_cache(plans) -> dict[tuple[str, str, str], dict]:
    found = {}
    for record in load_jsonl(VISION):
        found[(record["style"], record["sample_id"], record["label"])] = record
    if not os.environ.get("LOVABLE_API_KEY"):
        return found
    pending = [
        (style, sample_id, row["label"])
        for (style, sample_id), rows in sorted(plans.items())
        for row in rows
        if (style, sample_id, row["label"]) not in found
    ]
    images: dict[tuple[str, str], str] = {}
    for index, (style, sample_id, label) in enumerate(pending, start=1):
        print(f"vision {index}/{len(pending)} {style}-{sample_id} {label}", flush=True)
        key = (style, sample_id)
        try:
            if key not in images:
                images[key] = prepare_vision_image(PREVIEW / f"{style}-{sample_id}.png")
            result = call_vision(images[key], QUESTIONS[label])
            for item in result["items"]:
                item["kind"] = label
            record = {"style": style, "sample_id": sample_id, "label": label, "error": "", **result}
            append_jsonl(VISION, record)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError) as error:
            record = {
                "style": style,
                "sample_id": sample_id,
                "label": label,
                "available": False,
                "count": None,
                "items": [],
                "error": f"{type(error).__name__}: {error}",
            }
            print(f"  echec {record['error']}", flush=True)
        found[(style, sample_id, label)] = record
    return found


def _rate(exact: int, total: int) -> str:
    if not total:
        return "0/0"
    return f"{exact}/{total} ({exact / total:.1%})"


def _plan_exact(rows: list[dict], totals: dict[str, int]) -> bool:
    return all(totals[row["label"]] == int(row["answer"]) for row in rows)


def write_report(test, detector, vision, threshold: float, refused: list[str], val_line: str) -> None:
    question_exact = 0
    question_total = 0
    plan_exact = 0
    vision_question_exact = 0
    vision_question_total = 0
    vision_plan_exact = 0
    vision_plans = 0
    curve_plans = []
    table_rows = []
    missing_vision = 0

    for key in sorted(test):
        rows = test[key]
        totals = _totals(detector[key]["items"])
        plan_exact += int(_plan_exact(rows, totals))
        vision_totals = {}
        vision_complete = True
        scores = []
        for row in rows:
            label = row["label"]
            question_total += 1
            question_exact += int(totals[label] == int(row["answer"]))
            record = vision.get((*key, label))
            vision_count = ""
            score_text = ""
            if not record or not record.get("available"):
                vision_complete = False
                missing_vision += 1
            else:
                kind_items = [{**item, "kind": label} for item in record["items"]]
                vision_count = len(kind_items)
                vision_totals[label] = vision_count
                vision_question_total += 1
                vision_question_exact += int(vision_count == int(row["answer"]))
                score = reliability_score(_of_kind(detector[key]["items"], label), kind_items)
                scores.append(score)
                score_text = f"{score:.3f}"
            table_rows.append(
                {
                    "plan": f"{key[0]}-{key[1]}",
                    "label": label,
                    "answer": row["answer"],
                    "detector": totals[label],
                    "vision": vision_count,
                    "score": score_text,
                    "detector_exact": int(totals[label] == int(row["answer"])),
                }
            )
        if vision_complete:
            vision_plans += 1
            vision_plan_exact += int(_plan_exact(rows, vision_totals))
            curve_plans.append({"exact": _plan_exact(rows, totals), "score": min(scores) if scores else 0.0})

    lines = [
        f"Plans de test : {len(test)}",
        f"Questions de test : {question_total}",
        val_line,
        f"Seuil retenu : {threshold:.2f}",
        "",
        f"Détecteur seul, plans exacts : {_rate(plan_exact, len(test))}",
        f"Détecteur seul, questions exactes : {_rate(question_exact, question_total)}",
    ]
    bins = Counter(error_bin(int(row["detector"]) - int(row["answer"])) for row in table_rows)
    lines.append(
        "  écarts  " + "  ".join(f"{name} {bins.get(name, 0)}" for name in ("0", "±1", "±2 ou plus"))
    )
    if vision_plans:
        lines.append(f"Vision seule, plans exacts : {_rate(vision_plan_exact, vision_plans)}")
        lines.append(f"Vision seule, questions exactes : {_rate(vision_question_exact, vision_question_total)}")
        lines.append("")
        lines.append("Combiné. Un plan est traité automatiquement quand le score d'accord vaut au moins le seuil.")
        lines.append("La précision est la part de ces plans dont le total du détecteur est exact.")
        for row in selective_table(curve_plans):
            precision = "—" if row["precision"] is None else f"{row['precision']:.1%}"
            lines.append(
                f"  seuil {row['threshold']:.2f}  couverture {row['coverage']:.1%} ({row['accepted']}/{row['plans']})  précision {precision}"
            )
        strict = selective_table(curve_plans, [1.0])[0]
        if strict["accepted"]:
            lines.append(
                f"Règle du produit (accord complet) : {strict['coverage']:.1%} des plans, "
                f"{strict['precision']:.1%} exacts parmi eux."
            )
    else:
        lines.append("Vision seule : non mesurée. Ni cache/vision.jsonl ni LOVABLE_API_KEY.")
        lines.append("La courbe combinée attend les boîtes du modèle de vision.")
    if missing_vision and vision_plans:
        lines.append(f"Questions sans réponse vision : {missing_vision}")
    lines.append("")
    if refused:
        lines.append("Plans de test que le filtre de périmètre refuserait :")
        lines.extend(f"  {line}" for line in refused)
    else:
        lines.append("Filtre de périmètre : aucun plan de test refusé.")
    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    with ROWS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["plan", "label", "answer", "detector", "vision", "score", "detector_exact"],
        )
        writer.writeheader()
        writer.writerows(table_rows)
    print(text, flush=True)


def main() -> None:
    rows = load_rows()
    validation = by_plan(rows, "val")
    test = by_plan(rows, "test")
    print(f"plans val={len(validation)} test={len(test)}", flush=True)
    refused = scope_audit(test)
    if refused:
        print("scope refusals", len(refused), flush=True)
    cache = detection_cache({**validation, **test})
    threshold = choose_threshold(validation, cache)
    save_threshold(threshold)
    detector = {}
    for key, (width, height, detections) in cache.items():
        if key in test:
            detector[key] = keep(detections, threshold, width, height)
    vision = vision_cache(test)
    write_report(test, detector, vision, threshold, refused, f"Plans de validation utilisés pour le seuil : {len(validation)}")


if __name__ == "__main__":
    main()
