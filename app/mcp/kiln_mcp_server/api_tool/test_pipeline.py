import json
from pathlib import Path

import httpx
import pytest
from kiln_ai.tools.built_in_tools.kiln_api_call_tool import (
    SSE_FINISHED_MESSAGE,
    prepare_api_request,
)
from mcp.types import TextContent

from kiln_mcp_server.api_tool.pipeline import coerce_query_params, run_api_call
from kiln_mcp_server.api_tool.policy import ConnectionPolicy
from kiln_mcp_server.api_tool.route_index import RouteIndex
from kiln_mcp_server.api_tool.tmp_files import TmpFileStore
from kiln_mcp_server.api_tool.tool import ApiToolDeps

CATALOGUE = "references/knowledge/api_docs/api_index.md"
ITEM_JSON = '{"id":"1","tags":null,"limit":0}'


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return await self.inner.handle_async_request(request)


def raising(error: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handler)


@pytest.fixture
def tmp_root(tmp_path) -> Path:
    return tmp_path / "kiln_mcp"


@pytest.fixture
def transport(api_app) -> CountingTransport:
    return CountingTransport(httpx.ASGITransport(app=api_app))


@pytest.fixture
def make_deps(api_app, tmp_root, transport):
    def make(transport: httpx.AsyncBaseTransport = transport, **kwargs) -> ApiToolDeps:
        return ApiToolDeps(
            api_base_url="http://kiln.test",
            route_index=RouteIndex.from_app(api_app),
            policy=ConnectionPolicy(),
            tmp_files=TmpFileStore(tmp_root),
            transport=transport,
            **kwargs,
        )

    return make


@pytest.fixture
def call(make_deps):
    async def run(
        method: str,
        url_path: str,
        *,
        deps: ApiToolDeps | None = None,
        send_progress=None,
        body=None,
        query_params=None,
        jq_filter=None,
        body_limit: int = 30000,
        save_to_tmpfile: bool = False,
    ) -> tuple[str, bool]:
        result = await run_api_call(
            deps or make_deps(),
            None,
            send_progress,
            method=method,
            url_path=url_path,
            body=body,
            query_params=query_params,
            jq_filter=jq_filter,
            body_limit=body_limit,
            save_to_tmpfile=save_to_tmpfile,
        )
        (content,) = result.content
        assert isinstance(content, TextContent)
        assert result.structuredContent is None
        return content.text, result.isError

    return run


def core_refusal(method: str, url_path: str, body=None) -> str:
    with pytest.raises(ValueError) as e:
        prepare_api_request(method, url_path, body)
    return str(e.value)


@pytest.mark.parametrize("body_limit", [0, -5])
async def test_a_bad_body_limit_is_refused(call, transport, body_limit):
    assert await call("GET", "/ping", body_limit=body_limit) == (
        f"body_limit must be a positive integer. Got: {body_limit}.",
        True,
    )
    assert transport.calls == 0


@pytest.mark.parametrize(
    "method, url_path, body",
    [
        ("PUT", "/api/items/1", None),
        ("GET", "api/items/1", None),
        ("GET", "/docs", None),
        ("GET", "/api/../docs", None),
        ("GET", "/api/items/1?x=1", None),
        ("GET", "/api/items/1", {"a": 1}),
    ],
)
async def test_core_refusals_pass_through_unchanged(call, method, url_path, body):
    assert await call(method, url_path, body=body) == (
        core_refusal(method, url_path, body),
        True,
    )


async def test_the_trailing_slash_is_removed_before_the_lookup(call):
    assert await call("get", "/api/items/1/") == (
        f'{{"status_code":200,"body":{ITEM_JSON}}}',
        False,
    )


async def test_an_unknown_endpoint(call, transport):
    assert await call("GET", "/api/nope") == (
        "No Kiln API endpoint matches GET /api/nope. Do not guess paths. Read the "
        f"API catalogues in the Kiln skill ({CATALOGUE}) to find the endpoint, then "
        "read its doc before you call it.",
        True,
    )
    assert transport.calls == 0


async def test_a_wrong_method(call, transport):
    assert await call("DELETE", "/api/items/1") == (
        "DELETE is not supported on /api/items/1. This path supports: GET, PATCH. "
        f"Read the endpoint's doc in the Kiln skill's API catalogues ({CATALOGUE}).",
        True,
    )
    assert transport.calls == 0


