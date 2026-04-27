---
status: complete
---

# Architecture: Timezone-Aware Datetimes

## Summary

Three small surgical changes plus an audit:

1. **Write side:** flip `KilnBaseModel.created_at`'s default factory from `datetime.now` to `datetime.now().astimezone()`. New writes are aware with the writer's local offset.
2. **Read side:** add a Pydantic field validator on `KilnBaseModel` that, if it receives a naive `datetime`, attaches the system's local timezone. This means downstream code only ever sees aware datetimes.
3. **Audit & fix:** find every comparison/arithmetic against stored datetimes that uses naive "now"; convert to aware. Find every other datetime field across `libs/core/kiln_ai/datamodel/` and apply the same default-factory + validator pattern (or lift to a shared helper).
4. **Frontend tests:** add tests that lock `formatDate` behavior across all three on-disk formats.

No data migration. No new fields. No new dependencies.

## Data Model

### `KilnBaseModel.created_at` (`libs/core/kiln_ai/datamodel/basemodel.py`)

Change:

```python
# Before
created_at: datetime = Field(
    default_factory=datetime.now,
    description="Timestamp when the model was created.",
)

# After
created_at: datetime = Field(
    default_factory=lambda: datetime.now().astimezone(),
    description="Timestamp when the model was created. Timezone-aware; "
                "stores the writer's local offset.",
)
```

### Naive-datetime normalizer (new)

Add a `@field_validator("created_at", mode="after")` on `KilnBaseModel`:

```python
@field_validator("created_at", mode="after")
@classmethod
def _normalize_created_at_tz(cls, v: datetime) -> datetime:
    if v.tzinfo is None:
        return v.astimezone()
    return v
```

Notes:
- `validate_assignment=True` is already set on `KilnBaseModel` → this validator runs on direct assignment too, catching test fixtures that assign naive datetimes.
- `mode="after"` lets Pydantic handle all string parsing first (including the `Z` suffix and ISO 8601 offsets). The validator only needs to handle the remaining case: a naive `datetime` with no timezone info.
- `datetime.astimezone()` (no arg) on a naive datetime treats it as local and attaches the local TZ — exactly what we want for the legacy assumption.

### Other datetime fields

Audit Phase 1 deliverable identifies every other datetime field across the datamodel directory. For each, decide:

- If it represents "moment something happened" → apply same default-factory + validator pattern. Hoist the validator into a reusable helper if more than one field needs it.
- If it's an in-memory cache timestamp (e.g., `provider_api.py: OpenAICompatibleProviderCache.last_updated`) → also fix the *comparison* call site (`datetime.now().astimezone() - self.last_updated`) to use aware "now". Don't necessarily change the field type if it's never serialized.

`provider_api.py` is **outside** the data model directory but the fix-pattern is identical and small — handle it in the consumer-fix phase.

## Component Breakdown

### `libs/core/kiln_ai/datamodel/basemodel.py`

- Update `created_at` default factory.
- Add `_normalize_created_at_tz` validator.
- Update docstring on `KilnBaseModel.created_at`.

### `libs/core/kiln_ai/datamodel/**` (other files)

- For each datetime field discovered in audit: same treatment.
- If validator is duplicated more than twice, extract to a shared helper (e.g., `Annotated[datetime, BeforeValidator(...)]`).

### `libs/core/kiln_ai/datamodel/test_basemodel.py`, `test_eval_model.py`

- Update existing fixtures: `datetime.now()` → `datetime.now().astimezone()`.
- Add new tests:
  - Round-trip: write a model, read JSON, assert offset is preserved.
  - Read legacy naive JSON: assert loaded `created_at.tzinfo is not None` and equals system local at load time.
  - Direct naive assignment via `validate_assignment`: assert it gets normalized to aware.

### `libs/core/kiln_ai/utils/logging.py:48`

- `start_time=datetime.datetime.now()` → `datetime.datetime.now().astimezone()` (if compared anywhere) or leave naive (if never compared to stored timestamps). Audit decides.

### `app/desktop/studio_server/provider_api.py`

