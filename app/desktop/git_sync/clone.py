import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pygit2

logger = logging.getLogger(__name__)

OS_GITIGNORE = """\
# macOS
.DS_Store
._*

# Windows
Thumbs.db
desktop.ini
ehthumbs.db

# Linux
*~
.directory
"""

DEFAULT_REMOTE_NAME = "origin"


def make_push_callbacks(
    cred_callbacks: pygit2.RemoteCallbacks,
    push_errors: list[str],
) -> pygit2.RemoteCallbacks:
    """Create RemoteCallbacks that capture push rejection messages.

    Reuses credentials from *cred_callbacks* and appends any push-rejection
    messages to *push_errors*.
    """

    class _PushCallbacks(pygit2.RemoteCallbacks):
        def push_update_reference(self, refname: str, message: str | None) -> None:
            if message is not None:
                push_errors.append(f"Push rejected for {refname}: {message}")

    return _PushCallbacks(credentials=cred_callbacks.credentials)  # type: ignore[arg-type]


def make_credentials(pat_token: str | None) -> pygit2.RemoteCallbacks:
    """Create pygit2 RemoteCallbacks that never prompt for credentials.

    If a PAT token is provided, uses it for authentication.
    If no token is provided, the callback raises an error instead of
    allowing pygit2 to fall through to system credential helpers
    (which may prompt on stdin).
    """

    def credentials_callback(
        url: str,
        username_from_url: str | None,
        allowed_types: int,
    ) -> Any:
        if pat_token is not None:
            if allowed_types & pygit2.enums.CredentialType.USERPASS_PLAINTEXT:
                return pygit2.UserPass(username="x-token", password=pat_token)  # type: ignore[attr-defined]
            if allowed_types & pygit2.enums.CredentialType.USERNAME:
                return pygit2.Username("x-token")
        raise pygit2.GitError(
            "Authentication required but no credentials available. "
            "Configure a Personal Access Token (PAT) for this repository."
        )

    callbacks = pygit2.RemoteCallbacks(credentials=credentials_callback)  # type: ignore[arg-type]
    return callbacks


def _build_authenticated_url(git_url: str, pat_token: str | None) -> str:
    """Insert PAT token into a git URL for authentication.

    Supports https:// URLs. For other URL schemes, returns the original URL.
    """
    if pat_token is None:
        return git_url

    if git_url.startswith("https://"):
        return git_url.replace("https://", f"https://x-token:{pat_token}@", 1)

    return git_url


