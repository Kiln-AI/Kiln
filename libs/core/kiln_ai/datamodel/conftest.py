import sys
import threading
import time
from collections.abc import Callable

import pytest

RACE_JOIN_TIMEOUT_SECONDS = 60.0


@pytest.fixture
def run_racing_threads() -> Callable[[list[threading.Thread]], None]:
    """Starts and joins threads with a tiny switch interval.

    The interpreter then changes threads often enough to hit race windows in a short run.
    The threads run as daemons and share one join deadline, so a stalled one fails the
    test instead of hanging the run.
    """

    def run(threads: list[threading.Thread]) -> None:
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            for thread in threads:
                thread.daemon = True
                thread.start()
            deadline = time.monotonic() + RACE_JOIN_TIMEOUT_SECONDS
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))
        finally:
            sys.setswitchinterval(switch_interval)
        stalled = [thread.name for thread in threads if thread.is_alive()]
        if stalled:
            pytest.fail(
                f"Threads still running after {RACE_JOIN_TIMEOUT_SECONDS}s: {stalled}"
            )

    return run
