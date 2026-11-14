"""Train the window and door detector on the CPU.

The checkpoint is written to counting/runs/window-door. Validation during
training uses the tiled val split, so it does not see the held-out plans.
"""

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent


def main() -> None:
    model = YOLO("yolo11n.pt")
    model.train(
        data=str(ROOT / "yolo" / "dataset.yaml"),
        epochs=30,
        imgsz=640,
        batch=8,
        device="cpu",
        workers=0,
        patience=8,
        cache="ram",
        project=str(ROOT / "runs"),
        name="window-door",
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
