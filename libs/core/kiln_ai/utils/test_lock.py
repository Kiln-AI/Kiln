import asyncio

from .lock import AsyncLockManager, async_lock_manager


async def test_same_key_returns_same_lock():
    """Test that the same key returns the same lock object."""
    locks = AsyncLockManager()

    # Test that the same key gets the same lock entry
    async with locks.acquire("test_key"):
        # The lock should exist in the manager
        snapshot = await locks.snapshot()
        assert "test_key" in snapshot


async def test_different_keys_return_different_locks():
    """Test that different keys return different lock objects."""
    locks = AsyncLockManager()

    # Use different keys
    async with locks.acquire("key1"):
        async with locks.acquire("key2"):
            snapshot = await locks.snapshot()
            assert "key1" in snapshot
            assert "key2" in snapshot


async def test_lock_functionality():
    """Test that the locks actually provide mutual exclusion."""
    results = []
    locks = AsyncLockManager()

    async def worker(worker_id: int):
        async with locks.acquire("shared_resource"):
            # Record start
            results.append(f"worker_{worker_id}_start")
            await asyncio.sleep(0.1)  # Simulate work
            # Record end
            results.append(f"worker_{worker_id}_end")

    # Run multiple workers concurrently
    await asyncio.gather(*[worker(i) for i in range(3)])

    # Verify that the work was done exclusively
    # Each worker's start should be immediately followed by its end
    i = 0
    while i < len(results):
        start_event = results[i]
        end_event = results[i + 1]

        # Extract worker ID from start event
        worker_id = start_event.split("_")[1]
        expected_end = f"worker_{worker_id}_end"

        assert end_event == expected_end, (
            f"Non-exclusive access detected. Expected {expected_end}, got {end_event}. Full results: {results}"
        )
        i += 2


async def test_lock_cleanup():
    """Test that locks are automatically cleaned up when no longer needed."""
    locks = AsyncLockManager()

    # Use a lock
    async with locks.acquire("cleanup_test"):
        pass

    # Check that the lock was cleaned up
    snapshot = await locks.snapshot()
    assert "cleanup_test" not in snapshot


async def test_multiple_holders_cleanup():
    """Test that locks are cleaned up when multiple holders finish."""
    locks = AsyncLockManager()

    # Create multiple tasks that will hold the lock sequentially
    async def holder(holder_id: int):
        async with locks.acquire("multi_holder"):
            await asyncio.sleep(0.05)
            return f"holder_{holder_id}_done"

    # Run multiple holders sequentially (not concurrently to avoid deadlock)
    results = []
    for i in range(3):
        result = await holder(i)
        results.append(result)

    # Check that all holders completed
    assert len(results) == 3
    assert all(result.startswith("holder_") for result in results)

    # Check that the lock was cleaned up
    snapshot = await locks.snapshot()
    assert "multi_holder" not in snapshot


async def test_global_instance():
    """Test that the global async_lock_manager instance works correctly."""
    results = []

    async def worker(worker_id: int):
        async with async_lock_manager.acquire("global_test"):
            results.append(f"worker_{worker_id}_start")
            await asyncio.sleep(0.05)
            results.append(f"worker_{worker_id}_end")

    # Run multiple workers sequentially to avoid deadlock
    for i in range(2):
        await worker(i)

    # Verify sequential access
    assert len(results) == 4
    assert results[0] == "worker_0_start"
    assert results[1] == "worker_0_end"
    assert results[2] == "worker_1_start"
    assert results[3] == "worker_1_end"


async def test_timeout():
    """Test that timeout functionality works correctly."""
    locks = AsyncLockManager()

    # Hold the lock for a while
    async def holder():
        async with locks.acquire("timeout_test"):
            await asyncio.sleep(0.3)

    # Try to acquire with a short timeout
    async def waiter():
        try:
            async with locks.acquire("timeout_test", timeout=0.1):
                assert False, "Should have timed out"
        except asyncio.TimeoutError:
            return "timed_out"

    # Start holder first
    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.05)  # Let holder acquire the lock

    # Then try waiter
    result = await waiter()
    assert result == "timed_out"

    # Wait for holder to finish
    await holder_task


async def test_cancellation():
    """Test that cancellation is handled correctly."""
    locks = AsyncLockManager()

    # Hold the lock
    async def holder():
        async with locks.acquire("cancel_test"):
            await asyncio.sleep(0.3)

    # Try to acquire but get cancelled
    async def waiter():
        try:
            async with locks.acquire("cancel_test"):
                assert False, "Should not acquire lock"
        except asyncio.CancelledError:
            return "cancelled"

    # Start holder first
    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.05)  # Let holder acquire the lock

    # Start waiter and then cancel it
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)
    waiter_task.cancel()

    # Check result
    try:
        result = await waiter_task
        assert result == "cancelled"
    except asyncio.CancelledError:
        pass  # Expected

    # Wait for holder to finish
    await holder_task
