import sys
from datetime import datetime
from pathlib import Path

import tomli


def get_kiln_version():
    """Extract version from libs/core/pyproject.toml"""
    # Find the project root (4 levels up from this script)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent.parent
    pyproject_path = project_root / "libs" / "core" / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"Could not find {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomli.load(f)

    try:
        version = data["project"]["version"]
        return version
    except KeyError:
        raise ValueError("Could not find project.version in pyproject.toml")


def process_template(template_path, output_path, version):
    """Process a template file and generate output with version replaced"""
    with open(template_path, "r") as f:
        content = f.read()

    content = content.replace("[[KILN_VERSION]]", version)

    current_date = datetime.now().strftime("%Y-%m-%d")
    content = content.replace("[[DATE]]", current_date)

    with open(output_path, "w") as f:
        f.write(content)

    print(f"✔ Generated {output_path.name} from template (version {version})")


def main():
    """Generate files from templates with current Kiln version"""
    try:
        version = get_kiln_version()
        print(f"📦 Kiln version: {version}")

        # Get the appimage directory
        script_dir = Path(__file__).parent
        appimage_dir = script_dir.parent

        # Template mappings (template_file -> output_file)
        templates = [
            ("AppImageBuilder.template.yml", "AppImageBuilder.yml"),
            (
                "desktop/com.kiln.KilnAI.template.desktop",
                "desktop/com.kiln.KilnAI.desktop",
            ),
            (
                "desktop/com.kiln.KilnAI.appdata.template.xml",
                "desktop/com.kiln.KilnAI.appdata.xml",
            ),
        ]

        for template_name, output_name in templates:
            template_path = appimage_dir / template_name
            output_path = appimage_dir / output_name

            if not template_path.exists():
                print(
                    f"⚠️  Warning: Template {template_path} not found", file=sys.stderr
                )
                continue

            process_template(template_path, output_path, version)

        print("✅ Version update complete!")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
