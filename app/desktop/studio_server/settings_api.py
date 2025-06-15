import os
import subprocess
import sys
from typing import Any

from fastapi import FastAPI, HTTPException
from kiln_ai.utils.config import Config

from app.desktop.log_config import get_log_file_path


def open_logs_folder() -> None:
    log_dir = os.path.dirname(get_log_file_path("dummy.log"))
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", log_dir], check=True)
    elif sys.platform.startswith("win"):
        os.startfile(log_dir)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", log_dir], check=True)


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
