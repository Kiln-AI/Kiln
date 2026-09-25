import base64
import io
import os
import tkinter
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image, ImageChops, ImageFilter
from PyInstaller.building import splash_templates
from PyInstaller.building.splash import Splash

from app.desktop import pyinstaller_build
from app.desktop.pyinstaller_build import (
    IMAGE_SIZING_LINE,
    SCALE_PICKER_PROCS_TCL,
    insert_before_image_sizing,
    main,
    prepare_splash,
    render_splash_png,
    scaled_variant_picker_tcl,
    scaled_variants,
    splash_pixel_size,
    tcl_variant_list,
)

SPLASH_MASTER_PATH = os.path.join(os.path.dirname(__file__), "splash@3x.png")


@pytest.fixture
def master():
    with Image.open(SPLASH_MASTER_PATH) as image:
        yield image


@pytest.fixture
def restore_build_script(monkeypatch):
    monkeypatch.setattr(splash_templates, "build_script", splash_templates.build_script)


@pytest.fixture
def tcl():
    interpreter = tkinter.Tcl()
    interpreter.eval(SCALE_PICKER_PROCS_TCL)
    return interpreter


def png_size(png: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png)) as image:
        return image.size


def test_splash_master_is_3x_of_a_splash_under_400_logical_px(master):
    width, height = splash_pixel_size(master.size, 1.0)
    assert 340 <= width <= 400
    assert height < width


@pytest.mark.parametrize(
    "scale, expected",
    [
        (1.0, (373, 227)),
        (1.5, (560, 340)),
        (2.0, (747, 453)),
        (3.0, (1120, 680)),
    ],
)
def test_splash_pixel_size(scale, expected):
    assert splash_pixel_size((1120, 680), scale) == expected


def test_render_splash_png_downscales_to_opaque_rgb(master):
    png = render_splash_png(master, 1.0)
    with Image.open(io.BytesIO(png)) as rendered:
        assert rendered.format == "PNG"
        assert rendered.mode == "RGB"
        assert rendered.size == splash_pixel_size(master.size, 1.0)


@pytest.mark.parametrize("scale", pyinstaller_build.DISPLAY_SCALES)
def test_render_splash_png_has_no_halo_around_edges(master, scale):
    with Image.open(io.BytesIO(render_splash_png(master, scale))) as rendered:
        source = master.convert("RGB")
        window = 2 * round(pyinstaller_build.MASTER_SCALE / scale) + 1
        darkest = source.filter(ImageFilter.MinFilter(window))
        brightest = source.filter(ImageFilter.MaxFilter(window))
        darkest = darkest.resize(rendered.size, Image.Resampling.NEAREST)
        brightest = brightest.resize(rendered.size, Image.Resampling.NEAREST)
        assert ImageChops.subtract(rendered, brightest).getbbox() is None
        assert ImageChops.subtract(darkest, rendered).getbbox() is None


def test_scaled_variants_render_every_display_scale(master):
    variants = scaled_variants(master)
    assert list(variants) == list(pyinstaller_build.DISPLAY_SCALES)
    for scale, png in variants.items():
        assert png_size(png) == splash_pixel_size(master.size, scale)


@pytest.mark.parametrize(
    "resources, expected_scale",
    [
        ("Xft.dpi:\t192\nXft.antialias:\t1", 2.0),
        ("Xft.antialias:\t1\nXft.dpi:\t144", 1.5),
        ("Xft.dpi: 120", 1.25),
        ("Xft.antialias:\t1", 1.0),
        ("", 1.0),
    ],
)
def test_scale_from_xresources(tcl, resources, expected_scale):
    tcl.setvar("resources", resources)
    assert float(tcl.eval("kiln_scale_from_xresources $resources")) == expected_scale


@pytest.mark.parametrize(
    "display_scale, expected_variant",
    [
        (1.0, ""),
        (1.1, ""),
        (1.125, ""),
        (1.2, "1.25x"),
        (1.5, "1.5x"),
        (2.0, "2x"),
        (2.6, "2.5x"),
        (4.0, "3x"),
    ],
)
def test_closest_splash_variant(tcl, display_scale, expected_variant):
    variants = {1.25: b"1.25x", 1.5: b"1.5x", 2.0: b"2x", 2.5: b"2.5x", 3.0: b"3x"}
    tcl.setvar("variants", tcl_variant_list(variants))
    picked = tcl.eval(f"kiln_closest_splash_variant {display_scale} $variants")
    assert base64.b64decode(picked) == expected_variant.encode()


def test_scaled_variant_picker_tcl_embeds_every_variant():
    variants = {1.5: b"one-and-a-half", 2.0: b"double"}
    picker = scaled_variant_picker_tcl(variants)
    assert SCALE_PICKER_PROCS_TCL in picker
    assert tcl_variant_list(variants) in picker
    assert "image create photo splash_image -format png" in picker


def test_insert_before_image_sizing():
    script = f"image create photo splash_image\n{IMAGE_SIZING_LINE}\nframe .root"
    assert insert_before_image_sizing(script, "swap image") == (
        f"image create photo splash_image\nswap image\n{IMAGE_SIZING_LINE}\nframe .root"
    )


def test_insert_before_image_sizing_fails_when_pyinstaller_script_changes():
    with pytest.raises(RuntimeError, match="no longer contains"):
        insert_before_image_sizing("frame .root", "swap image")


def test_pyinstaller_splash_script_gets_picker_before_image_sizing(
    restore_build_script, tmp_path, master
):
    splash_path = prepare_splash(SPLASH_MASTER_PATH, str(tmp_path))
    with Image.open(splash_path) as splash:
        assert splash.size == splash_pixel_size(master.size, 1.0)

    pyinstaller_splash_settings = SimpleNamespace(
        text_pos=None,
        always_on_top=True,
        minify_script=True,
        script_name=str(tmp_path / "splash_script.tcl"),
    )
    script = Splash.generate_script(pyinstaller_splash_settings)

    image_swap = script.index("set kiln_splash_data [kiln_closest_splash_variant")
    assert (
        script.index("image create photo splash_image\n")
        < image_swap
        < script.index(IMAGE_SIZING_LINE)
    )
    for png in scaled_variants(master).values():
        assert base64.b64encode(png).decode("ascii") in script


@pytest.mark.parametrize(
    "extra_args",
    [
        [],
        ["--add-data", "./taskbar.png:.", "-n", "Kiln", "./desktop/desktop.py"],
    ],
)
def test_main_swaps_splash_master_for_rendered_splash(extra_args):
    with (
        patch.object(
            pyinstaller_build, "prepare_splash", return_value="/tmp/splash.png"
        ) as prepare,
        patch("PyInstaller.__main__.run") as run,
    ):
        main(["--windowed", "--splash-master=desktop/splash@3x.png", *extra_args])

    assert prepare.call_args.args[0] == "desktop/splash@3x.png"
    run.assert_called_once_with(["--splash=/tmp/splash.png", "--windowed", *extra_args])


def test_main_without_splash_master_passes_args_through():
    args = ["--onedir", "--icon=../mac_icon.png", "./desktop/desktop.py"]
    with (
        patch.object(pyinstaller_build, "prepare_splash") as prepare,
        patch("PyInstaller.__main__.run") as run,
    ):
        main(args)

    prepare.assert_not_called()
    run.assert_called_once_with(args)
