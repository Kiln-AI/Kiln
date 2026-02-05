# Custom Models v2 - Implementation Plan

## Goal

Redesign the custom models system to:
1. Support custom models for **both** built-in providers and custom OpenAI-compatible providers in a **unified data structure**
2. Allow setting **model property overrides** (structured output mode, reasoning capable, etc.) when creating custom models
3. Maintain **backwards compatibility** with the legacy `custom_models` config field
4. Provide an **Advanced UI section** for setting overrides when adding models

## Background

### Current Limitations
- Custom models only work with built-in providers (the UI hardcodes provider checks)
- Custom models have no way to set properties like `supports_structured_output`, `structured_output_mode`, `reasoning_capable`, etc.
- This makes custom models hard to use effectively - they default to conservative settings

### KilnModelProvider Fields
From `libs/core/kiln_ai/adapters/ml_model_list.py`, these are the key fields that affect model behavior:

```python
class KilnModelProvider(BaseModel):
    name: ModelProviderName
    model_id: str | None = None
    supports_structured_output: bool = True
    supports_data_gen: bool = True
    suggested_for_data_gen: bool = False
    untested_model: bool = False
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.default
    parser: ModelParserID | None = None
    formatter: ModelFormatterID | None = None
    reasoning_capable: bool = False
    supports_logprobs: bool = False
    suggested_for_evals: bool = False
    supports_function_calling: bool = True
    supports_doc_extraction: bool = False
    supports_vision: bool = False
    multimodal_capable: bool = False
    # ... and more
```

---

## Design

### New Config Field: `user_model_registry`

A single config field that stores all user-defined custom models with optional property overrides.

```python
"user_model_registry": ConfigProperty(
    list,  # List[dict] - see UserModelEntry below
    default_lambda=lambda: [],
),
```

### Data Structure: `UserModelEntry`

```python
class UserModelEntry(BaseModel):
    """A user-defined custom model entry."""
    
    # Provider identification
    provider_type: Literal["builtin", "custom"]  # "builtin" = ModelProviderName enum, "custom" = openai_compatible
    provider_id: str  # For builtin: enum value like "openai". For custom: the custom provider name
    
    # Model identification
    model_id: str  # The model ID to use with the provider's API
    
    # Display name (optional, defaults to model_id)
    name: str | None = None
    
    # Property overrides (optional)
    # Any field from KilnModelProvider can be overridden
    # Backend validates these against KilnModelProvider fields
    overrides: dict | None = None
```

### Examples

```python
# Built-in provider, no overrides (like current custom_models)
{
    "provider_type": "builtin",
    "provider_id": "openai",
    "model_id": "gpt-4o-mini-custom"
}

# Built-in provider with overrides
{
    "provider_type": "builtin",
    "provider_id": "openai",
    "model_id": "o1-preview-custom",
    "name": "O1 Preview (Custom)",
    "overrides": {
        "reasoning_capable": True,
        "supports_structured_output": False
    }
}

# Custom provider, no overrides
{
    "provider_type": "custom",
    "provider_id": "MyLocalLLM",
    "model_id": "llama3"
}

# Custom provider with overrides
{
    "provider_type": "custom",
    "provider_id": "MyLocalLLM",
    "model_id": "deepseek-r1",
    "name": "DeepSeek R1 (Local)",
    "overrides": {
        "reasoning_capable": True,
        "parser": "r1_thinking",
        "structured_output_mode": "json_schema"
    }
}
```

### Legacy `custom_models` Support

The existing `custom_models` field (list of `"provider::model"` strings) is treated as legacy:
- **Not removed** - maintains backwards compatibility
- **Blended at runtime** - converted to `UserModelEntry` format with no overrides
- **UI shows both** - combined list in the manage models UI
- **New models use new format** - all new additions go to `user_model_registry`

```python
# Legacy format in custom_models:
["openai::gpt-4o-custom", "groq::llama-custom"]

# Converted at runtime to:
[
    {"provider_type": "builtin", "provider_id": "openai", "model_id": "gpt-4o-custom"},
    {"provider_type": "builtin", "provider_id": "groq", "model_id": "llama-custom"}
]
```

---

## Implementation Plan

### Phase 1: Add New Config Field and Pydantic Model

**File:** `libs/core/kiln_ai/utils/config.py`

