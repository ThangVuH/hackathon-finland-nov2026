"""Turn a free question into a template and its parameters.

Translations of one question must land on the same template and the same
parameters. A question with no template is unverified: a generic vision
model may answer it, and the badge stays unverified.

Proofs:
- text boxes, for a label count
- room polygons, for an area
- detector boxes, for a drawn object the detector knows
- file quantity, for an IFC total
- unverified vision, when nothing matched
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from export_yolo import questions_path

QUOTED = re.compile(r"[«»„“”\"'‚‘’]\s*([^«»„“”\"'‚‘’]+?)\s*[«»„“”\"'‚‘’]")
CODE = re.compile(r"\b([A-Za-z]*\d+\.\d+)\b")
LABEL_TAIL = re.compile(r"labelled '(.*)' are there on this floor|labelled '(.*)' on this floor")
ROOM_NAME = re.compile(r"\('(.*)'\)")
LETTER = re.compile(r"(?:apartment|appartamento|appartement|wohnung)\s+([A-Za-z])\b", re.IGNORECASE)
ENGLISH = {"how", "what", "which", "could", "is", "are", "can", "on"}

PROOF = {
    "label_count": "text_boxes",
    "labelled_area": "room_polygons",
    "room_area": "room_polygons",
    "apartment_area": "room_polygons",
    "indoor_total": "room_polygons",
    "apartment_count": "text_boxes",
    "window": "detector_boxes",
    "door": "detector_boxes",
    "sink": "detector_boxes",
    "toilet_bowl": "detector_boxes",
    "toilet": "detector_boxes",
    "wc_room": "detector_boxes",
    "basin": "detector_boxes",
    "bath": "detector_boxes",
    "shower": "detector_boxes",
    "kitchen": "detector_boxes",
    "floor": "detector_boxes",
    "sauna": "detector_boxes",
    "wall_length": "file_quantity",
    "wall_volume": "file_quantity",
    "slab_volume": "file_quantity",
    "storey_area": "file_quantity",
    "ifc_room": "file_quantity",
    "fixture_count": "file_quantity",
    "unverified": "unverified_vlm",
}


def _fold(text: str) -> str:
    return text.casefold()


def _has(text: str, *parts: str) -> bool:
    return any(part in text for part in parts)


def _straight(question: str) -> str:
    return question.replace("\u2019", "'").replace("\u2018", "'").replace("\u201a", "'")


def _label_text(question: str) -> str:
    found = LABEL_TAIL.search(question)
    if found is None:
        return ""
    return next(group for group in found.groups() if group is not None)


def _demo(question: str) -> tuple[str, tuple, str] | None:
    path = Path(__file__).resolve().parent / "route_demo.json"
    if not path.is_file():
        return None
    template = json.loads(path.read_text(encoding="utf-8")).get(question)
    if template is None:
        return None
    if template in ("aucun", "none", "unverified"):
        return "unverified", (), PROOF["unverified"]
    return template, (), PROOF.get(template, PROOF["unverified"])


def route(question: str) -> tuple[str, tuple, str]:
    """Return template, parameters, and the proof that would be shown."""
    question = _straight(question)
    preregistered = _demo(question)
    if preregistered is not None:
        return preregistered
    folded = _fold(question)
    quotes = tuple(QUOTED.findall(question))
    code = CODE.search(question)
    letter = LETTER.search(question)
    code_text = code.group(1) if code else ""
    letter_text = letter.group(1).upper() if letter else ""
    area = _has(
        folded,
        "net floor area",
        "net area",
        "superficie netta",
        "surface nette",
        "nettofläche",
        "nettoflaeche",
        "nettoareal",
        "nettowohnfläche",
        "nettowohnflaeche",
        "netopõrandapind",
        "netopohrandapind",
        "nettovolumen",
        "netto-volumen",
    )
    if code_text and area and _has(folded, "room ", "locale ", "pièce ", "piece ", "raum ", "rummet"):
        named = ROOM_NAME.search(question)
        label = named.group(1) if named else (quotes[0] if quotes else "")
        return "room_area", (code_text, label), PROOF["room_area"]
    if letter_text and area:
        return "apartment_area", (letter_text,), PROOF["apartment_area"]
    if area and _has(folded, "labelled", "denominat", "désign", "design", "bezeichn"):
        return "labelled_area", (_label_text(question) or (quotes[0] if quotes else ""),), PROOF["labelled_area"]
    if _has(
        folded,
        "numbered indoor",
        "interni numerati",
        "intérieures numérot",
        "interieures numerot",
        "nummerierten innen",
    ):
        return "indoor_total", (), PROOF["indoor_total"]
    if _has(folded, "rooms labelled", "denominazione", "bezeichnung", "désignation", "designation"):
        return "label_count", (_label_text(question) or (quotes[0] if quotes else ""),), PROOF["label_count"]
    if _has(folded, "apartments", "appartamenti", "appartements", "wohnungen") and not area:
        return "apartment_count", (), PROOF["apartment_count"]
    if _has(folded, "sinks and wash", "pesu- ja tiskiallasta"):
        return "sink", ("sink",), PROOF["sink"]
    if _has(folded, "showers and bathtub", "suihkua ja kylpyammetta"):
        return "shower", ("shower",), PROOF["shower"]
    if _has(folded, "bathtub", "vasche da bagno", "badewanne", "baignoire"):
        return "bath", ("bath",), PROOF["bath"]
    if _has(folded, "toilet bowl", "wc seat", "wc-istuin"):
        return "toilet_bowl", ("toilet",), PROOF["toilet_bowl"]
    if _has(folded, "wc-til", "separate wc", "wc rooms", "wc-tila"):
        return "wc_room", ("wc_room",), PROOF["wc_room"]
    if _has(folded, "washbasin", "lavabi", "lavabo"):
        return "basin", ("basin",), PROOF["basin"]
    if _has(folded, "toilet", " wc", "wcs"):
        return "toilet", ("toilet",), PROOF["toilet"]
    if _has(folded, "kitchen", "keittiö", "keittio"):
        return "kitchen", ("kitchen",), PROOF["kitchen"]
    if _has(folded, "sauna"):
        return "sauna", ("sauna",), PROOF["sauna"]
    if _has(folded, "floors", "storeys", "kerrosta", "kerrosta"):
        return "floor", ("floor",), PROOF["floor"]
    if _has(folded, "length of all walls", "længde af alle vægge", "laengde af alle vaegge", "wie lang sind alle wände", "wie lang sind alle wande"):
        return "wall_length", (quotes[-1] if quotes else "",), PROOF["wall_length"]
    if _has(folded, "nettovolumen", "netto-volumen", "net volume") and _has(folded, "slab", "dæk", "daek", "plader", "decken"):
        return "slab_volume", (quotes[-1] if quotes else "",), PROOF["slab_volume"]
    if _has(folded, "nettovolumen", "netto-volumen", "net volume") and _has(folded, "wall", "væg", "vaeg", "wände", "wande"):
        return "wall_volume", (quotes[-1] if quotes else "",), PROOF["wall_volume"]
    if _has(folded, "all rooms (spaces)", "kõigi ruumide", "koigi ruumide", "alle rum"):
        return "storey_area", (quotes[-1] if quotes else "",), PROOF["storey_area"]
    if area and _has(folded, " of the room", "af rummet", "ruumi "):
        return "ifc_room", (quotes[0] if quotes else "", quotes[-1] if quotes else ""), PROOF["ifc_room"]
    if _has(folded, "sanitary fixture"):
        return "fixture_count", ("fixture",), PROOF["fixture_count"]
    if _has(folded, "window", "ikkuna", "finestre", "fenêtre", "fenetre", "fenster", "vindue", "aken", "akent"):
        return "window", ("window",), PROOF["window"]
    if _has(folded, "door", "ovea", "ovia", "ovi", "porte", "türen", "turen", "døre", "dore", " ust"):
        return "door", ("door",), PROOF["door"]
    return "unverified", (), PROOF["unverified"]


def _pairs(path: Path) -> list[list[str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    groups = []
    index = 0
    while index < len(rows):
        question = rows[index]["question"]
        if question.split()[0].casefold() not in ENGLISH:
            index += 1
            continue
        group = [question]
        nxt = index + 1
        while nxt < len(rows):
            other = rows[nxt]
            if other["path"] != rows[index]["path"] or other["answer"] != rows[index]["answer"]:
                break
            if other["question"].split()[0].casefold() in ENGLISH:
                break
            group.append(other["question"])
            nxt += 1
        if len(group) > 1:
            groups.append(group)
        index = nxt if nxt > index else index + 1
    return groups


def main() -> None:
    groups = _pairs(questions_path())
    agree = 0
    by_lang: Counter = Counter()
    by_lang_ok: Counter = Counter()
    misses: Counter = Counter()
    recognized = 0
    for group in groups:
        base = route(group[0])
        if base[0] != "unverified":
            recognized += 1
        for other in group[1:]:
            lang = other.split()[0]
            by_lang[lang] += 1
            if route(other) == base:
                agree += 1
                by_lang_ok[lang] += 1
            else:
                misses[(base[0], route(other)[0], lang)] += 1
    total = sum(by_lang.values())
    lines = [
        "Preview questions. A pair agrees when every translation has the same template and parameters.",
        f"groups {len(groups)}  translation lines {total}  agree {agree}/{total}",
        f"groups whose English question has a template {recognized}/{len(groups)}",
    ]
    for lang, count in by_lang.most_common():
        lines.append(f"  {lang}  {by_lang_ok[lang]}/{count}")
    lines.append("largest disagreements:")
    for key, count in misses.most_common(12):
        lines.append(f"  {count}  {key}")
    text = "\n".join(lines) + "\n"
    out = Path(__file__).resolve().parent / "route_question.txt"
    out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
