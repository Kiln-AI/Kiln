# Kiln AI REST Server

[![PyPI - Version](https://img.shields.io/pypi/v/kiln-server.svg)](https://pypi.org/project/kiln-server)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kiln-server.svg)](https://pypi.org/project/kiln-server)

---

## About Kiln AI

Learn more about Kiln AI at [kiln.tech](https://kiln.tech)

This package is the Kiln AI server package. There is also a separate desktop application and python library package.

Github: [github.com/Kiln-AI/kiln](https://github.com/Kiln-AI/kiln)

## Installation

We suggest installing with uv:

```console
uv tool install kiln_server
```

## REST API Docs

Our OpenAPI docs: [https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.html](https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.html)

## Running the server

After installing, run:

```console
kiln_server
```

## kiln_server Command Options

```
usage: kiln_server [-h] [--host HOST] [--port PORT] [--log-level LOG_LEVEL] [--auto-reload AUTO_RELOAD]

Run the Kiln AI REST Server.

options:
  -h, --help            show this help message and exit
  --host HOST           Host for network transports.
  --port PORT           Port for network transports.
  --log-level LOG_LEVEL
                        Log level for the server when using network transports.
  --auto-reload AUTO_RELOAD
                        Enable auto-reload for the server.
```

## Using the server in another FastAPI app

See server.py for examples, but you can connect individual API endpoints to your app like this:

```python
from kiln_server.project_api import connect_project_api

app = FastAPI()
connect_project_api(app)
```

The `kiln_server` app turns on the `kiln_ai` datamodel cache while it runs (`default_lifespan` in server.py). With `KILN_DISABLE_MODEL_CACHE=true` set, it calls `ModelCache.shared().disable()` instead, and the cache stays off for the whole process; `kiln_mcp` does the same. An app that connects the endpoints itself starts with the cache off, so every request reads and validates its records from disk again. To keep loaded records in memory between requests, call `set_model_cache_enabled(True)` from `kiln_ai.datamodel` when your app starts, for example in its `lifespan`. To also honour `KILN_DISABLE_MODEL_CACHE` as `kiln_server` does, call `apply_model_cache_setting(disable=Config.shared().disable_model_cache)` from `kiln_ai.datamodel.model_cache` instead.

## Kiln MCP Server

Also included in this package is a MCP server for serving Kiln tools.

See [it's README](./kiln_server/mcp/README.md) for details.
