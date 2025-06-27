import base64


def to_base64_url(mime_type: str, bytes: bytes) -> str:
    base64_url = f"data:{mime_type};base64,{base64.b64encode(bytes).decode('utf-8')}"
    return base64_url


def from_base64_url(base64_url: str) -> bytes:
    return base64.b64decode(base64_url.split(",")[1])
