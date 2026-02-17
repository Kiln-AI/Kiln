from typing import Any

from app.desktop.log_config import get_log_file_path
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.auth import (
    check_entitlements_v1_check_entitlements_get,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from app.desktop.studio_server.utils.response_utils import check_response_error
from fastapi import FastAPI, HTTPException
from kiln_ai.utils.config import Config
from kiln_ai.utils.filesystem import open_folder
from kiln_server.project_api import project_from_id


def open_logs_folder() -> None:
    open_folder(get_log_file_path("dummy.log"))


def connect_settings(app: FastAPI):
    @app.post("/api/settings")
    def update_settings(
        new_settings: dict[str, int | float | str | bool | list | None],
    ):
        Config.shared().update_settings(new_settings)
        return Config.shared().settings(hide_sensitive=True)

    @app.get("/api/settings")
    def read_settings() -> dict[str, Any]:
        settings = Config.shared().settings(hide_sensitive=True)
        return settings

    @app.get("/api/settings/{item_id}")
    def read_setting_item(item_id: str):
        settings = Config.shared().settings(hide_sensitive=True)
        return {item_id: settings.get(item_id, None)}

    @app.post("/api/open_logs")
    def open_logs():
        try:
            open_logs_folder()
            return {"message": "opened"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/open_project_folder/{project_id}")
    def open_project_folder(project_id: str):
        try:
            project = project_from_id(project_id)
            path = project.path
            if not path:
                raise HTTPException(status_code=500, detail="Project path not found")

            open_folder(path)
            return {"message": "opened"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/check_entitlements")
    async def check_entitlements(feature_codes: str) -> dict[str, bool]:
        """Check whether the authenticated user has the given entitlements.

        Args:
            feature_codes: Comma-separated entitlement feature codes to check

        Returns:
            Dict mapping each feature code to a boolean indicating if user has that entitlement
        """
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        detailed_result = (
            await check_entitlements_v1_check_entitlements_get.asyncio_detailed(
                client=client,
                feature_codes=feature_codes,
            )
        )
        check_response_error(detailed_result)

        result = detailed_result.parsed
        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to check entitlements. Please try again.",
            )

        return result.additional_properties
