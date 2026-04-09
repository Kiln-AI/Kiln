import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi import Path as FastAPIPath
from kiln_server.project_api import add_project_to_config, default_project_path
from pydantic import BaseModel, Field

from app.desktop.git_sync.clone import (
    clone_repo,
    compute_clone_path,
    list_remote_branches,
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

logger = logging.getLogger(__name__)


class TestAccessRequest(BaseModel):
    """Request to test read access to a git remote."""

    git_url: str = Field(description="The git remote URL to test access against.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
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
        description="Auth method that succeeded: 'system_keys' or 'pat_token'. Null on failure.",
    )


class ListBranchesRequest(BaseModel):
    """Request to list branches on a git remote."""

    git_url: str = Field(description="The git remote URL to list branches from.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys' (SSH agent) or 'pat_token' (HTTPS PAT).",
    )


class ListBranchesResponse(BaseModel):
    """List of branches available on the remote."""

    branches: list[str] = Field(description="Branch names available on the remote.")
    default_branch: str | None = Field(
        default=None, description="The HEAD branch of the remote, if detected."
    )


class CloneRequest(BaseModel):
    """Request to clone a git repository."""

    git_url: str = Field(description="The git remote URL to clone.")
    branch: str = Field(description="The branch to check out after cloning.")
    pat_token: str | None = Field(
        default=None, description="Optional personal access token for authentication."
    )
    auth_mode: Literal["system_keys", "pat_token"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys' (SSH agent) or 'pat_token' (HTTPS PAT).",
    )
    project_name: str = Field(
        default="project", description="Human-readable project name for the clone dir."
    )
    project_id: str = Field(
        default="", description="Unique project identifier used in the clone path."
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
    auth_mode: Literal["system_keys", "pat_token"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys' (SSH agent) or 'pat_token' (HTTPS PAT).",
    )


class ScanProjectsRequest(BaseModel):
    """Request to scan a cloned repo for Kiln project files."""

    clone_path: str = Field(description="Local filesystem path of the cloned repo.")


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
    auth_mode: Literal["system_keys", "pat_token"] = Field(
        default="system_keys",
        description="Auth mode detected during setup: 'system_keys' or 'pat_token'.",
    )
    sync_mode: str = Field(default="auto", description="Sync mode: 'auto' or 'manual'.")


class GitSyncConfigResponse(BaseModel):
    """Current git sync configuration for a project (PAT redacted)."""

    sync_mode: str = Field(description="Sync mode: 'auto' or 'manual'.")
    auth_mode: Literal["system_keys", "pat_token"] = Field(
        default="system_keys",
        description="Auth mode: 'system_keys' (SSH agent) or 'pat_token' (HTTPS PAT).",
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


class UpdateConfigRequest(BaseModel):
    """Request to partially update a git sync configuration."""

    sync_mode: str | None = Field(
        default=None, description="New sync mode, if changing."
    )
    pat_token: str | None = Field(
        default=None, description="New personal access token, if changing."
    )
    auth_mode: Literal["system_keys", "pat_token"] | None = Field(
        default=None, description="New auth mode, if changing."
    )


class DeleteConfigResponse(BaseModel):
    """Confirmation that a git sync configuration was deleted."""

    message: str = Field(description="Human-readable confirmation message.")


def connect_git_sync_api(app: FastAPI):
    @app.post(
        "/api/git_sync/test_access",
        summary="Test Git Remote Access",
        tags=["Git Sync"],
    )
    async def api_test_access(request: TestAccessRequest) -> TestAccessResponse:
        success, message, detected_mode = await asyncio.to_thread(
            test_remote_access, request.git_url, request.pat_token
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
    )
    async def api_clone(request: CloneRequest) -> CloneResponse:
        try:
            base_dir = Path(default_project_path())
            clone_path = compute_clone_path(
                base_dir, request.project_name, request.project_id
            )

            await asyncio.to_thread(
                clone_repo,
                request.git_url,
                clone_path,
                request.branch,
                request.pat_token,
                request.auth_mode,
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
    )
    async def api_test_write_access(
        request: TestWriteAccessRequest,
    ) -> TestAccessResponse:
        success, message = await asyncio.to_thread(
            test_write_access,
            Path(request.clone_path),
            request.pat_token,
            request.auth_mode,
        )
        auth_required = not success and "auth" in message.lower()
        return TestAccessResponse(
            success=success, message=message, auth_required=auth_required
        )

    @app.post(
        "/api/git_sync/scan_projects",
        summary="Scan for Kiln Projects",
        tags=["Git Sync"],
    )
    async def api_scan_projects(
        request: ScanProjectsRequest,
    ) -> ScanProjectsResponse:
        clone_path = Path(request.clone_path)
        if not clone_path.exists():
            raise HTTPException(status_code=400, detail="Clone path does not exist")

        results = await asyncio.to_thread(scan_for_projects, clone_path)
        projects = [ProjectInfo(**r) for r in results]
        return ScanProjectsResponse(projects=projects)

    @app.post(
        "/api/git_sync/save_config",
        summary="Save Git Sync Config",
        tags=["Git Sync"],
    )
    async def api_save_config(request: SaveConfigRequest) -> GitSyncConfigResponse:
        if Path(request.project_path).is_absolute():
            raise HTTPException(
                status_code=400,
                detail="project_path must be a relative path within the clone",
            )
        full_project_path = str(Path(request.clone_path) / request.project_path)

        project_config = GitSyncProjectConfig(
            sync_mode=request.sync_mode,
            auth_mode=request.auth_mode,
            remote_name=request.remote_name,
            branch=request.branch,
            clone_path=request.clone_path,
            git_url=request.git_url,
            pat_token=request.pat_token,
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
        )

    @app.get(
        "/api/git_sync/config/{project_id}",
        summary="Get Git Sync Config",
        tags=["Git Sync"],
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
            auth_mode=config.get("auth_mode", "system_keys"),
            remote_name=config["remote_name"],
            branch=config["branch"],
            clone_path=config.get("clone_path"),
            git_url=config.get("git_url"),
            has_pat_token=config.get("pat_token") is not None,
        )

    @app.post(
        "/api/git_sync/update_config/{project_id}",
        summary="Update Git Sync Config",
        tags=["Git Sync"],
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
        if request.auth_mode is not None:
            config["auth_mode"] = request.auth_mode

        save_git_sync_config(project_path, config)

        return GitSyncConfigResponse(
            sync_mode=config["sync_mode"],
            auth_mode=config.get("auth_mode", "system_keys"),
            remote_name=config["remote_name"],
            branch=config["branch"],
            clone_path=config.get("clone_path"),
            git_url=config.get("git_url"),
            has_pat_token=config.get("pat_token") is not None,
        )

    @app.delete(
        "/api/git_sync/config/{project_id}",
        summary="Delete Git Sync Config",
        tags=["Git Sync"],
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
