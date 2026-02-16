import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserModelEntry(BaseModel):
    """
    A user-defined custom model entry.

    Attributes:
        id: Unique identifier for this entry (auto-generated if not provided)
        provider_type: "builtin" for ModelProviderName enum providers, "custom" for openai_compatible
        provider_id: For builtin: enum value like "openai". For custom: the custom provider name
        model_id: The model ID to use with the provider's API
        name: Display name (optional, defaults to model_id)
        overrides: Property overrides from KilnModelProvider (optional)

    Note on overrides:
        The overrides field accepts any keys for forward compatibility. When a UserModelEntry
        is converted to a KilnModelProvider via user_model_to_provider(), only valid
        KilnModelProvider fields are applied. Unknown fields are silently ignored.
        This allows new fields to be added to KilnModelProvider without breaking existing
        UserModelEntry data.
    """

    provider_type: Literal["builtin", "custom"]
    provider_id: str
    model_id: str
    name: str | None = None
    overrides: dict[str, Any] | None = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
