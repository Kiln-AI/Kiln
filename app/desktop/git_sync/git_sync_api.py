import asyncio
import html
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as FastAPIPath
from fastapi.responses import HTMLResponse
from kiln_ai.utils.project_utils import (
    DuplicateProjectError,
    check_duplicate_project_id,
)
from kiln_server.project_api import add_project_to_config, default_project_path
from kiln_server.utils.agent_checks import DENY_AGENT
from pydantic import BaseModel, Field

from app.desktop.git_sync.clone import (
    clone_repo,
    compute_clone_path,
    compute_temp_clone_path,
    list_remote_branches,
    rename_clone_to_final_path,
    scan_for_projects,
    test_remote_access,
    test_write_access,
)
from app.desktop.git_sync.config import (
    GitSyncProjectConfig,
    delete_git_sync_config,
    get_git_sync_config,
    project_path_from_id,
    save_git_sync_config,
)
from app.desktop.git_sync.oauth import (
    OAuthError,
    OAuthFlowManager,
    build_authorize_url,
    build_install_url,
    exchange_code_for_token,
    parse_github_owner_repo,
    resolve_github_owner_id,
    resolve_github_repo_id,
)

logger = logging.getLogger(__name__)


_OAUTH_PAGE_STYLES = """
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f8fafc;
    color: #0f172a;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .card {
    max-width: 420px;
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }
  .icon {
    width: 56px;
    height: 56px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .icon.success { background: #dcfce7; color: #15803d; }
  .icon.error { background: #fee2e2; color: #b91c1c; }
  .icon svg { width: 28px; height: 28px; }
  h1 { font-size: 20px; font-weight: 600; margin: 0; }
  p { font-size: 14px; color: #64748b; margin: 0; line-height: 1.5; }
  .detail { color: #475569; word-break: break-word; }
"""

_SUCCESS_ICON_PATH = "M4.5 12.75l6 6 9-13.5"
_ERROR_ICON_PATH = "M6 18L18 6M6 6l12 12"


def _render_oauth_page(title: str, body: str, *, is_error: bool = False) -> str:
    icon_class = "error" if is_error else "success"
    icon_path = _ERROR_ICON_PATH if is_error else _SUCCESS_ICON_PATH
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escaped_title}</title>
<style>{_OAUTH_PAGE_STYLES}</style>
</head>
<body>
  <div class="card">
    <div class="icon {icon_class}">
      <svg fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="{icon_path}" />
      </svg>
    </div>
    <h1>{escaped_title}</h1>
    {body}
  </div>
</body>
</html>
"""


_RETURN_TO_KILN = "<p>Return to Kiln to continue setup</p>"
OAUTH_SUCCESS_HTML = _render_oauth_page("Authorization Complete", _RETURN_TO_KILN)
INSTALL_COMPLETE_HTML = _render_oauth_page("Install Complete", _RETURN_TO_KILN)


def render_oauth_error_page(message: str) -> str:
    body = (
        f'<p class="detail">{html.escape(message)}</p>'
        "<p>You can close this tab and try again in Kiln.</p>"
    )
    return _render_oauth_page("Authorization Failed", body, is_error=True)


class TestAccessRequest(BaseModel):
    """Request to test read access to a git remote."""

    git_url: str = Field(description="The git remote URL to test access against.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    oauth_token: str | None = Field(
        default=None, description="Optional OAuth token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys', 'pat_token', or 'github_oauth'.",
    )


class TestAccessResponse(BaseModel):
    """Result of a git remote access test."""

    success: bool = Field(description="Whether access to the remote succeeded.")
    message: str = Field(description="Human-readable result message.")
    auth_required: bool = Field(
        default=False,
        description="True when the failure is due to missing authentication.",
    )
    auth_method: str | None = Field(
        default=None,
        description="Auth method that succeeded: 'system_keys', 'pat_token', or 'github_oauth'. Null on failure.",
    )


class ListBranchesRequest(BaseModel):
    """Request to list branches on a git remote."""

    git_url: str = Field(description="The git remote URL to list branches from.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    oauth_token: str | None = Field(
        default=None, description="Optional OAuth token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys', 'pat_token', or 'github_oauth'.",
    )


class ListBranchesResponse(BaseModel):
    """List of branches available on the remote."""

    branches: list[str] = Field(description="Branch names available on the remote.")
    default_branch: str | None = Field(
        default=None, description="The HEAD branch of the remote, if detected."
    )


class CloneRequest(BaseModel):
    """Request to clone a git repository into a temporary directory."""

    git_url: str = Field(description="The git remote URL to clone.")
    branch: str = Field(description="The branch to check out after cloning.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    oauth_token: str | None = Field(
        default=None, description="Optional OAuth token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys', 'pat_token', or 'github_oauth'.",
    )


class CloneResponse(BaseModel):
    """Result of a clone operation."""

    clone_path: str = Field(description="Filesystem path where the repo was cloned.")
    success: bool = Field(description="Whether the clone succeeded.")
    message: str = Field(description="Human-readable result message.")


class TestWriteAccessRequest(BaseModel):
    """Request to test push/write access to a cloned repo's remote."""

    clone_path: str = Field(description="Local filesystem path of the cloned repo.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    oauth_token: str | None = Field(
        default=None, description="Optional OAuth token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys', 'pat_token', or 'github_oauth'.",
    )


