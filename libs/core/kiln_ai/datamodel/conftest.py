import sys
import threading
from collections.abc import Callable

import pytest


@pytest.fixture
def run_racing_threads() -> Callable[[list[threading.Thread]], None]:
    """Starts and joins threads with a tiny switch interval.

    The interpreter then changes threads often enough to hit race windows in a short run.
    """

    def run(threads: list[threading.Thread]) -> None:
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            sys.setswitchinterval(switch_interval)

    return run
