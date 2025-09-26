import os
import subprocess
import sys
from pathlib import Path


def open_folder(path: str | Path) -> None:
    dir = os.path.dirname(path)
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", dir], check=True)
    elif sys.platform.startswith("win"):
        os.startfile(dir)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", dir], check=True)
