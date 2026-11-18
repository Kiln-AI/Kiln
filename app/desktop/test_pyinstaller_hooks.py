import ast
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parent / "pyinstaller_hooks"
NLTK_HOOK = HOOKS_DIR / "rthooks" / "pyi_rth_nltk_data_path.py"


def test_rthooks_dat_registers_the_nltk_hook():
    rthooks = ast.literal_eval((HOOKS_DIR / "rthooks.dat").read_text())
    assert rthooks == {"nltk": [NLTK_HOOK.name]}
    assert NLTK_HOOK.is_file()


def test_nltk_hook_adds_bundled_data_path_without_importing_nltk(tmp_path):
    probe = (
        "import runpy, sys\n"
        f"sys._MEIPASS = {str(tmp_path)!r}\n"
        f"runpy.run_path({str(NLTK_HOOK)!r})\n"
        "sys.stdout.write(f\"{'nltk' in sys.modules}\\n\")\n"
        "import nltk\n"
        "sys.stdout.write(f'{nltk.data.path[0]}\\n')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert result.stdout.splitlines() == ["False", str(tmp_path / "nltk_data")]
