# Kiln AI Server

[![PyPI - Version](https://img.shields.io/pypi/v/kiln-server.svg)](https://pypi.org/project/kiln-server)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kiln-server.svg)](https://pypi.org/project/kiln-server)

---

## About Kiln AI

Learn more about Kiln AI at [getkiln.ai](https://getkiln.ai)

This package is the Kiln AI server package. There is also a separate desktop application and python library package.

Github: [github.com/Kiln-AI/kiln](https://github.com/Kiln-AI/kiln)

## Installation

```console
pip install kiln_server
```

## API Docs

Our OpenApi docs: [https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.html](https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.html)

## Running the server

```console
python -m kiln_server.server
```

With auto-reload:

```console
AUTO_RELOAD=true python -m kiln_server.server
```

## Using the server in another FastAPI app

See server.py for examples, but you can connect individual API endpoints to your app like this:

```python
from kiln_server.project_api import connect_project_api

app = FastAPI()
connect_project_api(app)
```