```python
"user_model_registry": ConfigProperty(
    list,
    default_lambda=lambda: [],
),
```

**File:** `libs/core/kiln_ai/adapters/ml_model_list.py` (or new file)

```python
from typing import Literal, Any
from pydantic import BaseModel, field_validator

class UserModelEntry(BaseModel):
    """A user-defined custom model entry."""
    
    provider_type: Literal["builtin", "custom"]
    provider_id: str
    model_id: str
    name: str | None = None
    overrides: dict[str, Any] | None = None
    
    @field_validator("overrides")
    @classmethod
    def validate_overrides(cls, v: dict | None) -> dict | None:
        if v is None:
            return None
        
        # Get valid field names from KilnModelProvider
        valid_fields = set(KilnModelProvider.model_fields.keys())
        # Remove fields that shouldn't be overridden
        valid_fields -= {"name", "model_id"}
        
        invalid_fields = set(v.keys()) - valid_fields
        if invalid_fields:
            raise ValueError(f"Invalid override fields: {invalid_fields}")
        
        return v
```

---

### Phase 2: Backend - Helper Functions for User Models

**File:** `libs/core/kiln_ai/adapters/provider_tools.py`

```python
def get_all_user_models() -> list[UserModelEntry]:
    """
    Returns all user-defined models, combining user_model_registry with legacy custom_models.
    """
    result = []
    
    # Load from new registry
    registry = Config.shared().user_model_registry or []
    for entry in registry:
        try:
            result.append(UserModelEntry(**entry))
        except Exception:
            logger.warning(f"Invalid user model entry: {entry}")
    
    # Load legacy custom_models and convert
    legacy_models = Config.shared().custom_models or []
    for model_str in legacy_models:
        try:
            parts = model_str.split("::", 1)
            if len(parts) == 2:
                provider_id, model_id = parts
                # Check if already in registry (avoid duplicates)
                if not any(
                    m.provider_type == "builtin" and 
                    m.provider_id == provider_id and 
                    m.model_id == model_id 
                    for m in result
                ):
                    result.append(UserModelEntry(
                        provider_type="builtin",
                        provider_id=provider_id,
                        model_id=model_id
                    ))
        except Exception:
            logger.warning(f"Invalid legacy custom model: {model_str}")
    
    return result


def user_model_to_provider(entry: UserModelEntry) -> KilnModelProvider:
    """
    Convert a UserModelEntry to a KilnModelProvider with overrides applied.
    """
    # Determine the base provider name
    if entry.provider_type == "builtin":
        if entry.provider_id not in ModelProviderName.__members__:
            raise ValueError(f"Invalid built-in provider: {entry.provider_id}")
        provider_name = ModelProviderName(entry.provider_id)
    else:
        provider_name = ModelProviderName.openai_compatible
    
    # Build base provider
    base_kwargs = {
        "name": provider_name,
        "model_id": entry.model_id,
        "untested_model": True,  # User models are untested by default
        "supports_structured_output": False,  # Conservative defaults
        "supports_data_gen": False,
        "structured_output_mode": StructuredOutputMode.json_instructions,
    }
    
    # For custom providers, store the provider name
    if entry.provider_type == "custom":
        base_kwargs["openai_compatible_provider_name"] = entry.provider_id
    
    # Apply overrides
    if entry.overrides:
        base_kwargs.update(entry.overrides)
    
    return KilnModelProvider(**base_kwargs)


def find_user_model(model_id: str) -> KilnModelProvider | None:
    """
    Find a user model by its full model ID and return as KilnModelProvider.
    
    Model ID format: "user_model::{provider_type}::{provider_id}::{model_id}"
    """
    if not model_id.startswith("user_model::"):
        return None
    
    parts = model_id.split("::", 3)
    if len(parts) != 4:
        return None
    
    _, provider_type, provider_id, actual_model_id = parts
    
    # Find matching entry
    for entry in get_all_user_models():
        if (entry.provider_type == provider_type and 
            entry.provider_id == provider_id and 
            entry.model_id == actual_model_id):
            return user_model_to_provider(entry)
    
    return None
```

---

### Phase 3: Backend - Update Model Resolution

**File:** `libs/core/kiln_ai/adapters/provider_tools.py`

Update `kiln_model_provider_from()` to check user models first:

