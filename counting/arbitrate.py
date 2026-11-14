"""Agree two independent counts, or hand the drawing to a person.

The detector proposes the total. The vision model confirms it or contradicts it.
Reliable means the totals match and every box has a partner above MATCH_IOU.
Otherwise the unmatched boxes are marked for a one-click keep or drop.
"""

from __future__ import annotations

from count_metrics import iou
from questions import kind_of

MATCH_IOU = 0.3
LABEL = {"window": "Window", "door": "Door"}
PLURAL = {"window": "windows", "door": "doors"}


def to_milli(box: list[float], width: int, height: int) -> dict[str, int]:
    """Pixel xyxy to the 0-1000 [ymin, xmin, ymax, xmax] scale the canvas uses.

    A window can be a couple of pixels on a large sheet. Rounding must not
    collapse that box to zero area, or the count would drop it.
    """

    def span(start: float, end: float, size: int) -> tuple[int, int]:
        if size <= 0:
            return 0, 0
        lo = min(start, end) / size * 1000
        hi = max(start, end) / size * 1000
        left = int(min(1000, max(0, round(lo))))
        right = int(min(1000, max(0, round(hi))))
        if right <= left and hi > lo:
            right = min(1000, left + 1)
        return left, right

    x0, y0, x1, y1 = box
    xmin, xmax = span(x0, x1, width)
    ymin, ymax = span(y0, y1, height)
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}


def _xyxy(item: dict) -> list[float]:
    return [float(item["xmin"]), float(item["ymin"]), float(item["xmax"]), float(item["ymax"])]


def _item_kind(item: dict) -> str | None:
    return kind_of(str(item.get("kind") or "")) or kind_of(str(item.get("label") or ""))


def match_indices(detector: list[dict], vision: list[dict], threshold: float = MATCH_IOU) -> set[tuple[int, int]]:
    """Greedy one-to-one match. Higher-scoring detector boxes claim a vision box first."""
    order = sorted(range(len(detector)), key=lambda index: float(detector[index].get("score") or 0), reverse=True)
    used: set[int] = set()
    pairs: set[tuple[int, int]] = set()
    for index in order:
        best = None
        best_overlap = threshold
        box = _xyxy(detector[index])
        for other, candidate in enumerate(vision):
            if other in used:
                continue
            overlap = iou(box, _xyxy(candidate))
            if overlap >= best_overlap:
                best_overlap = overlap
                best = other
        if best is not None:
            used.add(best)
            pairs.add((index, best))
    return pairs


def reliability_score(detector: list[dict], vision: list[dict]) -> float:
    """1 only when the totals match and every box overlaps a partner.

    A count mismatch stays strictly below 1, so it can never be marked reliable.
    Equal empty counts score 1: both engines saw nothing.
    """
    if len(detector) != len(vision):
        matched = len(match_indices(detector, vision))
        overlap = matched / max(len(detector), len(vision), 1)
        return min(0.5, overlap * 0.5)
    if not detector:
        return 1.0
    return len(match_indices(detector, vision)) / len(detector)


def selective_table(plans: list[dict], thresholds: list[float] | None = None) -> list[dict]:
    """Precision among plans the checker would accept, against the share it accepts.

    Each plan has `exact` (its automatic count matches the gold total) and `score`.
    """
    if thresholds is None:
        thresholds = [0.0, 0.25, 0.5, 0.75, 1.0]
    total = len(plans)
    rows = []
    for threshold in thresholds:
        accepted = [plan for plan in plans if plan["score"] >= threshold]
        exact = sum(1 for plan in accepted if plan["exact"])
        rows.append(
            {
                "threshold": threshold,
                "accepted": len(accepted),
                "plans": total,
                "coverage": (len(accepted) / total) if total else 0.0,
                "precision": (exact / len(accepted)) if accepted else None,
            }
        )
    return rows


def _copy(item: dict, **flags) -> dict:
    kept = {
        "kind": item.get("kind") or "",
        "label": item.get("label") or "",
        "ymin": int(item["ymin"]),
        "xmin": int(item["xmin"]),
        "ymax": int(item["ymax"]),
        "xmax": int(item["xmax"]),
        "score": item.get("score"),
    }
    kept.update(flags)
    return kept


def _class_items(items: list[dict], kind: str) -> list[dict]:
    return [item for item in items if _item_kind(item) == kind]