def _run_git_ls_remote(
    git_url: str, pat_token: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git ls-remote --symref against the given URL.

    Returns the CompletedProcess result. Raises no exception on failure;
    caller should check returncode.
    """
    authenticated_url = _build_authenticated_url(git_url, pat_token)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", "ls-remote", "--symref", authenticated_url],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def test_remote_access(git_url: str, pat_token: str | None = None) -> tuple[bool, str]:
    """Test access to a remote by listing references.

    Returns (success, message). On auth failure, message indicates credentials are needed.
    """
    try:
        result = _run_git_ls_remote(git_url, pat_token)
        if result.returncode == 0:
            return True, "Access successful"
        error_str = result.stderr.lower()
        # TODO: make auth detection more robust — this is brittle string matching
        if (
            "401" in error_str
            or "403" in error_str
            or "auth" in error_str
            or "terminal prompts disabled" in error_str
        ):
            return False, "Authentication required"
        return False, f"Cannot access remote: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "Cannot access remote: connection timed out"
    except Exception as e:
        return False, f"Cannot access remote: {e}"


def _parse_ls_remote_output(output: str) -> tuple[list[str], str | None]:
    """Parse the output of git ls-remote --symref.

    The output contains lines like:
        ref: refs/heads/main\tHEAD
        <oid>\tHEAD
        <oid>\trefs/heads/main
        <oid>\trefs/heads/feature

    Returns (branches, default_branch).
    """
    head_target: str | None = None
    branches: list[str] = []

    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Parse symref lines: "ref: refs/heads/main\tHEAD"
        if line.startswith("ref:"):
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[1].strip() == "HEAD":
                symref = parts[0].removeprefix("ref:").strip()
                if symref.startswith("refs/heads/"):
                    head_target = symref.removeprefix("refs/heads/")
            continue

        # Parse ref lines: "<oid>\t<refname>"
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        ref_name = parts[1].strip()
        if ref_name.startswith("refs/heads/"):
            branch_name = ref_name.removeprefix("refs/heads/")
            branches.append(branch_name)

    branches.sort()

    if head_target is None:
        if "main" in branches:
            head_target = "main"
        elif "master" in branches:
            head_target = "master"

    return branches, head_target


def list_remote_branches(
    git_url: str, pat_token: str | None = None
) -> tuple[list[str], str | None]:
    """List branches from a remote.

    Returns (branches, default_branch). default_branch is the HEAD symref target
    if available, otherwise None.
    """
    result = _run_git_ls_remote(git_url, pat_token)
    if result.returncode != 0:
        raise pygit2.GitError(f"Failed to list remote refs: {result.stderr.strip()}")

    return _parse_ls_remote_output(result.stdout)


def compute_clone_path(base_dir: Path, project_name: str, project_id: str) -> Path:
    """Compute a unique clone path under .git-projects/.

    Format: .git-projects/[ID] - [projectname][N]
    where N is a counter suffix added only if the name collides.
    """
    git_projects_dir = base_dir / ".git-projects"
    git_projects_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^\w\s-]", "", project_name).strip()
    if not safe_name:
        safe_name = "project"

    base_name = f"{project_id} - {safe_name}"
    candidate = git_projects_dir / base_name

    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = git_projects_dir / f"{base_name}{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def clone_repo(
    git_url: str,
    clone_path: Path,
    branch: str,
    pat_token: str | None = None,
) -> pygit2.Repository:
    """Clone a repository into the given path.

    Sets up the clone with the specified branch and adds a .gitignore
    for common OS artifacts.
    """
    callbacks = make_credentials(pat_token)

    repo = pygit2.clone_repository(
        git_url,
        str(clone_path),
        checkout_branch=branch,
        callbacks=callbacks,
    )

    _ensure_gitignore(repo, clone_path, pat_token)

    return repo


def _ensure_gitignore(
    repo: pygit2.Repository, clone_path: Path, pat_token: str | None = None
) -> None:
    """Ensure the clone has a .gitignore covering common OS artifacts."""
    gitignore_path = clone_path / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        missing_patterns = []
        for line in OS_GITIGNORE.strip().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            if line.strip() not in content:
                missing_patterns.append(line.strip())

        if not missing_patterns:
            return

        with open(gitignore_path, "a") as f:
            f.write("\n# Added by Kiln AI\n")
            for pattern in missing_patterns:
                f.write(f"{pattern}\n")
    else:
        gitignore_path.write_text(OS_GITIGNORE)

    index = repo.index
    index.add(".gitignore")
    index.write()

    tree = index.write_tree()
    sig = pygit2.Signature("Kiln AI", "sync@kiln.ai")
    parents = [repo.head.target]
    repo.create_commit(
        repo.head.name,
        sig,
        sig,
        "[Kiln] Add .gitignore for OS artifacts",
        tree,
        parents,
    )

    callbacks = make_credentials(pat_token)
    remote = repo.remotes[DEFAULT_REMOTE_NAME]
    branch_name = repo.head.shorthand
    remote.push([f"refs/heads/{branch_name}"], callbacks=callbacks)


def test_write_access(
    clone_path: Path, pat_token: str | None = None
) -> tuple[bool, str]:
    """Test write access by pushing an empty commit.

    Returns (success, message).
    """
    try:
        repo = pygit2.Repository(str(clone_path))
        sig = pygit2.Signature("Kiln AI", "sync@kiln.ai")

        tree = repo.index.write_tree()
        parents = [repo.head.target]
        repo.create_commit(
            repo.head.name,
            sig,
            sig,
            "Empty commit: checking write access for Kiln AI Git Auto Sync setup",
            tree,
            parents,
        )

        cred_callbacks = make_credentials(pat_token)
        remote = repo.remotes[DEFAULT_REMOTE_NAME]
        branch_name = repo.head.shorthand

        push_errors: list[str] = []
        push_cb = make_push_callbacks(cred_callbacks, push_errors)

        remote.push([f"refs/heads/{branch_name}"], callbacks=push_cb)

        if push_errors:
            return False, "; ".join(push_errors)

        return True, "Write access confirmed"
    except pygit2.GitError as e:
        error_str = str(e).lower()
        if "401" in error_str or "403" in error_str or "auth" in error_str:
            return False, "Authentication failed - check your token permissions"
        return False, f"Write access check failed: {e}"
    except Exception as e:
        return False, f"Write access check failed: {e}"


def scan_for_projects(clone_path: Path) -> list[dict[str, str]]:
    """Scan a cloned repo for project.kiln files.

    Returns a list of dicts with 'path' (relative), 'name', and 'description'.
    """
    results: list[dict[str, str]] = []
    for kiln_file in clone_path.rglob("project.kiln"):
        rel_path = str(kiln_file.relative_to(clone_path))
        name = ""
        description = ""
        project_id = ""
        try:
            data = json.loads(kiln_file.read_text())
            name = data.get("name", "")
            description = data.get("description", "")
            project_id = data.get("id", "")
        except Exception:
            pass

        results.append(
            {
                "path": rel_path,
                "name": name or rel_path,
                "description": description,
                "id": project_id,
            }
        )

    results.sort(key=lambda r: r["path"])
    return results
