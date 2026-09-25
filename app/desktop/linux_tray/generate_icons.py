"""Generate the Linux tray icon assets from the vector logo.

Dev-time only. Run from the repo root after changing app/web_ui/static/logo.svg:

    uv run python -m app.desktop.linux_tray.generate_icons

Writes into app/desktop/linux_tray/icons/:

- kiln-symbolic.svg: a single-colour glyph that panels recolor to match their theme.
  GNOME/GTK force the fill of any `*-symbolic` icon to the foreground colour. KDE
  replaces the `current-color-scheme` stylesheet and `fill:currentColor` follows it.
- kiln-<size>.png: white silhouettes for panels that don't resolve the icon name.
  They are rendered from the vector at each exact size (area-coverage anti-aliasing,
  with the vertical stems snapped to whole pixels), never resized afterwards.
"""

import math
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from app.desktop.linux_tray.icons import (
    PIXMAP_SIZES,
    pixmap_filename,
    symbolic_icon_filename,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LOGO_SVG = REPO_ROOT / "app" / "web_ui" / "static" / "logo.svg"
ICON_DIR = Path(__file__).resolve().parent / "icons"

SUPERSAMPLE = 16
BEZIER_SEGMENTS = 23
CORNER_SEGMENTS = 11
SYMBOLIC_DEFAULT_COLOR = "#232629"

Point = tuple[float, float]

_SHAPE_ELEMENT = re.compile(r"<(rect|path)\s([^>]*)/>")
_ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
_PATH_TOKEN = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?")


@dataclass(frozen=True)
class LogoShape:
    element: str
    attributes: str
    outline: list[Point]


def _parse_path(d: str) -> list[Point]:
    """Flatten SVG path data that uses only absolute M/L/H/V/C/Z commands."""
    tokens = _PATH_TOKEN.findall(d)
    points: list[Point] = []
    index = 0
    command = ""
    x = y = 0.0

    def number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command == "Z":
                continue
        if command in ("M", "L"):
            x, y = number(), number()
            points.append((x, y))
        elif command == "H":
            x = number()
            points.append((x, y))
        elif command == "V":
            y = number()
            points.append((x, y))
        elif command == "C":
            x1, y1, x2, y2, x3, y3 = (number() for _ in range(6))
            for step in range(1, BEZIER_SEGMENTS + 1):
                t = step / BEZIER_SEGMENTS
                u = 1 - t
                points.append(
                    (
                        u**3 * x + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3,
                        u**3 * y + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3,
                    )
                )
            x, y = x3, y3
        elif command == "Z":
            raise ValueError("Unexpected number after SVG path command Z")
        else:
            raise ValueError(f"Unsupported SVG path command: {command}")
    return points


def _rounded_rect(x: float, y: float, w: float, h: float, r: float) -> list[Point]:
    corners = [
        (x + w - r, y + r, -90.0),
        (x + w - r, y + h - r, 0.0),
        (x + r, y + h - r, 90.0),
        (x + r, y + r, 180.0),
    ]
    points: list[Point] = []
    for cx, cy, start in corners:
        for step in range(CORNER_SEGMENTS + 1):
            angle = math.radians(start + 90.0 * step / CORNER_SEGMENTS)
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def load_logo_shapes(svg: str) -> list[LogoShape]:
    shapes = []
    for match in _SHAPE_ELEMENT.finditer(svg):
        element, attributes = match.group(1), match.group(2)
        attrs = dict(_ATTRIBUTE.findall(attributes))
        if element == "rect":
            outline = _rounded_rect(
                float(attrs["x"]),
                float(attrs["y"]),
                float(attrs["width"]),
                float(attrs["height"]),
                float(attrs.get("rx", 0)),
            )
        else:
            outline = _parse_path(attrs["d"])
        shapes.append(LogoShape(element, attributes, outline))
    if not shapes:
        raise ValueError("No <rect> or <path> shapes found in the logo SVG")
    return shapes


@dataclass(frozen=True)
class GlyphBounds:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def glyph_bounds(shapes: list[LogoShape]) -> GlyphBounds:
    xs = [x for shape in shapes for x, _ in shape.outline]
    ys = [y for shape in shapes for _, y in shape.outline]
    return GlyphBounds(min(xs), min(ys), max(xs), max(ys))


def _hinting_stops(shapes: list[LogoShape], bounds: GlyphBounds) -> list[float]:
    """Logo x positions snapped to whole pixels: glyph left, stem right, triangles left, glyph right."""
    stem = shapes[0].outline
    triangles = [point for shape in shapes[1:] for point in shape.outline]
    return [
        bounds.x0,
        max(x for x, _ in stem),
        min(x for x, _ in triangles),
        bounds.x1,
    ]


def _piecewise_linear(
    stops: list[float], targets: list[float]
) -> Callable[[float], float]:
    def mapped(x: float) -> float:
        if x <= stops[0]:
            return targets[0]
        for (x0, t0), (x1, t1) in zip(zip(stops, targets), zip(stops[1:], targets[1:])):
            if x <= x1:
                return t0 + (t1 - t0) * (x - x0) / (x1 - x0)
        return targets[-1]

    return mapped


def silhouette(shapes: list[LogoShape], size: int) -> Image.Image:
    """White glyph filling the canvas height, alpha = exact area coverage."""
    bounds = glyph_bounds(shapes)
    scale = size / bounds.height
    left = size / 2 - bounds.width * scale / 2

    stops = _hinting_stops(shapes, bounds)
    unsnapped = [left + (x - bounds.x0) * scale for x in stops]
    snapped = [float(round(x)) for x in unsnapped]
    recenter = round(size / 2 - (snapped[0] + snapped[-1]) / 2)
    to_pixel_x = _piecewise_linear(stops, [x + recenter for x in snapped])

    canvas = size * SUPERSAMPLE
    coverage = Image.new("L", (canvas, canvas), 0)
    draw = ImageDraw.Draw(coverage)
    for shape in shapes:
        draw.polygon(
            [
                (
                    to_pixel_x(x) * SUPERSAMPLE,
                    (y - bounds.y0) * scale * SUPERSAMPLE,
                )
                for x, y in shape.outline
            ],
            fill=255,
        )
    alpha = coverage.reduce(SUPERSAMPLE)
    white = Image.new("L", (size, size), 255)
    return Image.merge("RGBA", (white, white, white, alpha))


def symbolic_svg(shapes: list[LogoShape]) -> str:
    bounds = glyph_bounds(shapes)
    side = max(bounds.width, bounds.height)
    view_x = bounds.x0 - (side - bounds.width) / 2
    view_y = bounds.y0 - (side - bounds.height) / 2
    elements = []
    for shape in shapes:
        attributes = re.sub(r'\s*fill="[^"]*"', "", shape.attributes).strip()
        elements.append(
            f'  <{shape.element} {attributes} class="ColorScheme-Text" '
            'style="fill:currentColor"/>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        f'viewBox="{view_x:.2f} {view_y:.2f} {side:.2f} {side:.2f}">\n'
        '  <style type="text/css" id="current-color-scheme">'
        f".ColorScheme-Text {{ color:{SYMBOLIC_DEFAULT_COLOR}; }}</style>\n"
        + "\n".join(elements)
        + "\n</svg>\n"
    )


def generate(out_dir: Path, logo_svg: Path = LOGO_SVG) -> None:
    shapes = load_logo_shapes(logo_svg.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / symbolic_icon_filename()).write_text(symbolic_svg(shapes))
    for size in PIXMAP_SIZES:
        silhouette(shapes, size).save(out_dir / pixmap_filename(size), optimize=True)


if __name__ == "__main__":
    generate(ICON_DIR)
    sys.stdout.write(f"Wrote Linux tray icons to {ICON_DIR}\n")