```python
def kiln_model_provider_from(
    name: str, provider_name: str | None = None
) -> KilnModelProvider:
    # Check for user model first
    user_model = find_user_model(name)
    if user_model:
        return user_model
    
    # ... rest of existing logic unchanged ...
```

---

### Phase 4: Backend - Add KilnModelProvider Field

**File:** `libs/core/kiln_ai/adapters/ml_model_list.py`

Add field for custom provider name:

```python
class KilnModelProvider(BaseModel):
    # ... existing fields ...
    
    # For openai_compatible providers: the name of the custom provider
    openai_compatible_provider_name: str | None = None
```

---

### Phase 5: Backend - Pass Provider Name Through Adapter

**File:** `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`

Pass `openai_compatible_provider_name` to `lite_llm_core_config_for_provider()`:

```python
core_config = lite_llm_core_config_for_provider(
    provider_name=self.model_provider.name,
    openai_compatible_provider_name=self.model_provider.openai_compatible_provider_name,
)
```

---

### Phase 6: Backend API - Available Providers Endpoint

**File:** `app/desktop/studio_server/provider_api.py`

```python
class AvailableProviderInfo(BaseModel):
    id: str           # Provider identifier
    name: str         # Display name  
    provider_type: Literal["builtin", "custom"]


@app.get("/api/settings/available_providers")
async def get_available_providers() -> List[AvailableProviderInfo]:
    """Returns all providers that can have custom models added."""
    providers = []

    # Built-in providers with required API keys set
    for provider, warning in provider_warnings.items():
        has_keys = all(
            Config.shared().get_value(key) is not None 
            for key in warning.required_config_keys
        )
        if has_keys:
            providers.append(AvailableProviderInfo(
                id=str(provider.value),
                name=provider_name_from_id(provider),
                provider_type="builtin"
            ))

    # Custom OpenAI-compatible providers
    openai_compat_providers = Config.shared().openai_compatible_providers or []
    for provider in openai_compat_providers:
        if provider.get("name"):
            providers.append(AvailableProviderInfo(
                id=provider["name"],
                name=provider["name"],
                provider_type="custom"
            ))

    return providers
```

---

### Phase 7: Backend API - User Model Registry CRUD

**File:** `app/desktop/studio_server/provider_api.py`

```python
@app.get("/api/settings/user_models")
async def get_user_models() -> List[UserModelEntry]:
    """Returns all user-defined models (new registry + legacy combined)."""
    return get_all_user_models()


@app.post("/api/settings/user_models")
async def add_user_model(entry: UserModelEntry) -> JSONResponse:
    """Add a user-defined model to the registry."""
    
    # Validate provider exists
    if entry.provider_type == "builtin":
        if entry.provider_id not in ModelProviderName.__members__:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {entry.provider_id}")
        # Check if provider is configured
        # ... validation logic
    else:
        providers = Config.shared().openai_compatible_providers or []
        if not any(p.get("name") == entry.provider_id for p in providers):
            raise HTTPException(status_code=400, detail=f"Custom provider not found: {entry.provider_id}")
    
    # Add to registry
    registry = Config.shared().user_model_registry or []
    
    # Check for duplicate
    if any(
        e.get("provider_type") == entry.provider_type and
        e.get("provider_id") == entry.provider_id and
        e.get("model_id") == entry.model_id
        for e in registry
    ):
        raise HTTPException(status_code=400, detail="Model already exists")
    
    registry.append(entry.model_dump(exclude_none=True))
    Config.shared().user_model_registry = registry
    
    # Clear model cache so new model appears
    clear_available_models_cache()
    
    return JSONResponse(status_code=200, content={"message": "Model added"})


@app.delete("/api/settings/user_models")
async def delete_user_model(
    provider_type: str, 
    provider_id: str, 
    model_id: str
) -> JSONResponse:
    """Delete a user-defined model from the registry."""
    
    registry = Config.shared().user_model_registry or []
    original_len = len(registry)
    
    registry = [
        e for e in registry 
        if not (
            e.get("provider_type") == provider_type and
            e.get("provider_id") == provider_id and
            e.get("model_id") == model_id
        )
    ]
    
    if len(registry) == original_len:
        # Check if it's a legacy model
        legacy = Config.shared().custom_models or []
        legacy_id = f"{provider_id}::{model_id}"
        if legacy_id in legacy:
            legacy.remove(legacy_id)
            Config.shared().custom_models = legacy
        else:
            raise HTTPException(status_code=404, detail="Model not found")
    else:
        Config.shared().user_model_registry = registry
    
    clear_available_models_cache()
    return JSONResponse(status_code=200, content={"message": "Model deleted"})
```