@pytest.mark.parametrize(
    "method, url_path, template",
    [
        ("GET", "/api/things/special", "/api/things/special"),
        ("GET", "/api/things/specia%6C", "/api/things/special"),
        ("POST", "/api/secrets", "/api/secrets"),
    ],
)
async def test_a_blocked_endpoint_is_never_called(
    call, transport, method, url_path, template
):
    assert await call(method, url_path) == (
        f"The endpoint {method} {template} is not available to agents over MCP. Do "
        "not retry it and do not look for another way to call it. If the user needs "
        "this, ask them to do it in the Kiln app.",
        True,
    )
    assert transport.calls == 0


async def test_the_other_route_of_a_blocked_pair_is_called(call):
    assert await call("GET", "/api/things/other") == (
        '{"status_code":200,"body":{"thing":"other"}}',
        False,
    )


@pytest.mark.parametrize(
    "query_params, expected",
    [
        (None, None),
        ({}, None),
        ({"a": None}, None),
        ({"a": "x", "b": None}, {"a": "x"}),
        ({"flag": True, "off": False}, {"flag": "true", "off": "false"}),
        ({"n": 5}, {"n": "5"}),
        ({"f": 5.0}, {"f": "5"}),
        ({"f": 2.5}, {"f": "2.5"}),
        ({"f": 1e-7}, {"f": "1e-07"}),
        ({"ids": ["a", 1, 2.0, True]}, {"ids": ["a", "1", "2", "true"]}),
        ({"ids": []}, {"ids": []}),
    ],
)
def test_coerce_query_params(query_params, expected):
    assert coerce_query_params(query_params) == expected


async def test_query_params_reach_the_api(call):
    text, is_error = await call(
        "GET",
        "/api/items/1",
        query_params={"tags": ["a", 2], "limit": 5.0, "unused": None},
    )
    assert not is_error
    assert json.loads(text)["body"] == {"id": "1", "tags": ["a", "2"], "limit": 5}


async def test_api_errors_are_returned_as_data(call):
    assert await call("GET", "/api/missing") == (
        '{"status_code":404,"body":{"detail":"Item not found"}}',
        False,
    )
    text, is_error = await call("PATCH", "/api/items/1", body={})
    assert not is_error
    assert json.loads(text)["status_code"] == 422


async def test_the_result_is_compact_and_keeps_non_ascii(call):
    assert await call("PATCH", "/api/items/1", body={"name": "é"}) == (
        '{"status_code":200,"body":{"id":"1","name":"é"}}',
        False,
    )


async def test_jq_is_applied(call):
    assert await call("GET", "/api/items/1", jq_filter=".id") == (
        '{"status_code":200,"body":"1"}',
        False,
    )


async def test_a_jq_error_on_get(call):
    text, is_error = await call("GET", "/api/items/1", jq_filter=".[0]")
    assert is_error
    assert text.startswith("jq filter error: ")
    assert "Do not repeat" not in text


async def test_a_jq_error_on_post_says_the_request_completed(call):
    text, is_error = await call("POST", "/api/stream", jq_filter=".[0]")
    assert is_error
    assert text.startswith("jq filter error: ")
    assert text.endswith(
        " The POST request itself completed with status 200. Do not repeat it."
    )


async def test_jq_on_a_text_response(call):
    text, is_error = await call("GET", "/api/text", jq_filter=".")
    assert is_error
    assert text.startswith("Response is not valid JSON: ")


async def test_a_get_body_over_the_limit_is_refused(call):
    assert await call("GET", "/api/items/1", body_limit=10) == (
        "Body too long. Length 32 on limit 10. Either narrow your request (a "
        "`jq_filter`, paging or filter parameters), save it to a file with "
        "`save_to_tmpfile`, or call again passing a `body_limit` higher than 32.",
        True,
    )


async def test_the_limit_applies_to_get_only(call):
    assert await call("PATCH", "/api/items/1", body={"name": "n"}, body_limit=1) == (
        '{"status_code":200,"body":{"id":"1","name":"n"}}',
        False,
    )


async def test_the_limit_is_measured_after_jq(call):
    assert (await call("GET", "/api/items/1", jq_filter=".id", body_limit=3))[
        1
    ] is False
    text, is_error = await call("GET", "/api/items/1", jq_filter=".id", body_limit=2)
    assert is_error
    assert text.startswith("Body too long. Length 3 on limit 2.")


