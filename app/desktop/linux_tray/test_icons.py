import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.desktop.linux_tray.icons import (
    PIXMAP_SIZES,
    SYMBOLIC_ICON_NAME,
    argb32_pixmap,
    load_tray_icon,
    pixmap_filename,
    symbolic_icon_filename,
)

ICON_DIR = Path(__file__).parent / "icons"


def test_argb32_pixmap_reorders_channels_to_network_order_argb():
    image = Image.new("RGBA", (2, 1))
    image.putdata([(10, 20, 30, 40), (250, 251, 252, 0)])

    pixmap = argb32_pixmap(image)

    assert (pixmap.width, pixmap.height) == (2, 1)
    assert pixmap.argb32 == bytes([40, 10, 20, 30, 0, 250, 251, 252])


def test_argb32_pixmap_treats_images_without_alpha_as_opaque():
    pixmap = argb32_pixmap(Image.new("RGB", (1, 1), (1, 2, 3)))

    assert pixmap.argb32 == bytes([255, 1, 2, 3])


def test_load_tray_icon_reads_bundled_assets():
    icon = load_tray_icon(ICON_DIR)

    assert icon.name == SYMBOLIC_ICON_NAME
    assert icon.theme_path == str(ICON_DIR)
    assert [(p.width, p.height) for p in icon.pixmaps] == [(s, s) for s in PIXMAP_SIZES]
    for pixmap in icon.pixmaps:
        assert len(pixmap.argb32) == pixmap.width * pixmap.height * 4


def test_bundled_pixmaps_are_white_silhouettes():
    for size in PIXMAP_SIZES:
        with Image.open(ICON_DIR / pixmap_filename(size)) as image:
            rgba = image.convert("RGBA")
        visible = [px for px in rgba.getdata() if px[3] > 0]
        assert visible, f"{size}px icon is empty"
        assert {px[:3] for px in visible} == {(255, 255, 255)}


@pytest.mark.parametrize(
    "missing", [symbolic_icon_filename(), pixmap_filename(PIXMAP_SIZES[-1])]
)
def test_load_tray_icon_raises_when_an_asset_is_missing(tmp_path, missing):
    icon_dir = tmp_path / "icons"
    shutil.copytree(ICON_DIR, icon_dir)
    (icon_dir / missing).unlink()

    with pytest.raises(FileNotFoundError):
        load_tray_icon(icon_dir)