class ScanProjectsRequest(BaseModel):
    """Request to scan a cloned repo for Kiln project files."""

    clone_path: str = Field(description="Local filesystem path of the cloned repo.")


class RenameCloneRequest(BaseModel):
    """Request to rename a temp clone directory to its final path."""

    clone_path: str = Field(
        description="Current filesystem path of the cloned repo (typically in .tmp/)."
    )
    project_name: str = Field(
        description="Human-readable project name for the final directory."
    )
    project_id: str = Field(
        description="Unique project identifier used in the final path."
    )


class RenameCloneResponse(BaseModel):
    """Result of renaming a clone directory."""

    new_clone_path: str = Field(
        description="The new filesystem path of the renamed clone."
    )
    success: bool = Field(description="Whether the rename succeeded.")
    message: str = Field(description="Human-readable result message.")


class ProjectInfo(BaseModel):
    """Metadata about a discovered Kiln project."""

    path: str = Field(description="Relative path to the project.kiln file.")
    name: str = Field(description="Project name from the project file.")
    description: str = Field(description="Project description from the project file.")
    id: str = Field(default="", description="Unique project identifier.")


class ScanProjectsResponse(BaseModel):
    """Projects discovered inside a cloned repository."""

    projects: list[ProjectInfo] = Field(description="List of discovered projects.")


class SaveConfigRequest(BaseModel):
    """Request to save a complete git sync configuration for a project."""

    project_id: str = Field(description="Unique project identifier.")
    project_path: str = Field(
        description="Relative path to the project.kiln file within the clone."
    )
    git_url: str = Field(description="The git remote URL.")
    clone_path: str = Field(description="Local filesystem path of the clone.")
    branch: str = Field(description="Branch name to sync.")
    remote_name: str = Field(default="origin", description="Git remote name.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    oauth_token: str | None = Field(
        default=None, description="Optional OAuth token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode detected during setup: 'system_keys', 'pat_token', or 'github_oauth'.",
    )
    sync_mode: Literal["auto", "manual"] = Field(
        default="auto", description="Sync mode: 'auto' or 'manual'."
    )


class GitSyncConfigResponse(BaseModel):
    """Current git sync configuration for a project (PAT redacted)."""

    sync_mode: Literal["auto", "manual"] = Field(
        description="Sync mode: 'auto' or 'manual'."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys', 'pat_token', or 'github_oauth'.",
    )
    remote_name: str = Field(description="Git remote name.")
    branch: str = Field(description="Branch name being synced.")
    clone_path: str | None = Field(
        default=None, description="Local filesystem path of the clone."
    )
    git_url: str | None = Field(default=None, description="The git remote URL.")
    has_pat_token: bool = Field(
        default=False,
        description="Whether a PAT token is configured (token not shown).",
    )
    has_oauth_token: bool = Field(
        default=False,
        description="Whether an OAuth token is configured (token not shown).",
    )


class UpdateConfigRequest(BaseModel):
    """Request to partially update a git sync configuration."""

    sync_mode: Literal["auto", "manual"] | None = Field(
        default=None, description="New sync mode, if changing."
    )
    pat_token: str | None = Field(
        default=None, description="New personal access token, if changing."
    )
    oauth_token: str | None = Field(
        default=None, description="New OAuth token, if changing."
    )
    auth_mode: Literal["system_keys", "pat_token", "github_oauth"] | None = Field(
        default=None, description="New auth mode, if changing."
    )


class DeleteConfigResponse(BaseModel):
    """Confirmation that a git sync configuration was deleted."""

    message: str = Field(description="Human-readable confirmation message.")


class OAuthStartRequest(BaseModel):
    """Request to start a GitHub OAuth flow."""

    git_url: str = Field(description="The git remote URL to authenticate against.")


