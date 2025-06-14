import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.desktop.appimage.scripts.update_version import (
    get_kiln_version,
    main,
    process_template,
)


@pytest.fixture
def temp_appimage_dir():
    """Create a temporary directory structure that mimics the appimage layout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        appimage_dir = Path(tmpdir) / "app" / "desktop" / "appimage"
        scripts_dir = appimage_dir / "scripts"
        desktop_dir = appimage_dir / "desktop"

        # Create directory structure
        scripts_dir.mkdir(parents=True)
        desktop_dir.mkdir(parents=True)

        # Create the mock pyproject.toml
        project_root = Path(tmpdir)
        libs_core_dir = project_root / "libs" / "core"
        libs_core_dir.mkdir(parents=True)

        pyproject_content = """
[project]
version = "1.2.3"
name = "kiln-ai"
"""
        pyproject_path = libs_core_dir / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        yield appimage_dir, project_root


def test_get_kiln_version_success(temp_appimage_dir):
    """Test successfully getting version from pyproject.toml."""
    appimage_dir, project_root = temp_appimage_dir

    # Mock __file__ to be in the scripts directory
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        str(appimage_dir / "scripts" / "update_version.py"),
    ):
        version = get_kiln_version()
        assert version == "1.2.3"


def test_get_kiln_version_file_not_found():
    """Test error when pyproject.toml doesn't exist."""
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        "/some/nonexistent/path/update_version.py",
    ):
        with pytest.raises(FileNotFoundError) as exc_info:
            get_kiln_version()
        assert "Could not find" in str(exc_info.value)


def test_get_kiln_version_missing_version():
    """Test error when version is missing from pyproject.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure
        project_root = Path(tmpdir)
        libs_core_dir = project_root / "libs" / "core"
        libs_core_dir.mkdir(parents=True)

        # Create pyproject.toml without version
        pyproject_content = """
[project]
name = "kiln-ai"
"""
        pyproject_path = libs_core_dir / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Mock __file__ to be in the correct location
        script_path = (
            project_root
            / "app"
            / "desktop"
            / "appimage"
            / "scripts"
            / "update_version.py"
        )
        with patch(
            "app.desktop.appimage.scripts.update_version.__file__", str(script_path)
        ):
            with pytest.raises(ValueError) as exc_info:
                get_kiln_version()
            assert "Could not find project.version" in str(exc_info.value)


def test_process_template_basic():
    """Test basic template processing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "template.txt"
        output_path = Path(tmpdir) / "output.txt"

        # Create template
        template_content = "Version: [[KILN_VERSION]], Date: [[DATE]]"
        template_path.write_text(template_content)

        # Process template
        process_template(template_path, output_path, "2.0.0")

        # Check output
        output_content = output_path.read_text()
        assert "Version: 2.0.0" in output_content
        assert datetime.now().strftime("%Y-%m-%d") in output_content


