import logging
from typing import Any

from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.desktop.studio_server.chat.constants import _EXECUTOR_SERVER

logger = logging.getLogger(__name__)


class KilnToolInputMetadata(BaseModel):
    """Validated subset of ``kiln_metadata`` on tool-input-available events."""

    model_config = ConfigDict(extra="allow")

    executor: str | None = None
    requires_approval: bool | None = None
    permission: str | None = None
    approval_description: str | None = None

    @field_validator("requires_approval", mode="before")
    @classmethod
    def _requires_approval_must_be_bool_or_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        raise ValueError("requires_approval must be a boolean or null")

    @field_validator("executor", "permission", "approval_description", mode="before")
    @classmethod
    def _optional_str_fields(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        raise ValueError("must be a string or null")


def _parse_kiln_tool_metadata(raw: dict[str, Any]) -> KilnToolInputMetadata:
    try:
        return KilnToolInputMetadata.model_validate(dict(raw))
    except ValidationError:
        logger.debug("kiln_metadata validation failed, using narrowed fields: %s", raw)
        narrowed: dict[str, Any] = {}
        for key in ("executor", "permission", "approval_description"):
            v = raw.get(key)
            if isinstance(v, str):
                narrowed[key] = v
        ra = raw.get("requires_approval")
        if isinstance(ra, bool):
            narrowed["requires_approval"] = ra
        for k, v in raw.items():
            if k in narrowed or k == "requires_approval":
                continue
            narrowed[k] = v
        return KilnToolInputMetadata.model_validate(narrowed)


def _tool_input_executor_is_server(event: ToolInputAvailableEvent) -> bool:
    return _parse_kiln_tool_metadata(event.kiln_metadata).executor == _EXECUTOR_SERVER


def _tool_requires_user_approval(event: ToolInputAvailableEvent) -> bool:
    return _parse_kiln_tool_metadata(event.kiln_metadata).requires_approval is True