class OAuthStartResponse(BaseModel):
    """Response from starting a GitHub OAuth flow."""

    authorize_url: str = Field(
        description="GitHub OAuth authorization URL to open in the browser."
    )
    install_url: str = Field(
        description="GitHub App installation URL (used if app not yet installed on repo)."
    )
    state: str = Field(description="OAuth state parameter for polling.")
    owner_name: str = Field(description="Parsed owner name from git URL.")
    repo_name: str = Field(description="Parsed repo name from git URL.")
    owner_pre_selected: bool = Field(
        description="Whether the owner was pre-selected in the install URL."
    )
    repo_pre_selected: bool = Field(
        description="Whether the repo was pre-selected in the install URL."
    )


class OAuthStatusResponse(BaseModel):
    """Status of an in-progress OAuth flow."""

    complete: bool = Field(description="Whether the OAuth flow has completed.")
    oauth_token: str | None = Field(
        default=None, description="The OAuth token, if flow completed successfully."
    )
    error: str | None = Field(
        default=None, description="Error message, if flow failed."
    )


def _validate_clone_path(clone_path: str) -> Path:
    """Validate that a clone_path is within an OS temp directory.

    Setup wizard clone paths are created by compute_temp_clone_path() which
    uses tempfile.mkdtemp(), so legitimate paths always reside under the
    system temp directory.
    """
    import tempfile

    resolved = Path(clone_path).resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if not str(resolved).startswith(str(tmp_root) + os.sep):
        raise HTTPException(
            status_code=400,
            detail="clone_path must be within the system temp directory",
        )
    return resolved