---

### Phase 8: Backend API - Add User Models to Available Models

**File:** `app/desktop/studio_server/provider_api.py`

```python
def user_models_as_available() -> List[AvailableModels]:
    """
    Returns user models grouped by provider for the available_models endpoint.
    """
    user_models = get_all_user_models()
    if not user_models:
        return []
    
    # Group by provider
    by_provider: Dict[tuple[str, str], List[ModelDetails]] = {}
    
    for entry in user_models:
        key = (entry.provider_type, entry.provider_id)
        if key not in by_provider:
            by_provider[key] = []
        
        # Build model ID for selection
        full_model_id = f"user_model::{entry.provider_type}::{entry.provider_id}::{entry.model_id}"
        
        # Get display name
        display_name = entry.name or entry.model_id
        
        # Determine capabilities from overrides
        overrides = entry.overrides or {}
        
        by_provider[key].append(
            ModelDetails(
                id=full_model_id,
                name=display_name,
                supports_structured_output=overrides.get("supports_structured_output", False),
                supports_data_gen=overrides.get("supports_data_gen", False),
                supports_logprobs=overrides.get("supports_logprobs", False),
                supports_function_calling=overrides.get("supports_function_calling", False),
                untested_model=True,
                suggested_for_data_gen=False,
                suggested_for_evals=False,
                uncensored=overrides.get("uncensored", False),
                suggested_for_uncensored_data_gen=False,
                structured_output_mode=overrides.get(
                    "structured_output_mode", 
                    StructuredOutputMode.json_instructions
                ),
                supports_vision=overrides.get("supports_vision", False),
                supports_doc_extraction=overrides.get("supports_doc_extraction", False),
                suggested_for_doc_extraction=False,
                multimodal_capable=overrides.get("multimodal_capable", False),
                multimodal_mime_types=overrides.get("multimodal_mime_types"),
            )
        )
    
    # Create AvailableModels groups
    result = []
    for (provider_type, provider_id), models in by_provider.items():
        if provider_type == "builtin":
            provider_display = provider_name_from_id(provider_id) + " (Custom)"
        else:
            provider_display = provider_id + " (Custom)"
        
        result.append(AvailableModels(
            provider_name=provider_display,
            provider_id=f"user_model::{provider_type}::{provider_id}",
            models=models,
        ))
    
    return result
```

Update `get_available_models()`:

```python
@app.get("/api/available_models")
async def get_available_models() -> List[AvailableModels]:
    # ... existing code ...
    
    # Add user models (replaces old custom_models() call)
    user_model_groups = user_models_as_available()
    models.extend(user_model_groups)
    
    return models
```

---

### Phase 9: Frontend - Update Add Model Page

**File:** `app/web_ui/src/routes/(app)/settings/providers/add_models/+page.svelte`

