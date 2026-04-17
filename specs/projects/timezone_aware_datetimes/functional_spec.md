---
status: complete
---

# Functional Spec: Timezone-Aware Datetimes

## Behaviors

### Writing a new model instance

When any subclass of `KilnBaseModel` is instantiated and saved, its `created_at` MUST be a timezone-aware `datetime` carrying the writer's local UTC offset.

- Default factory: `datetime.now().astimezone()` (returns aware `datetime` with system local TZ attached).
- On-disk JSON serialization: ISO 8601 with offset, e.g. `2026-04-16T09:26:04.806292-04:00`.
- Pydantic v2 default datetime serialization preserves the offset; no custom serializer required, but a round-trip test must lock this.

### Reading an existing model instance from disk

When a JSON file is loaded into a Pydantic model:

- **Aware datetime in the JSON (has offset or `Z`):** parsed as-is. Awareness preserved.
- **Naive datetime in the JSON (no offset, no `Z`):** the parse layer MUST attach the system's *local* timezone before any downstream code touches the value. This makes legacy single-user data render correctly (writer == reader).

This must be enforced at the model boundary so all downstream consumers see only aware datetimes — no aware/naive comparison risk leaking out of the data layer.

### Comparing/computing with `created_at`

Any code that compares `created_at` to "now" or computes durations MUST use an aware "now":

- `datetime.now(timezone.utc)` (or `.astimezone()`) — both work.
- `datetime.utcnow()` — naive, FORBIDDEN going forward when comparing to model timestamps.
- `datetime.now()` (naive) — same, FORBIDDEN against model timestamps.

Tests building synthetic timestamps against models must produce aware datetimes too.

### Frontend rendering

`formatDate(dateString)` in `app/web_ui/src/lib/utils/formatters.ts` requires no production code change:

- New aware ISO with offset → JS `Date` parses to correct instant → renders in viewer's local TZ. ✓
- Aware ISO with `Z` → same. ✓
- Legacy naive ISO → JS `Date` parses as viewer's local → renders correctly for single-user. ✓

Behavior must be locked with tests covering all three formats.

## Edge Cases

- **User changed system TZ or traveled between writes (legacy naive data):** old naive timestamp is interpreted as *current* local TZ on read. May display ~hours off. Acknowledged, not fixed (no data to recover the original zone).
- **Shared dataset with mixed-version collaborators (legacy naive data):** a naive timestamp written by User A in TZ X, read by User B in TZ Y, will display in B's local TZ as if it were B-local. Already broken today; this project does not fix legacy data.
- **Future shared collaboration (new aware data):** the absolute instant is always correct. Both collaborators see correct relative times.
- **Pydantic field assigned a naive datetime in code (e.g., test fixture):** caught automatically. The field validator runs on assignment because `validate_assignment=True` is set on `KilnBaseModel`, so naive datetimes assigned in code are normalized to aware datetimes at assignment time.

## Inputs / Outputs

### Storage contract (on disk)

`created_at` field in any model JSON MUST conform to one of:

1. ISO 8601 with offset: `YYYY-MM-DDTHH:MM:SS[.ffffff]±HH:MM`
2. ISO 8601 with `Z`: `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`
3. (Legacy, read-only) naive ISO: `YYYY-MM-DDTHH:MM:SS[.ffffff]`

New writes MUST use form (1).

### API contract (over the wire)

FastAPI / Pydantic JSON responses serialize `created_at` as form (1) for all data. Legacy naive datetimes are normalized to aware at the model boundary (see "Reading an existing model instance"), so API responses always emit aware datetimes with an offset. The frontend handles all three forms for backward compatibility.

### Audit deliverable

Phase 1 produces a written audit (`specs/projects/timezone_aware_datetimes/audit.md`) listing:

- Every datetime field across `libs/core/kiln_ai/datamodel/**/*.py` (file:line).
- Every `datetime.now()` and `datetime.utcnow()` call in the repo (file:line, classified: storage / "now" math / unrelated).
- Every `.replace(tzinfo=...)` and `.astimezone(...)` call (file:line).
- Every comparison or arithmetic against `created_at` or other stored datetimes (file:line).
- Every test that constructs a naive `datetime` for use against a model.

## Out of Scope (Reiteration)

- Data migration of legacy naive timestamps.
- IANA timezone name storage.
- UI changes beyond test additions.
- Datetimes used purely for in-process state and never serialized (e.g., perf timers).
