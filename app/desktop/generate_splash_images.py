"""
Renders the desktop splash screen images from the source artwork. Not part of the build: run it once when the
artwork changes, and check in the images it writes.

    uv run python app/desktop/generate_splash_images.py

The source (splash/source@3x.png) is drawn at 3x the splash's on-screen size. Tk draws the splash image one image
pixel per screen pixel and never rescales it, so each output is rendered at the pixel size the splash occupies on
a display of that scale. splash.png is the 1x image passed to PyInstaller's --splash. pyinstaller_build.py embeds
the others in the splash script, which picks the one closest to the display's scale at startup.

Images are downscaled with a box filter (area averaging), which unlike Lanczos adds no light halo around edges.
"""

import os

from PIL import Image

SPLASH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splash")
SOURCE_PATH = os.path.join(SPLASH_DIR, "source@3x.png")
SOURCE_SCALE = 3
SPLASH_IMAGES = {1.0: "splash.png", 1.5: "splash@1.5x.png", 2.0: "splash@2x.png"}


def splash_pixel_size(
    source_size: tuple[int, int], display_scale: float
) -> tuple[int, int]:
    width, height = source_size
    return (
        round(width * display_scale / SOURCE_SCALE),
        round(height * display_scale / SOURCE_SCALE),
    )


def render_splash(source: Image.Image, display_scale: float) -> Image.Image:
    size = splash_pixel_size(source.size, display_scale)
    return source.convert("RGB").resize(size, Image.Resampling.BOX)


def main() -> None:
    with Image.open(SOURCE_PATH) as source:
        for display_scale, file_name in SPLASH_IMAGES.items():
            path = os.path.join(SPLASH_DIR, file_name)
            render_splash(source, display_scale).save(path, optimize=True)
            print(f"Wrote {path}")


if __name__ == "__main__":
    main()
