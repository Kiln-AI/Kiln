---
status: complete
---

# Phase 2: Data Model Fix

## Overview

Update `KilnBaseModel.created_at` to produce timezone-aware datetimes by default and normalize naive datetimes (from legacy data or direct assignment) to local-aware. This ensures all downstream consumers only ever see aware datetimes.

## Steps

1. **`basemodel.py` -- Update `created_at` default factory**
   Change `default_factory=datetime.now` to `default_factory=lambda: datetime.now().astimezone()`.

2. **`basemodel.py` -- Add `field_validator` import**
   Add `field_validator` to the pydantic import block.

3. **`basemodel.py` -- Add naive-to-aware field validator**
   Add `@field_validator("created_at", mode="after")` classmethod `_normalize_created_at_tz` that:
   - If value is a naive `datetime`, calls `.astimezone()` to attach local TZ.
   - Otherwise returns value unchanged.
   `mode="after"` lets Pydantic handle all string parsing first (including `Z` suffix and ISO 8601 offsets on Python 3.10+), so the validator only needs to handle the remaining case of a naive `datetime`.

4. **`test_basemodel.py:109` -- Fix naive `datetime.now()` in existing test**
   Change `now = datetime.datetime.now()` to `now = datetime.datetime.now().astimezone()`.

5. **`test_eval_model.py:1900,1911` -- Fix naive `datetime.now()` in existing test**
   Change `datetime.now()` to `datetime.now().astimezone()` at both lines. These go through `validate_assignment` so they'd be auto-promoted, but explicit is cleaner.

## Tests

Add the following tests to `test_basemodel.py`:

- **`test_created_at_is_timezone_aware`**: New model's `created_at.tzinfo` is not None.
- **`test_created_at_roundtrip_preserves_offset`**: Write model to JSON, read back, assert offset string present in JSON and loaded `created_at` has tzinfo.
- **`test_legacy_naive_json_loads_as_aware`**: Load JSON with a naive datetime string, assert `created_at.tzinfo is not None`.
- **`test_naive_assignment_normalized_via_validate_assignment`**: Assign a naive `datetime` to `model.created_at`, assert result has tzinfo.
- **`test_aware_datetime_preserved_on_load`**: Load JSON with offset datetime string, assert offset is preserved exactly.
