---
status: in_progress
---

# Phase 4: Frontend formatter tests

## Overview

Add comprehensive tests for `formatDate` in `app/web_ui/src/lib/utils/formatters.ts` covering all three on-disk datetime formats: UTC `Z` suffix, explicit positive/negative offsets, and legacy naive ISO strings. Mock `Date.now()` for deterministic results. No production code changes unless tests reveal a bug.

## Steps

1. Add `formatDate` import to `formatters.test.ts`
2. Add a `describe("formatDate", ...)` block with `vi.useFakeTimers()` / `vi.useRealTimers()` in `beforeEach`/`afterEach`
3. Pin `Date.now()` via `vi.setSystemTime(new Date("2026-04-16T13:26:04.806Z"))` so all relative-time branches are deterministic
4. Write test cases for each time bucket ("just now", "1 minute ago", "N minutes ago", "today", older date) across all three ISO formats (UTC Z, positive offset, negative offset, legacy naive)
5. Write edge-case tests: `undefined` input, empty string input

## Tests

- `returns "Unknown" for undefined`: verifies fallback
- `returns "Unknown" for empty string`: verifies fallback
- `returns "just now" for UTC Z timestamp within last minute`: e.g. `2026-04-16T13:25:30.000Z`
- `returns "just now" for offset timestamp within last minute`: e.g. `2026-04-16T09:25:30.000-04:00`
- `returns "1 minute ago" for timestamp 90 seconds ago (Z)`: boundary test
- `returns "N minutes ago" for timestamp N minutes ago (positive offset)`: e.g. `2026-04-16T21:16:04.000+08:00` (10 min ago)
- `returns "N minutes ago" for timestamp N minutes ago (negative offset)`: e.g. `2026-04-16T09:01:04.000-04:00` (25 min ago)
- `returns time + "today" for timestamp earlier today (Z)`: earlier same day
- `returns full date for timestamp from a different day (Z)`: previous day
- `returns full date for timestamp from a different day (offset)`: previous day with offset
- `returns "just now" for legacy naive ISO within last minute`: e.g. naive string parsed as local
- `all three formats for same instant produce identical output`: UTC Z, +08:00, and -04:00 representing the same moment all yield the same result