```typescript
type ProviderInfo = {
  id: string
  name: string
  provider_type: "builtin" | "custom"
}

type UserModelEntry = {
  provider_type: "builtin" | "custom"
  provider_id: string
  model_id: string
  name?: string
  overrides?: Record<string, unknown>
}

let available_providers: ProviderInfo[] = []
let user_models: UserModelEntry[] = []

// Form state
let new_model_provider: string | null = null
let new_model_name: string | null = null
let new_model_display_name: string | null = null
let show_advanced = false

// Override form state (Advanced section)
let override_supports_structured_output: boolean | null = null
let override_structured_output_mode: string | null = null
let override_supports_data_gen: boolean | null = null
let override_supports_logprobs: boolean | null = null
let override_supports_function_calling: boolean | null = null
let override_supports_vision: boolean | null = null
let override_reasoning_capable: boolean | null = null
let override_parser: string | null = null

const load_data = async () => {
  try {
    loading = true
    
    // Load available providers
    const { data: providers } = await client.GET("/api/settings/available_providers")
    available_providers = providers || []
    
    // Load user models
    const { data: models } = await client.GET("/api/settings/user_models")
    user_models = models || []
    
    if (available_providers.length > 0) {
      new_model_provider = available_providers[0].id
    }
  } catch (e) {
    error = createKilnError(e)
  } finally {
    loading = false
  }
}

function build_overrides(): Record<string, unknown> | undefined {
  const overrides: Record<string, unknown> = {}
  
  if (override_supports_structured_output !== null) {
    overrides.supports_structured_output = override_supports_structured_output
  }
  if (override_structured_output_mode !== null) {
    overrides.structured_output_mode = override_structured_output_mode
  }
  if (override_supports_data_gen !== null) {
    overrides.supports_data_gen = override_supports_data_gen
  }
  if (override_supports_logprobs !== null) {
    overrides.supports_logprobs = override_supports_logprobs
  }
  if (override_supports_function_calling !== null) {
    overrides.supports_function_calling = override_supports_function_calling
  }
  if (override_supports_vision !== null) {
    overrides.supports_vision = override_supports_vision
  }
  if (override_reasoning_capable !== null) {
    overrides.reasoning_capable = override_reasoning_capable
  }
  if (override_parser !== null) {
    overrides.parser = override_parser
  }
  
  return Object.keys(overrides).length > 0 ? overrides : undefined
}

async function add_model() {
  if (!new_model_provider || !new_model_name) {
    throw new KilnError("Provider and model ID are required", null)
  }
  
  const provider = available_providers.find(p => p.id === new_model_provider)
  if (!provider) {
    throw new KilnError("Provider not found", null)
  }
  
  const entry: UserModelEntry = {
    provider_type: provider.provider_type,
    provider_id: new_model_provider,
    model_id: new_model_name,
  }
  
  if (new_model_display_name) {
    entry.name = new_model_display_name
  }
  
  const overrides = build_overrides()
  if (overrides) {
    entry.overrides = overrides
  }
  
  const { error: add_error } = await client.POST("/api/settings/user_models", {
    body: entry
  })
  if (add_error) throw add_error
  
  // Reset form
  new_model_name = null
  new_model_display_name = null
  reset_overrides()
  
  // Refresh list
  await load_data()
  
  return true
}

function reset_overrides() {
  override_supports_structured_output = null
  override_structured_output_mode = null
  override_supports_data_gen = null
  override_supports_logprobs = null
  override_supports_function_calling = null
  override_supports_vision = null
  override_reasoning_capable = null
  override_parser = null
  show_advanced = false
}
```

---

### Phase 10: Frontend - Add Model Dialog with Advanced Section

**File:** `app/web_ui/src/routes/(app)/settings/providers/add_models/+page.svelte`

```svelte
<Dialog bind:this={add_model_dialog} title="Add Model" ...>
  <div class="text-sm">Add a model from an existing provider.</div>
  <div class="text-sm text-gray-500 mt-3">
    Provide the exact model ID used by the provider API.
  </div>
  
  <div class="flex flex-col gap-4 mt-8">
    <FormElement
      label="Model Provider"
      id="model_provider"
      inputType="select"
      select_options={available_providers.map(p => [p.id, p.name])}
      bind:value={new_model_provider}
    />
    
    <FormElement
      label="Model ID"
      id="model_id"
      inputType="input"
      placeholder="e.g., gpt-4o-mini or llama3"
      bind:value={new_model_name}
    />
    
    <FormElement
      label="Display Name (Optional)"
      id="display_name"
      inputType="input"
      placeholder="e.g., My Custom Model"
      bind:value={new_model_display_name}
    />
    
    <!-- Advanced Section -->
    <div class="collapse collapse-arrow bg-base-200">
      <input type="checkbox" bind:checked={show_advanced} />
      <div class="collapse-title font-medium">
        Advanced Options
      </div>
      <div class="collapse-content">
        <div class="flex flex-col gap-4 pt-2">
          
          <FormElement
            label="Supports Structured Output"
            id="supports_structured_output"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_supports_structured_output}
          />
          
          <FormElement
            label="Structured Output Mode"
            id="structured_output_mode"
            inputType="select"
            select_options={[
              ["", "Default (JSON Instructions)"],
              ["json_schema", "JSON Schema"],
              ["json_mode", "JSON Mode"],
              ["json_instructions", "JSON Instructions"],
            ]}
            bind:value={override_structured_output_mode}
          />
          
          <FormElement
            label="Supports Data Generation"
            id="supports_data_gen"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_supports_data_gen}
          />
          
          <FormElement
            label="Supports Logprobs"
            id="supports_logprobs"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_supports_logprobs}
          />
          
          <FormElement
            label="Supports Function Calling"
            id="supports_function_calling"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_supports_function_calling}
          />
          
          <FormElement
            label="Supports Vision"
            id="supports_vision"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_supports_vision}
          />
          
          <FormElement
            label="Reasoning Capable (Thinking Model)"
            id="reasoning_capable"
            inputType="select"
            select_options={[["", "Default (No)"], ["true", "Yes"], ["false", "No"]]}
            bind:value={override_reasoning_capable}
          />
          
          <FormElement
            label="Output Parser"
            id="parser"
            inputType="select"
            select_options={[
              ["", "None"],
              ["r1_thinking", "R1 Thinking (<think> tags)"],
            ]}
            bind:value={override_parser}
          />
          
        </div>
      </div>
    </div>
  </div>
</Dialog>
```