async def test_a_body_at_the_limit_is_returned(call):
    assert await call("GET", "/api/items/1", body_limit=len(ITEM_JSON)) == (
        f'{{"status_code":200,"body":{ITEM_JSON}}}',
        False,
    )


async def test_an_api_error_over_the_limit_is_returned(call):
    assert (await call("GET", "/api/missing", body_limit=1))[1] is False


@pytest.mark.parametrize(
    "url_path, jq_filter, content, suffix",
    [
        ("/api/items/1", None, ITEM_JSON, ".json"),
        ("/api/items/1", ".id", '"1"', ".json"),
        ("/api/text", None, "plain text", ".txt"),
    ],
)
async def test_a_saved_result(call, tmp_root, url_path, jq_filter, content, suffix):
    text, is_error = await call(
        "GET", url_path, jq_filter=jq_filter, save_to_tmpfile=True, body_limit=1
    )
    assert not is_error
    result = json.loads(text)
    assert list(result) == ["status_code", "body_path", "size_bytes"]
    assert result["status_code"] == 200
    path = Path(result["body_path"])
    assert path.parent == tmp_root
    assert path.suffix == suffix
    assert path.read_text(encoding="utf-8") == content
    assert result["size_bytes"] == len(content.encode())
    assert text == json.dumps(result, separators=(",", ":"))


async def test_an_api_error_is_never_saved(call, tmp_root):
    assert await call("GET", "/api/missing", save_to_tmpfile=True) == (
        '{"status_code":404,"body":{"detail":"Item not found"}}',
        False,
    )
    assert not tmp_root.exists()


@pytest.mark.parametrize(
    "method, url_path, ending",
    [
        ("GET", "/api/items/1", " Call again without save_to_tmpfile."),
        ("POST", "/api/stream", " Do not repeat the POST."),
    ],
)
async def test_a_failed_save(call, tmp_root, method, url_path, ending):
    tmp_root.write_text("not a folder")
    assert await call(method, url_path, save_to_tmpfile=True) == (
        f"Could not save the response to a temporary file: {tmp_root} exists but is "
        "not a folder owned by the current user. The request completed with status "
        f"200.{ending}",
        True,
    )


async def test_an_event_stream_is_summarised(call):
    text, is_error = await call("POST", "/api/stream")
    assert not is_error
    assert json.loads(text) == {
        "status_code": 200,
        "body": {"event_count": 2, "message": SSE_FINISHED_MESSAGE},
    }


@pytest.mark.parametrize(
    "error, method, expected",
    [
        (
            httpx.ReadTimeout("slow"),
            "GET",
            "Request to /api/items/1 timed out after 900.0s",
        ),
        (
            httpx.ConnectTimeout("slow"),
            "PATCH",
            "Request to /api/items/1 timed out after 30.0s. The PATCH may have taken "
            "effect. Check the state before you repeat it.",
        ),
        (
            httpx.ConnectError("refused"),
            "GET",
            "Could not connect to server for /api/items/1",
        ),
        (
            httpx.ConnectError("refused"),
            "PATCH",
            "Could not connect to server for /api/items/1. The PATCH may have taken "
            "effect. Check the state before you repeat it.",
        ),
    ],
)
async def test_timeouts_and_connection_failures(
    call, make_deps, error, method, expected
):
    body = {"name": "n"} if method == "PATCH" else None
    assert await call(
        method, "/api/items/1", body=body, deps=make_deps(raising(error))
    ) == (expected, True)


async def test_an_unexpected_exception(call, make_deps, caplog):
    deps = make_deps(raising(RuntimeError("boom")))
    assert await call("GET", "/api/items/1", deps=deps) == (
        "Unexpected error in call_kiln_api: RuntimeError: boom",
        True,
    )
    assert "call_kiln_api failed: GET /api/items/1" in caplog.text


async def test_progress_is_sent_while_a_slow_call_runs(call, make_deps):
    updates: list[str | None] = []

    async def send(progress: float, total: float | None, message: str | None):
        updates.append(message)

    _, is_error = await call(
        "GET",
        "/api/slow",
        query_params={"seconds": 0.2},
        deps=make_deps(progress_interval=0.02),
        send_progress=send,
    )
    assert not is_error
    assert updates
    assert all(
        message is not None and message.startswith("GET /api/slow: still running, ")
        for message in updates
    )
