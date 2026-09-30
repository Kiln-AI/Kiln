"""Tiny shared test fixtures for the chat package."""

import json


def sse_text_delta(delta: str, text_id: str = "text-test") -> bytes:
    payload = {
        "type": "text-delta",
        "id": text_id,
        "delta": delta,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
