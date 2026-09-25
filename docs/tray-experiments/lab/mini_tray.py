"""Minimal pystray repro: python mini_tray.py <png> [seconds]. Honors PYSTRAY_BACKEND."""

import sys
import threading

import pystray
from PIL import Image

img = Image.open(sys.argv[1])
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 6
print("backend:", pystray.Icon.__module__, "image:", img.mode, img.size, flush=True)
icon = pystray.Icon(
    "kiln", img, "Kiln", pystray.Menu(pystray.MenuItem("Quit", lambda i: i.stop()))
)
threading.Timer(secs, icon.stop).start()
icon.run()
