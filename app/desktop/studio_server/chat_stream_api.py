import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.litellm_utils import AISDKStreamTransport
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredInputType,
    StructuredOutputMode,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

AISDK_STREAM_HEADER = "x-vercel-ai-ui-message-stream"
AISDK_STREAM_VERSION = "v1"

MATH_TOOL_IDS = [
    KilnBuiltInToolId.ADD_NUMBERS.value,
    KilnBuiltInToolId.SUBTRACT_NUMBERS.value,
    KilnBuiltInToolId.MULTIPLY_NUMBERS.value,
    KilnBuiltInToolId.DIVIDE_NUMBERS.value,
]

HARDCODED_RUN_CONFIG = KilnAgentRunConfigProperties(
    model_name="minimax_m2_5",
    model_provider_name=ModelProviderName.openrouter,
    prompt_id="simple_prompt_builder",
    structured_output_mode=StructuredOutputMode.json_instruction_and_object,
    tools_config=ToolsRunConfig(tools=MATH_TOOL_IDS),
)


class ChatStreamRequest(BaseModel):
    """Request for streaming chat compatible with Vercel AI SDK data stream protocol."""

    input: str | StructuredInputType = Field(
        description="User input - plain text or structured (dict/list) for tasks with input schema"
    )


def connect_chat_stream_api(app: FastAPI) -> None:
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/chat/stream",
        response_class=StreamingResponse,
    )
    async def chat_stream(
        project_id: str,
        task_id: str,
        request: ChatStreamRequest,
    ) -> StreamingResponse:
        """
        Stream a task run using the Vercel AI SDK data stream protocol.

        Returns SSE with x-vercel-ai-ui-message-stream: v1 header.
        Compatible with useChat from @ai-sdk/react, @ai-sdk/svelte, @ai-sdk/vue.
        """
        task = task_from_id(project_id, task_id)

        adapter = adapter_for_task(
            task,
            run_config_properties=HARDCODED_RUN_CONFIG,
            base_adapter_config=AdapterConfig(),
        )

        input_value = request.input
        if task.input_schema() is not None and isinstance(input_value, str):
            raise HTTPException(
                status_code=400,
                detail="Task has structured input schema - provide input as JSON object.",
            )

        async def event_generator():
            queue: asyncio.Queue[dict | str] = asyncio.Queue()

            async def on_part(part: dict | str) -> None:
                await queue.put(part)

            transport = AISDKStreamTransport(on_part=on_part)
            invoke_task = asyncio.create_task(
                adapter.invoke(input_value, stream_transport=transport)
            )

            try:
                while True:
                    part = await queue.get()
                    if part == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    if isinstance(part, dict):
                        yield f"data: {json.dumps(part)}\n\n"
                    else:
                        yield f"data: {json.dumps(part)}\n\n"
            finally:
                await invoke_task

        return StreamingResponse(
            content=event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                AISDK_STREAM_HEADER: AISDK_STREAM_VERSION,
            },
        )
