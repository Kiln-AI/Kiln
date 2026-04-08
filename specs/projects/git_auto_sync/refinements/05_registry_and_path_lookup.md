# Refinement: Registry Race Fix + Path-to-Project Lookup

**Resolves:** Crit #5 (registry TOCTOU race), Crit #6 (`find_project_id_for_path` unspecified)

## Registry race fix (#5)

Add a `threading.Lock` to `GitSyncRegistry` protecting `get_or_create_for_project`:

```python
_lock = threading.Lock()

@classmethod
def get_or_create_for_project(cls, project_path: Path) -> GitSyncManager | None:
    repo_path = cls._find_repo_root(project_path)
    if repo_path is None:
        return None
    with cls._lock:
        if repo_path not in cls._managers:
            manager = GitSyncManager(repo_path=repo_path)
            cls.register(repo_path, manager)
        return cls._managers[repo_path]
```

## find_project_id_for_path (#6)

Walk up the directory tree from the given file path until finding a folder that contains `project.kiln`. Read that file to get the project ID.

```python
def find_project_id_for_path(path: Path) -> str | None:
    """Given a file path, find the owning project by walking up
    until a directory contains 'project.kiln'."""
    current = path if path.is_dir() else path.parent
    while current != current.parent:
        project_file = current / "project.kiln"
        if project_file.exists():
            # Read project ID from the file
            ...
            return project_id
        current = current.parent
    return None
```

For URL extraction (`_extract_project_id`): straightforward parse of `/api/projects/{project_id}/...` from the request path.
