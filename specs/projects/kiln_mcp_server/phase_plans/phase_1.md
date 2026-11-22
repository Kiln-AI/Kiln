---
status: complete
---

# Phase 1: The `app/mcp` project, the `/mcp` mount and `kiln_skill`

## Overview

Create the `kiln-mcp-server` workspace project under `app/mcp`, build a stateless Streamable HTTP MCP server named `kiln` in it, and mount it on the desktop app at `/mcp`. The server registers one tool in this phase, `kiln_skill`, which serves the skill tree shipped as package data. The tree is a placeholder: one hand-written `SKILL.md`. The phase also adds the PyInstaller hook that bundles the tree, the workspace wiring and the CI wiring.

Specs: [mcp_server_and_api_tool](../components/mcp_server_and_api_tool.md) sections 1–2, [skill_and_content](../components/skill_and_content.md) sections 2–3, [architecture](../architecture.md) section 9.1.

Left for phase 2, because they belong to `call_kiln_api`: the `api_app` and `tmp_root` arguments of `build_kiln_mcp_server`, the temp-file store and its purge in `KilnMcpServer.run()`, `default_tmp_root`, the `app/desktop/conftest.py` fixture, `local_api_base_url`, `CALL_KILN_API_DESCRIPTION`, and the route index. The model info parts of section 9.1 are phase 4.

## Steps

1. **Project.** `app/mcp/pyproject.toml` (no `app/mcp/__init__.py`):
   - `name = "kiln-mcp-server"`, `version = "1.2.1"`, `requires-python = ">=3.10"`, no licence field, no console script.
   - dependencies `kiln-ai`, `kiln-server`, `fastapi>=0.115.4`, `starlette>=1.3.1`, `httpx>=0.27.2`, `pydantic>=2.9.2`, `mcp>=1.30.0,<2`; `[tool.uv.sources]` for the two workspace members; `[tool.uv] exclude-newer = "7 days"`; hatchling build backend; `[tool.hatch.metadata] requires-python = ">=3.10"`.
   - Root `pyproject.toml`: `"app/mcp"` in workspace members, `kiln-mcp-server = { workspace = true }` source, `"kiln-mcp-server"` dependency. `app/desktop/pyproject.toml`: the same dependency and source. `uv lock` (`mcp` stays 1.30.0).
   - `.gitattributes`: `app/mcp/kiln_mcp_server/skill/** text eol=lf`.

2. **`kiln_mcp_server/texts.py`** (no imports): `WHAT_KILN_IS`, `SERVER_INSTRUCTIONS` (starts with `WHAT_KILN_IS`), `SKILL_TOOL_DESCRIPTION` (contains `WHAT_KILN_IS + "."`), `PATH_DESCRIPTION`, with the draft texts of server doc 2.4 and skill doc 2.2.

3. **`kiln_mcp_server/addresses.py`**:
   ```python
   def is_loopback_host(host: str) -> bool
   def transport_security_for(host: str) -> TransportSecuritySettings
   def app_origin(host: str, port: int) -> str
   ```
   Loopback bind: protection on, names `127.0.0.1`, `localhost`, `[::1]` plus the bound host when it is another loopback address; `allowed_hosts` = each name and `name:*`; `allowed_origins` = `http://name` and `http://name:*`. Any other bind: protection off. `app_origin` per server doc 2.3.

4. **`kiln_mcp_server/skill_files.py`** (no SDK import): `DEFAULT_ORIGIN`, `API_CATALOGUE_INDEX_PATH`, `SkillIndex`, `SkillPathError`, `build_index`, `get_index` (`lru_cache(maxsize=1)`), `resolve_path`, `read_file`, `strip_front_matter`, `apply_origin`, `read_skill`, and the error texts of skill doc 2.5 (`HINT`, `E_ABS`, `E_UP`, `E_SCHEME`, `E_SKILL`, `E_CTRL`, the not-found text). Path rules exactly as skill doc 2.4; the `api_docs` listing is shortened.

5. **`kiln_mcp_server/skill_tool.py`**: `SKILL_TOOL_NAME = "kiln_skill"` and
   ```python
   def register_skill_tool(mcp: FastMCP, *, bound_host: str, bound_port: int,
                           index: SkillIndex | None = None) -> None
   ```
   The tool has one optional `path` argument (alias `resource`), `meta={"anthropic/alwaysLoad": True}`, read-only/idempotent/closed-world annotations, `structured_output=False`, returns `CallToolResult` with one `TextContent`; `SkillPathError` becomes `isError=True` with its text. The file read runs in `asyncio.to_thread`. `index` lets tests pass a synthetic tree; the server passes none, so the cached shipped index is used.

