"""
Runs PyInstaller for the desktop app, rendering the splash screen image first.

PyInstaller's splash screen is a Tk window drawn by the bootloader before Python starts. Tk draws the image one
image pixel per screen pixel and never rescales it, so the image must be rendered at the pixel size it should
occupy on screen:

- The bundled splash image is the master downscaled to its size on a standard-DPI (100%) display.
- Renders for common display scale factors are embedded in the splash script, which swaps in the one closest to
  the display's scale before the window is shown. The scale comes from the screen DPI on Windows (the executable
  is declared DPI aware in win_manifest.xml, otherwise Windows reports 96 and bitmap-stretches the window), and
  from the desktop's Xft.dpi resource on X11 (the same source Tk 9 uses).

Usage, from the `app` directory:
    python desktop/pyinstaller_build.py --splash-master=desktop/splash@3x.png [pyinstaller args...]
"""

import argparse
import base64
import io
import os
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

from PIL import Image

MASTER_SCALE = 3
DISPLAY_SCALES = (1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)

# The line of PyInstaller's splash script (6.22.3) that reads the image size to lay out the window.
IMAGE_SIZING_LINE = "set image_width [image width splash_image]"

SCALE_PICKER_PROCS_TCL = r"""
proc kiln_scale_from_xresources {resources} {
    if {[regexp -line {^Xft\.dpi:\s*([0-9.]+)} $resources -> dpi]} {
        return [expr {$dpi / 96.0}]
    }
    return 1.0
}
proc kiln_display_scale {} {
    if {[tk windowingsystem] eq "win32"} {
        return [expr {[winfo fpixels . 1i] / 96.0}]
    }
    if {[catch {exec xrdb -query} resources]} {
        return 1.0
    }
    return [kiln_scale_from_xresources $resources]
}
proc kiln_closest_splash_variant {display_scale variants} {
    set best_scale 1.0
    set best_data {}
    foreach {scale data} $variants {
        if {abs($scale - $display_scale) < abs($best_scale - $display_scale)} {
            set best_scale $scale
            set best_data $data
        }
    }
    return $best_data
}
"""


def splash_pixel_size(
    master_size: tuple[int, int], display_scale: float
) -> tuple[int, int]:
    width, height = master_size
    return (
        round(width * display_scale / MASTER_SCALE),
        round(height * display_scale / MASTER_SCALE),
    )


def render_splash_png(master: Image.Image, display_scale: float) -> bytes:
    size = splash_pixel_size(master.size, display_scale)
    rendered = master.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    png = io.BytesIO()
    rendered.save(png, format="PNG", optimize=True)
    return png.getvalue()


def scaled_variants(master: Image.Image) -> dict[float, bytes]:
    return {scale: render_splash_png(master, scale) for scale in DISPLAY_SCALES}


def tcl_variant_list(variants: dict[float, bytes]) -> str:
    return "\n".join(
        f"{scale} {{{base64.b64encode(png).decode('ascii')}}}"
        for scale, png in sorted(variants.items())
    )


def scaled_variant_picker_tcl(variants: dict[float, bytes]) -> str:
    """
    Tcl that replaces `splash_image`, the 1x image from the bootloader, with the variant closest to the display's
    scale. Keeps the 1x image when it is the closest.
    """
    return f"""{SCALE_PICKER_PROCS_TCL}
set kiln_splash_data [kiln_closest_splash_variant [kiln_display_scale] {{
{tcl_variant_list(variants)}
}}]
if {{$kiln_splash_data ne {{}}}} {{
    image delete splash_image
    image create photo splash_image -format png -data $kiln_splash_data
}}
unset kiln_splash_data
"""


def insert_before_image_sizing(script: str, tcl: str) -> str:
    if IMAGE_SIZING_LINE not in script:
        raise RuntimeError(
            f"PyInstaller's splash script no longer contains {IMAGE_SIZING_LINE!r}. "
            "Find the new place to swap the splash image after upgrading PyInstaller."
        )
    return script.replace(IMAGE_SIZING_LINE, f"{tcl}\n{IMAGE_SIZING_LINE}", 1)


def install_splash_script_addition(tcl: str) -> None:
    from PyInstaller.building import splash_templates

    build_pyinstaller_script = splash_templates.build_script

    def build_script(*args: Any, **kwargs: Any) -> str:
        return insert_before_image_sizing(
            build_pyinstaller_script(*args, **kwargs), tcl
        )

    setattr(splash_templates, "build_script", build_script)


def prepare_splash(master_path: str, out_dir: str) -> str:
    """
    Writes the 1x splash image into out_dir and returns its path. Installs the script addition that swaps in
    a sharper variant on high-DPI displays.
    """
    splash_path = os.path.join(out_dir, "splash.png")
    with Image.open(master_path) as master:
        with open(splash_path, "wb") as splash_file:
            splash_file.write(render_splash_png(master, 1.0))
        install_splash_script_addition(
            scaled_variant_picker_tcl(scaled_variants(master))
        )
    return splash_path


def main(argv: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--splash-master",
        help=f"Splash image drawn at {MASTER_SCALE}x its on-screen size. Replaces pyinstaller's --splash.",
    )
    args, pyinstaller_args = parser.parse_known_args(argv)

    import PyInstaller.__main__

    with tempfile.TemporaryDirectory() as splash_dir:
        if args.splash_master:
            splash_path = prepare_splash(args.splash_master, splash_dir)
            pyinstaller_args = [f"--splash={splash_path}", *pyinstaller_args]
        PyInstaller.__main__.run(pyinstaller_args)


if __name__ == "__main__":
    main(sys.argv[1:])
