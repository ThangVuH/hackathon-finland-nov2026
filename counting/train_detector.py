"""Train the multi-class detector.

The run is counting/runs/multiclass. It does not replace the window-door
weights. Ultralytics still writes best.pt by mAP. select_exact.py chooses
the epoch by exact validation counts and writes best_exact.pt.
"""

import sys
from pathlib import Path

import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
LAST = ROOT / "runs" / "multiclass" / "weights" / "last.pt"


def main() -> None:
    if "--resume" in sys.argv:
        if not LAST.is_file():
            raise SystemExit(f"nothing to resume at {LAST}")
        YOLO(str(LAST)).train(resume=True)
        return
    device = "0" if torch.cuda.is_available() else "cpu"
    model = YOLO("yolo11n.pt")
    model.train(
        data=str(ROOT / "yolo-multiclass" / "dataset.yaml"),
        epochs=30,
        imgsz=640,
        batch=8,
        device=device,
        workers=0,
        patience=100,
        save_period=1,
        cache="ram" if device == "cpu" else False,
        project=str(ROOT / "runs"),
        name="multiclass",
        exist_ok=True,
        plots=False,
        hsv_h=0.0,
        hsv_s=0.15,
        hsv_v=0.15,
        degrees=0.0,
        flipud=0.5,
        fliplr=0.5,
        mosaic=0.8,
        scale=0.2,
        close_mosaic=6,
    )


if __name__ == "__main__":
    main()
