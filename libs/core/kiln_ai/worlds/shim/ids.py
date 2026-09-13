"""Seeded identifier generation.

A world that mints ids with `uuid4()` cannot be replayed. `Ids` draws from a `random.Random`
seeded from the fixture (or the world name, for a blank instance) and the caller's seed, so
the same fixture and seed produce the same id stream in any process, and two different
fixtures never collide on the same caller seed.
"""

from __future__ import annotations

import hashlib
import random
import uuid

from .errors import WorldBug


def instance_seed(source: str, caller_seed: bytes | int | None) -> bytes:
    """Derive an instance's seed from what it is a copy of and what the caller asked for."""
    if caller_seed is None:
        seed_bytes = b"default"
    elif isinstance(caller_seed, bool):
        raise WorldBug("seed must be bytes or an int, not a bool")
    elif isinstance(caller_seed, int):
        if not 0 <= caller_seed < 1 << 64:
            raise WorldBug(
                f"an int seed must fit in eight bytes (0 to 2**64 - 1), got {caller_seed}"
            )
        seed_bytes = caller_seed.to_bytes(8, "big")
    elif isinstance(caller_seed, (bytes, bytearray)):
        seed_bytes = bytes(caller_seed)
    else:
        raise WorldBug(
            f"seed must be bytes, an int or None, got {type(caller_seed).__name__}"
        )
    return hashlib.sha256(source.encode("utf-8") + b"\0" + seed_bytes).digest()


class Ids:
    def __init__(self, seed: bytes) -> None:
        self.seed = seed
        self.random = random.Random(int.from_bytes(seed, "big"))

    def uuid(self) -> str:
        return str(uuid.UUID(int=self.random.getrandbits(128), version=4))
