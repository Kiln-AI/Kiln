"""Generate Linux tray icon experiment assets from the vector logo.

Run from the repo root:

    uv run python scripts/gen_tray_icons.py

Source: app/web_ui/static/logo.svg (three filled shapes: a rounded rect and two
rounded triangles). We parse the SVG path data ourselves (it only uses M/L/H/V/C/Z)
and rasterize from vector at each exact pixel size:

- Shapes are filled at SUPERSAMPLE x resolution and box-averaged down. That is an
  area-coverage anti-alias, done on premultiplied values, so no straight-alpha
  fringing is possible.
- Key x edges (rect left/right, triangle left, glyph right) are snapped to whole
  pixels per size, so the vertical stems stay crisp at 16-24px (simple hinting).

Outputs go to app/desktop/tray_icons/<set>/kiln-<size>.png, plus kiln-symbolic.svg
and a hicolor-style themed tree for the multi-size variant. The contact sheet is
written to docs/tray-experiments/contact_sheet.png.
"""

import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
LOGO_SVG = ROOT / "app/web_ui/static/logo.svg"
TASKBAR_PNG = ROOT / "app/desktop/taskbar.png"
OUT_DIR = ROOT / "app/desktop/tray_icons"
DOCS_DIR = ROOT / "docs/tray-experiments"

SIZES = [16, 22, 24, 32, 48, 64]
SUPERSAMPLE = 16
BRAND_BLUE = (0x41, 0x5C, 0xF5)
PR1814_BG = (68, 70, 60)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
EDGE_ALPHA = 0.45

SHEET_SIZES = [16, 22, 24]
SHEET_BACKGROUNDS = {
    "light #f6f5f4": (0xF6, 0xF5, 0xF4),
    "dark #1d1d1d": (0x1D, 0x1D, 0x1D),
    "black #000000": (0, 0, 0),
    "mid #3d6fb5": (0x3D, 0x6F, 0xB5),
}


# ---------------------------------------------------------------- SVG parsing


def _parse_path(d: str) -> list[tuple[float, float]]:
    tokens = re.findall(r"[MLHVCZmlhvcz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    pts: list[tuple[float, float]] = []
    i = 0
    cmd = ""
    x = y = 0.0

    def num() -> float:
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
        if cmd in "mlhvc":
            raise ValueError(f"relative path command {cmd} not supported")
        if cmd == "M" or cmd == "L":
            x, y = num(), num()
            pts.append((x, y))
        elif cmd == "H":
            x = num()
            pts.append((x, y))
        elif cmd == "V":
            y = num()
            pts.append((x, y))
        elif cmd == "C":
            x1, y1, x2, y2, x3, y3 = (num() for _ in range(6))
            for t in np.linspace(0, 1, 24)[1:]:
                mt = 1 - t
                bx = mt**3 * x + 3 * mt**2 * t * x1 + 3 * mt * t**2 * x2 + t**3 * x3
                by = mt**3 * y + 3 * mt**2 * t * y1 + 3 * mt * t**2 * y2 + t**3 * y3
                pts.append((bx, by))
            x, y = x3, y3
        elif cmd == "Z":
            pass
    return pts


def _rounded_rect(
    x: float, y: float, w: float, h: float, r: float
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    corners = [
        (x + w - r, y + r, -90),
        (x + w - r, y + h - r, 0),
        (x + r, y + h - r, 90),
        (x + r, y + r, 180),
    ]
    for cx, cy, start in corners:
        for a in np.linspace(start, start + 90, 12):
            rad = np.radians(a)
            pts.append((cx + r * np.cos(rad), cy + r * np.sin(rad)))
    return pts


def load_logo_shapes() -> list[tuple[tuple[int, int, int], list[tuple[float, float]]]]:
    svg = LOGO_SVG.read_text()
    shapes = []
    for m in re.finditer(r"<(rect|path)\s([^>]*)/>", svg):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(2)))
        fill = attrs["fill"].lstrip("#")
        color = (int(fill[0:2], 16), int(fill[2:4], 16), int(fill[4:6], 16))
        if m.group(1) == "rect":
            pts = _rounded_rect(
                float(attrs["x"]),
                float(attrs["y"]),
                float(attrs["width"]),
                float(attrs["height"]),
                float(attrs.get("rx", 0)),
            )
        else:
            pts = _parse_path(attrs["d"])
        shapes.append((color, pts))
    return shapes


