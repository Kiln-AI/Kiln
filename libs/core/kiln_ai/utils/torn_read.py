"""Read project files again when a read met a file that another writer was saving.

`KilnBaseModel.save_to_file` truncates a file and then writes it in place. A scan
that runs in a worker thread can open the file between the two steps and read an
empty or partial document. `load_from_file` then raises `json.JSONDecodeError`.
The writer finishes in milliseconds, so one more read after a short delay gets the
full file. All other errors are real errors, and the helper does not retry them.

An atomic `save_to_file` (write a temporary file, then `os.replace`) removes the
cause. Until then, the threaded scans that can meet a concurrent save use this.
"""

import asyncio
import json
import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

TORN_READ_RETRY_DELAY_SECONDS = 0.1


def retry_on_torn_read(read: Callable[[], T]) -> T:
    """Call `read`. If it raises `json.JSONDecodeError`, wait
    `TORN_READ_RETRY_DELAY_SECONDS` and call it one more time.

    A second `json.JSONDecodeError` propagates: the file is not partly written but
    damaged, or the writer is very slow. Blocking: call it in a worker thread.
    """
    try:
        return read()
    except json.JSONDecodeError as e:
        logger.info("A project file was not readable (%s). Reading it again.", e)
        time.sleep(TORN_READ_RETRY_DELAY_SECONDS)
        return read()


async def to_thread_retrying_torn_read(read: Callable[[], T]) -> T:
    """Run `read` in a worker thread through `retry_on_torn_read`."""

    def retrying() -> T:
        return retry_on_torn_read(read)

    return await asyncio.to_thread(retrying)
