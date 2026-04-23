---
status: complete
---

# Phase 3: Consumer Audit Fixes

## Overview

Apply the Phase 1 audit findings to non-datamodel code. Fix every `datetime.now()` call that is compared against now-aware stored timestamps, and update test fixtures that assign naive datetimes to fields on plain dataclasses (which bypass Pydantic's validator).

## Steps

1. **`provider_api.py:2050` — Fix `is_stale()` comparison**
   Change `datetime.now()` to `datetime.now().astimezone()` so the staleness comparison is aware-consistent with the `last_updated` field.

2. **`provider_api.py:2157` — Fix cache construction**
   Change `last_updated=datetime.now()` to `last_updated=datetime.now().astimezone()` in the `OpenAICompatibleProviderCache` constructor.

3. **`logging.py:48` — No change needed**
   Per audit, this is unrelated (passed to litellm `Logging` constructor, never compared to stored timestamps).

4. **`test_provider_api.py:1958,1965,1969,2020` — Fix test fixtures**
   Change all `datetime.now()` to `datetime.now().astimezone()` for `last_updated` on the plain `@dataclass` cache object.

5. **`test_tool_api.py:2721,2797,2868,2950` — Fix test fixtures**
   Change all `datetime.now()` to `datetime.now().astimezone()` for `created_at` on `Mock()` objects (which bypass Pydantic validation).

6. **RAG test fixtures — No change needed**
   `test_rag_runners.py` and `test_deduplication.py` use `MagicMock` objects with naive `datetime(2023, 1, N)` or naive strings assigned to `created_at`. These are only compared against each other within groups (via `min()`), never against aware datetimes. Awareness is consistent within each group, so no TypeError risk.

## Tests

No new tests needed for this phase — the changes are making existing code and tests awareness-consistent. The full Python test suite must pass without TypeErrors after these changes.
