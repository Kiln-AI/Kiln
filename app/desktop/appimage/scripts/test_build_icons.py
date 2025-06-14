import os
import tempfile
from unittest.mock import patch

import pytest
from PIL import Image

from app.desktop.appimage.scripts.build_icons import main, parse_args


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def test_image(temp_dir):
    """Create a test image file."""
    img_path = os.path.join(temp_dir, "test_icon.png")
    img = Image.new("RGB", (512, 512), color="red")
    img.save(img_path, "PNG")
    return img_path


def test_parse_args():
    """Test argument parsing."""
    # Test with minimal arguments
    with patch("sys.argv", ["build_icons.py", "icon.png", "16", "32"]):
        args = parse_args()
        assert args.src == "icon.png"
        assert args.sizes == [16, 32]
        assert args.out_dir == "."

    # Test with output directory specified
    with patch("sys.argv", ["build_icons.py", "icon.png", "64", "--out-dir", "/tmp"]):
        args = parse_args()
        assert args.src == "icon.png"
        assert args.sizes == [64]
        assert args.out_dir == "/tmp"


def test_main_success(test_image, temp_dir, capsys):
    """Test successful icon generation."""
    out_dir = os.path.join(temp_dir, "output")
    with patch(
        "sys.argv",
        ["build_icons.py", test_image, "16", "32", "64", "--out-dir", out_dir],
    ):
        main()

    # Check that subdirectories and files were created
    for size in [16, 32, 64]:
        icon_path = os.path.join(out_dir, f"{size}x{size}", "kiln-ai.png")
        assert os.path.exists(icon_path)

        # Verify image dimensions
        img = Image.open(icon_path)
        assert img.size == (size, size)

    # Check output messages
    captured = capsys.readouterr()
    assert "✔ Saved:" in captured.out
    assert captured.out.count("✔ Saved:") == 3


def test_main_source_not_found(temp_dir, capsys):
    """Test error when source image doesn't exist."""
    with patch(
        "sys.argv", ["build_icons.py", "nonexistent.png", "16", "--out-dir", temp_dir]
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "❌ Error: source image not found:" in captured.err
    assert "nonexistent.png" in captured.err


def test_main_invalid_image(temp_dir, capsys):
    """Test error when file exists but is not a valid image."""
    # Create an invalid image file
    invalid_img = os.path.join(temp_dir, "invalid.png")
    with open(invalid_img, "w") as f:
        f.write("This is not an image")

    with patch(
        "sys.argv", ["build_icons.py", invalid_img, "16", "--out-dir", temp_dir]
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "❌ Failed to open image:" in captured.err


def test_main_multiple_sizes(test_image, temp_dir):
    """Test generating multiple icon sizes at once."""
    out_dir = os.path.join(temp_dir, "icons")
    sizes = [16, 24, 32, 48, 64, 128, 256]

    with patch(
        "sys.argv",
        ["build_icons.py", test_image]
        + [str(s) for s in sizes]
        + ["--out-dir", out_dir],
    ):
        main()

    # Verify all sizes were created
    for size in sizes:
        icon_path = os.path.join(out_dir, f"{size}x{size}", "kiln-ai.png")
        assert os.path.exists(icon_path)
        img = Image.open(icon_path)
        assert img.size == (size, size)


def test_main_existing_directories(test_image, temp_dir):
    """Test that existing directories are handled properly."""
    # Pre-create some directories
    os.makedirs(os.path.join(temp_dir, "16x16"))
    os.makedirs(os.path.join(temp_dir, "32x32"))

    with patch(
        "sys.argv",
        ["build_icons.py", test_image, "16", "32", "--out-dir", temp_dir],
    ):
        main()

    # Should succeed without errors
    assert os.path.exists(os.path.join(temp_dir, "16x16", "kiln-ai.png"))
    assert os.path.exists(os.path.join(temp_dir, "32x32", "kiln-ai.png"))


def test_image_quality(test_image, temp_dir):
    """Test that images are resized with proper quality settings."""
    with patch(
        "sys.argv",
        ["build_icons.py", test_image, "128", "--out-dir", temp_dir],
    ):
        main()

    # Open the resized image
    resized_path = os.path.join(temp_dir, "128x128", "kiln-ai.png")
    img = Image.open(resized_path)

    # The image should be resized using LANCZOS resampling
    # We can't directly test the resampling method, but we can verify
    # the image exists and has the correct dimensions
    assert img.size == (128, 128)
    assert img.mode in ["RGB", "RGBA"]  # PNG supports both modes


def test_main_entry_point(test_image, temp_dir):
    """Test the script can be run as a module."""
    with patch(
        "sys.argv",
        ["build_icons.py", test_image, "32", "--out-dir", temp_dir],
    ):
        # Import and run the module
        import app.desktop.appimage.scripts.build_icons as module

        # Mock the __name__ check
        with patch.object(module, "__name__", "__main__"):
            # This would normally trigger main() to run
            if module.__name__ == "__main__":
                module.main()

    # Verify it worked
    assert os.path.exists(os.path.join(temp_dir, "32x32", "kiln-ai.png"))