SHAPES = load_logo_shapes()
_ALL = np.array([p for _, pts in SHAPES for p in pts])
GLYPH_X0, GLYPH_Y0 = _ALL.min(0)
GLYPH_X1, GLYPH_Y1 = _ALL.max(0)
# stems we snap to whole pixels: rect left, rect right, triangles left, glyph right
_RECT = SHAPES[0][1]
X_STOPS = [
    GLYPH_X0,
    max(p[0] for p in _RECT),
    min(p[0] for _, pts in SHAPES[1:] for p in pts),
    GLYPH_X1,
]


# ---------------------------------------------------------------- rendering


def _x_mapper(box_x: float, box_y: float, box_h: float, hint: bool):
    """Return a function mapping logo-space x to canvas pixels (float)."""
    scale = box_h / (GLYPH_Y1 - GLYPH_Y0)
    glyph_w = (GLYPH_X1 - GLYPH_X0) * scale
    raw = [box_x + (sx - GLYPH_X0) * scale for sx in X_STOPS]
    if not hint:
        return lambda x: box_x + (x - GLYPH_X0) * scale, scale
    snapped = [float(round(v)) for v in raw]
    # keep total width centered after rounding
    shift = round((raw[0] + glyph_w / 2) - (snapped[0] + snapped[-1]) / 2)
    snapped = [v + shift for v in snapped]

    def fx(x: float) -> float:
        return float(np.interp(x, X_STOPS, snapped))

    return fx, scale


def render_coverage(
    size: int, box: tuple[float, float, float] | None = None, hint: bool = True
) -> list[tuple[tuple[int, int, int], np.ndarray]]:
    """Per-shape coverage masks (float 0..1) at `size`.

    box = (x_center, y_top, height) in pixels; default fills the canvas height.
    """
    if box is None:
        box = (size / 2, 0.0, float(size))
    cx, top, h = box
    if hint:
        top = float(round(top))
        h = float(round(h))
    scale = h / (GLYPH_Y1 - GLYPH_Y0)
    glyph_w = (GLYPH_X1 - GLYPH_X0) * scale
    fx, _ = _x_mapper(cx - glyph_w / 2, top, h, hint)

    ss = SUPERSAMPLE
    out = []
    for color, pts in SHAPES:
        mask = Image.new("L", (size * ss, size * ss), 0)
        poly = [(fx(x) * ss, (top + (y - GLYPH_Y0) * scale) * ss) for x, y in pts]
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        cov = np.asarray(mask, dtype=np.float64) / 255.0
        cov = cov.reshape(size, ss, size, ss).mean(axis=(1, 3))
        out.append((color, cov))
    return out


def _to_image(premul_rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    alpha = np.clip(alpha, 0, 1)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    rgb = np.where(alpha[..., None] > 0, premul_rgb / safe, 0)
    arr = np.dstack([rgb, alpha[..., None]]) * 255.0
    return Image.fromarray(np.clip(np.round(arr), 0, 255).astype(np.uint8), "RGBA")


def compose(layers: list[tuple[tuple[int, int, int], np.ndarray]]) -> Image.Image:
    """Porter-Duff 'over' of (color, coverage) layers, bottom first, premultiplied."""
    h, w = layers[0][1].shape
    prem = np.zeros((h, w, 3))
    alpha = np.zeros((h, w))
    for color, cov in layers:
        c = np.array(color, dtype=np.float64) / 255.0
        prem = c * cov[..., None] + prem * (1 - cov[..., None])
        alpha = cov + alpha * (1 - cov)
    return _to_image(prem, alpha)


def glyph_union(covs: list[tuple[tuple[int, int, int], np.ndarray]]) -> np.ndarray:
    # shapes don't overlap, so coverage adds
    return np.clip(sum(c for _, c in covs), 0, 1)


def make_color(size: int) -> Image.Image:
    return compose(render_coverage(size))


def make_mono(size: int, color: tuple[int, int, int]) -> Image.Image:
    return compose([(color, glyph_union(render_coverage(size)))])


def make_mono_edge(
    size: int, color: tuple[int, int, int], edge: tuple[int, int, int]
) -> Image.Image:
    # 1px inset so the outline isn't clipped by the canvas
    cov = glyph_union(render_coverage(size, box=(size / 2, 1, size - 2)))
    cov_img = Image.fromarray(np.round(cov * 255).astype(np.uint8), "L")
    dil = np.asarray(cov_img.filter(ImageFilter.MaxFilter(3)), dtype=np.float64) / 255
    return compose([(edge, dil * EDGE_ALPHA), (color, cov)])


def _rounded_square_cov(size: int, radius_frac: float) -> np.ndarray:
    ss = SUPERSAMPLE
    mask = Image.new("L", (size * ss, size * ss), 0)
    r = size * ss * radius_frac
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * ss - 1, size * ss - 1), radius=r, fill=255
    )
    return (
        (np.asarray(mask, dtype=np.float64) / 255)
        .reshape(size, ss, size, ss)
        .mean(axis=(1, 3))
    )


