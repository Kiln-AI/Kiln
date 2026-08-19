---
status: complete
---

# Phase 3: Deferred `litellm` Import in the Root `conftest.py`

## Overview

pytest imports the root `conftest.py` on **every** invocation, and that conftest
imported `litellm` at module scope. Importing litellm costs several seconds, so
every run paid it even when no collected test touched litellm — a tax on the most
common agent action, iterating on a single test file (F6).

The fix makes the import lazy: the autouse fixture looks litellm up in
`sys.modules` and does litellm-specific setup and teardown only when something has
already imported it. This cannot skip a needed cache flush — the flush is skipped
only when litellm is absent from `sys.modules`, i.e. nothing imported it, so there
are no cached HTTP clients to flush and no cross-test state to leak.

The dangerous failure mode here is silently collecting fewer tests, so the pass and
skip counts are the primary assertion.

## Steps

1. Delete `import litellm` and
   `from kiln_ai.datamodel.basemodel import KilnAttachmentModel` from the top of
   `conftest.py`. Add `import sys` and switch `from typing import Callable` to
   `from typing import TYPE_CHECKING, Callable`, with the datamodel import moved
   under `if TYPE_CHECKING:` so the annotation still resolves for type checkers.

2. Rewrite the autouse fixture to guard on `sys.modules` and absorb the logging
   setup. Rename it `_litellm_per_test_setup`: it no longer only clears httpx
   clients, and it has no `yield`, so "teardown" is not part of what it does
   either. Comment what the guard costs — a run that never imports litellm also
   never configures litellm logging, so the `LiteLLM` logger keeps its default
   level and `ModelCalls` gets no handler. Nothing depends on that today.

   ```python
   @pytest.fixture(autouse=True)
   def _litellm_per_test_setup() -> None:
       litellm = sys.modules.get("litellm")
       if litellm is None:
           return

       from kiln_ai.utils.logging import setup_litellm_logging

       setup_litellm_logging("test_model_calls.log")
       litellm.in_memory_llm_clients_cache.flush_cache()
   ```

3. Delete the session-scoped autouse `setup_test_logging` fixture; its body is now
   the guarded lines above. Calling `setup_litellm_logging` per test is cheap and
   idempotent — it early-returns as soon as a `CustomLiteLLMLogger` is already in
   `litellm.callbacks` (`libs/core/kiln_ai/utils/logging.py:137-140`), so every call
   after the first is a short list scan.

4. In the `mock_attachment_factory` fixture, quote the return annotation
   (`-> "KilnAttachmentModel"`) and do the `KilnAttachmentModel` import locally
   inside `create_attachment`.

Import ordering holds throughout: pytest imports the root conftest before collecting
test modules, and any module that uses litellm imports it at its own module scope,
so by the time that module's tests run, `sys.modules` has it.

## Tests

No new unit tests — this changes fixture plumbing, and the existing suite is the
assertion. Verified:

- Full suite `uv run python3 -m pytest --benchmark-quiet -q -n auto .` reports
  **6369 passed, 10020 skipped, 0 errors**, identical to before the change. A drop
  in either count would mean tests silently stopped running.
- Single test file (`libs/core/kiln_ai/utils/test_config.py`, 42 tests): 1.93 /
  1.93 / 1.93 s, against 11.72 / 11.31 / 11.20 s measured on this machine with the
  module-scope `import litellm` temporarily restored. Treat that as one point
  measurement, not a headline multiple — a warm box sees a much smaller ratio,
  since litellm's first import also fetches its model-cost map. F6 records the
  spread across three machines.
- **Architecture open verification item — log path.** `setup_litellm_logging` now
  resolves its log path during a test, while the autouse `use_temp_settings_dir`
  fixture has `Config.settings_path` patched. Confirmed by a probe test that imports
  litellm and reads the `ModelCalls` logger's handler: `baseFilename` is
  `~/.kiln_ai/logs/test_model_calls.log`, unchanged. `get_log_file_path` reads
  `Config.settings_dir()`, which derives from `Path.home()` and is not the patched
  method, so no session-scoped fallback fixture is needed.
- The same probe asserts a `CustomLiteLLMLogger` is registered in
  `litellm.callbacks`, so logging is still configured for runs that use litellm.
- **Recorded, not fixed:** moving path resolution to function scope makes it
  order-dependent. `test_lancedb_adapter.py:47` and `test_vector_store_registry.py:16`
  patch `Config.settings_dir` itself to `tmp_path` via their own autouse fixtures,
  and because `setup_litellm_logging` is idempotent, whichever runs first wins for
  the whole worker. Correct today because pytest instantiates root-conftest autouse
  fixtures before module-level ones — a documented property, but load-bearing and
  unobvious, so it is called out in a comment on the fixture and in `architecture.md` §4.
- `uv run ./checks.sh --agent-mode` green.