def connect_git_sync_api(app: FastAPI):
    @app.post(
        "/api/git_sync/test_access",
        summary="Test Git Remote Access",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_test_access(request: TestAccessRequest) -> TestAccessResponse:
        success, message, detected_mode = await asyncio.to_thread(
            test_remote_access,
            request.git_url,
            request.pat_token,
            auth_mode=request.auth_mode,
            oauth_token=request.oauth_token,
        )
        auth_required = not success and "auth" in message.lower()
        return TestAccessResponse(
            success=success,
            message=message,
            auth_required=auth_required,
            auth_method=detected_mode,
        )

    @app.post(
        "/api/git_sync/list_branches",
        summary="List Remote Branches",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_list_branches(
        request: ListBranchesRequest,
    ) -> ListBranchesResponse:
        try:
            branches, default_branch = await asyncio.to_thread(
                list_remote_branches,
                request.git_url,
                request.pat_token,
                request.auth_mode,
                request.oauth_token,
            )
            return ListBranchesResponse(
                branches=branches, default_branch=default_branch
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to list branches: {e}")

    @app.post(
        "/api/git_sync/clone",
        summary="Clone Repository",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_clone(request: CloneRequest) -> CloneResponse:
        try:
            clone_path = compute_temp_clone_path()

            await asyncio.to_thread(
                clone_repo,
                request.git_url,
                clone_path,
                request.branch,
                request.pat_token,
                request.auth_mode,
                request.oauth_token,
            )

            return CloneResponse(
                clone_path=str(clone_path),
                success=True,
                message="Repository cloned successfully",
            )
        except Exception as e:
            error_str = str(e).lower()
            if "401" in error_str or "403" in error_str or "auth" in error_str:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication failed - check your token permissions",
                )
            raise HTTPException(status_code=400, detail=f"Clone failed: {e}")

    @app.post(
        "/api/git_sync/test_write_access",
        summary="Test Write Access",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_test_write_access(
        request: TestWriteAccessRequest,
    ) -> TestAccessResponse:
        _validate_clone_path(request.clone_path)
        success, message = await asyncio.to_thread(
            test_write_access,
            Path(request.clone_path),
            request.pat_token,
            request.auth_mode,
            request.oauth_token,
        )
        auth_required = not success and "auth" in message.lower()
        return TestAccessResponse(
            success=success, message=message, auth_required=auth_required
        )

    @app.post(
        "/api/git_sync/scan_projects",
        summary="Scan for Kiln Projects",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_scan_projects(
        request: ScanProjectsRequest,
    ) -> ScanProjectsResponse:
        _validate_clone_path(request.clone_path)
        clone_path = Path(request.clone_path)
        if not clone_path.exists():
            raise HTTPException(status_code=400, detail="Clone path does not exist")

        results = await asyncio.to_thread(scan_for_projects, clone_path)
        projects = [ProjectInfo(**r) for r in results]
        return ScanProjectsResponse(projects=projects)

    @app.post(
        "/api/git_sync/rename_clone",
        summary="Rename Clone to Final Path",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_rename_clone(request: RenameCloneRequest) -> RenameCloneResponse:
        base_dir = Path(default_project_path())
        current_path = Path(request.clone_path).resolve()

        if not current_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail="clone_path does not exist or is not a directory",
            )

        final_path = compute_clone_path(
            base_dir, request.project_name, request.project_id
        )
        allowed_dir = (base_dir / ".git-projects").resolve()
        if not str(final_path.resolve()).startswith(str(allowed_dir) + os.sep):
            raise HTTPException(
                status_code=400,
                detail="Destination path must be within the .git-projects directory",
            )

        try:
            new_path = await asyncio.to_thread(
                rename_clone_to_final_path,
                current_path,
                final_path,
            )

            return RenameCloneResponse(
                new_clone_path=str(new_path),
                success=True,
                message="Clone renamed successfully",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to rename clone: {e}")

    @app.post(
        "/api/git_sync/save_config",
        summary="Save Git Sync Config",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_save_config(request: SaveConfigRequest) -> GitSyncConfigResponse:
        if Path(request.project_path).is_absolute():
            raise HTTPException(
                status_code=400,
                detail="project_path must be a relative path within the clone",
            )
        full_project_path = str(Path(request.clone_path) / request.project_path)

        try:
            check_duplicate_project_id(request.project_id, full_project_path)
        except DuplicateProjectError as e:
            raise HTTPException(status_code=409, detail=str(e))

        project_config = GitSyncProjectConfig(
            sync_mode=request.sync_mode,
            auth_mode=request.auth_mode,
            remote_name=request.remote_name,
            branch=request.branch,
            clone_path=request.clone_path,
            git_url=request.git_url,
            pat_token=request.pat_token,
            oauth_token=request.oauth_token,
        )
        save_git_sync_config(full_project_path, project_config)
        add_project_to_config(full_project_path)

        return GitSyncConfigResponse(
            sync_mode=request.sync_mode,
            auth_mode=request.auth_mode,
            remote_name=request.remote_name,
            branch=request.branch,
            clone_path=request.clone_path,
            git_url=request.git_url,
            has_pat_token=request.pat_token is not None,
            has_oauth_token=request.oauth_token is not None,
        )

    @app.get(
        "/api/git_sync/config/{project_id}",
        summary="Get Git Sync Config",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_get_config(
        project_id: str = FastAPIPath(
            description="The unique identifier of the project."
        ),
    ) -> GitSyncConfigResponse:
        project_path = project_path_from_id(project_id)
        if project_path is None:
            raise HTTPException(status_code=404, detail="Project not found")
        config = get_git_sync_config(project_path)
        if config is None:
            raise HTTPException(
                status_code=404, detail="Git sync config not found for this project"
            )

        return GitSyncConfigResponse(
            sync_mode=config["sync_mode"],
            auth_mode=config["auth_mode"],
            remote_name=config["remote_name"],
            branch=config["branch"],
            clone_path=config.get("clone_path"),
            git_url=config.get("git_url"),
            has_pat_token=config.get("pat_token") is not None,
            has_oauth_token=config.get("oauth_token") is not None,
        )

    @app.patch(
        "/api/git_sync/update_config/{project_id}",
        summary="Update Git Sync Config",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_update_config(
        request: UpdateConfigRequest,
        project_id: str = FastAPIPath(
            description="The unique identifier of the project."
        ),
    ) -> GitSyncConfigResponse:
        project_path = project_path_from_id(project_id)
        if project_path is None:
            raise HTTPException(status_code=404, detail="Project not found")
        config = get_git_sync_config(project_path)
        if config is None:
            raise HTTPException(
                status_code=404, detail="Git sync config not found for this project"
            )

        if request.sync_mode is not None:
            config["sync_mode"] = request.sync_mode
        if request.pat_token is not None:
            config["pat_token"] = request.pat_token
        if request.oauth_token is not None:
            config["oauth_token"] = request.oauth_token
        if request.auth_mode is not None:
            config["auth_mode"] = request.auth_mode
            # Clearing tokens that belong to other auth modes is the only way
            # to remove stored credentials through this endpoint -- `None` in
            # the request body means "don't change" rather than "clear".
            if request.auth_mode == "pat_token":
                config["oauth_token"] = None
            elif request.auth_mode == "github_oauth":
                config["pat_token"] = None
            elif request.auth_mode == "system_keys":
                config["pat_token"] = None
                config["oauth_token"] = None

        save_git_sync_config(project_path, config)

        return GitSyncConfigResponse(
            sync_mode=config["sync_mode"],
            auth_mode=config["auth_mode"],
            remote_name=config["remote_name"],
            branch=config["branch"],
            clone_path=config.get("clone_path"),
            git_url=config.get("git_url"),
            has_pat_token=config.get("pat_token") is not None,
            has_oauth_token=config.get("oauth_token") is not None,
        )

    # OAuth endpoints

    oauth_manager = OAuthFlowManager()

    @app.post(
        "/api/git_sync/oauth/start",
        summary="Start GitHub OAuth Flow",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_oauth_start(request: OAuthStartRequest) -> OAuthStartResponse:
        parsed = parse_github_owner_repo(request.git_url)
        if parsed is None:
            raise HTTPException(
                status_code=400,
                detail="Could not parse GitHub owner/repo from the provided URL",
            )
        owner, repo = parsed

        owner_id, repo_id = await asyncio.gather(
            resolve_github_owner_id(owner),
            resolve_github_repo_id(owner, repo),
        )

        flow = oauth_manager.start_flow(request.git_url)
        install_url = build_install_url(owner_id, repo_id)
        authorize_url = build_authorize_url(flow)

        return OAuthStartResponse(
            authorize_url=authorize_url,
            install_url=install_url,
            state=flow.state,
            owner_name=owner,
            repo_name=repo,
            owner_pre_selected=owner_id is not None,
            repo_pre_selected=repo_id is not None,
        )

    @app.get(
        "/api/git_sync/oauth/callback",
        summary="OAuth Callback",
        tags=["Git Sync"],
        response_model=None,
        openapi_extra=DENY_AGENT,
    )
    async def api_oauth_callback(
        state: str = Query(
            default="",
            description="OAuth state parameter linking the callback to a pending flow.",
        ),
        code: str = Query(
            default="",
            description="Authorization code from GitHub to exchange for an access token.",
        ),
        error: str = Query(
            default="",
            description="Error code returned by GitHub if authorization was denied.",
        ),
        error_description: str = Query(
            default="",
            description="Human-readable description of the error from GitHub.",
        ),
    ) -> HTMLResponse:
        def error_page(msg: str) -> HTMLResponse:
            return HTMLResponse(render_oauth_error_page(msg))

        if not state:
            return error_page("Missing state parameter.")

        flow = oauth_manager.get_flow(state)
        if flow is None:
            return error_page(
                "Authorization session expired or invalid. Please start over in Kiln."
            )

        if error:
            desc = error_description or error
            oauth_manager.fail_flow(state, desc)
            return error_page(desc)

        if not code:
            oauth_manager.fail_flow(state, "Missing authorization code.")
            return error_page("Missing authorization code.")

        try:
            token = await exchange_code_for_token(code, flow.code_verifier)
            oauth_manager.complete_flow(state, token)
            return HTMLResponse(OAUTH_SUCCESS_HTML)
        except OAuthError as e:
            oauth_manager.fail_flow(state, str(e))
            return error_page(str(e))

    # GitHub App "Setup URL" — GitHub redirects here after the user installs
    # the app on a repository. Returning plain HTML (rather than an app route)
    # avoids the app's setup-redirect logic hijacking the install tab.
    @app.get(
        "/api/git_sync/oauth/authorize",
        summary="GitHub App Install Complete",
        tags=["Git Sync"],
        response_model=None,
        openapi_extra=DENY_AGENT,
    )
    async def api_oauth_installed() -> HTMLResponse:
        return HTMLResponse(INSTALL_COMPLETE_HTML)

    @app.get(
        "/api/git_sync/oauth/status/{state}",
        summary="OAuth Flow Status",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_oauth_status(
        state: str = FastAPIPath(description="The OAuth state parameter to check."),
    ) -> OAuthStatusResponse:
        flow = oauth_manager.get_flow(state)
        if flow is None:
            return OAuthStatusResponse(
                complete=False, error="Session expired or not found."
            )

        if flow.complete:
            consumed = oauth_manager.consume_flow(state)
            if consumed is not None:
                return OAuthStatusResponse(
                    complete=True,
                    oauth_token=consumed.oauth_token,
                    error=consumed.error,
                )
            return OAuthStatusResponse(
                complete=True,
                error="Flow already consumed by another request.",
            )

        return OAuthStatusResponse(complete=False)

    @app.delete(
        "/api/git_sync/config/{project_id}",
        summary="Delete Git Sync Config",
        tags=["Git Sync"],
        openapi_extra=DENY_AGENT,
    )
    async def api_delete_config(
        project_id: str = FastAPIPath(
            description="The unique identifier of the project."
        ),
    ) -> DeleteConfigResponse:
        project_path = project_path_from_id(project_id)
        if project_path is None:
            raise HTTPException(status_code=404, detail="Project not found")
        delete_git_sync_config(project_path)
        return DeleteConfigResponse(message="Config deleted")
