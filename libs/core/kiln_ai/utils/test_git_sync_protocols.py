from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest

from kiln_ai.utils.git_sync_protocols import (
    AtomicWriteCapable,
    SaveContext,
    default_save_context,
)


@pytest.mark.asyncio
async def test_default_save_context_is_no_op():
    entered = False
    exited = False

    async with default_save_context():
        entered = True

    exited = True
    assert entered
    assert exited


@pytest.mark.asyncio
async def test_default_save_context_propagates_exceptions():
    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with default_save_context():
            raise Boom("nope")


def test_save_context_type_assignable():
    # The alias should be assignable with our default; this mostly protects the
    # public shape of the type during refactors.
    ctx: SaveContext = default_save_context
    assert callable(ctx)


@pytest.mark.asyncio
async def test_atomic_write_capable_structural_duck_typing():
    entered_with_context: str | None = None

    class Fake:
        def atomic_write(self, context: str) -> AbstractAsyncContextManager[None]:
            @asynccontextmanager
            async def cm() -> AsyncIterator[None]:
                nonlocal entered_with_context
                entered_with_context = context
                yield

            return cm()

    fake: AtomicWriteCapable = Fake()
    async with fake.atomic_write("x"):
        pass
    assert entered_with_context == "x"
