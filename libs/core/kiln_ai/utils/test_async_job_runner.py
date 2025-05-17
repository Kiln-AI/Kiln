from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from kiln_ai.utils.async_job_runner import AsyncJobRunner, Progress


@pytest.mark.parametrize("concurrency", [0, -1, -25])
def test_invalid_concurrency_raises(concurrency):
    with pytest.raises(ValueError):
        AsyncJobRunner(concurrency=concurrency)


# Test with and without concurrency
@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_status_updates(concurrency):
    job_count = 50
    jobs = [{"id": i} for i in range(job_count)]

    runner = AsyncJobRunner(concurrency=concurrency)

    # fake run_job that succeeds
    mock_run_job_success = AsyncMock(return_value=True)

    # Expect the status updates in order, and 1 for each job
    expected_completed_count = 0
    async for progress in runner.run(jobs, mock_run_job_success):
        assert progress.complete == expected_completed_count
        expected_completed_count += 1
        assert progress.errors == 0
        assert progress.total == job_count

    # Verify last status update was complete
    assert expected_completed_count == job_count + 1

    # Verify run_job was called for each job
    assert mock_run_job_success.call_count == job_count

    # Verify run_job was called with the correct arguments
    for i in range(job_count):
        mock_run_job_success.assert_any_await(jobs[i])


# Test with and without concurrency
@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_status_updates_empty_job_list(concurrency):
    empty_job_list = []

    runner = AsyncJobRunner(concurrency=concurrency)

    # fake run_job that succeeds
    mock_run_job_success = AsyncMock(return_value=True)

    updates: List[Progress] = []
    async for progress in runner.run(empty_job_list, mock_run_job_success):
        updates.append(progress)

    # Verify last status update was complete
    assert len(updates) == 1

    assert updates[0].complete == 0
    assert updates[0].errors == 0
    assert updates[0].total == 0

    # Verify run_job was called for each job
    assert mock_run_job_success.call_count == 0


@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_all_failures(concurrency):
    job_count = 50
    jobs = [{"id": i} for i in range(job_count)]

    runner = AsyncJobRunner(concurrency=concurrency)

    # fake run_job that fails
    mock_run_job_failure = AsyncMock(return_value=False)

    # Expect the status updates in order, and 1 for each job
    expected_error_count = 0
    async for progress in runner.run(jobs, mock_run_job_failure):
        assert progress.complete == 0
        assert progress.errors == expected_error_count
        expected_error_count += 1
        assert progress.total == job_count

    # Verify last status update was complete
    assert expected_error_count == job_count + 1

    # Verify run_job was called for each job
    assert mock_run_job_failure.call_count == job_count

    # Verify run_job was called with the correct arguments
    for i in range(job_count):
        mock_run_job_failure.assert_any_await(jobs[i])


@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_partial_failures(concurrency):
    job_count = 50
    jobs = [{"id": i} for i in range(job_count)]

    # we want to fail on some jobs and succeed on others
    jobs_to_fail = set([0, 2, 4, 6, 8, 20, 25])

    runner = AsyncJobRunner(concurrency=concurrency)

    # fake run_job that fails
    mock_run_job_partial_success = AsyncMock(
        # return True for jobs that should succeed
        side_effect=lambda job: job["id"] not in jobs_to_fail
    )

    # Expect the status updates in order, and 1 for each job
    async for progress in runner.run(jobs, mock_run_job_partial_success):
        assert progress.total == job_count

    # Verify last status update was complete
    expected_error_count = len(jobs_to_fail)
    expected_success_count = len(jobs) - expected_error_count
    assert progress.errors == expected_error_count
    assert progress.complete == expected_success_count

    # Verify run_job was called for each job
    assert mock_run_job_partial_success.call_count == job_count

    # Verify run_job was called with the correct arguments
    for i in range(job_count):
        mock_run_job_partial_success.assert_any_await(jobs[i])


@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_partial_raises(concurrency):
    job_count = 50
    jobs = [{"id": i} for i in range(job_count)]

    runner = AsyncJobRunner(concurrency=concurrency)

    ids_to_fail = set([10, 25])

    def failure_fn(job):
        if job["id"] in ids_to_fail:
            raise Exception("job failed unexpectedly")
        return True

    # fake run_job that fails
    mock_run_job_partial_success = AsyncMock(side_effect=failure_fn)

    # generate all the values we expect to see in progress updates
    complete_values_expected = set([i for i in range(job_count - len(ids_to_fail) + 1)])
    errors_values_expected = set([i for i in range(len(ids_to_fail) + 1)])

    # keep track of all the updates we see
    updates: List[Progress] = []

    # we keep track of the progress values we have actually seen
    complete_values_actual = set()
    errors_values_actual = set()

    # Expect the status updates in order, and 1 for each job
    async for progress in runner.run(jobs, mock_run_job_partial_success):
        updates.append(progress)
        complete_values_actual.add(progress.complete)
        errors_values_actual.add(progress.errors)

        assert progress.total == job_count

    # complete values should be all the jobs, except for the ones that failed
    assert progress.complete == job_count - len(ids_to_fail)

    # check that the actual updates and expected updates are equivalent sets
    assert complete_values_actual == complete_values_expected
    assert errors_values_actual == errors_values_expected

    # we should have seen one update for each job, plus one for the initial status update
    assert len(updates) == job_count + 1


@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_job_runner_cancelled(concurrency):
    runner = AsyncJobRunner(concurrency=concurrency)
    jobs = [{"id": i} for i in range(10)]

    with patch.object(
        runner,
        "_run_worker",
        side_effect=Exception("run_worker raised an exception"),
    ):
        # if an exception is raised in the task, we should see it bubble up
        with pytest.raises(Exception, match="run_worker raised an exception"):
            async for _ in runner.run(jobs, AsyncMock(return_value=True)):
                pass
