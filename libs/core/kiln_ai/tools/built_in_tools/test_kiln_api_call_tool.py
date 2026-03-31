import json

import httpx
import pytest
import respx

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.built_in_tools.kiln_api_call_tool import KilnApiCallTool


@pytest.fixture
def tool():
    return KilnApiCallTool(api_base_url="http://test-server:8757")


class TestKilnApiCallToolInit:
    def test_default_base_url(self):
        tool = KilnApiCallTool()
        assert tool._api_base_url == "http://localhost:8757"

    def test_custom_base_url(self):
        tool = KilnApiCallTool(api_base_url="http://custom:9999")
        assert tool._api_base_url == "http://custom:9999"

    @pytest.mark.asyncio
    async def test_tool_metadata(self, tool):
        assert await tool.name() == "call_kiln_api"
        assert "Kiln API server" in await tool.description()
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
            assert parsed["body"] == '"test-value"'

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
            assert parsed["body"] == '"created"'

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
    async def test_timeout(self, tool):
        with respx.mock:
            respx.get("http://test-server:8757/test").mock(
                side_effect=httpx.TimeoutException("timeout")
            )
            with pytest.raises(
                TimeoutError, match=r"Request to /test timed out after 30\.0s"
            ):
                await tool.run(method="GET", url_path="/test")

    @pytest.mark.asyncio
    async def test_timeout_uses_longer_timeout_for_post(self, tool):
        with respx.mock:
            respx.post("http://test-server:8757/test").mock(
                side_effect=httpx.TimeoutException("timeout")
            )
            with pytest.raises(TimeoutError, match=r"timed out after 300\.0s"):
                await tool.run(method="POST", url_path="/test", body="{}")


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
