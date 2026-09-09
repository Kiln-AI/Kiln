"""Synthetic-instance handoff into sandboxed children. Stdlib only.

The parent serializes the active :class:`~kiln_ai.datamodel.synthetic_world.SyntheticInstance`
to a plain dict (``SyntheticInstance.to_sandbox_dict``) and passes it through the spawn
args. The child calls :func:`apply_synthetic_instance` before running user code, which
exports the instance as environment variables and puts the world's shared ``lib/`` on
``sys.path``. User code (tools and scorers) reads it back through
``kiln.synthetic_instance()`` or the env vars directly.

Kept stdlib-only because both child entry points import it and they must not pull in
Pydantic or the Kiln datamodel.
"""

from __future__ import annotations

import os
import sys
from typing import Any

ENV_INSTANCE_ID = "KILN_SYNTHETIC_INSTANCE_ID"
ENV_INSTANCE_PATH = "KILN_SYNTHETIC_INSTANCE_PATH"
ENV_FIXTURE_DATA_PATH = "KILN_SYNTHETIC_FIXTURE_DATA_PATH"
ENV_FROZEN_TIME = "KILN_SYNTHETIC_FROZEN_TIME"
ENV_WORLD_ID = "KILN_SYNTHETIC_WORLD_ID"
ENV_FIXTURE_ID = "KILN_SYNTHETIC_FIXTURE_ID"
ENV_WORLD_LIB_PATH = "KILN_SYNTHETIC_WORLD_LIB_PATH"

_ENV_BY_KEY: dict[str, str] = {
    "instance_id": ENV_INSTANCE_ID,
    "path": ENV_INSTANCE_PATH,
    "fixture_data_path": ENV_FIXTURE_DATA_PATH,
    "frozen_time": ENV_FROZEN_TIME,
    "world_id": ENV_WORLD_ID,
    "fixture_id": ENV_FIXTURE_ID,
    "world_lib_path": ENV_WORLD_LIB_PATH,
}


def apply_synthetic_instance(instance: dict[str, Any] | None) -> None:
    """Export *instance* to the child's environment and import path.

    A no-op for ``None``, so callers without an active instance pay nothing. Values
    that are ``None`` are left unset rather than exported as the string ``"None"``.
    """
    if not instance:
        return
    for key, env_name in _ENV_BY_KEY.items():
        value = instance.get(key)
        if value is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = str(value)
    lib_path = instance.get("world_lib_path")
    if lib_path and os.path.isdir(lib_path) and lib_path not in sys.path:
        sys.path.insert(0, lib_path)


def synthetic_instance_from_env() -> dict[str, Any] | None:
    """The active instance as seen from inside a child, or ``None`` when there is none."""
    instance_id = os.environ.get(ENV_INSTANCE_ID)
    if not instance_id:
        return None
    return {key: os.environ.get(env_name) for key, env_name in _ENV_BY_KEY.items()}
