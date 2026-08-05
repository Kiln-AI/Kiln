"""Shared multiprocessing spawn helpers.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.
"""

import multiprocessing.process
import sys
import threading
import types

_spawn_lock = threading.Lock()
"""Process-global lock shared by code-evals (``run_scorer``) and code tools.

Serializes the ``__main__`` stub-swap window around ``p.start()``,
preventing the PyInstaller concurrent-spawn bug #7410.
"""


def start_process_with_light_main(
    p: multiprocessing.process.BaseProcess,
) -> None:
    """Start *p* under ``_spawn_lock`` with ``sys.modules['__main__']`` swapped for a stub.

    Prevents the spawn child from re-importing the parent's heavy
    ``__main__`` module (e.g. dev_server.py which transitively pulls
    in litellm, google.cloud.aiplatform, etc.).

    ``multiprocessing.spawn.get_preparation_data`` reads
    ``sys.modules['__main__']`` to decide what to re-execute in the
    child.  By swapping in a lightweight stub named ``"__main__"``
    (with no ``__file__`` or ``__spec__``) before ``p.start()``
    (which pickles the prep data), neither ``init_main_from_name``
    nor ``init_main_from_path`` is set, so the child skips the
    heavy re-import entirely.

    The stub is named ``"__main__"`` (not ``"__mp_main__"``, which
    would collide with multiprocessing's internal main-module
    name).  Third-party code that inspects
    ``sys.modules["__main__"].__name__`` during the brief swap
    window sees the expected ``"__main__"`` value.

    This stays within ``multiprocessing.spawn``'s existing
    bootstrap, so ``freeze_support()`` and PyInstaller frozen
    builds continue to work.

    Thread safety: the swap is process-global, but the window is
    sub-millisecond (only spans ``p.start()``), is serialized by
    ``_spawn_lock``, and ``__main__`` is not read by request-
    handling code, so cross-thread visibility is benign.
    """
    with _spawn_lock:
        _real_main = sys.modules.get("__main__")
        if _real_main is not None:
            _light_main = types.ModuleType("__main__")
            sys.modules["__main__"] = _light_main
            try:
                p.start()
            finally:
                sys.modules["__main__"] = _real_main
        else:
            p.start()
