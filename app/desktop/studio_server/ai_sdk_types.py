"""
Pydantic models for AI SDK stream protocol compatibility.

These types mirror the AI SDK's UIMessageChunk and UIMessage structures
so our /chat/stream endpoint can accept and return the format expected
by useChat from @ai-sdk/react, @ai-sdk/svelte, @ai-sdk/vue.
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class UIMessagePart(BaseModel):
    """Union of UIMessage part types - we only need to parse text parts for input extraction."""

    type: str = "text"
    text: str | None = None


class UIMessage(BaseModel):
    """AI SDK UIMessage - used when accepting messages array in request body."""

    id: str = ""
    role: str = "user"
    metadata: dict[str, Any] | None = None
    parts: list[UIMessagePart] = Field(default_factory=list)


class ChatStreamRequestBody(BaseModel):
    """
    Request body for /chat/stream - supports both AI SDK and legacy formats.

    AI SDK useChat sends: { "messages": UIMessage[] }
    Legacy format: { "input": str | StructuredInputType }
    """

    messages: list[UIMessage] | None = Field(
        default=None,
        description="AI SDK format - full conversation history. Last user message text is used as input.",
    )
    input: str | dict | list | None = Field(
        default=None,
        description="Legacy format - direct user input (plain text or structured for JSON schema tasks).",
    )

    @model_validator(mode="after")
    def check_input_or_messages(self) -> "ChatStreamRequestBody":
        if self.messages is None and self.input is None:
            raise ValueError("Either 'messages' or 'input' must be provided")
        if self.messages is not None and self.input is not None:
            raise ValueError("Provide either 'messages' or 'input', not both")
        return self


def extract_user_input_from_messages(messages: list[UIMessage]) -> str:
    """Extract the concatenated text from the last user message's parts."""
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        texts: list[str] = []
        for part in msg.parts:
            if part.type == "text" and part.text:
                texts.append(part.text)
        if texts:
            return " ".join(texts)
    return ""
