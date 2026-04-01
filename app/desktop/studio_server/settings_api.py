from typing import Annotated, Any

from app.desktop.log_config import get_log_file_path
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.auth import (
    check_entitlements_v1_check_entitlements_get,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import FastAPI, HTTPException, Path, Query
from kiln_ai.utils.config import Config
from kiln_ai.utils.filesystem import open_folder
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    DENY_AGENT,
    agent_policy_require_approval,
)


def open_logs_folder() -> None:
    open_folder(get_log_file_path("dummy.log"))


def connect_settings(app: FastAPI):
    @app.post(
        "/api/settings",
        summary="Update Settings",
        tags=["Settings & Utilities"],
        openapi_extra=DENY_AGENT,
    )
    def update_settings(
        new_settings: dict[str, int | float | str | bool | list | None],
    ):
        Config.shared().update_settings(new_settings)
        return Config.shared().settings(hide_sensitive=True)

    @app.get(
        "/api/settings",
        summary="Get Settings",
        tags=["Settings & Utilities"],
        openapi_extra=DENY_AGENT,
    )
    def read_settings() -> dict[str, Any]:
        settings = Config.shared().settings(hide_sensitive=True)
        return settings

    @app.get(
        "/api/settings/{item_id}",
        summary="Get Setting Item",
        tags=["Settings & Utilities"],
        openapi_extra=DENY_AGENT,
    )
    def read_setting_item(
        item_id: Annotated[str, Path(description="The setting item key to retrieve.")],
    ):
        settings = Config.shared().settings(hide_sensitive=True)
        return {item_id: settings.get(item_id, None)}

    @app.post(
        "/api/open_logs",
        summary="Open Logs Folder",
        tags=["Settings & Utilities"],
        openapi_extra=agent_policy_require_approval(
            "This will open an external application to view logs. Allow?"
        ),
    )
    def open_logs():
        """Opens the log folder in the system file browser."""
        try:
            open_logs_folder()
            return {"message": "opened"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/api/open_project_folder/{project_id}",
        summary="Open Project Folder",
        tags=["Settings & Utilities"],
        openapi_extra=DENY_AGENT,
    )
    def open_project_folder(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ):
        """Opens the project folder in the system file browser."""
        try:
            project = project_from_id(project_id)
            path = project.path
            if not path:
                raise HTTPException(status_code=500, detail="Project path not found")

            open_folder(path)
            return {"message": "opened"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get(
        "/api/check_entitlements",
        summary="Check Entitlements",
        tags=["Settings & Utilities"],
        openapi_extra=DENY_AGENT,
    )
    async def check_entitlements(
        feature_codes: Annotated[
            str,
            Query(
                description="Comma-separated list of entitlement feature codes to check."
            ),
        ],
    ) -> dict[str, bool]:
        """Check whether the authenticated user has the given entitlements.

        The feature_codes parameter should be a comma-separated list of entitlement feature codes to check.
        Returns a dict mapping each feature code to a boolean indicating if the user has that entitlement.
        """
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        detailed_result = (
            await check_entitlements_v1_check_entitlements_get.asyncio_detailed(
                client=client,
                feature_codes=feature_codes,
            )
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to check entitlements. Please try again.",
        )

        return result.additional_properties
