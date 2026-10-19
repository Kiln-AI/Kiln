from dataclasses import dataclass
from pathlib import Path

from PIL import Image

SYMBOLIC_ICON_NAME = "kiln-symbolic"
PIXMAP_SIZES = (16, 22, 24, 32, 48, 64)


def symbolic_icon_filename() -> str:
    return f"{SYMBOLIC_ICON_NAME}.svg"


def pixmap_filename(size: int) -> str:
    return f"kiln-{size}.png"


@dataclass(frozen=True)
class Pixmap:
    """One StatusNotifierItem pixmap: ARGB32, network byte order, straight alpha."""

    width: int
    height: int
    argb32: bytes


@dataclass(frozen=True)
class TrayIcon:
    """What the tray exposes to the panel: a themed icon name plus pixmap fallbacks.

    Panels that resolve `name` inside `theme_path` recolor the symbolic SVG to
    match their theme. Panels that don't fall back to `pixmaps`.
    """

    name: str
    theme_path: str
    pixmaps: tuple[Pixmap, ...]


def argb32_pixmap(image: Image.Image) -> Pixmap:
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    argb = Image.merge("RGBA", (alpha, red, green, blue))
    return Pixmap(width=rgba.width, height=rgba.height, argb32=argb.tobytes())


def load_tray_icon(icon_dir: Path) -> TrayIcon:
    """Load the bundled Linux tray icon. Raises FileNotFoundError if an asset is missing."""
    symbolic_icon = icon_dir / symbolic_icon_filename()
    if not symbolic_icon.is_file():
        raise FileNotFoundError(symbolic_icon)

    pixmaps = []
    for size in PIXMAP_SIZES:
        with Image.open(icon_dir / pixmap_filename(size)) as image:
            pixmaps.append(argb32_pixmap(image))

    return TrayIcon(
        name=SYMBOLIC_ICON_NAME,
        theme_path=str(icon_dir),
        pixmaps=tuple(pixmaps),
    )
