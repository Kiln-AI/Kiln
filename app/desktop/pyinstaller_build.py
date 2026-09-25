"""
Runs PyInstaller for the desktop app, adding high-DPI variants of the splash image to its splash screen.

PyInstaller's splash screen is a Tk window drawn by the bootloader before Python starts. Tk draws the image one
image pixel per screen pixel and never rescales it, and PyInstaller takes a single image (`--splash`, the 1x
image). The splash script PyInstaller generates has no hook for more, so this adds Tcl to it that swaps in the
checked-in variant closest to the display's scale before the window is shown. The scale comes from the screen DPI
on Windows (the executable is declared DPI aware in win_manifest.xml, otherwise Windows reports 96 and
bitmap-stretches the window), and from the desktop's Xft.dpi resource on X11 (the same source Tk 9 uses).

The splash images are made by generate_splash_images.py; nothing is rendered at build time.

Usage, from the `app` directory:
    python desktop/pyinstaller_build.py [pyinstaller args...]
"""

import base64
import os
import sys
from collections.abc import Sequence
from typing import Any

SPLASH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splash")
SPLASH_VARIANTS = {1.5: "splash@1.5x.png", 2.0: "splash@2x.png"}

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


def read_splash_variants() -> dict[float, bytes]:
    variants = {}
    for scale, file_name in SPLASH_VARIANTS.items():
        with open(os.path.join(SPLASH_DIR, file_name), "rb") as png:
            variants[scale] = png.read()
    return variants


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


def main(argv: Sequence[str]) -> None:
    import PyInstaller.__main__

    install_splash_script_addition(scaled_variant_picker_tcl(read_splash_variants()))
    PyInstaller.__main__.run(list(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
