"""What one question costs. No vision call is made.

LLM counts come from the page path: a recognized PDF or IFC template does not
call a model. Pixel windows and doors call the detector and, when a key is
set, one vision call. Sinks, toilets, showers and saunas call the detector only.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

from drawing_objects import dataset_root
from export_yolo import PREVIEW
from file_question import answer_file
from pdf_questions import _factor, _plan
from read_pdf import pdf_lines
from swiss_doors import _strokes
from swiss_index import _smallest
from swiss_text import _rooms

ROOT = Path(__file__).resolve().parent


def _median(values: list[float]) -> float:
    return statistics.median(values)


def _pdf_times() -> dict[str, list[float]]:
    data = dataset_root() / "swiss_dwellings"
    stems = sorted(path.stem for path in data.glob("site*.pdf"))[:10]
    times = {"plan": [], "label": [], "room": [], "door": []}
    for stem in stems:
        pdf = data / f"{stem}.pdf"
        started = time.perf_counter()
        words, polygons, printed, written, _dxf = _plan(pdf, data / f"{stem}.dxf")
        times["plan"].append(time.perf_counter() - started)
        started = time.perf_counter()
        lines = pdf_lines(pdf)
        _rooms(lines)
        times["label"].append(time.perf_counter() - started)
        started = time.perf_counter()
        factor = _factor(printed, written)
        point = next((point for text, point in words if any(character.isdigit() for character in text)), None)
        if point is not None and factor is not None:
            chosen = _smallest([(polygon, polygon.area) for polygon in polygons], point)
            if chosen is not None:
                _ = chosen[1] * factor
        times["room"].append(time.perf_counter() - started)
        started = time.perf_counter()
        _strokes(pdf)
        times["door"].append(time.perf_counter() - started)
    return times


def _ifc_times() -> list[float]:
    data = dataset_root() / "ifc_bench"
    times = []
    for path in sorted(data.glob("*.ifc")):
        payload = path.read_bytes()
        started = time.perf_counter()
        answer_file(path.name, payload, "What is the net floor area of the room 'Office' on 'Level 1', in m²?")
        times.append(time.perf_counter() - started)
    return times


def _detector_times() -> tuple[float, list[float], list[float], list[int]]:
    from PIL import Image

    from engine import detect_openings

    images = sorted(PREVIEW.glob("high_quality_architectural-*.png"))[:6]
    if len(images) < 6:
        images = sorted(PREVIEW.glob("*.png"))[:6]
    first = Image.open(images[0]).convert("RGB")
    started = time.perf_counter()
    detect_openings(first, ("window", "door"))
    startup = time.perf_counter() - started
    wall, cpu, pixels = [], [], []
    for path in images[1:]:
        image = Image.open(path).convert("RGB")
        pixels.append(image.size[0] * image.size[1])
        cpu0 = time.process_time()
        started = time.perf_counter()
        detect_openings(image, ("window", "door"))
        wall.append(time.perf_counter() - started)
        cpu.append(time.process_time() - cpu0)
    return startup, wall, cpu, pixels


def main() -> None:
    pdf = _pdf_times()
    ifc = _ifc_times()
    startup, wall, cpu, pixels = _detector_times()
    lines = [
        "Inference cost. No vision call was made. The 429 measurement is not used as a comparison.",
        "PDF times are 10 revision plans. IFC times are the bench files. Detector times are 5 plans after one warmup.",
        "CPU seconds are process time on this machine, not a claim about another machine.",
        "",
        f"PDF plan read, median { _median(pdf['plan']):.3f} s",
        f"label count after the plan is open, median { _median(pdf['label']):.3f} s",
        f"one room area after the plan is open, median { _median(pdf['room']):.3f} s",
        f"door strokes, median { _median(pdf['door']):.3f} s",
        f"IFC list, median { _median(ifc):.3f} s over {len(ifc)} files",
        f"detector warmup, including the weight load, {startup:.1f} s",
        f"detector per plan, median wall { _median(wall):.3f} s, median CPU { _median(cpu):.3f} s, median pixels {int(_median(pixels))}",
        "",
        "LLM calls on the page path:",
        "labels, areas, apartment count, PDF doors, IFC: 0",
        "sinks, toilets, showers, saunas: 0, detector only",
        "windows and doors on pixels: 0 when no key is set; 1 vision call when a key is set, plus the detector",
    ]
    text = "\n".join(lines) + "\n"
    (ROOT / "cost_table.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
