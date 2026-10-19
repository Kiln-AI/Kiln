from pathlib import Path


def reload_excludes(repo_root: Path) -> list[str]:
    """Absolute paths of the folders under repo_root that auto-reload should not watch."""
    # Uvicorn (0.32) skips a folder only when given its absolute path, and fails to
    # start if that path doesn't exist, so only existing folders are listed.
    folders = (repo_root / ".venv", repo_root / ".worktrees")
    return [str(folder) for folder in folders if folder.is_dir()]
