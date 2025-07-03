from unittest.mock import patch

import litellm
import pytest
from dotenv import load_dotenv
from kiln_ai.utils.config import Config


@pytest.fixture(autouse=True)
def _clear_httpx_clients() -> None:
    litellm.in_memory_llm_clients_cache.flush_cache()


@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv()


# mock out the settings path so we don't clobber the user's actual settings during tests
@pytest.fixture(autouse=True)
def use_temp_settings_dir(tmp_path):
    with patch.object(
        Config, "settings_path", return_value=str(tmp_path / "settings.yaml")
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    from kiln_ai.utils.logging import setup_litellm_logging

    setup_litellm_logging("test_model_calls.log")
    yield


def pytest_addoption(parser):
    parser.addoption(
        "--runpaid",
        action="store_true",
        default=False,
        help="run tests that make paid API calls",
    )
    parser.addoption(
        "--runsinglewithoutchecks",
        action="store_true",
        default=False,
        help="if testing a single test, don't check for skips like runpaid",
    )
    parser.addoption(
        "--ollama",
        action="store_true",
        default=False,
        help="run tests that use ollama server",
    )


def is_single_manual_test(config, items) -> bool:
    # Check if we're running manually (eg, in vscode)
    if not config.getoption("--runsinglewithoutchecks"):
        return False

    if len(items) == 1:
        return True
    if len(items) == 0:
        return False

    # Check if all of the items are the same prefix, expluding a.b.c[param]
    # This is still a 'single test' for the purposes of this flag
    prefix = items[0].name.split("[")[0] + "["
    for item in items:
        if not item.name.startswith(prefix):
            return False
    return True


def pytest_collection_modifyitems(config, items):
    # Always run test if it's a single test manually invoked
    if is_single_manual_test(config, items):
        return

    # Mark tests that use paid services as skipped unless --runpaid is passed
    if not config.getoption("--runpaid"):
        skip_paid = pytest.mark.skip(reason="need --runpaid option to run")
        for item in items:
            if "paid" in item.keywords:
                item.add_marker(skip_paid)

    # Mark tests that use ollama server as skipped unless --ollama is passed
    if not config.getoption("--ollama"):
        skip_ollama = pytest.mark.skip(reason="need --ollama option to run")
        for item in items:
            if "ollama" in item.keywords:
                item.add_marker(skip_ollama)
