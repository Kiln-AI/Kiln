import asyncio
from typing import Dict

# dict is not thread-safe so this can only work as expected in a single-threaded environment:
# - asyncio.Lock is tied to the event loop it was created in, and cannot be used from other threads
# - thread creation is not atomic, so we would need a thread lock when creating a new lock
_lock_registry: Dict[str, asyncio.Lock] = {}


def loop_local_mutex(key: str) -> asyncio.Lock:
    if key not in _lock_registry:
        _lock_registry[key] = asyncio.Lock()
    return _lock_registry[key]