- Line 2050: `if datetime.now().astimezone() - self.last_updated > timedelta(minutes=60)` — uses aware "now" for comparison with aware `last_updated`.
- Line 2155+: cache construction also uses aware datetime.

### `app/desktop/studio_server/test_provider_api.py`, `test_tool_api.py`

- Test fixtures that assign `datetime.now()` directly to `created_at`/`last_updated` need updating to match the field's awareness.

### `app/web_ui/src/lib/utils/formatters.test.ts` (new file or extend existing)

- Add tests for `formatDate` covering:
  - `2026-04-16T13:26:04.806292Z` (UTC explicit)
  - `2026-04-16T09:26:04.806292-04:00` (offset)
  - `2026-04-16T21:26:26.944258+08:00` (offset)
  - `2026-04-16T09:26:04.806292` (legacy naive — confirms parsed-as-local behavior)
  - All formats for "just now", "X minutes ago", and "today" branches.
- Mock `Date.now()` so tests are deterministic.
- Tests must NOT depend on the runner's TZ. Use `Intl.DateTimeFormat().resolvedOptions().timeZone` aware comparisons or assert against expected output computed from the test's own current TZ.

## Public Interfaces

No external API changes. JSON shape on the wire is the same string-typed `created_at` field; format simply gains an offset.

OpenAPI-generated TS types (`app/web_ui/src/lib/types.ts`) are unchanged — `created_at` remains `string`.

## Design Decisions (and rejected alternatives)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Storage format | ISO 8601 with writer's local offset | ISO 8601 `Z` (always UTC); naive UTC; epoch ms; UTC + IANA name field | Same audit cost as `Z`; preserves origin offset for free; honest format on disk. IANA is YAGNI. |
| Legacy read interpretation | Assume writer's local TZ | Assume UTC | Single-user dominant case stays correct; UTC-assumption would shift every existing user's data on first render after upgrade. |
| Migration | None | One-shot rewrite | We don't know which TZ wrote legacy data; rewriting could make it worse. |
| Frontend production code change | None (tests only) | Add explicit "assume UTC if no offset" adapter | Browser default (parse-as-local) matches our legacy semantics; no adapter needed. |

## Technical Challenges

### Aware/naive comparison TypeError surface area

Risk: any code path that compares `created_at` (now aware) to `datetime.now()` (still naive) raises `TypeError: can't compare offset-naive and offset-aware datetimes`.

Mitigation: Phase 1 audit produces an exhaustive list. Phase 2 fixes them. CI runs the full Python test suite — any missed call site fails loudly.

### Pydantic JSON serialization of aware datetimes

Risk: Pydantic v2 might emit a format the frontend doesn't parse cleanly.

Mitigation: round-trip test in Phase 1 — model → `.model_dump_json()` → parse string → assert it contains `+` or `-` offset (not `Z`, not naive). If serialization doesn't match expectations, add a `@field_serializer` to force `isoformat()`.

### Test runner timezone

Risk: tests that compute "expected output" from `astimezone()` may behave differently on CI (often UTC) vs developer machines.

Mitigation: tests build aware datetimes with explicit offsets and assert behavior is deterministic given the offset. Don't rely on system TZ in assertions.

## Error Handling

No new error paths. Validator handles malformed strings by raising the same `ValueError` Pydantic already raises for bad ISO inputs.

## Testing Strategy

**Per phase:**
- Phase 1 (audit): no test changes; deliverable is a doc.
- Phase 2 (data model): unit tests on basemodel + each touched datamodel file. Round-trip JSON tests. Validator tests.
- Phase 3 (consumer fixes): update existing failing tests; add comparison tests where missing.
- Phase 4 (frontend): pure unit tests on `formatDate` across all 3 formats.

**Commands:** `uv run ./checks.sh --agent-mode` from repo root must pass after every phase.

## Single-File vs Multi-File Architecture Decision

This architecture fits in one file (~150 lines of technical content). No component designs (`/components/*.md`) needed. Implementation plan can reference this doc directly.
