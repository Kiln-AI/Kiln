import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

logger = logging.getLogger(__name__)


class TimingLogger:
    """A utility for timing code execution with context manager support."""

    def __init__(self, operation: str, name: str):
        """
        Initialize the timing logger.

        Args:
            name: Name/description of the operation being timed
            print_start: Whether to print when the operation starts
        """
        self.operation = operation
        self.name = name
        self.start_time: Optional[float] = None

    def timestamp(self) -> str:
        """Generate a timestamp string in ISO format."""
        return datetime.now().isoformat()

    def __enter__(self):
        """Enter the context manager and start timing."""
        self.start_time = time.time()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and print timing results."""
        if self.start_time is not None:
            show_time = os.getenv("KILN_SHOW_TIMING", "false")
            if show_time != "true":
                return

            duration = time.time() - self.start_time
            printable_operation = self.operation.replace("[", "_").replace("]", "_")
            printable_name = self.name.replace("[", "_").replace("]", "_")
            logger.warning(
                f"{self.timestamp()} timing_logger [{printable_operation}][{printable_name}][{duration:.2f}s]"
            )


@contextmanager
def time_operation(
    operation: str, name: str = "unknown"
) -> Generator[None, None, None]:
    """
    Context manager for timing operations.

    Args:
        type: Type/category of the operation being timed
        name: Name/description of the operation being timed

    Example:
        with time_operation("api", "my_task"):
            # Your code here
            time.sleep(1)
    """
    timing_logger = TimingLogger(operation, name)
    with timing_logger:
        yield