6. **`kiln_mcp_server/server.py`**: `MCP_PATH`, `SERVER_NAME`, `McpEndpoint` (405 with `Allow: POST` for any non-POST `http` request; `_git_sync_no_write_lock = True`), `KilnMcpServer` (`asgi_app`, `run()` enters the session manager), `_preserve_root_logging()`, and
   ```python
   def build_kiln_mcp_server(*, app_version: str, host: str, port: int) -> KilnMcpServer
   ```
   following server doc 2.1 steps 1–3, 5 (skill tool only), 6 (start check), 7 and 8. `kiln_mcp_server/__init__.py` exports `build_kiln_mcp_server`, `KilnMcpServer`, `MCP_PATH`.

7. **Placeholder tree**: `kiln_mcp_server/skill/SKILL.md` with `name: kiln` and a `description`, saying what Kiln is and that the full skill is not in this build.

8. **Desktop mount**: `app/desktop/studio_server/kiln_mcp_mount.py` with `connect_kiln_mcp_server(app, *, host, port)`; it stores the server on `app.state.kiln_mcp_server` and adds the `/mcp` route with `include_in_schema=False`. In `app/desktop/desktop_server.py`: `make_app(tk_root=None, *, host=None, port=None)` (missing values from `Config.shared()`), `connect_kiln_mcp_server` as the last `connect_*` before `connect_webhost`, `async with app.state.kiln_mcp_server.run(): yield` in `lifespan`, and `server_config` passing host and port to `make_app` and setting `timeout_graceful_shutdown=2`.

9. **PyInstaller hook**: `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py` with `datas = collect_data_files("kiln_mcp_server")`.

10. **CI**: `build_and_test.yml` gets a `uv build` step in `./app/mcp`; `playwright.yml` gets `app/mcp/**` in both path filters; `build_desktop.yml` gets `app/mcp/**`, `app/desktop/build_desktop_app.sh` and `app/desktop/pyinstaller_hooks/**` in its pull-request paths.

## Tests

- `kiln_mcp_server/test_texts.py`: instructions start with `WHAT_KILN_IS`; the tool description contains `WHAT_KILN_IS + "."`; `WHAT_KILN_IS` is the agreed sentence; instructions under 4,000 characters and their first 500 name `kiln_skill` and `/kiln`; the tool description names `/kiln`; `texts.py` imports nothing.
- `kiln_mcp_server/test_addresses.py`: loopback hosts give protection with the expected lists; `0.0.0.0`, `::`, `192.168.1.5`, `kiln.lan` give none; `127.0.0.2` adds itself; the `app_origin` table of server doc section 10.
- `kiln_mcp_server/test_skill_files.py`: the cases of skill doc section 10 for step 1 (index keys, missing `SKILL.md`, hidden and `__pycache__` skipped, every row of the resolve table, exact error texts, nearest-folder and sub-folder listings, case suggestion, folder path, short `api_docs` listing, raw cleaning and cut, front matter strip, reference file keeps front matter, origin replacement, byte-exact read).
- `kiln_mcp_server/test_skill_tool.py` (FastMCP in-memory client session): schema has only an optional `path`; `_meta` always-load; no args returns `SKILL.md` without front matter; a path returns the file; `resource` alias; stray `name`/`skill`/`id` ignored; an error is `isError` without the SDK prefix; no structured content; a non-default origin is replaced; the Host header is not used; a wrong type is an error; the description is 100–150 words with the `/kiln` rule in the first 500 characters.
- `kiln_mcp_server/test_server.py`: `serverInfo` name and version; `instructions`; `tools/list` holds `kiln_skill`; prompts and resources empty; a broken index fails the build with its `RuntimeError`; no root handler added and the root level kept; two servers in one process both run; `POST` works, `GET`/`DELETE`/`PUT` give 405 with `Allow: POST`; `Host: evil.com` gives 421 and `Origin: http://evil.com` 403 on a loopback build, both 200 on a `0.0.0.0` build; `McpEndpoint._git_sync_no_write_lock` is true.
- `app/desktop/studio_server/test_kiln_mcp_mount.py`: the routes end with `/mcp` then the web host mount; `/mcp` is not in `openapi()`; `initialize` and `tools/list` through `TestClient`; `GET /mcp` gives 405; the default `TestClient` host gives 421; `GitSyncMiddleware._resolve_endpoint` returns the marked endpoint for `/mcp`; `server_config()` sets `timeout_graceful_shutdown=2` and passes host and port through; `make_app(host="0.0.0.0", port=9000)` builds a server without the Host check; bare `make_app()` uses the `Config` host and port; `connect_kiln_mcp_server` works with `Config.shared` patched to raise.
- `app/desktop/test_pyinstaller_hooks.py`: `app/mcp/__init__.py` does not exist; the hook file exists; the data files that `collect_data_files("kiln_mcp_server")` returns under `kiln_mcp_server/skill/` are exactly the keys of `skill_files.get_index().files`.
