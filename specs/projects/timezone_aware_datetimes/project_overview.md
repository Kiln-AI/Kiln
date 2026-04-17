---
status: complete
---

# Timezone-Aware Datetimes

## Problem

Kiln stores datetimes (e.g., `TaskRun.created_at`) as naive ISO strings — `"2026-04-16T09:26:04.806292"` — produced by `datetime.now()`. The string carries no timezone information, so the absolute instant is unrecoverable.

This breaks any cross-timezone collaboration. Concrete incident:

- Toronto user creates a run at local 09:26 (`2026-04-16T09:26:04.806292`).
- Taipei user creates a run at local 21:26 (`2026-04-16T21:26:26.944258`) — same instant, ~22 seconds later.
- For the Toronto user, both runs render as "just now" (their browser parses both naive strings as Toronto-local).
- For the Taipei user, the Toronto run appears to have happened ~12 hours ago.

The web frontend's `formatDate` (`app/web_ui/src/lib/utils/formatters.ts`) does `new Date(dateString)`, which per ECMA-262 parses naive ISO as **local** time. That's the root cause of the wrong "hours ago" rendering.

## What We're Building

Make Kiln's datetimes carry the writer's timezone offset on disk going forward, while continuing to render correctly for legacy single-user data.

**Storage format (new writes):** ISO 8601 with the writer's local offset, e.g. `2026-04-16T09:26:04.806292-04:00` (Toronto) or `2026-04-16T21:26:26.944258+08:00` (Taipei). Same instant, but origin offset preserved for free.

**Read behavior:**
- Aware datetimes (offset present) → use as-is.
- Naive datetimes (legacy data) → assume **writer's local time** (not UTC). Single-user setups (the dominant case) render correctly because writer == reader.

**Rendering:** All UI rendering remains in the *viewer's* local time via the existing `formatDate` helper. No new TZ name display needed in this project.

## Why This Approach

- **Format change is honest:** offset is part of ISO 8601 / RFC 3339; tools outside Kiln can interpret it without our docs.
- **Preserve creator origin for free:** we pay the audit cost anyway (any aware-datetime introduction risks `TypeError: can't compare offset-naive and offset-aware`); writing the local offset costs nothing more than writing `Z`.
- **No data migration:** old naive data stays naive on disk; only the read-path interpretation changes.
- **Frontend is mostly free:** modern JS `new Date()` parses both offset-bearing and naive ISO correctly (naive → local); tests confirm and lock behavior.

## Out of Scope

- Migrating existing on-disk timestamps.
- Storing IANA timezone names (`Asia/Taipei`) — offset is sufficient for the bug.
- Showing "created at 9:26 AM Taipei time" in UI — viewer-local is enough for now.
- Datetimes outside data-model state (e.g., logs, telemetry) unless they intersect stored timestamps.
