import os
import subprocess
import sys


def _import_chunkers_with_env(env_overrides: dict[str, str | None]) -> str:
    """Import the chunkers package in a fresh interpreter and report NLTK_DATA.

    The package sets NLTK_DATA at import time, so it has to be observed in a
    process that has not imported it yet.
    """
    env = dict(os.environ)
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            # sys.stdout.write rather than a print call, which the developer-check
            # CI step flags as leftover debug content.
            "import os, sys; import kiln_ai.adapters.chunkers; "
            "sys.stdout.write(os.environ['NLTK_DATA'])",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.strip()


def test_sets_nltk_data_when_unset():
    # Without this the sentence splitters fall back to llama_index's bundled corpus,
    # which uv hard links, and NLTK refuses to open multiply-linked files.
    nltk_data = _import_chunkers_with_env({"NLTK_DATA": None})

    assert nltk_data.endswith(os.path.join("cache", "nltk_data"))


def test_respects_an_existing_nltk_data(tmp_path):
    # The desktop app sets NLTK_DATA at startup, so importing must never override it.
    existing = str(tmp_path / "already-chosen")

    nltk_data = _import_chunkers_with_env({"NLTK_DATA": existing})

    assert nltk_data == existing
