import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pygit2

from app.desktop.git_sync.config import AuthMode

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


def make_credentials(
    pat_token: str | None, auth_mode: str = "system_keys"
) -> pygit2.RemoteCallbacks:
    """Create pygit2 RemoteCallbacks using the specified auth strategy.

    auth_mode="system_keys": Use SSH keys from ~/.ssh/ (id_ed25519, id_rsa, id_ecdsa).
    auth_mode="pat_token": Use PAT token for HTTPS auth.

    This prevents pygit2 from falling through to system credential
    helpers which may prompt on stdin (fatal for a headless server).
    """

    called = False

    def credentials_callback(
        url: str,
        username_from_url: str | None,
        allowed_types: int,
    ) -> Any:
        nonlocal called
        if called:
            raise pygit2.GitError(
                "Authentication failed. Credentials were rejected by the server."
            )
        called = True

        if auth_mode == "system_keys":
            if allowed_types & pygit2.enums.CredentialType.SSH_KEY:
                username = username_from_url or "git"
                ssh_dir = os.path.expanduser("~/.ssh")
                for key_name in ("id_ed25519", "id_rsa", "id_ecdsa"):
                    priv = os.path.join(ssh_dir, key_name)
                    pub = priv + ".pub"
                    if os.path.isfile(priv) and os.path.isfile(pub):
                        return pygit2.Keypair(username, pub, priv, "")  # type: ignore[attr-defined]
            if allowed_types & pygit2.enums.CredentialType.USERNAME:
                return pygit2.Username("git")

        if auth_mode == "pat_token" and pat_token is not None:
            if allowed_types & pygit2.enums.CredentialType.USERPASS_PLAINTEXT:
                return pygit2.UserPass(username="x-token", password=pat_token)  # type: ignore[attr-defined]
            if allowed_types & pygit2.enums.CredentialType.USERNAME:
                return pygit2.Username("x-token")

        raise pygit2.GitError(
            "Authentication failed: no credentials available. "
            f"auth_mode={auth_mode}. "
            "Configure a Personal Access Token (PAT) for this repository."
        )

    callbacks = pygit2.RemoteCallbacks(credentials=credentials_callback)  # type: ignore[arg-type]
    return callbacks


def _ls_remote_pygit2(
    git_url: str,
    pat_token: str | None = None,
    auth_mode: AuthMode = "system_keys",
) -> list[dict[str, Any]]:
    """Fetch remote references using pygit2 (no system git required).

    Creates a temporary bare repo and uses Remote.ls_remotes() to list
    refs from the remote URL with proper auth callbacks.

    Returns list of ref dicts with keys: name, oid, symref_target, etc.
    Raises pygit2.GitError on failure.
    """
    callbacks = make_credentials(pat_token, auth_mode)
    tmpdir = tempfile.mkdtemp(prefix="kiln_ls_remote_")
    try:
        repo = pygit2.init_repository(tmpdir, bare=True)
        remote = repo.remotes.create("probe", git_url)
        return remote.ls_remotes(callbacks=callbacks)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_remote_access(
    git_url: str,
    pat_token: str | None = None,
    auth_mode: AuthMode | None = None,
) -> tuple[bool, str, str | None]:
    """Test access to a remote by listing references via pygit2.

    If auth_mode is provided, tests with that specific mode.
    If auth_mode is None, infers mode from pat_token: uses "pat_token"
    when a PAT is provided, "system_keys" otherwise.

    Returns (success, message, auth_mode_used).
    auth_mode_used is set on success to indicate which mode worked.
    """
    if auth_mode is not None:
        mode = auth_mode
    elif pat_token is not None:
        mode = "pat_token"
    else:
        mode = "system_keys"

    try:
        _ls_remote_pygit2(git_url, pat_token, mode)
        return True, "Access successful", mode
    except pygit2.GitError as e:
        error_lower = str(e).lower()
        if (
            "401" in error_lower
            or "403" in error_lower
            or "auth" in error_lower
            or "credentials" in error_lower
        ):
            return False, "Authentication failed", None
        return False, f"Cannot access remote: {e}", None
    except Exception as e:
        return False, f"Cannot access remote: {e}", None


def list_remote_branches(
    git_url: str,
    pat_token: str | None = None,
    auth_mode: AuthMode = "system_keys",
) -> tuple[list[str], str | None]:
    """List branches from a remote using pygit2.

    Returns (branches, default_branch). default_branch is the HEAD symref target
    if available, otherwise None.
    """
    ref_list = _ls_remote_pygit2(git_url, pat_token, auth_mode)

    branches: list[str] = []
    head_target: str | None = None

    for ref_dict in ref_list:
        name = ref_dict.get("name", "")
        symref_target = ref_dict.get("symref_target")

        if name.startswith("refs/heads/"):
            branches.append(name.removeprefix("refs/heads/"))

        if name == "HEAD" and symref_target:
            symref = str(symref_target)
            if symref.startswith("refs/heads/"):
                head_target = symref.removeprefix("refs/heads/")

    branches.sort()

    if head_target is None:
        if "main" in branches:
            head_target = "main"
        elif "master" in branches:
            head_target = "master"

    return branches, head_target


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
    auth_mode: AuthMode = "system_keys",
) -> pygit2.Repository:
    """Clone a repository into the given path.

    Sets up the clone with the specified branch and adds a .gitignore
    for common OS artifacts.
    """
    callbacks = make_credentials(pat_token, auth_mode)

    repo = pygit2.clone_repository(
        git_url,
        str(clone_path),
        checkout_branch=branch,
        callbacks=callbacks,
    )

    _ensure_gitignore(repo, clone_path, pat_token, auth_mode)

    return repo


def _ensure_gitignore(
    repo: pygit2.Repository,
    clone_path: Path,
    pat_token: str | None = None,
    auth_mode: AuthMode = "system_keys",
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

    callbacks = make_credentials(pat_token, auth_mode)
    remote = repo.remotes[DEFAULT_REMOTE_NAME]
    branch_name = repo.head.shorthand
    remote.push([f"refs/heads/{branch_name}"], callbacks=callbacks)


def test_write_access(
    clone_path: Path,
    pat_token: str | None = None,
    auth_mode: AuthMode = "system_keys",
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

        cred_callbacks = make_credentials(pat_token, auth_mode)
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
