---
status: draft
---

# Phase 1: Foundations -- validation endpoint + helpers

## Overview

Add the backend validation endpoint for Jinja templates, regenerate the OpenAPI client, and add the `buildJinjaInputTransform` and `inputTransformsEqual` helpers to the frontend. These are the building blocks that Phase 2's UI will consume.

## Steps

1. Add `ValidateInputTransformTemplateRequest` and `ValidateInputTransformTemplateResponse` Pydantic models to `app/desktop/studio_server/run_config_api.py`.
2. Add `POST /api/validate_input_transform_template` endpoint inside `connect_run_config_api(app)` that wraps `compile_template_or_raise`.
3. Regenerate the OpenAPI TS client via `app/web_ui/src/lib/generate_schema.sh`.
4. Add `buildJinjaInputTransform` and `inputTransformsEqual` helpers to `app/web_ui/src/lib/utils/run_config_formatters.ts`.

## Tests

### Backend (`app/desktop/studio_server/test_run_config_api.py`)
- `test_validate_input_transform_template_valid`: valid template returns `{valid: true, error: null}`, HTTP 200.
- `test_validate_input_transform_template_invalid`: invalid template (e.g. `{{ unclosed`) returns `{valid: false, error: <msg>}`, HTTP 200.
- `test_validate_input_transform_template_empty`: empty string returns `{valid: true, error: null}` (engine permits it; UI forbids).

### Frontend helpers (`run_config_formatters.test.ts`)
- `buildJinjaInputTransform("x")` returns `{type: "jinja", template: "x"}`.
- `inputTransformsEqual`: null/null true; null/set false; same template true; different template false.
