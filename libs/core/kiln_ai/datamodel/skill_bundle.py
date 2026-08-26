"""Atomic creation of skill bundles (SKILL.md + references/ + assets/).

A skill bundle is created fully formed or not at all: the whole tree is staged
in a hidden directory inside the project folder (same filesystem as skills/),
then committed with a single os.rename. No observer — the studio server reads
disk live — can ever see a partial skill.

Skills are install-once: iteration happens by creating a new skill (e.g. a
clone with a new name), never by mutating an installed one. Stored eval
results that reference a skill therefore stay valid, since drive fingerprints
don't cover skill files.
"""

from __future__ import annotations

import os
import shutil
import uuid
from typing import Dict, Optional

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import (
    RESOURCE_DIR_NAMES,
    Skill,
)

MAX_RESOURCE_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024

STAGING_DIR_NAME = ".skill_staging"


class SkillBundleValidationError(ValueError):
    """A skill bundle failed validation. Carries every failure, not just the first."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid skill bundle: " + "; ".join(errors))


def validate_resource_path(path: str) -> str | None:
    """Validate a bundle-relative resource path. Returns an error message or None."""
    if not path or not path.strip():
        return "resource path cannot be empty"
    if "\\" in path:
        return f"resource path must use forward slashes: {path!r}"
    if "\x00" in path:
        return f"resource path contains a null byte: {path!r}"
    segments = path.split("/")
    if segments[0] not in RESOURCE_DIR_NAMES:
        return f"resource path must start with 'references/' or 'assets/': {path!r}"
    if len(segments) < 2 or segments[-1] == "":
        return f"resource path must include a filename: {path!r}"
    for segment in segments[1:]:
        if segment in ("", ".", ".."):
            return f"resource path contains an invalid segment: {path!r}"
    return None


def validate_bundle_files(files: Dict[str, bytes]) -> list[str]:
    """Validate resource files for a bundle, accumulating every failure."""
    errors: list[str] = []
    total_bytes = 0
    for path, content in files.items():
        path_error = validate_resource_path(path)
        if path_error is not None:
            errors.append(path_error)
            continue
        total_bytes += len(content)
        if len(content) > MAX_RESOURCE_FILE_BYTES:
            errors.append(
                f"file too large: {path} is {len(content)} bytes (cap {MAX_RESOURCE_FILE_BYTES})"
            )
        # The skill tool decodes references as UTF-8 at runtime — reject at
        # install time, not at runtime. Assets may be binary.
        if path.startswith("references/"):
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"references file is not UTF-8 text: {path}")
    if total_bytes > MAX_BUNDLE_BYTES:
        errors.append(
            f"bundle too large: {total_bytes} bytes total (cap {MAX_BUNDLE_BYTES})"
        )
    return errors


def create_skill_with_files(
    project: Project,
    name: str,
    description: str,
    body: str,
    files: Optional[Dict[str, bytes]] = None,
) -> Skill:
    """Create a skill atomically, with optional resource files.

    files maps bundle-relative paths ('references/…', 'assets/…') to content.
    Raises SkillBundleValidationError with every failure accumulated, so a
    caller fixes the bundle once rather than one round trip per defect.
    """
    if project.path is None:
        raise ValueError("Project must be saved before creating skills")
    files = files or {}

    errors = validate_bundle_files(files)
    if not body or not body.strip():
        errors.append("body must be non-empty")
    existing_names = {s.name for s in project.skills(readonly=True)}
    if name in existing_names:
        errors.append(
            f"skill name {name!r} already exists — skills are install-once; "
            "pick a new name (a new version is a new skill)"
        )
    if errors:
        raise SkillBundleValidationError(errors)

    skill = Skill(
        name=name,
        description=description,
        parent=project,
    )
    final_path = skill.build_path()
    if final_path is None:
        raise ValueError("Could not build skill path from project")
    final_dir = final_path.parent

    # Stage outside skills/ so a half-written bundle is never enumerable as a
    # child, but on the same filesystem so the commit rename is atomic.
    staging_root = project.path.parent / STAGING_DIR_NAME
    staging_root.mkdir(exist_ok=True)
    staging_dir = staging_root / f"skill-{uuid.uuid4().hex}"
    staging_dir.mkdir()
    try:
        skill.path = staging_dir / Skill.base_filename()
        skill.save_to_file()
        skill.save_skill_md(body)
        for relative_path, content in files.items():
            destination = staging_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            raise SkillBundleValidationError(
                [f"skill directory already exists: {final_dir.name}"]
            )
        # The commit point: before this rename the skill doesn't exist
        # anywhere visible; after it, it exists fully formed.
        os.rename(staging_dir, final_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    skill.path = final_path
    return skill


def clone_skill(
    project: Project,
    source: Skill,
    name: str,
    description: str,
    body: str,
) -> Skill:
    """Create a new skill from an existing one, copying all resource files.

    name/description/body may differ from the source (a clone is a new skill,
    not a mutation).
    """
    files = {
        path: source.read_resource_bytes(path) for path in source.list_resource_files()
    }
    return create_skill_with_files(
        project,
        name=name,
        description=description,
        body=body,
        files=files,
    )
