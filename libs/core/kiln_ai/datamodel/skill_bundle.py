"""Atomic creation of skill bundles (SKILL.md + references/ + assets/).

A skill bundle is created fully formed or not at all: the whole tree is staged
in a hidden directory inside the project folder (same filesystem as skills/),
then committed with a single os.rename. No observer — the studio server reads
disk live — can ever see a partial skill.

Skills are install-once: iteration happens by creating a new skill (e.g. a
clone), never by mutating an installed one. Stored eval results that
reference a skill therefore stay valid, since drive fingerprints don't cover
skill files. Names may repeat across skills — coexisting versions of a skill
share a name and differ by id — so identity is always the id.
"""

from __future__ import annotations

import errno
import os
import shutil
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, Iterable, Optional

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import (
    RESOURCE_DIR_NAMES,
    SKILL_MD_FILENAME,
    Skill,
)

MAX_RESOURCE_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_FILE_COUNT = 500

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
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return f"resource path contains characters that cannot be encoded: {path!r}"
    if path.startswith("/"):
        return f"resource path must be relative: {path!r}"
    if path.endswith("/"):
        return f"resource path must include a filename: {path!r}"
    for segment in path.split("/"):
        if segment in ("", ".", ".."):
            return f"resource path contains an invalid segment: {path!r}"
    return None


def _unsafe_copy_path_error(path: str) -> str | None:
    """Containment-only checks for paths of files copied from disk.

    Unlike _unsafe_path_error this allows backslashes: on POSIX a backslash is
    a legal character inside a filename, and hand-added files must stay
    cloneable. Walk-derived paths never use backslash as a separator
    (as_posix normalizes), so containment is all that matters here.
    """
    if not path or not path.strip():
        return "resource path cannot be empty"
    if "\x00" in path:
        return f"resource path contains a null byte: {path!r}"
    try:
        os.fsencode(path)
    except UnicodeEncodeError:
        return f"resource path contains characters that cannot be encoded: {path!r}"
    if path.startswith("/"):
        return f"resource path must be relative: {path!r}"
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
    if len(files) > MAX_BUNDLE_FILE_COUNT:
        errors.append(f"too many files: {len(files)} (cap {MAX_BUNDLE_FILE_COUNT})")
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
                f"file too large: {path!r} is {len(content)} bytes (cap {MAX_RESOURCE_FILE_BYTES})"
            )
        # The skill tool decodes references as UTF-8 at runtime — reject at
        # install time, not at runtime. Assets may be binary.
        if path.startswith("references/"):
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"references file is not UTF-8 text: {path!r}")
    if total_bytes > MAX_BUNDLE_BYTES:
        errors.append(
            f"bundle too large: {total_bytes} bytes total (cap {MAX_BUNDLE_BYTES})"
        )

    errors.extend(path_collision_errors(valid_paths))
    return errors


def path_collision_errors(paths: list[str]) -> list[str]:
    """Errors for paths that collide once written to a real filesystem: no two
    paths differing only by case or Unicode normalization (case-insensitive,
    normalization-insensitive filesystems on macOS/Windows would silently
    overwrite), and no path that is both a file and a parent directory of
    another file."""

    def fold(path: str) -> str:
        return unicodedata.normalize("NFC", path).casefold()

    errors: list[str] = []
    seen_folded: dict[str, str] = {}
    for path in paths:
        folded = fold(path)
        if folded in seen_folded:
            errors.append(
                f"file paths collide on a case- or normalization-insensitive "
                f"filesystem: {seen_folded[folded]!r} and {path!r}"
            )
        else:
            seen_folded[folded] = path
    dir_prefixes = {
        fold("/".join(path.split("/")[:i]))
        for path in paths
        for i in range(1, len(path.split("/")))
    }
    for path in paths:
        if fold(path) in dir_prefixes:
            errors.append(f"path is used as both a file and a directory: {path!r}")
    return errors


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


