import os

import pytest
from PIL import Image, ImageChops, ImageFilter

from app.desktop.generate_splash_images import (
    SOURCE_PATH,
    SOURCE_SCALE,
    SPLASH_DIR,
    SPLASH_IMAGES,
    render_splash,
    splash_pixel_size,
)


@pytest.fixture
def source():
    with Image.open(SOURCE_PATH) as image:
        yield image


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


def test_1x_splash_is_under_400_logical_px(source):
    width, height = splash_pixel_size(source.size, 1.0)
    assert 340 <= width <= 400
    assert height < width


@pytest.mark.parametrize("scale, file_name", SPLASH_IMAGES.items())
def test_checked_in_splash_images_match_the_source(source, scale, file_name):
    with Image.open(os.path.join(SPLASH_DIR, file_name)) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"
        assert image.size == splash_pixel_size(source.size, scale)


@pytest.mark.parametrize("scale", SPLASH_IMAGES)
def test_render_splash_has_no_halo_around_edges(source, scale):
    rendered = render_splash(source, scale)
    source_rgb = source.convert("RGB")
    window = 2 * round(SOURCE_SCALE / scale) + 1
    darkest = source_rgb.filter(ImageFilter.MinFilter(window))
    brightest = source_rgb.filter(ImageFilter.MaxFilter(window))
    darkest = darkest.resize(rendered.size, Image.Resampling.NEAREST)
    brightest = brightest.resize(rendered.size, Image.Resampling.NEAREST)
    assert ImageChops.subtract(rendered, brightest).getbbox() is None
    assert ImageChops.subtract(darkest, rendered).getbbox() is None
