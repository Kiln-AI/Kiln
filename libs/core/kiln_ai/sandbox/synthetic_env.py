"""Synthetic-instance handoff into sandboxed children. Stdlib only.

The parent serializes the active :class:`~kiln_ai.datamodel.synthetic_world.SyntheticInstance`
to a plain dict (``SyntheticInstance.to_sandbox_dict``) and passes it through the spawn
args. The child calls :func:`apply_synthetic_instance` before running user code, which
exports the instance as environment variables and puts the world's shared ``lib/`` on
``sys.path``. User code (tools and scorers) reads it back through
``kiln.synthetic_instance()`` or the env vars directly.

Exported variables:

    KILN_SYNTHETIC_INSTANCE_ID, KILN_SYNTHETIC_WORLD_ID
    KILN_SYNTHETIC_INSTANCE_PATH      local state directory (file-backed launchers)
    KILN_SYNTHETIC_ENDPOINT           URL of a hosted instance (network launchers)
    KILN_SYNTHETIC_CONNECTION         the full connection as JSON: transport, url, headers,
                                      command, args, env (credentials included; this is
                                      the one place they travel, into the tool's process)
    KILN_SYNTHETIC_SOURCE_PATH        the read-only original of a file-backed instance
    KILN_SYNTHETIC_WORLD_LIB_PATH     the world's lib/, also prepended to sys.path
    KILN_SYNTHETIC_CONFIG             the launch config, as JSON
    KILN_SYNTHETIC_METADATA           what the launcher reported, as JSON
    KILN_SYNTHETIC_<KEY>              one per scalar metadata entry, e.g. KILN_SYNTHETIC_FROZEN_TIME

Kept stdlib-only because both child entry points import it and they must not pull in
Pydantic or the Kiln datamodel.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

ENV_PREFIX = "KILN_SYNTHETIC_"
ENV_INSTANCE_ID = "KILN_SYNTHETIC_INSTANCE_ID"
ENV_INSTANCE_PATH = "KILN_SYNTHETIC_INSTANCE_PATH"
ENV_ENDPOINT = "KILN_SYNTHETIC_ENDPOINT"
ENV_SOURCE_PATH = "KILN_SYNTHETIC_SOURCE_PATH"
ENV_WORLD_ID = "KILN_SYNTHETIC_WORLD_ID"
ENV_WORLD_LIB_PATH = "KILN_SYNTHETIC_WORLD_LIB_PATH"
ENV_CONFIG = "KILN_SYNTHETIC_CONFIG"
ENV_METADATA = "KILN_SYNTHETIC_METADATA"
ENV_CONNECTION = "KILN_SYNTHETIC_CONNECTION"

_ENV_BY_KEY: dict[str, str] = {
    "instance_id": ENV_INSTANCE_ID,
    "path": ENV_INSTANCE_PATH,
    "endpoint": ENV_ENDPOINT,
    "source_path": ENV_SOURCE_PATH,
    "world_id": ENV_WORLD_ID,
    "world_lib_path": ENV_WORLD_LIB_PATH,
}
_JSON_BY_KEY: dict[str, str] = {
    "config": ENV_CONFIG,
    "metadata": ENV_METADATA,
    "connection": ENV_CONNECTION,
}
_RESERVED = set(_ENV_BY_KEY.values()) | set(_JSON_BY_KEY.values())


def metadata_env_name(key: str) -> str:
    return ENV_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").upper()


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
    for key, env_name in _JSON_BY_KEY.items():
        value = instance.get(key)
        if key == "connection" and value is None:
            os.environ.pop(env_name, None)
            continue
        os.environ[env_name] = json.dumps(value or {}, sort_keys=True)
    metadata = instance.get("metadata") or {}
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)) and not isinstance(
                value, bool
            ):
                name = metadata_env_name(str(key))
                if name not in _RESERVED:
                    os.environ[name] = str(value)
            elif isinstance(value, bool):
                name = metadata_env_name(str(key))
                if name not in _RESERVED:
                    os.environ[name] = "true" if value else "false"
    lib_path = instance.get("world_lib_path")
    if lib_path and os.path.isdir(lib_path) and lib_path not in sys.path:
        sys.path.insert(0, lib_path)


def synthetic_instance_from_env() -> dict[str, Any] | None:
    """The active instance as seen from inside a child, or ``None`` when there is none."""
    instance_id = os.environ.get(ENV_INSTANCE_ID)
    if not instance_id:
        return None
    result: dict[str, Any] = {
        key: os.environ.get(env_name) for key, env_name in _ENV_BY_KEY.items()
    }
    for key, env_name in _JSON_BY_KEY.items():
        raw = os.environ.get(env_name)
        empty = None if key == "connection" else {}
        try:
            result[key] = json.loads(raw) if raw else empty
        except json.JSONDecodeError:
            result[key] = empty
    return result
