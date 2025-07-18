import base64


def to_base64_url(mime_type: str, bytes: bytes) -> str:
    base64_url = f"data:{mime_type};base64,{base64.b64encode(bytes).decode('utf-8')}"
    return base64_url


def from_base64_url(base64_url: str) -> bytes:
    if not base64_url.startswith("data:") or "," not in base64_url:
        raise ValueError("Invalid base64 URL format")

    parts = base64_url.split(",")
    if len(parts) != 2:
        raise ValueError("Invalid base64 URL format")

    try:
        return base64.b64decode(parts[1])
    except Exception as e:
        raise ValueError(f"Failed to decode base64 data: {e}")
