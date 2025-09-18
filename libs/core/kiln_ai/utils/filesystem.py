import os
import subprocess
import sys
from pathlib import Path


def open_folder(path: str | Path) -> None:
    log_dir = os.path.dirname(path)
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", log_dir], check=True)
    elif sys.platform.startswith("win"):
        os.startfile(log_dir)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", log_dir], check=True)
