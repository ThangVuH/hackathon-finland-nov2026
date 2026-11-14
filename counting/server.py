"""Counting service.

Run from this folder:

    python -m uvicorn server:app --port 8765

POST /detect with a floor-plan image and a question. The response is the
detector total, its rectangles on the 0-1000 scale, and a confidence index.
Out-of-scope files are refused here, before the network runs.

POST /arbitrate joins that result with the vision model's boxes.
"""

from __future__ import annotations

from io import BytesIO

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from arbitrate import arbitrate
from engine import detect_openings
from file_question import answer_file
from questions import question_type
from scope import assess, name_reason

app = FastAPI(title="Stoa checker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/detect")
async def detect(file: UploadFile = File(...), question: str = Form(...)) -> dict:
    filename = file.filename or "drawing.png"
    kind = question_type(question)
    reason = name_reason(filename)
    if reason:
        return {
            "ok": True,
            "scope": "out_of_scope",
            "question_type": kind,
            "reason": reason,
            "confidence": 0,
            "items": [],
        }
    try:
        image = Image.open(BytesIO(await file.read())).convert("RGB")
    except Exception:
        return {
            "ok": False,
            "error": "The file could not be read as an image.",
            "scope": "out_of_scope",
            "question_type": kind,
            "reason": "Unreadable file.",
            "confidence": 0,
            "items": [],
        }
    reason = assess(filename, image)
    if reason:
        return {
            "ok": True,
            "scope": "out_of_scope",
            "question_type": kind,
            "reason": reason,
            "confidence": 0,
            "items": [],
        }
    if kind == "other":
        return {
            "ok": True,
            "scope": "floor_plan",
            "question_type": kind,
            "reason": "",
            "confidence": 0,
            "items": [],
        }
    kinds = ("window", "door") if kind == "both" else (kind,)
    found = detect_openings(image, kinds)
    return {
        "ok": True,
        "scope": "floor_plan",
        "question_type": kind,
        "reason": "",
        **found,
    }


@app.post("/file")
async def read_file(file: UploadFile = File(...), question: str = Form(...)) -> dict:
    data = await file.read()
    result = answer_file(file.filename or "drawing", data, question)
    result["ok"] = True
    return result


@app.post("/arbitrate")
async def arbitrate_route(body: dict) -> dict:
    vision = body.get("vision")
    result = arbitrate(
        str(body.get("question_type") or "other"),
        list(body.get("detector_items") or []),
        float(body.get("confidence") or 0),
        vision if isinstance(vision, dict) else None,
    )
    result["ok"] = True
    return result
