import json

from app.desktop.studio_server.api_client.kiln_ai_server_client.types import Response
from fastapi import HTTPException


def check_response_error(
    response: Response, default_detail: str = "Unknown error."
) -> None:
    """Check if the response is an error with user centric message."""
    if not (200 <= response.status_code < 300):
        # response.content is a bytes object
        # We check if it's a JSON object with a user message field
        detail = default_detail
        if response.content.startswith(b"{"):
            try:
                json_data = json.loads(response.content)
                detail = json_data.get("message", default_detail)
            except json.JSONDecodeError:
                pass
        raise HTTPException(
            status_code=response.status_code,
            detail=detail,
        )
