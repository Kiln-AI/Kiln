# Kiln AI

Coming soon...

|         |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CI      | [![Build and Test](https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml) [![Format and Lint](https://github.com/Kiln-AI/kiln/actions/workflows/format_and_lint.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/format_and_lint.yml) [![Desktop Apps Build](https://github.com/Kiln-AI/kiln/actions/workflows/build_desktop.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/build_desktop.yml) [![Web UI Build](https://github.com/Kiln-AI/kiln/actions/workflows/web_format_lint_build.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/web_format_lint_build.yml) ![badge](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/scosman/57742c1b1b60d597a6aba5d5148d728e/raw/test_count_kiln.json) |
| Package | [![PyPI - Version](https://img.shields.io/pypi/v/kiln-ai.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/kiln-ai/) [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kiln-ai.svg?logo=python&label=Python&logoColor=gold)](https://pypi.org/project/kiln-ai/)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Meta    | [![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/) [![types - Mypy](https://img.shields.io/badge/types-pyright-blue.svg)](https://github.com/microsoft/pyright)                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

## Development

Running the desktop app without building executable:

`python -m app.desktop.desktop`

Run the API server with auto-reload for development:

`AUTO_RELOAD=true python -m libs.studio.kiln_studio.server`

Run the web UI with auto-reload for development (Node and `npm install` required):

In /app/web_ui: `npm run dev --`
