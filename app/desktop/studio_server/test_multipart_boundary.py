import io
import zipfile

import httpx
import pytest
from python_multipart.multipart import parse_options_header

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post import (
    _get_kwargs,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.body_start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post import (
    BodyStartPromptOptimizationJobV1JobsPromptOptimizationJobStartPost,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import File


def _make_zip_with_content(text: str) -> bytes:
    """Create a zip file in memory containing a single text file with the given content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("marker.txt", text)
    return buf.getvalue()


def _read_httpx_stream(request: httpx.Request) -> bytes:
    """Read all bytes from an httpx Request's streaming body."""
    return b"".join(request.stream)


def _build_multipart_request(
    zip_bytes: bytes,
    task_id: str = "task-1",
    run_config_id: str = "rc-1",
    eval_ids: list[str] | None = None,
) -> httpx.Request:
    """Build a real httpx Request from the SDK's multipart body."""
    body = BodyStartPromptOptimizationJobV1JobsPromptOptimizationJobStartPost(
        task_id=task_id,
        target_run_config_id=run_config_id,
        eval_ids=eval_ids or ["eval-1"],
        project_zip=File(
            payload=io.BytesIO(zip_bytes),
            file_name="project.zip",
            mime_type="application/zip",
        ),
    )
    kwargs = _get_kwargs(body=body)
    return httpx.Request(
        method=kwargs["method"],
        url=f"http://localhost{kwargs['url']}",
        files=kwargs["files"],
        headers=kwargs.get("headers", {}),
    )


def _extract_zip_from_multipart(request: httpx.Request) -> bytes:
    """Extract the project_zip file bytes from a multipart httpx Request."""
    content_type = request.headers["content-type"]
    _, params = parse_options_header(content_type.encode())
    boundary = params[b"boundary"]
    raw_body = _read_httpx_stream(request)
    parts = raw_body.split(b"--" + boundary)

    for part in parts:
        if b'name="project_zip"' in part:
            header_end = part.find(b"\r\n\r\n")
            assert header_end != -1
            file_data = part[header_end + 4 :]
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]
            return file_data

    raise AssertionError("project_zip part not found in multipart body")


def test_get_kwargs_does_not_hardcode_content_type():
    """Regression: _get_kwargs must not set a Content-Type header.

    When a Content-Type header is hardcoded (e.g. with boundary=+++) httpx
    cannot negotiate its own boundary, which corrupts multipart parsing
    whenever the payload contains the same boundary string.
    """
    zip_bytes = _make_zip_with_content("+++ test marker +++")
    body = BodyStartPromptOptimizationJobV1JobsPromptOptimizationJobStartPost(
        task_id="t1",
        target_run_config_id="rc1",
        eval_ids=["e1"],
        project_zip=File(
            payload=io.BytesIO(zip_bytes),
            file_name="project.zip",
            mime_type="application/zip",
        ),
    )

    kwargs = _get_kwargs(body=body)

    headers = kwargs.get("headers", {})
    assert "Content-Type" not in headers, (
        f"SDK must not hardcode a Content-Type header on multipart endpoints, "
        f"but found: {headers.get('Content-Type')}"
    )
    assert "files" in kwargs, "_get_kwargs should set 'files' for multipart upload"


def test_multipart_roundtrip_with_triple_plus_content():
    """Upload a zip whose contents include '+++' and verify the multipart body
    can be parsed without corruption.

    This is the core regression test: a hardcoded boundary=+++ would make the
    multipart parser split on the '+++' inside the zip, producing a 400 error.
    """
    marker = "+++ test marker +++"
    zip_bytes = _make_zip_with_content(marker)

    request = _build_multipart_request(zip_bytes, eval_ids=["eval-1", "eval-2"])

    content_type = request.headers["content-type"]
    assert "multipart/form-data" in content_type
    assert "boundary=+++" not in content_type

    file_data = _extract_zip_from_multipart(request)
    zf = zipfile.ZipFile(io.BytesIO(file_data))
    extracted = zf.read("marker.txt").decode()
    assert extracted == marker


@pytest.mark.parametrize(
    "content",
    [
        "+++",
        "------",
        "boundary=+++",
        "--boundary\r\n",
        'Content-Disposition: form-data; name="inject"',
    ],
    ids=[
        "triple-plus",
        "dashes",
        "fake-boundary-header",
        "boundary-line",
        "header-injection",
    ],
)
def test_multipart_encoding_resilient_to_adversarial_content(content: str):
    """Verify multipart encoding stays correct even when zip content contains
    strings that look like multipart delimiters or headers."""
    zip_bytes = _make_zip_with_content(content)

    request = _build_multipart_request(zip_bytes)

    content_type = request.headers["content-type"]
    assert "multipart/form-data" in content_type
    assert "boundary=+++" not in content_type

    file_data = _extract_zip_from_multipart(request)
    zf = zipfile.ZipFile(io.BytesIO(file_data))
    extracted = zf.read("marker.txt").decode()
    assert extracted == content
