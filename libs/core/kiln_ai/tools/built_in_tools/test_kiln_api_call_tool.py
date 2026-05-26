import asyncio
import contextlib
import json

import httpx
import pytest
import respx

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.built_in_tools.kiln_api_call_tool import (
    CONNECT_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    KilnApiCallTool,
)


@pytest.fixture
def tool():
    return KilnApiCallTool(api_base_url="http://test-server:8757")


class TestRunCallingConvention:
    """run() must work via both tool-execution paths: the adapter's
    ``tool.run(context, **args)`` (LiteLlmAdapter.process_tool_calls) and the
    studio_server executor's ``tool.run(**args)`` (no context)."""

    @pytest.mark.asyncio
    async def test_run_with_positional_context(self, tool):
        # Mirrors LiteLlmAdapter.process_tool_calls: context passed positionally,
        # call args expanded as keywords.
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            args = {"method": "GET", "url_path": "/test"}
            result = await tool.run(ToolCallContext(allow_saving=False), **args)
            assert json.loads(result.output)["status_code"] == 200

    @pytest.mark.asyncio
    async def test_run_without_context(self, tool):
        # Mirrors studio_server.chat.stream_session.execute_tool: tool.run(**args).
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            result = await tool.run(method="GET", url_path="/test")
            assert json.loads(result.output)["status_code"] == 200

    @pytest.mark.asyncio
    async def test_run_with_positional_context_and_jq(self, tool):
        # jq_filter must still bind as a keyword-only arg when context is passed
        # positionally — i.e. the adapter convention with the full set of args.
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"name": "v", "extra": 1})
            )
            args = {"method": "GET", "url_path": "/test", "jq_filter": ".name"}
            result = await tool.run(ToolCallContext(allow_saving=False), **args)
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"] == "v"


