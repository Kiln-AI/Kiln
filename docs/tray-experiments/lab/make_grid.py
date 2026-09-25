"""Assemble labeled tray crops into one comparison image.

python make_grid.py <out.png> <title> <crop.png>... (label = file stem after the 2nd '-')
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out, title, files = sys.argv[1], sys.argv[2], sys.argv[3:]
zoom = 3
try:
    font = ImageFont.truetype("DejaVuSans.ttf", 14)
except OSError:
    font = ImageFont.load_default()
crops = [(Path(f).stem.split("-", 2)[-1], Image.open(f).convert("RGB")) for f in files]
cw = max(c.width for _, c in crops) * zoom
ch = max(c.height for _, c in crops) * zoom
label_w = 230
cols = 2
rows = (len(crops) + cols - 1) // cols
W = cols * (label_w + cw + 10)
H = 30 + rows * (ch + 6)
sheet = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(sheet)
d.text((8, 7), title, fill="black", font=font)
for i, (label, c) in enumerate(crops):
    col, row = i % cols, i // cols
    x = col * (label_w + cw + 10)
    y = 30 + row * (ch + 6)
    d.text((x + 6, y + ch // 2 - 8), label, fill="black", font=font)
    sheet.paste(
        c.resize((c.width * zoom, c.height * zoom), Image.Resampling.NEAREST),
        (x + label_w, y),
    )
sheet.save(out, optimize=True)
print(out, sheet.size)
