import importlib
import os
import runpy
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.desktop.dev_env import set_dev_env_vars

REPO_ROOT = Path(__file__).resolve().parents[2]

DEV_ENV_VARS = ("KILN_SKIP_REMOTE_MODEL_LIST", "DEBUG_EVENT_LOOP", "KILN_DEV_MODE")

# Run in a subprocess: an in-process check can't tell what dev_server imported
# from what the test session had already imported.
LAUNCHER_PROBE = """
import os
import sys

import app.desktop.dev_server  # noqa: F401

assert "app.desktop.desktop_server" not in sys.modules, "launcher imported the app tree"
assert "app.desktop.dev_app" not in sys.modules, "launcher imported the app tree"
assert os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] == "true"
assert os.environ["DEBUG_EVENT_LOOP"] == "true"
assert os.environ["KILN_DEV_MODE"] == "true"
"""


@pytest.fixture
def run_dev_server_main():
    """Runs dev_server.py as __main__, with everything it launches stubbed out.

    The module body writes to the real process environment (the dev env vars, and
    KILN_LOCAL_API_PORT), which anything else running in this worker would
    otherwise inherit — hence the patch.dict wrapping the whole test.
    """
    with patch.dict(os.environ):

        def _run():
            with (
                patch("uvicorn.run") as mock_uvicorn_run,
                patch(
                    "app.desktop.util.resource_limits.setup_resource_limits"
                ) as mock_setup_resource_limits,
                patch("kiln_ai.utils.config.Config.shared") as mock_shared_config,
            ):
                mock_shared_config.return_value.kiln_local_api_host = "127.0.0.1"
                mock_shared_config.return_value.kiln_local_api_port = 8757
                runpy.run_module("app.desktop.dev_server", run_name="__main__")
                return mock_uvicorn_run, mock_setup_resource_limits

        yield _run


@pytest.fixture
def env_when_app_built():
    """Stubs out make_app, and captures the environment dev_app.py imports it in.

    The stub snapshots the environment when dev_app.py looks `make_app` up — at its
    import statement, not at the call — so a `set_dev_env_vars()` that drifted below
    that import fails this too, which is the whole reason for the file's noqa.
    """
    captured_env = {}

    class EnvCapturingStub(types.ModuleType):
        def __getattr__(self, name):
            if name != "make_app":
                raise AttributeError(name)
            captured_env.update(os.environ)
            return lambda: MagicMock(name="fastapi_app")

    desktop_package = sys.modules["app.desktop"]
    previously_imported = getattr(desktop_package, "dev_app", None)

    # patch.dict restores each dict wholesale, so the stub, the dev_app module the
    # test imports, and the env vars that import sets all go away with the test.
    with (
        patch.dict(
            sys.modules,
            {
                "app.desktop.desktop_server": EnvCapturingStub(
                    "app.desktop.desktop_server"
                )
            },
        ),
        patch.dict(os.environ),
    ):
        sys.modules.pop("app.desktop.dev_app", None)
        for env_var in DEV_ENV_VARS:
            os.environ.pop(env_var, None)
        yield captured_env

    # Importing a submodule also binds it on its package, which patch.dict does not
    # cover: without this, `from app.desktop import dev_app` would find the module
    # built with the stub.
    if previously_imported is None:
        vars(desktop_package).pop("dev_app", None)
    else:
        desktop_package.dev_app = previously_imported


def test_launcher_does_not_import_the_app_tree():
    # The point of the dev_app split: importing the app tree is the slow part of a
    # start, and the launcher paying it too made every start twice as long.
    result = subprocess.run(
        [sys.executable, "-c", LAUNCHER_PROBE],
        cwd=REPO_ROOT,
        # Without stripping these the probe's env assertions pass on an inherited
        # value — conftest's autouse fixture exports one of them for every test.
        env={k: v for k, v in os.environ.items() if k not in DEV_ENV_VARS},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_serves_the_app_from_the_dev_app_module(run_dev_server_main):
    mock_uvicorn_run, _ = run_dev_server_main()

    # An import string, not an app object, so the reload worker builds the app.
    assert mock_uvicorn_run.call_args.args == ("app.desktop.dev_app:dev_app",)


def test_uvicorn_run_options(run_dev_server_main):
    mock_uvicorn_run, mock_setup_resource_limits = run_dev_server_main()

    assert mock_uvicorn_run.call_args.kwargs == {
        "host": "127.0.0.1",
        "port": 8757,
        "reload": True,
        "reload_delay": 0.1,
        "timeout_graceful_shutdown": 1,
    }
    mock_setup_resource_limits.assert_called_once()


def test_kiln_port_is_exported_for_reload_workers(run_dev_server_main):
    os.environ["KILN_PORT"] = "1234"
    os.environ.pop("KILN_LOCAL_API_PORT", None)

    run_dev_server_main()

    assert os.environ["KILN_LOCAL_API_PORT"] == "1234"


def test_no_kiln_port_leaves_the_configured_port_alone(run_dev_server_main):
    os.environ.pop("KILN_PORT", None)
    os.environ.pop("KILN_LOCAL_API_PORT", None)

    run_dev_server_main()

    assert "KILN_LOCAL_API_PORT" not in os.environ


def test_launcher_sets_the_dev_env_vars(run_dev_server_main):
    for env_var in DEV_ENV_VARS:
        os.environ.pop(env_var, None)

    run_dev_server_main()

    assert [os.environ[env_var] for env_var in DEV_ENV_VARS] == ["true"] * 3


def test_dev_app_sets_dev_env_vars_before_importing_the_app(env_when_app_built):
    dev_app_module = importlib.import_module("app.desktop.dev_app")

    assert {var: env_when_app_built.get(var) for var in DEV_ENV_VARS} == dict.fromkeys(
        DEV_ENV_VARS, "true"
    )
    assert dev_app_module.dev_app is not None


def test_set_dev_env_vars_keeps_an_explicit_skip_remote_model_list():
    with patch.dict(os.environ):
        os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "false"

        set_dev_env_vars()

        assert os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] == "false"


@pytest.mark.parametrize("env_var", ["DEBUG_EVENT_LOOP", "KILN_DEV_MODE"])
def test_set_dev_env_vars_overrides_the_dev_mode_flags(env_var):
    # Deliberately unlike KILN_SKIP_REMOTE_MODEL_LIST above: running the dev server
    # is what these two describe, so the dev server decides them.
    with patch.dict(os.environ):
        os.environ[env_var] = "false"

        set_dev_env_vars()

        assert os.environ[env_var] == "true"
