"""Vision alone, after counting/vlm_alone.txt. Does not choose a method.

One window question on each of the 27 test plans, plus eight Swiss training
questions. Detector boxes come from the epoch22 cache. Plans are not predicted again.
A failed call stays unverified.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from export_yolo import PREVIEW, load_splits, questions_path
from gold import QUESTIONS

ROOT = Path(__file__).resolve().parent
DECLARATION = ROOT / "vlm_alone.txt"
CACHE = ROOT / "vlm_frozen_cache.json"
OUT = ROOT / "vlm_alone_result.txt"
PROMPT = (
    'Count only. Reply with JSON {"count": integer, "items": [{"ymin":0,"xmin":0,"ymax":1,"xmax":1}]}. '
    "Boxes are 0-1000. Question: "
)
ENV = ROOT.parent / "STOA-eyes" / ".env"
CUTOFF = {
    "window": 0.30,
    "door": 0.45,
    "sink": 0.60,
    "toilet": 0.45,
    "shower": 0.15,
    "sauna_stove": 0.15,
}


def _key() -> tuple[str, str]:
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values.get("STOA_API_KEY", ""), values.get("STOA_MODEL", "gemini-3.6-flash")


def _cache() -> dict:
    if CACHE.is_file():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _store(key: str, value: dict) -> None:
    cached = _cache()
    cached[key] = value
    CACHE.write_text(json.dumps(cached), encoding="utf-8")


def _iou(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = width * height
    if inter == 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (area_a + area_b - inter)


def _detector_rows(style: str, sample: str) -> list | None:
    path = ROOT / "runs" / "multiclass" / "det_cache" / "epoch22.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get(f"{style}|{sample}")


def _agrees(rows: list | None, items: list, image: Path, vision_count: int) -> bool:
    if rows is None:
        return False
    from PIL import Image

    with Image.open(image) as picture:
        width, height = picture.size
    detector = []
    for name, score, box in rows:
        if name != "window" or score < CUTOFF["window"]:
            continue
        x0, y0, x1, y1 = box
        detector.append([x0 / width * 1000, y0 / height * 1000, x1 / width * 1000, y1 / height * 1000])
    vision = []
    for item in items:
        try:
            vision.append([float(item["xmin"]), float(item["ymin"]), float(item["xmax"]), float(item["ymax"])])
        except (KeyError, TypeError, ValueError):
            return False
    if len(detector) != vision_count or len(detector) != len(vision):
        return False
    used: set[int] = set()
    for box in detector:
        partner = next((index for index, other in enumerate(vision) if index not in used and _iou(box, other) >= 0.3), None)
        if partner is None:
            return False
        used.add(partner)
    return len(used) == len(vision)


def _ask(image_path: Path, question: str) -> dict:
    key, model = _key()
    if not key:
        return {"ok": False, "error": "no-key"}
    import base64

    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = PROMPT + question
    body = json.dumps(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": encoded}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return {"ok": True, "count": parsed.get("count"), "items": parsed.get("items") or []}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as error:
            if attempt == 3:
                return {"ok": False, "error": type(error).__name__}
            time.sleep(2 ** attempt)
    return {"ok": False, "error": "unverified"}


def _cases() -> list[dict]:
    splits = load_splits()
    test = {key for key, split in splits.items() if split == "test"}
    cases = []
    seen = set()
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row["question"] != QUESTIONS["window"]:
            continue
        if not str(row["path"]).startswith("data/cubicasa5k/"):
            continue
        stem = Path(row["path"]).stem
        style, sample = stem.rsplit("-", 1)
        if (style, sample) not in test or (style, sample) in seen:
            continue
        seen.add((style, sample))
        cases.append(
            {
                "key": f"cubi|{style}|{sample}",
                "image": str(PREVIEW / f"{stem}.png"),
                "question": row["question"],
                "answer": float(row["answer"]),
                "rows": _detector_rows(style, sample),
            }
        )
    return cases


def _swiss_cases() -> list[dict]:
    import csv

    import pymupdf

    from drawing_objects import dataset_root

    train = {
        row["stem"]
        for row in csv.DictReader((ROOT / "swiss_split.csv").open(encoding="utf-8"))
        if row["split"] == "train"
    }
    picked = []
    pages: dict[str, str] = {}
    out_dir = ROOT / "vlm_swiss_pages"
    out_dir.mkdir(exist_ok=True)
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if len(picked) >= 8:
            break
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        question = row["question"]
        if stem not in train or not question.startswith(("How many rooms labelled", "What is the net floor area of room ", "How many doors (interior")):
            continue
        if stem not in pages:
            document = pymupdf.open(dataset_root() / "swiss_dwellings" / f"{stem}.pdf")
            image = out_dir / f"{stem}.png"
            document[0].get_pixmap(matrix=pymupdf.Matrix(1.0, 1.0), alpha=False).save(image)
            document.close()
            pages[stem] = str(image)
        picked.append(
            {
                "key": f"swiss|{stem}|{question}",
                "image": pages[stem],
                "question": question,
                "answer": float(row["answer"]),
            }
        )
    return picked


def _log(line: str) -> None:
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def main() -> None:
    declared = DECLARATION.read_text(encoding="utf-8") if DECLARATION.is_file() else ""
    if "gemini-3.6-flash" not in declared or "Count only." not in declared:
        raise SystemExit("Freeze the model and the prompt in counting/vlm_alone.txt before running this.")
    OUT.write_text("", encoding="utf-8")
    _log("model gemini-3.6-flash")
    _log("prompt " + PROMPT + "{question}")
    cases = _cases()
    exact = asked = reliable = reliable_exact = failed = 0
    for case in cases:
        cached = _cache().get(case["key"])
        result = cached if cached is not None else _ask(Path(case["image"]), case["question"])
        if cached is None:
            _store(case["key"], result)
        asked += 1
        if not result.get("ok"):
            failed += 1
            _log(f"{case['key']}\tmissing\t{result.get('error', '')}")
            continue
        count = result.get("count")
        exact_here = count == case["answer"]
        if exact_here:
            exact += 1
        boxes = result.get("items") or []
        agreed = _agrees(case.get("rows"), boxes, Path(case["image"]), count if isinstance(count, int) else -1)
        if agreed:
            reliable += 1
            if count == case["answer"]:
                reliable_exact += 1
        _log(f"{case['key']}\t{'exact' if exact_here else 'wrong'}\treliable {int(agreed)}")
    text = "\n".join(
        [
            "Vision alone. Declared before the calls. Not used to choose a method.",
            f"window questions on the 27 plans: {len(cases)}",
            f"success {asked - failed}  missing {failed}  asked {asked}",
            f"precision {exact}/{asked - failed}" if asked != failed else "precision not computed, no success",
            f"badge coverage {reliable}/{asked - failed}" if asked != failed else "badge coverage not computed, no success",
            f"badge precision {reliable_exact}/{reliable}" if reliable else "badge precision not computed, no reliable call",
            "Reliable means the counts match and every detector box has a vision box at IoU 0.3.",
        ]
    )
    swiss_exact = swiss_failed = 0
    swiss_cases = _swiss_cases()
    for case in swiss_cases:
        cached = _cache().get(case["key"])
        result = cached if cached is not None else _ask(Path(case["image"]), case["question"])
        if cached is None:
            _store(case["key"], result)
        if not result.get("ok"):
            swiss_failed += 1
            _log(f"{case['key']}\tmissing\t{result.get('error', '')}")
            continue
        swiss_hit = result.get("count") == case["answer"]
        if swiss_hit:
            swiss_exact += 1
        _log(f"{case['key']}\t{'exact' if swiss_hit else 'wrong'}")
    text += "\n" + "\n".join(
        [
            f"Swiss training sample, not the 15: {len(swiss_cases)}",
            f"success {len(swiss_cases) - swiss_failed}  missing {swiss_failed}  asked {len(swiss_cases)}",
            f"precision {swiss_exact}/{len(swiss_cases) - swiss_failed}" if swiss_cases and swiss_failed != len(swiss_cases) else "precision not computed, no success",
        ]
    )
    _log(text)


if __name__ == "__main__":
    main()
