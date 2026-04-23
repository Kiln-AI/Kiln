---
status: complete
---

# Phase 9: Move `tests/assets/` to `libs/core/tests/assets/`

## Overview

Moves test asset files from the root `tests/assets/` directory into `libs/core/tests/assets/`, co-locating them with the core library that primarily consumes them. Migrates the associated pytest fixtures (`MockFileFactoryMimeType`, `test_data_dir`, `mock_file_factory`, `mock_attachment_factory`) from the root `conftest.py` into `libs/core/conftest.py`, and creates a bridge `libs/server/conftest.py` for the one server-side consumer.

## Steps

1. Create `libs/core/tests/` directory; `git mv tests/assets libs/core/tests/assets`.
2. Remove empty `tests/` directory.
3. Create `libs/core/conftest.py` with `MockFileFactoryMimeType` enum and the three fixtures (`test_data_dir`, `mock_file_factory`, `mock_attachment_factory`), with `test_data_dir` pointing to `Path(__file__).parent / "tests" / "assets"`.
4. Create `libs/server/conftest.py` that imports `MockFileFactoryMimeType` from `libs.core.conftest` and provides `test_data_dir` and `mock_file_factory` fixtures pointing to the core assets directory (inlined for reliability since conftest cross-imports can be fragile).
5. Remove the four fixture definitions and their unused imports (`shutil`, `uuid`, `Enum`, `Path`, `Callable`, `KilnAttachmentModel`) from root `conftest.py`.
6. Update all `from conftest import MockFileFactoryMimeType` imports in consumer test files to `from libs.core.conftest import MockFileFactoryMimeType` (5 files in `libs/core`, 1 in `libs/server`).
7. Run `ruff check --fix` and `ruff format` to fix import ordering.

## Tests

- No new tests needed; this is a structural move.
- Validated by running `uv run pytest libs/core -q -n auto`, `uv run pytest libs/server -q -n auto`, and full suite `uv run pytest --collect-only -q` confirming identical test count (12867) before and after.
