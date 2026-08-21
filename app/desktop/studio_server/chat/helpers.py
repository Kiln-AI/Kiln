"""Tiny shared test fixtures for the chat package.

Phase 4 note: this module used to also carry the httpx mock builders
(``make_httpx_mock`` / ``make_n_round_mock_client`` and the PATCH_* targets)
that drove the deleted ``POST /api/chat`` route tests; the surviving suites
script upstream rounds through ``chat/test_fakes.py`` instead, so only the
SSE payload builder remains.
"""

import json


def sse_text_delta(delta: str, text_id: str = "text-test") -> bytes:
    payload = {
        "type": "text-delta",
        "id": text_id,
        "delta": delta,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
