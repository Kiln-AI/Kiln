---
status: complete
---

# Implementation Plan: Timezone-Aware Datetimes

## Phases

- [x] **Phase 1: Audit.** Read-only deliverable. Produce `specs/projects/timezone_aware_datetimes/audit.md` enumerating: every datetime field in `libs/core/kiln_ai/datamodel/**/*.py`; every `datetime.now()` / `datetime.utcnow()` / `.replace(tzinfo=...)` / `.astimezone(...)` call across the repo (file:line, with classification: storage default / "now" math against stored timestamps / unrelated / test fixture); every test that builds a naive datetime against a model. No code changes.

- [x] **Phase 2: Data model fix.** Update `KilnBaseModel.created_at` default factory to `datetime.now().astimezone()`. Add `@field_validator("created_at", mode="before")` that promotes naive datetimes/strings to local-aware. Apply same pattern to any other datetime fields surfaced in Phase 1 audit within `libs/core/kiln_ai/datamodel/`. Add unit tests: write→read round-trip preserves offset; legacy naive JSON loads as aware-local; direct naive assignment is normalized via `validate_assignment`. Update existing datamodel tests that build naive datetimes.

- [x] **Phase 3: Consumer audit fixes.** Apply Phase 1 audit to non-datamodel code: fix every `datetime.now()` / `datetime.utcnow()` comparison against now-aware stored timestamps (notably `app/desktop/studio_server/provider_api.py:2050,2157`, `libs/core/kiln_ai/utils/logging.py:48`, plus anything else surfaced). Update test fixtures (`test_provider_api.py`, `test_tool_api.py`) that assign naive datetimes. Run full Python suite; resolve any TypeErrors.

- [ ] **Phase 4: Frontend formatter tests.** Add tests for `formatDate` (`app/web_ui/src/lib/utils/formatters.ts`) covering UTC `Z`, explicit positive/negative offsets, and legacy naive ISO. Mock `Date.now()` for determinism; assert outputs are computed relative to viewer's local TZ. No production code change unless tests reveal one.
