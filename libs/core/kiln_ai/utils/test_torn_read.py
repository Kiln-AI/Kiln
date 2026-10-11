import json
import threading

import pytest

from kiln_ai.utils import torn_read
from kiln_ai.utils.torn_read import retry_on_torn_read, to_thread_retrying_torn_read


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(torn_read, "TORN_READ_RETRY_DELAY_SECONDS", 0)


def _reader(failures: list[Exception]):
    calls: list[int] = []

    def read() -> str:
        calls.append(1)
        if failures:
            raise failures.pop(0)
        return "full file"

    return read, calls


def _torn() -> json.JSONDecodeError:
    # What json.loads raises on an empty file: the writer truncated it, and has
    # not written the new content yet.
    return json.JSONDecodeError("Expecting value", "", 0)


def test_returns_the_result_with_no_retry_when_the_read_works():
    read, calls = _reader([])
    assert retry_on_torn_read(read) == "full file"
    assert len(calls) == 1


def test_reads_again_after_a_torn_read():
    read, calls = _reader([_torn()])
    assert retry_on_torn_read(read) == "full file"
    assert len(calls) == 2


def test_raises_when_the_second_read_is_torn_too():
    read, calls = _reader([_torn(), _torn()])
    with pytest.raises(json.JSONDecodeError):
        retry_on_torn_read(read)
    assert len(calls) == 2


def test_does_not_retry_other_errors():
    # A ValueError that is not a JSONDecodeError is a real error, for example a
    # model that fails validation. Reading again cannot fix it.
    read, calls = _reader([ValueError("bad model")])
    with pytest.raises(ValueError, match="bad model"):
        retry_on_torn_read(read)
    assert len(calls) == 1


def test_a_real_empty_file_is_the_error_it_retries(tmp_path):
    path = tmp_path / "task_run.kiln"
    path.write_text("")
    with pytest.raises(json.JSONDecodeError):
        json.loads(path.read_text())


@pytest.mark.asyncio
async def test_to_thread_variant_reads_again_in_a_worker_thread():
    loop_thread = threading.get_ident()
    threads: list[int] = []
    failures = [_torn()]

    def read() -> str:
        threads.append(threading.get_ident())
        if failures:
            raise failures.pop(0)
        return "full file"

    assert await to_thread_retrying_torn_read(read) == "full file"
    assert len(threads) == 2
    assert loop_thread not in threads
