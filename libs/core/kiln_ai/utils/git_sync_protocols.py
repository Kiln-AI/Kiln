from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

SaveContext = Callable[[], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def default_save_context() -> AsyncIterator[None]:
    yield


class AtomicWriteCapable(Protocol):
    def atomic_write(self, context: str) -> AbstractAsyncContextManager[None]: ...
