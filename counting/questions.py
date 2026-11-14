"""Which count a question is asking for.

Windows and doors are the classes the trained detector can check.
Anything else is left to the vision model, with an explicit warning.
"""

from __future__ import annotations

import re
import unicodedata

QuestionType = str  # "window" | "door" | "both" | "other"


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode().lower()


def asked_kinds(question: str) -> list[str]:
    text = fold(question)
    found = []
    if re.search(r"\b(windows?|fenetres?|ikkuna\w*|finestr\w*|fenster\w*|vindue\w*|aken\w*)\b", text):
        found.append("window")
    if re.search(r"\b(doors?|portes?|ovea|ovia|ovi|turen|dore\w*|ust)\b", text):
        found.append("door")
    return found


def question_type(question: str) -> QuestionType:
    text = fold(question)
    if re.search(r"\bshowers?\b", text) or "suihku" in text:
        return "shower"
    if re.search(r"\bsinks?\b", text) or "tiskiallas" in text:
        return "sink"
    if re.search(r"\btoilets?\b", text) or re.search(r"\bwc\b", text):
        return "toilet"
    if "sauna" in text:
        return "sauna_stove"
    kinds = asked_kinds(question)
    if len(kinds) == 2:
        return "both"
    if len(kinds) == 1:
        return kinds[0]
    return "other"


def kind_of(value: str) -> str | None:
    kinds = asked_kinds(value)
    if len(kinds) == 1:
        return kinds[0]
    return None
