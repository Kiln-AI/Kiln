---
status: draft
---

# Phase 1: Audit

## Overview

Produce a comprehensive read-only audit document (`specs/projects/timezone_aware_datetimes/audit.md`) that enumerates every datetime field, every `datetime.now()`/`datetime.utcnow()` call, every `.replace(tzinfo=...)`/`.astimezone(...)` call, every comparison/arithmetic against stored datetimes, and every test that constructs a naive datetime for use against a model. No code changes.

## Steps

1. Search all `libs/core/kiln_ai/datamodel/**/*.py` files for datetime field declarations (`: datetime`, `: Optional[datetime]`).
2. Search the entire repo for `datetime.now()`, `datetime.utcnow()`, `.replace(tzinfo=...)`, `.astimezone(...)` calls in `*.py` files.
3. Search for comparisons/arithmetic against `created_at` or other stored datetime fields.
4. Search for test files that construct naive datetimes assigned to model fields.
5. Classify each finding per the functional spec categories: storage default, "now" math against stored timestamps, unrelated/in-process, test fixture.
6. Write findings to `specs/projects/timezone_aware_datetimes/audit.md`.

## Tests

- No tests: this phase is a read-only document deliverable with no code changes.