def make_tile(size: int) -> Image.Image:
    tile = _rounded_square_cov(size, 0.22)
    pad = max(2.0, round(size * 0.2))
    cov = glyph_union(render_coverage(size, box=(size / 2, pad, size - 2 * pad)))
    return compose([(BRAND_BLUE, tile), (WHITE, cov * tile)])


def make_pr1814(size: int) -> Image.Image:
    """Exact PR #1814 approach: composite taskbar.png on #44463c, RGB, LANCZOS."""
    src = Image.open(TASKBAR_PNG).convert("RGBA")
    bg = Image.new("RGBA", src.size, (*PR1814_BG, 255))
    bg.alpha_composite(src)
    return bg.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)


def make_straight_lanczos(size: int) -> Image.Image:
    """True straight-alpha LANCZOS (each channel independently) of taskbar.png.

    Pillow's Image.resize premultiplies RGBA internally, so a naive
    `im.resize()` does NOT show this artifact. This is what a straight-alpha
    resizer (and what pystray's xorg backend then shows after dropping alpha)
    looks like.
    """
    src = Image.open(TASKBAR_PNG).convert("RGBA")
    chans = [c.resize((size, size), Image.Resampling.LANCZOS) for c in src.split()]
    return Image.merge("RGBA", chans)


def make_pillow_resize(size: int) -> Image.Image:
    """What current code + pystray effectively feed a tray: Image.resize of the 88px PNG."""
    return (
        Image.open(TASKBAR_PNG)
        .convert("RGBA")
        .resize((size, size), Image.Resampling.LANCZOS)
    )


def make_xorg_baseline(size: int) -> Image.Image:
    """What pystray's xorg backend draws for the current baseline: alpha dropped."""
    resized = Image.open(TASKBAR_PNG).resize((size, size), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (size, size))
    out.paste(resized)
    return out


ASSET_SETS = {
    "color": make_color,
    "tile": make_tile,
    "mono-white": lambda s: make_mono(s, WHITE),
    "mono-black": lambda s: make_mono(s, BLACK),
    "mono-white-edge": lambda s: make_mono_edge(s, WHITE, BLACK),
    "mono-black-edge": lambda s: make_mono_edge(s, BLACK, WHITE),
    "pr1814": make_pr1814,
}

# only shown on the contact sheet, not bundled
COMPARISON_SETS = {
    "baseline via xorg (alpha dropped)": make_xorg_baseline,
    "taskbar.png Image.resize (premultiplied)": make_pillow_resize,
    "taskbar.png straight-alpha LANCZOS": make_straight_lanczos,
}


# ---------------------------------------------------------------- symbolic SVG


