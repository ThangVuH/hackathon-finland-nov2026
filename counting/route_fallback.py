"""When keywords miss, a model may only pick a known template or none.

The sentences below are paraphrases in Spanish, Swedish, Dutch and Polish.
None of those languages is in the preview keyword list. The key is read
from the site env file and is not printed.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from route_question import PROOF, route

ROOT = Path(__file__).resolve().parent
ENV = ROOT.parent / "STOA-eyes" / ".env"
TEMPLATES = tuple(name for name in PROOF if name != "unverified") + ("aucun",)
CASES = [
    ("es", "¿Cuántas ventanas se ven en esta planta?", "window"),
    ("sv", "Hur många dörrar finns inritade på den här ritningen?", "door"),
    ("nl", "Hoeveel deuren staan er op deze plattegrond?", "door"),
    ("pl", "Ile okien widać na tym rzucie kondygnacji?", "window"),
    ("es", "¿Cuál es la superficie neta de la habitación 2.10?", "room_area"),
    ("sv", "Hur stor är den sammanlagda ytan för rum märkta Zimmer?", "labelled_area"),
    ("nl", "Wat is de netto-oppervlakte van appartement A?", "apartment_area"),
    ("pl", "Jaki jest numer telefonu architekta?", "aucun"),
]


def _key() -> tuple[str, str]:
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values.get("STOA_API_KEY", ""), values.get("STOA_MODEL", "gemini-3.6-flash")


CACHE = ROOT / "route_cache.json"
MAX_IN_FLIGHT = 2
_flight = 0
_flight_lock = __import__("threading").Lock()


def _cache() -> dict[str, str]:
    if not CACHE.is_file():
        return {}
    return json.loads(CACHE.read_text(encoding="utf-8"))


def _store(question: str, template: str) -> None:
    cached = _cache()
    cached[question] = template
    CACHE.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")


def classify(question: str) -> str:
    keyword = route(question)
    if keyword[0] != "unverified":
        return keyword[0]
    cached = _cache().get(question)
    if cached:
        return cached
    key, model = _key()
    if not key:
        return "unverified"
    prompt = (
        "Classify the question into exactly one template from this list, or aucun. "
        "Reply with JSON {\"template\": \"...\"} and nothing else.\n"
        + ", ".join(TEMPLATES)
        + "\nQuestion: "
        + question
    )
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": "You only choose a template name from the list."}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
    ).encode("utf-8")
    global _flight
    for attempt in range(4):
        with _flight_lock:
            if _flight >= MAX_IN_FLIGHT:
                time.sleep(2)
            _flight += 1
        try:
            request = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=body,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            chosen = json.loads(text).get("template", "aucun")
            chosen = chosen if chosen in TEMPLATES else "aucun"
            _store(question, chosen)
            return chosen
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
            time.sleep(2 ** attempt)
        finally:
            with _flight_lock:
                _flight = max(0, _flight - 1)
    return "unverified"


def main() -> None:
    lines = ["Keyword miss, then the model. Languages are not in the preview.", ""]
    hits = 0
    for lang, question, expected in CASES:
        keyword = route(question)[0]
        chosen = classify(question)
        hits += int(chosen == expected)
        lines.append(f"{lang}  keyword {keyword:12}  model {chosen:16}  expected {expected}")
        lines.append(f"    {question}")
    lines.append("")
    lines.append(f"model matches the expected template {hits}/{len(CASES)}")
    text = "\n".join(lines) + "\n"
    (ROOT / "route_fallback.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
