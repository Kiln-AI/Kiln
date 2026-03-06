import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.litellm_utils import (
    AISDKStreamTransport,
    OpenAISSEStreamTransport,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredInputType,
    StructuredOutputMode,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_server.task_api import task_from_id

from app.desktop.studio_server.ai_sdk_types import (
    ChatStreamRequestBody,
    extract_user_input_from_messages,
)

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


def connect_chat_stream_api(app: FastAPI) -> None:
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/chat/stream",
        response_class=StreamingResponse,
    )
    async def chat_stream(
        project_id: str,
        task_id: str,
        request: ChatStreamRequestBody,
    ) -> StreamingResponse:
        """
        Stream a task run using the Vercel AI SDK data stream protocol.

        Accepts either:
        - messages: UIMessage[] (AI SDK useChat format) - extracts last user message text
        - input: str | object (legacy) - direct user input

        Returns SSE stream of UIMessageChunk with x-vercel-ai-ui-message-stream: v1.
        Compatible with useChat from @ai-sdk/react, @ai-sdk/svelte, @ai-sdk/vue.
        """
        task = task_from_id(project_id, task_id)

        adapter = adapter_for_task(
            task,
            run_config_properties=HARDCODED_RUN_CONFIG,
            base_adapter_config=AdapterConfig(),
        )

        if request.messages is not None:
            input_value: str | StructuredInputType = extract_user_input_from_messages(
                request.messages
            )
            if not input_value:
                raise HTTPException(
                    status_code=400,
                    detail="No user message text found in messages array.",
                )
        else:
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

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/chat/openai-stream",
        response_class=StreamingResponse,
    )
    async def chat_openai_stream(
        project_id: str,
        task_id: str,
        request: ChatStreamRequestBody,
    ) -> StreamingResponse:
        """
        Stream a task run using the raw OpenAI streaming format.

        Accepts same request body as /chat/stream (messages or input).
        Returns SSE stream of OpenAI chat completion chunks (choices[].delta).
        Compatible with OpenAI SDK, fetch, and other OpenAI API clients.
        """
        task = task_from_id(project_id, task_id)

        adapter = adapter_for_task(
            task,
            run_config_properties=HARDCODED_RUN_CONFIG,
            base_adapter_config=AdapterConfig(),
        )

        if request.messages is not None:
            input_value: str | StructuredInputType = extract_user_input_from_messages(
                request.messages
            )
            if not input_value:
                raise HTTPException(
                    status_code=400,
                    detail="No user message text found in messages array.",
                )
        else:
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

            transport = OpenAISSEStreamTransport(on_part=on_part)
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
            },
        )