---

### Phase 11: Frontend - Display Model List with Override Badges

Update the model list display to show when models have overrides:

```svelte
{#each user_models as model}
  <div class="flex flex-row gap-2 card bg-base-200 py-2 px-4 items-center">
    <div class="font-medium min-w-24">
      {model.provider_type === "custom" ? model.provider_id : provider_name_from_id(model.provider_id)}
    </div>
    <div class="grow">
      {model.name || model.model_id}
      {#if model.overrides && Object.keys(model.overrides).length > 0}
        <span class="badge badge-sm badge-info ml-2">Custom Settings</span>
      {/if}
    </div>
    <button
      on:click={() => remove_model(model)}
      class="link text-sm text-gray-500"
    >
      Remove
    </button>
  </div>
{/each}
```

---

## Testing Plan

### Unit Tests

1. **UserModelEntry validation** - Test override field validation
2. **`get_all_user_models()`** - Test combining registry with legacy
3. **`user_model_to_provider()`** - Test override application
4. **`find_user_model()`** - Test model ID parsing and lookup

### API Tests

1. **`/api/settings/available_providers`** - Returns both provider types
2. **`/api/settings/user_models` GET** - Returns combined list
3. **`/api/settings/user_models` POST** - Creates with/without overrides
4. **`/api/settings/user_models` DELETE** - Deletes from registry and legacy
5. **`/api/available_models`** - Includes user models with correct capabilities

### Integration Tests

1. Create model with custom provider + overrides
2. Use model in a task
3. Verify overrides are applied (e.g., structured output mode)
4. Delete model, verify removed

### Manual Testing

1. Add model without overrides → verify conservative defaults
2. Add model with "Reasoning Capable" → verify thinking behavior
3. Add model with "JSON Schema" mode → verify structured output works
4. Edit existing model (future feature)
5. Legacy models appear in list

---

## Files Summary

| File | Changes |
|------|---------|
| `libs/core/kiln_ai/utils/config.py` | Add `user_model_registry` ConfigProperty |
| `libs/core/kiln_ai/adapters/ml_model_list.py` | Add `UserModelEntry` model, `openai_compatible_provider_name` field |
| `libs/core/kiln_ai/adapters/provider_tools.py` | Add `get_all_user_models()`, `user_model_to_provider()`, `find_user_model()`; update `kiln_model_provider_from()` |
| `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py` | Pass `openai_compatible_provider_name` to config |
| `app/desktop/studio_server/provider_api.py` | Add `/api/settings/available_providers`, `/api/settings/user_models` endpoints; add `user_models_as_available()` |
| `app/web_ui/src/routes/(app)/settings/providers/add_models/+page.svelte` | Load from APIs; add Advanced section; handle overrides |

---

## Model ID Format

| Context | Format | Example |
|---------|--------|---------|
| Storage (user_model_registry) | Structured dict | `{"provider_type": "custom", "provider_id": "MyAPI", "model_id": "llama3"}` |
| Storage (legacy custom_models) | String | `"openai::gpt-4o-custom"` |
| Selection/Routing | `user_model::{type}::{provider}::{model}` | `"user_model::custom::MyAPI::llama3"` |

---

## Future Enhancements

1. **Edit existing models** - Update overrides for existing entries
2. **Import/Export** - Share model configurations
3. **Model testing** - Verify model works before saving
4. **Suggested overrides** - Auto-detect capabilities based on model name patterns
