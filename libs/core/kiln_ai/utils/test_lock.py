import asyncio

from .lock import asyncio_mutex


async def test_same_key_returns_same_lock():
    """Test that the same key returns the same lock object."""
    lock1 = asyncio_mutex("test_key")
    lock2 = asyncio_mutex("test_key")

    # Should be the exact same object
    assert lock1 is lock2
    assert id(lock1) == id(lock2)


async def test_different_keys_return_different_locks():
    """Test that different keys return different lock objects."""
    lock1 = asyncio_mutex("key1")
    lock2 = asyncio_mutex("key2")

    # Should be different objects
    assert lock1 is not lock2
    assert id(lock1) != id(lock2)


async def test_lock_functionality():
    """Test that the locks actually provide mutual exclusion."""
    results = []

    async def worker(worker_id: int):
        async with asyncio_mutex("shared_resource"):
            # Record start
            results.append(f"worker_{worker_id}_start")
            await asyncio.sleep(0.2)  # Simulate work
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
            f"Non-exclusive access detected. Expected {expected_end}, got {expected_end}. Full results: {results}"
        )
        i += 2


async def test_lock_registry_persistence():
    """Test that the lock registry persists locks across multiple function calls."""
    # Get a lock for a key
    lock1 = asyncio_mutex("persistent_key")

    # Do some other operations
    _ = asyncio_mutex("other_key1")
    _ = asyncio_mutex("other_key2")

    # Get the same key again
    lock2 = asyncio_mutex("persistent_key")

    # Should be the same object
    assert lock1 is lock2
