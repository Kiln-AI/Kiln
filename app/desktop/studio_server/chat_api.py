import json
import logging

import httpx
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)


def connect_chat_api(app: FastAPI) -> None:
    @app.post("/api/chat")
    async def chat(request: Request) -> StreamingResponse:
        api_key = get_copilot_api_key()
        body = await request.body()

        upstream_url = f"{_get_base_url()}/v1/chat/"
        headers = {
            **_get_common_headers(),
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async def stream_upstream():
            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    upstream_url,
                    content=body,
                    headers=headers,
                ) as upstream:
                    if upstream.status_code != 200:
                        error_body = await upstream.aread()
                        detail = "Chat request failed."
                        if error_body.startswith(b"{"):
                            try:
                                detail = (
                                    json.loads(error_body).get("message", detail)
                                    or detail
                                )
                            except json.JSONDecodeError:
                                logger.error(f"Error decoding error body: {error_body}")
                                pass
                        yield f"data: {json.dumps({'type': 'error', 'message': detail})}\n\n".encode()
                        return

                    async for chunk in upstream.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            content=stream_upstream(),
            media_type="text/event-stream",
        )