class TestKilnApiCallToolInit:
    def test_custom_base_url(self):
        tool = KilnApiCallTool(api_base_url="http://custom:9999")
        assert tool._api_base_url == "http://custom:9999"

    @pytest.mark.asyncio
    async def test_tool_metadata(self, tool):
        assert await tool.name() == "call_kiln_api"
        assert "Kiln REST API" in await tool.description()
        assert await tool.id() == KilnBuiltInToolId.CALL_KILN_API


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_invalid_method(self, tool):
        with pytest.raises(ValueError, match="Invalid method 'INVALID'"):
            await tool.run(method="INVALID", url_path="/test")

    @pytest.mark.asyncio
    async def test_method_case_insensitive(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            result = await tool.run(method="get", url_path="/test")
            assert "status_code" in json.loads(result.output)

    @pytest.mark.asyncio
    async def test_url_path_missing_slash(self, tool):
        with pytest.raises(ValueError, match="url_path must start with '/'"):
            await tool.run(method="GET", url_path="no-slash")

    @pytest.mark.asyncio
    async def test_body_with_get(self, tool):
        with pytest.raises(ValueError, match="body parameter not allowed with GET"):
            await tool.run(method="GET", url_path="/test", body="data")

    @pytest.mark.asyncio
    async def test_body_with_delete(self, tool):
        with pytest.raises(ValueError, match="body parameter not allowed with DELETE"):
            await tool.run(method="DELETE", url_path="/test", body="data")

    @pytest.mark.asyncio
    async def test_url_path_with_query_string_rejected(self, tool):
        with pytest.raises(ValueError, match="must not contain a query string"):
            await tool.run(method="GET", url_path="/test?foo=bar")

    @pytest.mark.asyncio
    async def test_url_path_with_fragment_rejected(self, tool):
        with pytest.raises(ValueError, match="query string or fragment"):
            await tool.run(method="GET", url_path="/test#section")


class TestQueryParams:
    @pytest.mark.asyncio
    async def test_get_with_string_params(self, tool):
        with respx.mock:
            route = respx.get("http://test-server:8757/api/items").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            await tool.run(
                method="GET",
                url_path="/api/items",
                query_params={"tag": "v1"},
            )
            assert route.calls.last.request.url.query == b"tag=v1"

    @pytest.mark.asyncio
    async def test_get_with_list_params_repeated_key(self, tool):
        with respx.mock:
            route = respx.get("http://test-server:8757/api/eval/run_comparison").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            await tool.run(
                method="GET",
                url_path="/api/eval/run_comparison",
                query_params={"run_config_ids": ["a", "b"], "all_run_configs": "false"},
            )
            query = route.calls.last.request.url.query.decode()
            assert "run_config_ids=a" in query
            assert "run_config_ids=b" in query
            assert "all_run_configs=false" in query

    @pytest.mark.asyncio
    async def test_post_with_query_params_and_body(self, tool):
        with respx.mock:
            route = respx.post("http://test-server:8757/api/items").mock(
                return_value=httpx.Response(201, json={"id": "new"})
            )
            await tool.run(
                method="POST",
                url_path="/api/items",
                body={"name": "x"},
                query_params={"dry_run": "true"},
            )
            assert route.calls.last.request.url.query == b"dry_run=true"
            assert (
                route.calls.last.request.content == json.dumps({"name": "x"}).encode()
            )

    @pytest.mark.asyncio
    async def test_empty_query_params_no_query_string(self, tool):
        with respx.mock:
            route = respx.get("http://test-server:8757/api/items").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            await tool.run(
                method="GET",
                url_path="/api/items",
                query_params=None,
            )
            assert route.calls.last.request.url.query == b""


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_get_request(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/api/projects").mock(
                return_value=httpx.Response(200, json={"projects": ["p1", "p2"]})
            )
            result = await tool.run(method="GET", url_path="/api/projects")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert "projects" in parsed["body"]

    @pytest.mark.asyncio
    async def test_post_request_with_body(self, tool):
        with respx.mock:
            route = respx.post("http://test-server:8757/api/projects").mock(
                return_value=httpx.Response(201, json={"id": "new-project"})
            )
            body = json.dumps({"name": "test-project"})
            result = await tool.run(method="POST", url_path="/api/projects", body=body)
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 201
            assert route.calls.last.request.content == body.encode()

    @pytest.mark.asyncio
    async def test_post_request_with_dict_body(self, tool):
        with respx.mock:
            route = respx.post("http://test-server:8757/api/projects").mock(
                return_value=httpx.Response(201, json={"id": "new-project"})
            )
            payload = {"name": "test-project"}
            result = await tool.run(
                method="POST", url_path="/api/projects", body=payload
            )
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 201
            expected = json.dumps(payload).encode()
            assert route.calls.last.request.content == expected

    @pytest.mark.asyncio
    async def test_post_request_with_list_body(self, tool):
        with respx.mock:
            route = respx.post("http://test-server:8757/api/batch").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            payload = [{"id": 1}, {"id": 2}]
            await tool.run(method="POST", url_path="/api/batch", body=payload)
            expected = json.dumps(payload).encode()
            assert route.calls.last.request.content == expected

    @pytest.mark.asyncio
    async def test_patch_request(self, tool):
        with respx.mock:
            route = respx.patch("http://test-server:8757/api/projects/123").mock(
                return_value=httpx.Response(200, json={"updated": True})
            )
            body = json.dumps({"name": "updated"})
            result = await tool.run(
                method="PATCH", url_path="/api/projects/123", body=body
            )
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert route.calls.last.request.content == body.encode()

    @pytest.mark.asyncio
    async def test_patch_request_with_dict_body(self, tool):
        with respx.mock:
            route = respx.patch("http://test-server:8757/api/projects/123").mock(
                return_value=httpx.Response(200, json={"updated": True})
            )
            payload = {"name": "updated"}
            await tool.run(method="PATCH", url_path="/api/projects/123", body=payload)
            expected = json.dumps(payload).encode()
            assert route.calls.last.request.content == expected

    @pytest.mark.asyncio
    async def test_delete_request(self, tool):
        with respx.mock:
            respx.delete("http://test-server:8757/api/projects/123").mock(
                return_value=httpx.Response(204, text="")
            )
            result = await tool.run(method="DELETE", url_path="/api/projects/123")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 204


class TestJqFilter:
    @pytest.mark.asyncio
    async def test_jq_filter_on_success(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"name": "test-value"})
            )
            result = await tool.run(method="GET", url_path="/test", jq_filter=".name")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"] == "test-value"

    @pytest.mark.asyncio
    async def test_jq_filter_applies_to_2xx_not_only_200(self, tool):
        with respx.mock:
            respx.post("http://test-server:8757/api/items").mock(
                return_value=httpx.Response(201, json={"id": "new", "name": "created"})
            )
            result = await tool.run(
                method="POST",
                url_path="/api/items",
                body="{}",
                jq_filter=".name",
            )
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 201
            assert parsed["body"] == "created"

    @pytest.mark.asyncio
    async def test_jq_filter_extracts_array(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"items": [{"id": 1}, {"id": 2}]})
            )
            result = await tool.run(
                method="GET", url_path="/test", jq_filter=".items[] | .id"
            )
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"] == "1\n2"

    @pytest.mark.asyncio
    async def test_jq_filter_not_applied_on_error(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(404, json={"error": "not found"})
            )
            result = await tool.run(method="GET", url_path="/test", jq_filter=".name")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 404
            assert "error" in parsed["body"]

    @pytest.mark.asyncio
    async def test_jq_filter_on_500(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )
            result = await tool.run(method="GET", url_path="/test", jq_filter=".name")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 500
            assert parsed["body"] == "Internal Server Error"


