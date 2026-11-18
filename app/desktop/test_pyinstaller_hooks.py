import ast
import json
import subprocess
import sys
from pathlib import Path

import _pyinstaller_hooks_contrib
from PyInstaller import HOMEPATH
from PyInstaller.building.build_main import discover_hook_directories
from PyInstaller.depend.analysis import HOOK_PRIORITY_USER_HOOKS, PyiModuleGraph

HOOKS_DIR = Path(__file__).parent / "pyinstaller_hooks"
NLTK_HOOK = HOOKS_DIR / "rthooks" / "pyi_rth_nltk_data_path.py"


def test_rthooks_dat_registers_the_nltk_hook():
    rthooks = ast.literal_eval((HOOKS_DIR / "rthooks.dat").read_text())
    assert rthooks == {"nltk": [NLTK_HOOK.name]}
    assert NLTK_HOOK.is_file()


def test_contrib_still_has_an_nltk_runtime_hook():
    # If this fails, contrib no longer imports nltk in every process, and the
    # Kiln hook may no longer be needed.
    contrib_rthooks = (
        Path(_pyinstaller_hooks_contrib.__file__).parent / "rthooks.dat"
    ).read_text()
    assert "nltk" in ast.literal_eval(contrib_rthooks)


def test_kiln_nltk_hook_replaces_the_contrib_hook():
    # The hook folders in the order `Analysis` gives them: `--additional-hooks-dir`
    # first, then the installed hook packages. PyInstaller keeps the first
    # runtime hook registered for a module. `_available_rthooks` is private,
    # but PyInstaller is pinned to an exact version.
    graph = PyiModuleGraph(
        HOMEPATH,
        user_hook_dirs=[
            (str(HOOKS_DIR), HOOK_PRIORITY_USER_HOOKS),
            *discover_hook_directories(),
        ],
    )
    assert graph._available_rthooks["nltk"] == [str(NLTK_HOOK)]


def _run_probe(code: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_nltk_hook_adds_bundled_data_path_without_importing_nltk(tmp_path):
    bundled = str(tmp_path / "nltk_data")
    without_hook = _run_probe(
        "import json, sys\n"
        "import nltk\n"
        "sys.stdout.write(json.dumps({'path': list(nltk.data.path)}))\n"
    )
    with_hook = _run_probe(
        "import copy, importlib, json, runpy, sys\n"
        f"sys._MEIPASS = {str(tmp_path)!r}\n"
        f"runpy.run_path({str(NLTK_HOOK)!r})\n"
        "nltk_at_start = 'nltk' in sys.modules\n"
        "import nltk\n"
        "path = list(nltk.data.path)\n"
        "filename = nltk.data.__spec__.loader.get_filename('nltk.data')\n"
        "copy.copy(nltk.data.__spec__.loader)\n"
        "importlib.reload(nltk.data)\n"
        "sys.stdout.write(json.dumps({\n"
        "    'nltk_at_start': nltk_at_start,\n"
        "    'path': path,\n"
        "    'filename': filename,\n"
        "    'path_after_reload': list(nltk.data.path),\n"
        "}))\n"
    )

    assert with_hook["nltk_at_start"] is False
    # The hook adds one folder, first, and keeps the default ones.
    assert with_hook["path"] == [bundled, *without_hook["path"]]
    # The wrapped loader forwards the methods it does not define.
    assert Path(with_hook["filename"]).name == "data.py"
    # A reload does not add the folder twice.
    assert with_hook["path_after_reload"].count(bundled) == 1
