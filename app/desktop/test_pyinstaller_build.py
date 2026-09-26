import base64
import tkinter
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyInstaller.building import splash_templates
from PyInstaller.building.splash import Splash

from app.desktop import generate_splash_images, pyinstaller_build
from app.desktop.pyinstaller_build import (
    IMAGE_SIZING_LINE,
    SCALE_PICKER_PROCS_TCL,
    SPLASH_VARIANTS,
    insert_before_image_sizing,
    install_splash_script_addition,
    main,
    read_splash_variants,
    scaled_variant_picker_tcl,
    tcl_variant_list,
)


@pytest.fixture
def restore_build_script(monkeypatch):
    monkeypatch.setattr(splash_templates, "build_script", splash_templates.build_script)


@pytest.fixture
def tcl():
    interpreter = tkinter.Tcl()
    interpreter.eval(SCALE_PICKER_PROCS_TCL)
    return interpreter


def test_splash_variants_are_the_generated_high_dpi_images():
    generated = dict(generate_splash_images.SPLASH_IMAGES)
    assert generated.pop(1.0) == "splash.png"
    assert SPLASH_VARIANTS == generated
    assert set(read_splash_variants()) == set(SPLASH_VARIANTS)


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
        (1.2, ""),
        (1.25, ""),
        (1.3, "1.5x"),
        (1.5, "1.5x"),
        (1.8, "2x"),
        (2.0, "2x"),
        (3.0, "2x"),
    ],
)
def test_closest_splash_variant(tcl, display_scale, expected_variant):
    variants = {1.5: b"1.5x", 2.0: b"2x"}
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
    restore_build_script, tmp_path
):
    variants = read_splash_variants()
    install_splash_script_addition(scaled_variant_picker_tcl(variants))

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
    for png in variants.values():
        assert base64.b64encode(png).decode("ascii") in script


def test_main_adds_splash_variants_and_passes_args_through():
    args = ["--windowed", "--splash=../splash/splash.png", "./desktop/desktop.py"]
    with (
        patch.object(pyinstaller_build, "install_splash_script_addition") as install,
        patch("PyInstaller.__main__.run") as run,
    ):
        main(args)

    install.assert_called_once_with(scaled_variant_picker_tcl(read_splash_variants()))
    run.assert_called_once_with(args)
