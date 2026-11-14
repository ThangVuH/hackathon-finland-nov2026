"""Run the frozen epoch choice at the deadline.

The deadline is 22:00 Europe/Paris on 14 Nov 2026. If all 30 epoch files
exist earlier, the choice runs then. It does not look at a score to wait
longer. Training is stopped so the scoring has the CPU. Only epoch files
whose size was stable before that stop are candidates.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "runs" / "multiclass" / "weights"
DEADLINE = datetime(2026, 11, 14, 22, 0, tzinfo=ZoneInfo("Europe/Paris"))


def _sizes() -> dict[str, int]:
    return {path.name: path.stat().st_size for path in RUN.glob("epoch*.pt")}


def _stable() -> list[str]:
    first = _sizes()
    time.sleep(3)
    second = _sizes()
    return sorted(name for name, size in second.items() if first.get(name) == size and size > 0)


def _stop_training() -> None:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*train_detector.py*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=False)


def main() -> None:
    while True:
        now = datetime.now(DEADLINE.tzinfo)
        ready = len(list(RUN.glob("epoch*.pt")))
        if now >= DEADLINE or ready >= 30:
            print(f"selection starts {now.isoformat()} with {ready} epoch files", flush=True)
            break
        time.sleep(60)
    names = _stable()
    (RUN / "selection_epochs.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    print("candidates", ", ".join(names), flush=True)
    _stop_training()
    subprocess.run([sys.executable, str(ROOT / "select_exact.py")], check=False)


if __name__ == "__main__":
    main()
