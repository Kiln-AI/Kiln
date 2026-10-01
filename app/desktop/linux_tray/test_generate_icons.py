import pytest
from PIL import Image, ImageChops

from app.desktop.linux_tray.generate_icons import (
    ICON_DIR,
    LOGO_SVG,
    generate,
    load_logo_shapes,
    symbolic_svg,
)
from app.desktop.linux_tray.icons import (
    PIXMAP_SIZES,
    pixmap_filename,
    symbolic_icon_filename,
)


def test_committed_icons_match_the_generator(tmp_path):
    generate(tmp_path)

    assert (tmp_path / symbolic_icon_filename()).read_text() == (
        ICON_DIR / symbolic_icon_filename()
    ).read_text(), "Run: uv run python -m app.desktop.linux_tray.generate_icons"
    for size in PIXMAP_SIZES:
        name = pixmap_filename(size)
        with (
            Image.open(tmp_path / name) as generated,
            Image.open(ICON_DIR / name) as committed,
        ):
            difference = ImageChops.difference(
                generated.convert("RGBA"), committed.convert("RGBA")
            )
        assert difference.getbbox() is None, (
            f"{name} is stale. Run: uv run python -m app.desktop.linux_tray.generate_icons"
        )


def test_symbolic_svg_is_recolorable_by_gnome_and_kde():
    svg = symbolic_svg(load_logo_shapes(LOGO_SVG.read_text()))

    assert 'id="current-color-scheme"' in svg
    assert "fill=" not in svg
    assert svg.count('class="ColorScheme-Text" style="fill:currentColor"') == 3


@pytest.mark.parametrize(
    "svg, error",
    [
        ('<svg><path d="M0 0l10 10Z" fill="#000000"/></svg>', "command: l"),
        ("<svg><circle r='1'/></svg>", "No <rect> or <path>"),
        (
            '<svg><path d="M0 0 L1 1 Z 5 5" fill="#000000"/></svg>',
            "after SVG path command Z",
        ),
    ],
)
def test_load_logo_shapes_rejects_unsupported_svg(svg, error):
    with pytest.raises(ValueError, match=error):
        load_logo_shapes(svg)