class TestJqErrors:
    @pytest.mark.asyncio
    async def test_invalid_jq_syntax(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"name": "test"})
            )
            with pytest.raises(ValueError, match="jq filter error"):
                await tool.run(method="GET", url_path="/test", jq_filter=".[invalid")

    @pytest.mark.asyncio
    async def test_jq_runtime_error(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"value": 10})
            )
            with pytest.raises(ValueError, match="jq filter error"):
                await tool.run(method="GET", url_path="/test", jq_filter=".value / 0")

    @pytest.mark.asyncio
    async def test_jq_on_non_json_response(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, text="not json")
            )
            with pytest.raises(ValueError, match="Response is not valid JSON"):
                await tool.run(method="GET", url_path="/test", jq_filter=".name")


class TestHttpErrors:
    @pytest.mark.asyncio
    async def test_connection_refused(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            with pytest.raises(
                ConnectionError,
                match=r"^Could not connect to server for /test$",
            ):
                await tool.run(method="GET", url_path="/test")

    @pytest.mark.asyncio
    async def test_read_timeout_reports_read_bound(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                side_effect=httpx.ReadTimeout("timeout")
            )
            with pytest.raises(
                TimeoutError,
                match=rf"Request to /test timed out after {READ_TIMEOUT_SECONDS}s",
            ):
                await tool.run(method="GET", url_path="/test")

    @pytest.mark.asyncio
    async def test_read_timeout_on_post(self, tool):
        with respx.mock:
            respx.post("http://test-server:8757/test").mock(
                side_effect=httpx.ReadTimeout("timeout")
            )
            with pytest.raises(
                TimeoutError, match=rf"timed out after {READ_TIMEOUT_SECONDS}s"
            ):
                await tool.run(method="POST", url_path="/test", body="{}")

    @pytest.mark.asyncio
    async def test_connect_timeout_reports_connect_bound(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                side_effect=httpx.ConnectTimeout("timeout")
            )
            with pytest.raises(
                TimeoutError,
                match=rf"Request to /test timed out after {CONNECT_TIMEOUT_SECONDS}s",
            ):
                await tool.run(method="GET", url_path="/test")


class TestResponseConstruction:
    @pytest.mark.asyncio
    async def test_output_is_valid_json(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(200, json={"data": "value"})
            )
            result = await tool.run(method="GET", url_path="/test")
            parsed = json.loads(result.output)
            assert "status_code" in parsed
            assert "body" in parsed

    @pytest.mark.asyncio
    async def test_status_code_is_integer(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(201, json={})
            )
            result = await tool.run(method="GET", url_path="/test")
            parsed = json.loads(result.output)
            assert isinstance(parsed["status_code"], int)
            assert parsed["status_code"] == 201

    @pytest.mark.asyncio
    async def test_json_response_body_is_object_not_double_encoded_string(self, tool):
        payload = {"projects": ["p1", "p2"], "nested": {"k": 1}}
        with respx.mock:
            respx.get("http://test-server:8757/api/projects").mock(
                return_value=httpx.Response(200, json=payload)
            )
            result = await tool.run(method="GET", url_path="/api/projects")
            parsed = json.loads(result.output)
            assert parsed["body"] == payload
            assert isinstance(parsed["body"], dict)

    @pytest.mark.asyncio
    async def test_json_array_response_body_is_list(self, tool):
        payload = [{"id": "a"}, {"id": "b"}]
        with respx.mock:
            respx.get("http://test-server:8757/api/items").mock(
                return_value=httpx.Response(200, json=payload)
            )
            result = await tool.run(method="GET", url_path="/api/items")
            parsed = json.loads(result.output)
            assert parsed["body"] == payload
            assert isinstance(parsed["body"], list)

    @pytest.mark.asyncio
    async def test_non_json_response_body_stays_plain_string(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )
            result = await tool.run(method="GET", url_path="/test")
            parsed = json.loads(result.output)
            assert parsed["body"] == "Internal Server Error"

    @pytest.mark.asyncio
    async def test_error_json_response_body_is_object(self, tool):
        err = {"error": "not found", "code": 404}
        with respx.mock:
            respx.get("http://test-server:8757/missing").mock(
                return_value=httpx.Response(404, json=err)
            )
            result = await tool.run(method="GET", url_path="/missing")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 404
            assert parsed["body"] == err


class TestSSEResponse:
    """SSE responses are drained (events counted, not retained); body returns
    {event_count, message}."""

    @pytest.mark.asyncio
    async def test_counts_events_and_excludes_complete_sentinel(self, tool):
        body = (
            'data: {"progress": 1, "total": 3}\n\n'
            'data: {"progress": 2, "total": 3}\n\n'
            'data: {"progress": 3, "total": 3}\n\n'
            "data: complete\n\n"
        )
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"]["event_count"] == 3

    @pytest.mark.asyncio
    async def test_incomplete_stream_counts_events(self, tool):
        body = 'data: {"progress": 1, "total": 3}\n\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_sse_with_jq_filter(self, tool):
        body = 'data: {"progress": 1}\n\ndata: {"progress": 2}\n\ndata: complete\n\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(
                method="GET",
                url_path="/api/eval/run",
                jq_filter=".event_count",
            )
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"] == 2

    @pytest.mark.asyncio
    async def test_non_json_data_lines_counted_not_parsed(self, tool):
        # Non-JSON payloads are still counted as events; we don't parse or keep
        # them.
        body = "data: hello\n\ndata: world\n\n"
        with respx.mock:
            respx.get("http://test-server:8757/api/stream").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/stream")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 2

    @pytest.mark.asyncio
    async def test_ignores_comments_and_non_data_fields(self, tool):
        body = (
            ": keepalive comment\n\n"
            "event: ping\n\n"
            'data: {"ok": true}\n\n'
            "data: complete\n\n"
        )
        with respx.mock:
            respx.get("http://test-server:8757/api/stream").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/stream")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_trailing_complete_sentinel_without_blank_line(self, tool):
        # Stream ends on "data: complete" with no final blank line, exercising
        # the post-loop flush branch rather than the in-loop break.
        body = 'data: {"progress": 1}\n\ndata: complete'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_trailing_event_flushed_without_blank_line(self, tool):
        # Last event has no terminating blank line; it must still be counted.
        body = 'data: {"progress": 1}\n\ndata: {"progress": 2}'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 2

    @pytest.mark.asyncio
    async def test_multiline_data_counted_as_one_event(self, tool):
        # Consecutive data: lines form a single event (joined per the SSE spec),
        # so the block below is two events, not four lines.
        body = 'data: {"a": 1,\ndata: "b": 2}\n\ndata: line1\ndata: line2\n\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/stream").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/stream")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_stream(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/api/stream").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content="",
                )
            )
            result = await tool.run(method="GET", url_path="/api/stream")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 0

    @pytest.mark.asyncio
    async def test_crlf_line_endings(self, tool):
        body = 'data: {"progress": 1}\r\n\r\ndata: complete\r\n\r\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content_type",
        [
            "text/event-stream",
            "text/event-stream; charset=utf-8",
            "TEXT/EVENT-STREAM",
        ],
    )
    async def test_content_type_variants_detected_as_sse(self, tool, content_type):
        body = 'data: {"ok": true}\n\ndata: complete\n\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/stream").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": content_type},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/stream")
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_post_returns_sse(self, tool):
        body = 'data: {"progress": 1}\n\ndata: complete\n\n'
        with respx.mock:
            respx.post("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(
                method="POST", url_path="/api/eval/run", body={"id": "x"}
            )
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_sse_with_query_params(self, tool):
        body = 'data: {"progress": 1}\n\ndata: complete\n\n'
        with respx.mock:
            route = respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(
                method="GET",
                url_path="/api/eval/run",
                query_params={"run_config_ids": ["a", "b"]},
            )
            query = route.calls.last.request.url.query.decode()
            assert "run_config_ids=a" in query
            assert "run_config_ids=b" in query
            parsed = json.loads(result.output)
            assert parsed["body"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_non_2xx_sse_response(self, tool):
        # An error status with an event-stream content-type is still drained as
        # SSE (detection is content-type based); jq is skipped because the
        # status is non-2xx.
        body = 'data: {"type": "error", "message": "boom"}\n\n'
        with respx.mock:
            respx.get("http://test-server:8757/api/eval/run").mock(
                return_value=httpx.Response(
                    500,
                    headers={"content-type": "text/event-stream"},
                    content=body,
                )
            )
            result = await tool.run(method="GET", url_path="/api/eval/run")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 500
            assert parsed["body"]["event_count"] == 1


@contextlib.asynccontextmanager
async def _sse_test_server(handler):
    """Run *handler* as a localhost server on an ephemeral port; yield base URL.

    Used to exercise real read-timeout behavior — respx returns mocked
    responses without going through httpx's timeout machinery, so it can't
    simulate inter-event delays.
    """
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield f"http://127.0.0.1:{port}"


class TestSSEReadTimeout:
    """The read timeout is per-read (idle), not a wall-clock cap on the stream."""

    @pytest.mark.asyncio
    async def test_slow_steady_stream_does_not_time_out(self, monkeypatch):
        # Read timeout 0.5s; emit 8 events 0.1s apart so the total (~0.8s)
        # exceeds the timeout while every gap stays well under it. If the bound
        # were a total cap this would raise TimeoutError.
        monkeypatch.setattr(
            "kiln_ai.tools.built_in_tools.kiln_api_call_tool.READ_TIMEOUT_SECONDS",
            0.5,
        )

        async def handler(reader, writer):
            await reader.read(65536)
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/event-stream\r\n"
                b"Connection: close\r\n\r\n"
            )
            await writer.drain()
            for i in range(8):
                await asyncio.sleep(0.1)
                writer.write(f'data: {{"progress": {i}}}\n\n'.encode())
                await writer.drain()
            writer.write(b"data: complete\n\n")
            await writer.drain()
            writer.close()

        async with _sse_test_server(handler) as base_url:
            tool = KilnApiCallTool(api_base_url=base_url)
            result = await tool.run(method="GET", url_path="/stream")
            parsed = json.loads(result.output)
            assert parsed["status_code"] == 200
            assert parsed["body"]["event_count"] == 8