def _sentence(kind: str, detector_count: int, vision_count: int | None, agreed: bool, vision_missing: bool) -> str:
    plural = PLURAL[kind]
    if vision_missing:
        return f"The detector counts {detector_count} {plural}. The vision model did not confirm it, so this stays unchecked."
    if agreed:
        return f"Both engines count {detector_count} {plural}, and the boxes overlap. This count is reliable."
    vision_text = "no answer" if vision_count is None else str(vision_count)
    return (
        f"The detector counts {detector_count} {plural}; the vision model counts {vision_text}. "
        "Highlighted boxes are the disagreement. Click one to keep it or drop it."
    )


def arbitrate(
    question_type: str,
    detector_items: list[dict],
    confidence: float,
    vision: dict | None,
) -> dict:
    """Build the payload the canvas already knows how to draw.

    `vision` is None when the vision call did not run. When it ran, it has
    `available`, `answer`, `object_type`, `count` and `items`.
    """
    if question_type == "other":
        return _unverified(vision)

    kinds = ["window", "door"] if question_type == "both" else [question_type]
    vision_items = list((vision or {}).get("items") or [])
    vision_missing = vision is None or not vision.get("available", False)
    if vision_items and vision and vision.get("object_type") and not any(_item_kind(item) for item in vision_items):
        for item in vision_items:
            item["kind"] = vision["object_type"]

    merged = []
    sentences = []
    scores = []
    agreed_all = True
    for kind in kinds:
        detected = _class_items(detector_items, kind)
        seen = [] if vision_missing else _class_items(vision_items, kind)
        score = 0.0 if vision_missing else reliability_score(detected, seen)
        scores.append(score)
        agreed = score >= 1.0
        agreed_all = agreed_all and agreed
        pairs = set() if vision_missing else match_indices(detected, seen)
        matched_detector = {pair[0] for pair in pairs}
        matched_vision = {pair[1] for pair in pairs}
        for index, item in enumerate(detected):
            merged.append(
                _copy(
                    item,
                    kind=kind,
                    source="both" if index in matched_detector else "detector",
                    disputed=index not in matched_detector,
                    included=True,
                )
            )
        for index, item in enumerate(seen):
            if index in matched_vision:
                continue
            merged.append(
                _copy(
                    item,
                    kind=kind,
                    label=item.get("label") or LABEL[kind],
                    source="vision",
                    disputed=True,
                    included=False,
                )
            )
        sentences.append(_sentence(kind, len(detected), None if vision_missing else len(seen), agreed, vision_missing))

    included = sum(1 for item in merged if item["included"])
    verdict = "reliable" if agreed_all else "review"
    if question_type == "both":
        object_type = "Opening"
    else:
        object_type = LABEL[question_type]
    warning = "" if verdict == "reliable" else "Click a highlighted box to keep it in the count or drop it."
    if vision_missing:
        warning = "The vision model did not answer, so the detector count is not confirmed."
    return {
        "answer": " ".join(sentences),
        "object_type": object_type,
        "count": included,
        "items": merged,
        "verdict": verdict,
        "warning": warning,
        "confidence": round(float(confidence), 4),
        "score": min(scores) if scores else 0.0,
    }


def _unverified(vision: dict | None) -> dict:
    if vision is None or not vision.get("available", False):
        reason = (vision or {}).get("error") or "The vision model is not configured, and this question is outside windows and doors."
        return {
            "answer": reason,
            "object_type": "",
            "count": 0,
            "items": [],
            "verdict": "refused",
            "warning": "No count was invented.",
            "confidence": 0.0,
            "score": 0.0,
        }
    items = []
    for item in vision.get("items") or []:
        items.append(
            _copy(
                item,
                kind=item.get("kind") or vision.get("object_type") or "",
                source="vision",
                disputed=False,
                included=True,
            )
        )
    answer = (vision.get("answer") or "").strip()
    warning = "Windows and doors are the classes the detector checks. This answer is the vision model alone."
    return {
        "answer": answer,
        "object_type": vision.get("object_type") or "",
        "count": len(items) if items else int(vision.get("count") or 0),
        "items": items,
        "verdict": "unverified",
        "warning": warning,
        "confidence": 0.0,
        "score": 0.0,
    }