def sweep_stale_skill_staging(project_file_paths: Iterable[Path | str]) -> None:
    """Sweep crash-orphaned skill staging debris for the given projects.

    Intended for app startup, so abandoned drafts never accumulate in synced
    project folders. Best-effort: never raises, never touches a staging dir
    younger than STALE_STAGING_AGE_SECS (it could be another process's live
    install).
    """
    for project_file_path in project_file_paths:
        try:
            staging_root = Path(project_file_path).parent / STAGING_DIR_NAME
            # is_dir() follows symlinks: a symlinked staging root (e.g. synced
            # in) must never redirect the sweep's deletions elsewhere.
            if staging_root.is_dir() and not staging_root.is_symlink():
                _sweep_stale_staging(staging_root)
                _remove_staging_root_if_empty(staging_root)
        except OSError:
            continue


def _fsync_best_effort(path: Path | str) -> None:
    """fsync a file or directory without ever failing the install: on Windows,
    fsync of a read-only fd and of directories is unsupported, and durability
    must never break creation itself."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _fsync_tree(root: Path) -> None:
    """Flush staged writes to stable storage before the commit rename, so a
    power loss after install can never leave truncated files behind the
    'fully formed' promise. Best-effort throughout."""
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            _fsync_best_effort(os.path.join(dirpath, name))
        _fsync_best_effort(dirpath)


def _remove_staging_root_if_empty(staging_root: Path) -> None:
    """Remove the hidden staging root so it doesn't linger in a synced project
    folder. A non-empty root (a concurrent install's live staging) is left."""
    try:
        os.rmdir(staging_root)
    except OSError:
        pass


def create_skill_with_files(
    project: Project,
    name: str,
    description: str,
    body: str,
    files: Optional[Dict[str, bytes]] = None,
    copy_files: Optional[Dict[str, Path]] = None,
    extra_dirs: Optional[list[str]] = None,
    validate_files: bool = True,
    extra_errors: Optional[list[str]] = None,
) -> Skill:
    """Create a skill atomically, with optional resource files.

    files maps bundle-relative paths ('references/…', 'assets/…') to content.
    copy_files maps bundle-relative paths to existing on-disk files, streamed
    into the bundle without loading them into memory — clone uses it.
    extra_dirs lists bundle-relative directories to create even when empty,
    so a cloned skill keeps scaffold directories its SKILL.md refers to.
    Raises SkillBundleValidationError with every failure accumulated, so a
    caller fixes the bundle once rather than one round trip per defect.
    extra_errors lets a caller merge failures it found upstream (e.g. request
    decoding) into that single accumulated report.

    validate_files=False skips the content rules (allowed roots, size caps,
    UTF-8 references) for files that already exist on disk — clone uses it so
    a skill with hand-added oversized or unusual files can still be cloned.
    Containment checks always run, on both files and copy_files.
    """
    if project.path is None:
        raise ValueError("Project must be saved before creating skills")
    files = files or {}
    copy_files = copy_files or {}
    extra_dirs = extra_dirs or []

    errors = list(extra_errors or [])
    if validate_files:
        errors.extend(validate_bundle_files(files))
    else:
        errors.extend(
            error
            for error in (_unsafe_path_error(path) for path in files)
            if error is not None
        )
    errors.extend(
        error
        for error in (
            _unsafe_copy_path_error(path) for path in [*copy_files, *extra_dirs]
        )
        if error is not None
    )
    if copy_files:
        for overlap in sorted(files.keys() & copy_files.keys()):
            errors.append(f"path appears in both files and copy_files: {overlap!r}")
        if validate_files:
            # Skipped for on-disk copies (clone): files that coexist on the
            # source filesystem can coexist on the destination, even when
            # they would collide on a case-insensitive filesystem.
            errors.extend(
                error
                for error in path_collision_errors([*files, *copy_files])
                if error not in errors
            )
    if not body or not body.strip():
        errors.append("body must be non-empty")
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
    try:
        staging_root.mkdir(exist_ok=True)
    except FileExistsError:
        # A regular file squatting on the staging dir name (e.g. a sync
        # conflict artifact) would otherwise break every install with a 500.
        raise SkillBundleValidationError(
            [
                f"a file named {STAGING_DIR_NAME!r} exists in the project "
                "folder where the skill staging directory belongs — remove "
                "it and retry"
            ]
        ) from None
    if staging_root.is_symlink():
        # Never stage through a symlink: the atomic-rename guarantee (and the
        # cleanup paths) assume the real directory lives in the project folder.
        raise SkillBundleValidationError(
            [
                f"{STAGING_DIR_NAME!r} in the project folder is a symlink — "
                "remove it and retry"
            ]
        )
    _sweep_stale_staging(staging_root)
    staging_dir = staging_root / f"skill-{uuid.uuid4().hex}"
    # parents=True: a concurrent install finishing at this moment may have
    # removed the just-created (empty) staging root.
    staging_dir.mkdir(parents=True)
    try:
        skill.path = staging_dir / Skill.base_filename()
        skill.save_to_file()
        skill.save_skill_md(body)
        for relative_path, content in files.items():
            destination = staging_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        for relative_path, source_path in copy_files.items():
            destination = staging_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(source_path, destination)
            except FileNotFoundError:
                # Source vanished since it was listed (e.g. the user is
                # editing the folder directly) — copy what still exists.
                continue
        for relative_dir in extra_dirs:
            (staging_dir / relative_dir).mkdir(parents=True, exist_ok=True)
        _fsync_tree(staging_dir)
        try:
            final_dir.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # A regular file squatting on the skills/ directory name (e.g. a
            # sync conflict artifact) — same friendly handling as the
            # staging-root squat above.
            raise SkillBundleValidationError(
                [
                    f"a file named {final_dir.parent.name!r} exists in the "
                    "project folder where the skills directory belongs — "
                    "remove it and retry"
                ]
            ) from None
        if final_dir.exists():
            raise SkillBundleValidationError(
                [f"skill directory already exists: {final_dir.name}"]
            )
        # The commit point: before this rename the skill doesn't exist
        # anywhere visible; after it, it exists fully formed. Flushing the
        # parent directory entry makes the reported success durable — without
        # it a power loss could roll the rename back after the 200.
        os.rename(staging_dir, final_dir)
        _fsync_best_effort(final_dir.parent)
    except UnicodeEncodeError as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        _remove_staging_root_if_empty(staging_root)
        # A path the filesystem encoding rejects that slipped past validation
        # is caller-fixable, not a crash.
        raise SkillBundleValidationError([f"could not write skill files: {e}"]) from e
    except OSError as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        _remove_staging_root_if_empty(staging_root)
        # An OS rejection of a filename (e.g. a Windows-specific restriction
        # the portability checks missed) is caller-fixable; environment
        # failures like a full disk or permissions are not — those propagate.
        if e.errno in (errno.EINVAL, errno.ENAMETOOLONG):
            raise SkillBundleValidationError(
                [f"could not write skill files: {e}"]
            ) from e
        raise
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        _remove_staging_root_if_empty(staging_root)
        raise

    _remove_staging_root_if_empty(staging_root)
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
    assets/ survive the clone too, as do empty scaffold directories. Files
    are streamed, never loaded into memory, and content validation is
    skipped since they already exist on disk; symlinks are not followed.

    name/description/body may differ from the source (a clone is a new skill,
    not a mutation).
    """
    if source.path is None:
        raise ValueError("Source skill must be saved before cloning")
    source_dir = source.path.parent
    copy_files: Dict[str, Path] = {}
    extra_dirs: list[str] = []
    for root, dirs, filenames in os.walk(source_dir, followlinks=False):
        root_path = Path(root)
        for dirname in dirs:
            dir_path = root_path / dirname
            if dir_path.is_symlink():
                continue
            extra_dirs.append(dir_path.relative_to(source_dir).as_posix())
        for filename in filenames:
            file_path = root_path / filename
            if file_path.is_symlink() or not file_path.is_file():
                continue
            relative = file_path.relative_to(source_dir).as_posix()
            # Case/normalization-folded: on a case-insensitive filesystem a
            # variant like 'Skill.MD' is the same file as the SKILL.md the
            # clone regenerates, and copying it would silently overwrite the
            # new identity/content in staging.
            folded = unicodedata.normalize("NFC", relative).casefold()
            if folded in (
                Skill.base_filename().casefold(),
                SKILL_MD_FILENAME.casefold(),
            ):
                continue
            copy_files[relative] = file_path
    return create_skill_with_files(
        project,
        name=name,
        description=description,
        body=body,
        copy_files=copy_files,
        extra_dirs=extra_dirs,
        validate_files=False,
    )
