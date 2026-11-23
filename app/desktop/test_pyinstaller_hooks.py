import ast
import json
import runpy
import subprocess
import sys
from pathlib import Path, PurePosixPath

import _pyinstaller_hooks_contrib
from kiln_mcp_server import skill_files
from PyInstaller import HOMEPATH
from PyInstaller.building.build_main import discover_hook_directories
from PyInstaller.depend.analysis import HOOK_PRIORITY_USER_HOOKS, PyiModuleGraph
from PyInstaller.utils.hooks import collect_data_files

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


MCP_PROJECT_DIR = Path(__file__).parent.parent / "mcp"
MCP_HOOK = HOOKS_DIR / "hook-kiln_mcp_server.py"


def test_the_mcp_project_folder_is_not_a_package():
    # The build runs with `--paths=.` from `app/`; a regular package there
    # named `mcp` would shadow the MCP SDK in the frozen app.
    assert MCP_PROJECT_DIR.is_dir()
    assert not (MCP_PROJECT_DIR / "__init__.py").exists()


def test_the_kiln_mcp_server_hook_exists():
    assert MCP_HOOK.is_file()


def test_the_bundled_data_is_exactly_the_skill_tree():
    datas = runpy.run_path(str(MCP_HOOK))["datas"]
    bundled = set()
    for source, dest in datas:
        dest_path = PurePosixPath(Path(dest).as_posix())
        if dest_path.parts[:2] == ("kiln_mcp_server", "skill"):
            relative = dest_path.relative_to("kiln_mcp_server/skill")
            bundled.add((relative / Path(source).name).as_posix())
    assert bundled == set(skill_files.get_index().files)


def test_the_bundled_data_skips_hidden_names(tmp_path, monkeypatch):
    package = tmp_path / "hidden_names_pkg"
    for relative in (
        "__init__.py",
        "skill/SKILL.md",
        "skill/.DS_Store",
        "skill/.hidden/a.md",
        "skill/references/.x",
        ".top",
    ):
        (package / relative).parent.mkdir(parents=True, exist_ok=True)
        (package / relative).touch()
    monkeypatch.syspath_prepend(str(tmp_path))
    excludes = runpy.run_path(str(MCP_HOOK))["DATA_EXCLUDES"]

    datas = collect_data_files("hidden_names_pkg", excludes=excludes)

    assert [Path(source).relative_to(package).as_posix() for source, _ in datas] == [
        "skill/SKILL.md"
    ]
