import asyncio
import logging
import random
from dataclasses import dataclass
from typing import AsyncGenerator, Awaitable, Callable, Generic, List, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Progress:
    complete: int
    total: int
    errors: int


class AsyncJobRunnerObserver(Generic[T]):
    async def on_error(self, job: T, error: Exception):
        """
        Called when a job raises an unhandled exception.
        """
        pass

    async def on_success(self, job: T):
        """
        Called when a job completes successfully.
        """
        pass

    async def on_job_start(self, job: T):
        """
        Called when a job starts.
        """
        pass


class AsyncJobRunner(Generic[T]):
    def __init__(
        self,
        jobs: List[T],
        run_job_fn: Callable[[T], Awaitable[bool]],
        concurrency: int = 1,
        observers: List[AsyncJobRunnerObserver[T]] | None = None,
    ):
        if concurrency < 1:
            raise ValueError("concurrency must be ≥ 1")
        self.concurrency = concurrency
        self.jobs = jobs
        self.run_job_fn = run_job_fn
        self.observers = observers or []

    async def notify_error(self, job: T, error: Exception):
        for observer in self.observers:
            await observer.on_error(job, error)

    async def notify_success(self, job: T):
        for observer in self.observers:
            await observer.on_success(job)

    async def notify_job_start(self, job: T):
        for observer in self.observers:
            await observer.on_job_start(job)

    async def run(self) -> AsyncGenerator[Progress, None]:
        """
        Runs the jobs with parallel workers and yields progress updates.
        """
        complete = 0
        errors = 0
        total = len(self.jobs)

        # Send initial status
        yield Progress(complete=complete, total=total, errors=errors)

        worker_queue: asyncio.Queue[T] = asyncio.Queue()
        for job in self.jobs:
            worker_queue.put_nowait(job)

        # simple status queue to return progress. True=success, False=error
        status_queue: asyncio.Queue[bool] = asyncio.Queue()

        workers = []
        for _ in range(self.concurrency):
            task = asyncio.create_task(
                self._run_worker(worker_queue, status_queue, self.run_job_fn),
            )
            workers.append(task)

        try:
            # Send status updates until workers are done, and they are all sent
            while not status_queue.empty() or not all(
                worker.done() for worker in workers
            ):
                try:
                    # Use timeout to prevent hanging if all workers complete
                    # between our while condition check and get()
                    success = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                    if success:
                        complete += 1
                    else:
                        errors += 1

                    yield Progress(
                        complete=complete,
                        total=total,
                        errors=errors,
                    )
                except asyncio.TimeoutError:
                    # Timeout is expected, just continue to recheck worker status
                    # Don't love this but beats sentinels for reliability
                    continue
        finally:
            # Cancel outstanding workers on early exit or error
            for w in workers:
                w.cancel()

            # These are redundant, but keeping them will catch async errors
            await asyncio.gather(*workers)
            await worker_queue.join()

    async def _run_worker(
        self,
        worker_queue: asyncio.Queue[T],
        status_queue: asyncio.Queue[bool],
        run_job_fn: Callable[[T], Awaitable[bool]],
    ):
        while True:
            try:
                job = worker_queue.get_nowait()
            except asyncio.QueueEmpty:
                # worker can end when the queue is empty
                break

            try:
                await self.notify_job_start(job)
                result = await run_job_fn(job)
                await self.notify_success(job)
            except Exception as e:
                logger.error("Job failed to complete", exc_info=True)
                await self.notify_error(job, e)
                result = False

            try:
                await status_queue.put(result)
            except Exception:
                logger.error("Failed to enqueue status for job", exc_info=True)
            finally:
                # Always mark the dequeued task as done, even on exceptions
                worker_queue.task_done()
