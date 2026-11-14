"""Pick the checkpoint by exact counts on the validation plans.

Rules fixed before any look at the 27 official test plans, and before using
validation scores to choose:

- The epoch is chosen first, with one global cutoff of 0.40 on every class.
  A tie keeps the earlier epoch. Ultralytics names that file epoch0.pt for
  the first completed epoch.
- Only that epoch then gets a per-class cutoff. The grid is 0.15, 0.30,
  0.45, 0.60. The cutoff is the middle of the contiguous plateau that
  matches the best exact count, not the maximum of that plateau. An even
  plateau uses the mean of its two central grid values. Two separate
  plateaus of equal length: the one nearer the middle of the grid, then
  the earlier one.
- The sauna question is scored with the sauna-stove count. That comparison
  cannot pass the definition ceiling. Sauna counts are written as fractions,
  not percentages.
- Kitchen is unmeasurable: every test answer is the training mode, and
  validation has one other plan. It is left out of the epoch choice, the
  cutoffs, and the global total.
- The choice does not run before 22:00 Europe/Paris on 14 Nov 2026, unless
  all 30 epoch files are already on disk. The clock is not moved after
  seeing a score.
- Candidates are the even epoch indexes at or after 10 (10, 12, 14, ...).
  If none of those files exist, the even indexes that do exist are used.
  This subset was fixed before any validation score.
- Each candidate is predicted once at confidence 0.05 and cached. The
  global cutoff and the class grid are applied to that cache, offline.
- max_det is 2000, the same value as the live predictor. A tile that
  returns that many boxes is reported. Within a tile, Ultralytics merges
  at IoU 0.5 before the cache. Across tiles, boxes are merged only after
  the confidence cutoff, by the same NMS as the live keeper.
- The 27 test plans are scored once, after the epoch and the cutoffs are
  frozen. Nothing in the choice reads them. The test report also gives the
  exact count on plans whose answer is not the training-set mode.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
from ultralytics import YOLO

from baseline import train_modes
from evaluate_counts import MAX_DET, nms
from export_yolo import PREVIEW, ROOT, TILE, load_splits, tile_origins
from gold import load_answers
from label_rules import CLASS_ID

NAMES = {index: name for name, index in CLASS_ID.items()}
QUESTION_CLASS = {name: name for name in CLASS_ID}
QUESTION_CLASS["sauna"] = "sauna_stove"
GLOBAL_THRESHOLD = 0.40
CLASS_GRID = (0.15, 0.30, 0.45, 0.60)
PREDICT_CONF = 0.05
UNMEASURED = {"kitchen"}
DEADLINE = datetime(2026, 11, 14, 22, 0, tzinfo=ZoneInfo("Europe/Paris"))
RUN = ROOT / "runs" / "multiclass" / "weights"
CANDIDATES = RUN / "selection_epochs.txt"
DET_CACHE = ROOT / "runs" / "multiclass" / "det_cache"
OUT = ROOT / "exact_selection.txt"


def _counts(detections: list[tuple[str, float, list[float]]], thresholds: dict[str, float]) -> dict[str, int]:
    grouped: dict[str, list[list[float]]] = defaultdict(list)
    scores: dict[str, list[float]] = defaultdict(list)
    for name, score, box in detections:
        if score < thresholds.get(name, 1.1):
            continue
        grouped[name].append(box)
        scores[name].append(score)
    return {name: len(nms(grouped[name], scores[name])) for name in CLASS_ID}


def _predict(model: YOLO, style: str, sample_id: str) -> list[tuple[str, float, list[float]]]:
    image = Image.open(PREVIEW / f"{style}-{sample_id}.png").convert("RGB")
    width, height = image.size
    found: list[tuple[str, float, list[float]]] = []
    for origin_x, origin_y, tile_w, tile_h in tile_origins(width, height):
        crop = image.crop((origin_x, origin_y, origin_x + tile_w, origin_y + tile_h))
        result = model.predict(
            crop, imgsz=TILE, conf=PREDICT_CONF, iou=0.5, max_det=MAX_DET, verbose=False, device="cpu"
        )[0]
        if result.boxes is not None and len(result.boxes) >= MAX_DET:
            print(f"  max_det reached {style}-{sample_id} {origin_x},{origin_y}", flush=True)
        if result.boxes is None or len(result.boxes) == 0:
            continue
        for box, score, class_id in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
        ):
            x0, y0, x1, y1 = box
            found.append(
                (
                    NAMES[int(class_id)],
                    float(score),
                    [x0 + origin_x, y0 + origin_y, x1 + origin_x, y1 + origin_y],
                )
            )
    image.close()
    return found


def _gold(split: str) -> dict[str, dict[tuple[str, str], int]]:
    splits = load_splits()
    grouped: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for (style, sample_id, kind), answer in load_answers().items():
        if splits.get((style, sample_id)) != split:
            continue
        if kind not in QUESTION_CLASS:
            continue
        grouped[QUESTION_CLASS[kind]][(style, sample_id)] = answer
    return grouped


def _exact(cache: dict, gold: dict[str, dict[tuple[str, str], int]], thresholds: dict[str, float]) -> int:
    exact = 0
    for kind, rows in gold.items():
        cutoff = {kind: thresholds[kind]}
        for key, answer in rows.items():
            exact += int(_counts(cache[key], cutoff).get(kind, 0) == answer)
    return exact


def _middle(span: list[float]) -> float:
    if len(span) % 2 == 1:
        return span[len(span) // 2]
    left = span[len(span) // 2 - 1]
    right = span[len(span) // 2]
    return (left + right) / 2


def _middle_index(span: list[float]) -> float:
    positions = [CLASS_GRID.index(threshold) for threshold in span]
    if len(positions) % 2 == 1:
        return float(positions[len(positions) // 2])
    left = positions[len(positions) // 2 - 1]
    right = positions[len(positions) // 2]
    return (left + right) / 2


def _plateau(scores: dict[float, int]) -> float:
    """Middle of the contiguous grid span that ties the best exact count.

    Distance is measured in grid steps, so 0.15 and 0.60 are equally far
    from the centre and the earlier one is kept.
    """
    best = max(scores[threshold] for threshold in CLASS_GRID)
    chosen = [threshold for threshold in CLASS_GRID if scores[threshold] == best]
    spans: list[list[float]] = [[chosen[0]]]
    for threshold in chosen[1:]:
        if CLASS_GRID.index(threshold) == CLASS_GRID.index(spans[-1][-1]) + 1:
            spans[-1].append(threshold)
        else:
            spans.append([threshold])
    center = (len(CLASS_GRID) - 1) / 2
    span = max(
        spans,
        key=lambda item: (len(item), -abs(_middle_index(item) - center), -CLASS_GRID.index(item[0])),
    )
    return _middle(span)


def _choose_thresholds(cache: dict, gold: dict[str, dict[tuple[str, str], int]]) -> dict[str, float]:
    chosen = {}
    for kind, rows in gold.items():
        scores = {
            threshold: _exact(cache, {kind: rows}, {kind: threshold})
            for threshold in CLASS_GRID
        }
        chosen[kind] = _plateau(scores)
    return chosen


def _candidate_epochs(found: list[tuple[int, Path]]) -> list[tuple[int, Path]]:
    """Even epochs from 10 up. Fixed before any validation score."""
    chosen = [item for item in found if item[0] >= 10 and item[0] % 2 == 0]
    if chosen:
        return chosen
    return [item for item in found if item[0] % 2 == 0]


def _checkpoints() -> list[tuple[int, Path]]:
    if CANDIDATES.is_file():
        names = [line.strip() for line in CANDIDATES.read_text(encoding="utf-8").splitlines() if line.strip()]
        paths = [RUN / name for name in names]
    else:
        paths = list(RUN.glob("epoch*.pt"))
    found = []
    for path in paths:
        if path.is_file():
            found.append((int(path.stem.removeprefix("epoch")), path))
    return _candidate_epochs(sorted(found))


def _ready() -> None:
    now = datetime.now(DEADLINE.tzinfo)
    on_disk = list(RUN.glob("epoch*.pt"))
    if now >= DEADLINE or len(on_disk) >= 30:
        return
    raise SystemExit(
        f"selection waits until {DEADLINE.isoformat()} "
        f"({len(on_disk)} epoch files now). The deadline is not moved after seeing a score."
    )


def _cache(model: YOLO, keys: set[tuple[str, str]]) -> dict:
    cache = {}
    for index, (style, sample_id) in enumerate(sorted(keys), start=1):
        print(f"  predict {index}/{len(keys)} {style}-{sample_id}", flush=True)
        cache[(style, sample_id)] = _predict(model, style, sample_id)
    return cache


def _cached(epoch: int, model: YOLO, keys: set[tuple[str, str]]) -> dict:
    """Predict each plan once at confidence 0.05. Cutoffs only filter the file."""
    path = DET_CACHE / f"epoch{epoch}.json"
    stored: dict[tuple[str, str], list] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        stored = {tuple(key.split("|", 1)): rows for key, rows in raw.items()}
    missing = {key for key in keys if key not in stored}
    if missing:
        stored.update(_cache(model, missing))
        serial = {f"{style}|{sample_id}": rows for (style, sample_id), rows in stored.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(serial), encoding="utf-8")
    return {key: stored[key] for key in keys}


def _keys(gold: dict[str, dict[tuple[str, str], int]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for rows in gold.values():
        keys.update(rows)
    return keys


def _measurable(gold: dict[str, dict[tuple[str, str], int]]) -> dict[str, dict[tuple[str, str], int]]:
    return {kind: rows for kind, rows in gold.items() if kind not in UNMEASURED}


def main() -> None:
    _ready()
    validation = _measurable(_gold("val"))
    val_keys = _keys(validation)
    global_cutoff = {kind: GLOBAL_THRESHOLD for kind in validation}
    best: tuple[int, int, dict, Path] | None = None
    checkpoints = _checkpoints()
    print("candidates", [epoch for epoch, _path in checkpoints], flush=True)
    for epoch, path in checkpoints:
        print(f"epoch {epoch}", flush=True)
        model = YOLO(str(path))
        cache = _cached(epoch, model, val_keys)
        exact = _exact(cache, validation, global_cutoff)
        print(f"  val exact at {GLOBAL_THRESHOLD:.2f} {exact}", flush=True)
        if best is None or (exact, -epoch) > (best[0], -best[1]):
            best = (exact, epoch, cache, path)
    if best is None:
        raise SystemExit(f"no epoch checkpoints in {RUN}")
    exact, epoch, cache, path = best
    thresholds = _choose_thresholds(cache, validation)
    lines = [
        "Epoch chosen on validation at a global cutoff of 0.40. A tie keeps the earlier epoch.",
        "Kitchen is unmeasurable and is not part of this choice or of the total.",
        "Class cutoffs are then the middle of the validation plateau on 0.15, 0.30, 0.45, 0.60.",
        f"checkpoint {path.name} ultralytics_epoch {epoch} val_exact_at_0.40 {exact}",
        "cutoffs",
    ]
    lines.extend(f"  {kind} {threshold:.2f}" for kind, threshold in sorted(thresholds.items()))
    print("SELECTION FROZEN", flush=True)
    test = _gold("test")
    measurable = _measurable(test)
    modes = train_modes()
    model = YOLO(str(path))
    test_cache = _cached(epoch, model, _keys(measurable))
    lines.append("test, scored once after the choice")
    lines.append("counts are exact/n, not percentages")
    total_exact = 0
    total_count = 0
    total_non_exact = 0
    total_non_count = 0
    for kind, rows in sorted(test.items()):
        if kind in UNMEASURED:
            lines.append(f"  {kind} unmeasurable {len(rows)} questions, not in the total")
            continue
        question = "sauna" if kind == "sauna_stove" else kind
        mode = modes[question]
        kind_exact = sum(
            int(_counts(test_cache[key], thresholds).get(kind, 0) == answer) for key, answer in rows.items()
        )
        nonmodal = [(key, answer) for key, answer in rows.items() if answer != mode]
        non_exact = sum(
            int(_counts(test_cache[key], thresholds).get(kind, 0) == answer) for key, answer in nonmodal
        )
        total_exact += kind_exact
        total_count += len(rows)
        total_non_exact += non_exact
        total_non_count += len(nonmodal)
        lines.append(
            f"  {kind} {kind_exact}/{len(rows)}  nonmodal {non_exact}/{len(nonmodal)}  train_mode {mode}"
        )
    lines.append(f"  all {total_exact}/{total_count}")
    lines.append(f"  nonmodal {total_non_exact}/{total_non_count}")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    chosen = RUN / "best_exact.pt"
    chosen.write_bytes(path.read_bytes())
    print(text, end="")


if __name__ == "__main__":
    main()