def symbolic_svg() -> str:
    """Monochrome SVG that both GNOME (-symbolic) and KDE (ColorScheme-Text) recolor.

    - GNOME/GTK: files named *-symbolic.svg are loaded through a wrapper that
      forces `fill` on rect/path to the foreground color, so any fill works.
    - KDE: KIconLoader replaces the <style id="current-color-scheme"> contents
      with the panel's color scheme, and `fill:currentColor` on elements with
      class ColorScheme-Text picks it up.
    """
    svg = LOGO_SVG.read_text()
    w = GLYPH_X1 - GLYPH_X0
    h = GLYPH_Y1 - GLYPH_Y0
    side = max(w, h)
    vx = GLYPH_X0 - (side - w) / 2
    vy = GLYPH_Y0 - (side - h) / 2
    body = []
    for m in re.finditer(r"<(rect|path)\s([^>]*)/>", svg):
        attrs = re.sub(r'\sfill="[^"]*"', "", " " + m.group(2)).strip()
        body.append(
            f'    <{m.group(1)} {attrs} class="ColorScheme-Text" style="fill:currentColor"/>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        f'viewBox="{vx:.2f} {vy:.2f} {side:.2f} {side:.2f}">\n'
        '  <style type="text/css" id="current-color-scheme">'
        ".ColorScheme-Text { color:#232629; }</style>\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )


# ---------------------------------------------------------------- contact sheet


def contact_sheet(sets: dict) -> Image.Image:
    from PIL import ImageFont

    zoom = 4
    gap = 6
    label_w = 300
    bg_names = list(SHEET_BACKGROUNDS)
    cell_w = sum(SHEET_SIZES) + sum(s * zoom for s in SHEET_SIZES) + gap * 7
    cell_h = max(SHEET_SIZES) * zoom + 2 * gap
    header_h = 28
    width = label_w + cell_w * len(bg_names)
    height = header_h + cell_h * len(sets)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    for j, name in enumerate(bg_names):
        draw.text(
            (label_w + j * cell_w + gap, 8),
            f"{name}   (1x 16/22/24, then 4x nearest)",
            fill=(0, 0, 0),
            font=font,
        )
    for i, (set_name, fn) in enumerate(sets.items()):
        y0 = header_h + i * cell_h
        draw.text((8, y0 + cell_h // 2 - 7), set_name, fill=(0, 0, 0), font=font)
        imgs = {s: fn(s).convert("RGBA") for s in SHEET_SIZES}
        for j, bg_name in enumerate(bg_names):
            bg = SHEET_BACKGROUNDS[bg_name]
            x0 = label_w + j * cell_w
            sheet.paste(bg, (x0, y0, x0 + cell_w, y0 + cell_h))
            x = x0 + gap
            for s in SHEET_SIZES:
                tile = Image.new("RGBA", (s, s), (*bg, 255))
                tile.alpha_composite(imgs[s])
                sheet.paste(tile.convert("RGB"), (x, y0 + gap))
                x += s + gap
            x += gap
            for s in SHEET_SIZES:
                tile = Image.new("RGBA", (s, s), (*bg, 255))
                tile.alpha_composite(imgs[s])
                big = tile.resize((s * zoom, s * zoom), Image.Resampling.NEAREST)
                sheet.paste(big.convert("RGB"), (x, y0 + gap))
                x += s * zoom + gap
        draw.line((0, y0, width, y0), fill=(200, 200, 200))
    return sheet


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    for set_name, fn in ASSET_SETS.items():
        d = OUT_DIR / set_name
        d.mkdir()
        for s in SIZES:
            fn(s).save(d / f"kiln-{s}.png", optimize=True)

    # symbolic icon: unthemed file directly in the icon theme path
    sym_dir = OUT_DIR / "symbolic"
    sym_dir.mkdir()
    (sym_dir / "kiln-symbolic.svg").write_text(symbolic_svg())

    # multi-size themed tree for the "themed" variant
    theme = OUT_DIR / "themed" / "hicolor"
    for s in SIZES:
        d = theme / f"{s}x{s}" / "apps"
        d.mkdir(parents=True)
        make_color(s).save(d / "kiln-tray-color.png", optimize=True)
    dirs = ",".join(f"{s}x{s}/apps" for s in SIZES)
    index = [
        "[Icon Theme]",
        "Name=Hicolor",
        "Comment=Kiln tray icons",
        f"Directories={dirs}",
        "",
    ]
    for s in SIZES:
        index += [f"[{s}x{s}/apps]", f"Size={s}", "Type=Fixed", ""]
    (theme / "index.theme").write_text("\n".join(index))

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    sheet_sets = {**ASSET_SETS, **COMPARISON_SETS}
    contact_sheet(sheet_sets).save(DOCS_DIR / "contact_sheet.png", optimize=True)
    print(f"wrote {OUT_DIR} and {DOCS_DIR / 'contact_sheet.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
