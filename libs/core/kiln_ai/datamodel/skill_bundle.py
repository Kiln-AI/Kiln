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
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import (
    RESOURCE_DIR_NAMES,
    SKILL_MD_FILENAME,
    Skill,
)

MAX_RESOURCE_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024

STAGING_DIR_NAME = ".skill_staging"
# Staging dirs orphaned by a hard crash (power loss between mkdir and rename)
# are swept on the next install once they are clearly not a live install.
STALE_STAGING_AGE_SECS = 24 * 60 * 60

# Characters legal on POSIX but not Windows. Project folders sync across
# platforms (git/Drive), so a path written on macOS must stay representable
# on a teammate's Windows machine.
_WINDOWS_FORBIDDEN_CHARS = set('<>:"|?*')
_WINDOWS_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {
    f"{device}{n}" for device in ("com", "lpt") for n in range(1, 10)
}


class SkillBundleValidationError(ValueError):
    """A skill bundle failed validation. Carries every failure, not just the first."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid skill bundle: " + "; ".join(errors))


def _unsafe_path_error(path: str) -> str | None:
    """Structural write-safety checks that apply to every staged file path,
    even ones copied verbatim from disk. Returns an error message or None."""
    if not path or not path.strip():
        return "resource path cannot be empty"
    if "\\" in path:
        return f"resource path must use forward slashes: {path!r}"
    if "\x00" in path:
        return f"resource path contains a null byte: {path!r}"
    if path.startswith("/"):
        return f"resource path must be relative: {path!r}"
    if path.endswith("/"):
        return f"resource path must include a filename: {path!r}"
    for segment in path.split("/"):
        if segment in ("", ".", ".."):
            return f"resource path contains an invalid segment: {path!r}"
    return None


def _segment_portability_error(segment: str, path: str) -> str | None:
    """Reject path segments that Windows cannot represent."""
    if any(c in _WINDOWS_FORBIDDEN_CHARS or ord(c) < 0x20 for c in segment):
        return f"resource path contains characters not allowed on Windows: {path!r}"
    if segment.endswith(".") or segment.endswith(" "):
        return f"resource path segment must not end with a dot or space: {path!r}"
    if segment.split(".")[0].lower() in _WINDOWS_RESERVED_NAMES:
        return f"resource path uses a name reserved on Windows: {path!r}"
    return None


def validate_resource_path(path: str) -> str | None:
    """Validate a bundle-relative resource path. Returns an error message or None."""
    unsafe = _unsafe_path_error(path)
    if unsafe is not None:
        return unsafe
    segments = path.split("/")
    if segments[0] not in RESOURCE_DIR_NAMES:
        return f"resource path must start with 'references/' or 'assets/': {path!r}"
    if len(segments) < 2:
        return f"resource path must include a filename: {path!r}"
    for segment in segments[1:]:
        portability = _segment_portability_error(segment, path)
        if portability is not None:
            return portability
    return None


def validate_bundle_files(files: Dict[str, bytes]) -> list[str]:
    """Validate resource files for a bundle, accumulating every failure."""
    errors: list[str] = []
    total_bytes = 0
    valid_paths: list[str] = []
    for path, content in files.items():
        path_error = validate_resource_path(path)
        if path_error is not None:
            errors.append(path_error)
            continue
        valid_paths.append(path)
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

    # Paths must not collide once written to a real filesystem: no two paths
    # differing only by case (case-insensitive filesystems on macOS/Windows
    # would silently overwrite), and no path that is both a file and a parent
    # directory of another file.
    seen_casefold: dict[str, str] = {}
    for path in valid_paths:
        folded = path.casefold()
        if folded in seen_casefold:
            errors.append(
                f"file paths differ only by case: {seen_casefold[folded]!r} and {path!r}"
            )
        else:
            seen_casefold[folded] = path
    dir_prefixes = {
        "/".join(path.split("/")[:i]).casefold()
        for path in valid_paths
        for i in range(1, len(path.split("/")))
    }
    for path in valid_paths:
        if path.casefold() in dir_prefixes:
            errors.append(f"path is used as both a file and a directory: {path!r}")
    return errors


def _existing_skill_name_conflict(project: Project, name: str) -> str | None:
    """Return an error message if the name is already taken, else None.

    Lenient to unreadable sibling skill files (e.g. written by a newer Kiln
    version and synced in) — those can't be name-checked but must not make
    every create fail.
    """
    existing, _load_errors = Skill.all_children_of_parent_path_with_errors(
        project.path, readonly=True
    )
    for skill in existing:
        if skill.name == name:
            archived_note = (
                " (an archived skill has this name)" if skill.is_archived else ""
            )
            return (
                f"skill name {name!r} already exists{archived_note} — skills are "
                "install-once; pick a new name (a new version is a new skill)"
            )
    return None


def _sweep_stale_staging(staging_root: Path) -> None:
    """Best-effort cleanup of staging dirs orphaned by a hard crash.

    Only removes dirs older than STALE_STAGING_AGE_SECS so a concurrent
    install's live staging dir is never touched.
    """
    try:
        cutoff = time.time() - STALE_STAGING_AGE_SECS
        for entry in staging_root.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
    except OSError:
        pass


def create_skill_with_files(
    project: Project,
    name: str,
    description: str,
    body: str,
    files: Optional[Dict[str, bytes]] = None,
    validate_files: bool = True,
) -> Skill:
    """Create a skill atomically, with optional resource files.

    files maps bundle-relative paths ('references/…', 'assets/…') to content.
    Raises SkillBundleValidationError with every failure accumulated, so a
    caller fixes the bundle once rather than one round trip per defect.

    validate_files=False skips the content rules (allowed roots, size caps,
    UTF-8 references) for files that already exist on disk — clone uses it so
    a skill with hand-added oversized or unusual files can still be cloned.
    Structural write-safety checks always run.
    """
    if project.path is None:
        raise ValueError("Project must be saved before creating skills")
    files = files or {}

    if validate_files:
        errors = validate_bundle_files(files)
    else:
        errors = [
            error
            for error in (_unsafe_path_error(path) for path in files)
            if error is not None
        ]
    if not body or not body.strip():
        errors.append("body must be non-empty")
    name_conflict = _existing_skill_name_conflict(project, name)
    if name_conflict is not None:
        errors.append(name_conflict)
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
    _sweep_stale_staging(staging_root)
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
    except OSError as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        # A filesystem rejection of a validated bundle (e.g. an OS-specific
        # filename restriction) is a caller-fixable problem, not a crash.
        raise SkillBundleValidationError([f"could not write skill files: {e}"]) from e
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
    """Create a new skill from an existing one, copying its files.

    Copies every regular file in the source skill's directory except skill.kiln
    (a clone gets a fresh identity) and SKILL.md (regenerated from the new
    name/description/body) — so hand-added files outside references/ and
    assets/ survive the clone too. Content validation is skipped for the copied
    files since they already exist on disk; symlinks are not followed.

    name/description/body may differ from the source (a clone is a new skill,
    not a mutation).
    """
    if source.path is None:
        raise ValueError("Source skill must be saved before cloning")
    source_dir = source.path.parent
    files: Dict[str, bytes] = {}
    for root, _dirs, filenames in os.walk(source_dir, followlinks=False):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.is_symlink() or not file_path.is_file():
                continue
            relative = file_path.relative_to(source_dir).as_posix()
            if relative in (Skill.base_filename(), SKILL_MD_FILENAME):
                continue
            files[relative] = file_path.read_bytes()
    return create_skill_with_files(
        project,
        name=name,
        description=description,
        body=body,
        files=files,
        validate_files=False,
    )
