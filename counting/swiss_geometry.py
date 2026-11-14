"""Swiss split, then one geometry rule on the training buildings only.

The preview has one floor per building, so holding out a building is holding
out a plan. Buildings whose answers were already opened stay in train.
Fifteen other buildings are the final set. Their answers are not read.

The area rule, fixed before this score: sum the shoelace areas of every
ROOM_OUTLINE polyline. Coordinates are metres. Nothing is dropped.

The door definition, fixed before this score: arcs plus polylines on the
DOOR layer. The constant is the most frequent training answer.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path

from audit_swiss import DOORS, TOTAL, WITHIN
from drawing_objects import dataset_root
from export_yolo import questions_path
from read_dxf import read_dxf

ROOT = Path(__file__).resolve().parent
SPLIT = ROOT / "swiss_split.csv"
OUT = ROOT / "swiss_geometry.txt"
SEED = 13
HOLDOUT_BUILDINGS = 15
SEEN = {
    "site11692_bldg18240_floor48820",
    "site1088_bldg2216_floor10132",
    "site421_bldg1097_floor4796",
    "site11711_bldg18268_floor48991",
    "site3421_bldg5295_floor23605",
    "site1138_bldg2292_floor10584",
    "site2152_bldg3002_floor13692",
    "site719_bldg1540_floor6678",
    "site1000_bldg2082_floor9385",
    "site2150_bldg3001_floor13690",
    "site1040_bldg2136_floor9659",
    "site248_bldg456_floor1800",
}


def _building(stem: str) -> str:
    site, building, _floor = stem.split("_")
    return f"{site}_{building}"


def _write_split(stems: list[str]) -> None:
    by_building: dict[str, list[str]] = {}
    for stem in stems:
        by_building.setdefault(_building(stem), []).append(stem)
    opened = {building for building, floors in by_building.items() if any(floor in SEEN for floor in floors)}
    eligible = sorted(building for building in by_building if building not in opened)
    random.Random(SEED).shuffle(eligible)
    holdout = set(eligible[:HOLDOUT_BUILDINGS])
    with SPLIT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["stem", "building", "split"])
        for stem in sorted(stems):
            building = _building(stem)
            role = "holdout" if building in holdout else "train"
            writer.writerow([stem, building, role])


def _load_split(stems: list[str]) -> dict[str, str]:
    if not SPLIT.is_file():
        _write_split(stems)
    rows = list(csv.DictReader(SPLIT.open(encoding="utf-8")))
    return {row["stem"]: row["split"] for row in rows}


def _shoelace(points: tuple[tuple[float, float], ...]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2


def _outline_area(path: Path) -> float:
    return sum(
        _shoelace(item.points)
        for item in read_dxf(path)
        if item.kind == "room_outline" and item.name == "lwpolyline"
    )


def _doors(path: Path) -> tuple[int, int]:
    arcs = polylines = 0
    for item in read_dxf(path):
        if item.kind != "door":
            continue
        if item.name == "arc":
            arcs += 1
        elif item.name == "lwpolyline":
            polylines += 1
    return arcs, polylines


def _close(predicted: float, answer: float) -> bool:
    if answer == 0:
        return predicted == 0
    return abs(predicted - answer) <= WITHIN * abs(answer)


def main() -> None:
    data = dataset_root() / "swiss_dwellings"
    stems = sorted(path.stem for path in data.glob("*.dxf"))
    split = _load_split(stems)
    train = {stem for stem, role in split.items() if role == "train"}
    holdout = {stem for stem, role in split.items() if role == "holdout"}
    area_hits = area_n = 0
    door_hits = door_n = 0
    arc_total = poly_total = 0
    door_answers: list[int] = []
    for line in questions_path().read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if not str(row["path"]).startswith("data/swiss_dwellings/"):
            continue
        stem = Path(row["path"]).stem
        if stem not in train or row["question"] not in (TOTAL, DOORS):
            continue
        path = data / f"{stem}.dxf"
        if row["question"] == TOTAL:
            area_n += 1
            area_hits += int(_close(_outline_area(path), float(row["answer"])))
        else:
            door_n += 1
            arcs, polylines = _doors(path)
            arc_total += arcs
            poly_total += polylines
            answer = int(row["answer"])
            door_answers.append(answer)
            door_hits += int(arcs + polylines == answer)
    counts = Counter(door_answers)
    mode_count = max(counts.values()) if counts else 0
    mode = min(answer for answer, count in counts.items() if count == mode_count) if counts else 0
    text = "\n".join(
        [
            "Split by building. The preview has one floor per building.",
            f"train {len(train)}  holdout {len(holdout)}  holdout answers were not read",
            "Buildings already opened are in train. Seed 13 picks the other fifteen.",
            "",
            "Area rule, fixed before the score: sum of ROOM_OUTLINE polylines, metres, nothing dropped.",
            f"definition on train, within 2%: {area_hits}/{area_n}",
            "",
            "Door definition, fixed before the score: arcs plus polylines on the DOOR layer.",
            f"train door entities arcs {arc_total} polylines {poly_total}",
            f"definition on train {door_hits}/{door_n}",
            f"constant, most frequent training answer {mode}: {mode_count}/{door_n}",
            "The holdout is not scored.",
            "",
        ]
    )
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