def test_process_template_with_print(capsys):
    """Test that process_template prints success message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "test.template"
        output_path = Path(tmpdir) / "test.yml"

        template_path.write_text("[[KILN_VERSION]]")
        process_template(template_path, output_path, "1.0.0")

        captured = capsys.readouterr()
        assert "✔ Generated test.yml from template (version 1.0.0)" in captured.out


def test_main_success(temp_appimage_dir, capsys):
    """Test successful main execution."""
    appimage_dir, project_root = temp_appimage_dir

    # Create template files
    templates = [
        ("AppImageBuilder.template.yml", "AppImageBuilder.yml"),
        ("desktop/com.kiln.KilnAI.template.desktop", "desktop/com.kiln.KilnAI.desktop"),
        (
            "desktop/com.kiln.KilnAI.appdata.template.xml",
            "desktop/com.kiln.KilnAI.appdata.xml",
        ),
    ]

    for template_name, _ in templates:
        template_path = appimage_dir / template_name
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text("Version: [[KILN_VERSION]], Date: [[DATE]]")

    # Mock __file__ to be in the scripts directory
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        str(appimage_dir / "scripts" / "update_version.py"),
    ):
        main()

    # Check that all output files were created
    for _, output_name in templates:
        output_path = appimage_dir / output_name
        assert output_path.exists()
        content = output_path.read_text()
        assert "Version: 1.2.3" in content
        assert datetime.now().strftime("%Y-%m-%d") in content

    # Check output messages
    captured = capsys.readouterr()
    assert "📦 Kiln version: 1.2.3" in captured.out
    assert "✅ Version update complete!" in captured.out
    assert captured.out.count("✔ Generated") == 3


def test_main_missing_template(temp_appimage_dir, capsys):
    """Test main execution when some templates are missing."""
    appimage_dir, project_root = temp_appimage_dir

    # Only create one template file
    template_path = appimage_dir / "AppImageBuilder.template.yml"
    template_path.write_text("Version: [[KILN_VERSION]]")

    # Mock __file__ to be in the scripts directory
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        str(appimage_dir / "scripts" / "update_version.py"),
    ):
        main()

    # Check that the existing template was processed
    output_path = appimage_dir / "AppImageBuilder.yml"
    assert output_path.exists()
    assert "Version: 1.2.3" in output_path.read_text()

    # Check warnings for missing templates
    captured = capsys.readouterr()
    assert "⚠️  Warning: Template" in captured.err
    assert "not found" in captured.err
    assert captured.err.count("⚠️  Warning:") == 2  # Two templates missing


def test_main_exception_handling(capsys):
    """Test main error handling."""
    # Mock get_kiln_version to raise an exception
    with patch(
        "app.desktop.appimage.scripts.update_version.get_kiln_version",
        side_effect=Exception("Test error"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "❌ Error: Test error" in captured.err


def test_main_template_processing_error(temp_appimage_dir, capsys):
    """Test error handling during template processing."""
    appimage_dir, project_root = temp_appimage_dir

    # Create a template file
    template_path = appimage_dir / "AppImageBuilder.template.yml"
    template_path.write_text("Test template")

    # Mock __file__ and process_template to raise an exception
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        str(appimage_dir / "scripts" / "update_version.py"),
    ):
        with patch(
            "app.desktop.appimage.scripts.update_version.process_template",
            side_effect=Exception("Processing error"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "❌ Error: Processing error" in captured.err


def test_date_replacement():
    """Test that [[DATE]] placeholder is replaced with current date."""
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "test.xml"
        output_path = Path(tmpdir) / "output.xml"

        template_content = '<release version="[[KILN_VERSION]]" date="[[DATE]]" />'
        template_path.write_text(template_content)

        # Process template
        process_template(template_path, output_path, "3.0.0")

        # Check output has today's date
        output_content = output_path.read_text()
        expected_date = datetime.now().strftime("%Y-%m-%d")
        assert f'date="{expected_date}"' in output_content
        assert 'version="3.0.0"' in output_content


def test_main_entry_point(temp_appimage_dir):
    """Test the script can be run as a module."""
    appimage_dir, project_root = temp_appimage_dir

    # Create at least one template
    template_path = appimage_dir / "AppImageBuilder.template.yml"
    template_path.write_text("Version: [[KILN_VERSION]]")

    # Mock __file__ to be in the scripts directory
    with patch(
        "app.desktop.appimage.scripts.update_version.__file__",
        str(appimage_dir / "scripts" / "update_version.py"),
    ):
        # Import and run the module
        import app.desktop.appimage.scripts.update_version as module

        # Mock the __name__ check
        with patch.object(module, "__name__", "__main__"):
            # This would normally trigger main() to run
            if module.__name__ == "__main__":
                module.main()

    # Verify it worked
    output_path = appimage_dir / "AppImageBuilder.yml"
    assert output_path.exists()
    assert "Version: 1.2.3" in output_path.read_text()
