---
status: complete
---

# Phase 2: Environment Options in the data model and Environment API

## Overview

Add named reset kwargs ("Environment Options" in the UI) to `Environment`, and let the Environment create and update routes read and write them. Validation errors from these routes return 400 with the friendly copy from `ui_design.md` (duplicate option name, non-object reset arguments, bad Server URL). This is the data the OpenEnv detail page (phase 6) edits and the run page (phase 7) reads.

## Steps

1. `libs/core/kiln_ai/datamodel/environment.py`:
   - Add `NamedResetKwargs(BaseModel)` with `name` (stripped, 1 to 120 chars, via `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]`) and `reset_kwargs: dict[str, JsonValue] = Field(default_factory=dict)`.
   - Add `Environment.named_reset_kwargs: list[NamedResetKwargs] = Field(default_factory=list)` with descriptions.
   - Add `@field_validator("named_reset_kwargs")` `unique_option_names`, raising `ValueError(f"An Environment Option named {name} already exists.")` on the first repeated name. Names are already stripped by the field type, so comparison is case-sensitive equality.
   - Export `NamedResetKwargs` from `kiln_ai.datamodel` if `Environment` is exported there.
2. `app/desktop/studio_server/environment_api.py`:
   - Add `NamedResetKwargsRequest(BaseModel)` with `name: str` and `reset_kwargs: JsonValue`, loosely typed so a non-object reaches the handler and gets the friendly 400 instead of FastAPI's generic 422.
   - `EnvironmentCreateRequest` and `EnvironmentUpdateRequest` gain `named_reset_kwargs: list[NamedResetKwargsRequest]` (create defaults to `[]`, update to `None` = unchanged). PATCH replaces the whole list.
   - `EnvironmentResponse` gains `named_reset_kwargs: list[NamedResetKwargs]`; `_env_response` copies it.
   - Add `_friendly_error(e: PydanticValidationError) -> str` mapping: an `env_url` error → "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8004."; a `named_reset_kwargs[i].reset_kwargs` `dict_type` error → "Reset arguments must be a JSON object."; a validator `value_error` → the validator's own message; anything else → `str(e)`.
   - Create and update catch `PydanticValidationError` and raise 400 with `_friendly_error`. PATCH validates the whole update on a copy before assigning, so a failed PATCH never leaves the loaded model half-changed.
3. Regenerate `app/web_ui/src/lib/api_schema.d.ts` with `generate_schema.sh`. Agent annotations are unchanged (no path, method or policy change).

## Tests

- `test_environment.py`:
  - `test_named_reset_kwargs_default_empty`: a new environment has `[]`.
  - `test_named_reset_kwargs_round_trip_preserves_order`: save and reload keeps names, kwargs (nested JSON) and order.
  - `test_duplicate_option_names_rejected`: same name twice raises with "An Environment Option named Acme Manager already exists."; names differing only by surrounding whitespace also collide; names differing by case are allowed.
  - `test_duplicate_rejected_on_assignment`: assigning a list with a duplicate to a saved environment raises.
  - `test_non_object_reset_kwargs_rejected`: list, string, number rejected.
  - `test_option_name_bounds`: empty or whitespace-only and over 120 chars rejected; name is stored stripped.
- `test_environment_api.py`:
  - `test_create_with_named_reset_kwargs`: create returns them, in order, and they're on disk.
  - `test_patch_replaces_named_reset_kwargs`: PATCH with a new list replaces; PATCH without the field leaves it; PATCH with `[]` clears it.
  - `test_duplicate_option_name_is_400`: create and PATCH, friendly message; disk unchanged after the failed PATCH.
  - `test_non_object_reset_kwargs_is_400` (parametrized array, string, number, null): "Reset arguments must be a JSON object."
  - `test_invalid_env_url` and `test_update`: assert the friendly URL message.
