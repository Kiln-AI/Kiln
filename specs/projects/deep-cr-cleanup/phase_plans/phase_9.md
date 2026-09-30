---
status: complete
---

# Phase 9: API typed trust response

## Overview

Replace the untyped `dict[str, bool]` return type on the two code-eval trust endpoints (`grant_code_eval_trust` and `check_code_eval_trust`) with a named Pydantic model `CodeEvalTrustResponse(BaseModel)` containing a single `trusted: bool` field. This produces a closed OpenAPI schema instead of an open bool-map, improving the TS client contract. Regen the OpenAPI/TS schema and update frontend call-site types accordingly.

## Steps

1. Define `CodeEvalTrustResponse(BaseModel)` in `eval_api.py` near the other response models (around line 207).
2. Update `grant_code_eval_trust_endpoint` return annotation from `dict[str, bool]` to `CodeEvalTrustResponse` and return body to `CodeEvalTrustResponse(trusted=True)`.
3. Update `check_code_eval_trust_endpoint` return annotation from `dict[str, bool]` to `CodeEvalTrustResponse` and return body to `CodeEvalTrustResponse(trusted=...)`.
4. Update backend tests in `test_eval_api.py` — the JSON shape `{"trusted": True/False}` is unchanged, so assertions on `response.json()` should still pass. Verify this.
5. Regenerate the OpenAPI schema (`generate_schema.sh`) and verify (`check_schema.sh`).
6. Update `v2_eval_api.ts` — change `checkCodeEvalTrust` and `grantCodeEvalTrust` return types from `{ [key: string]: boolean }` to `{ trusted: boolean }` (or use the generated schema type `CodeEvalTrustResponse`).
7. Frontend call sites in `+page.svelte` already read `.trusted` — no changes needed there since the shape is the same.

## Tests

- Existing `test_grant_trust`: verify still passes (JSON shape unchanged).
- Existing `test_check_trust_untrusted`: verify still passes.
- Existing `test_check_trust_after_grant`: verify still passes.
- Frontend `v2_eval_api.test.ts` checkCodeEvalTrust / grantCodeEvalTrust tests: verify still pass (mock data shape unchanged).
- Frontend `page.test.ts` trust-related tests: verify still pass.
