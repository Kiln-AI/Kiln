# Sentry — desktop server

Python errors from the packaged desktop app flow to Sentry project
`kiln-oy/desktop`. The web UI side is documented separately in
[`app/web_ui/docs/sentry.md`](../../web_ui/docs/sentry.md); both sides share
the same `SENTRY_ENV_NAME` / `SENTRY_RELEASE_TAG` job-level env vars in CI so
errors from a single build land under matching environment + release tags
across the two projects.

## Files involved

- `desktop.py` — calls `sentry_sdk.init` from the `__main__` block, gated on
  `SENTRY_DSN` being set in `_sentry_config.py`. Unset = no init, no events.
- `studio_server/_sentry_config.py` — auto-generated module containing
  `SENTRY_DSN`, `SENTRY_ENV`, and `SENTRY_RELEASE`. The committed copy holds
  `None` defaults; `build_desktop_app.sh` overwrites it with values from the
  CI-provided env vars before pyinstaller runs.
- `studio_server/_version.py` and `app/web_ui/src/lib/version` —
  auto-synced by `build_desktop_app.sh` from the canonical version in
  `app/desktop/pyproject.toml`. Bump the version there; the build script
  rewrites both mirrors before vite or pyinstaller run.
- `build_desktop_app.sh` — runs codegen for the version mirrors and
  `_sentry_config.py` at the very top of the script. Pyinstaller can't
  carry build-time env vars to the user's runtime, so we write them into
  python modules that get bundled.
- `.github/workflows/build_desktop.yml` and `windows_release_build.yml` —
  set `KILN_SENTRY_ENV` / `KILN_SENTRY_RELEASE` via the shared
  `SENTRY_ENV_NAME` / `SENTRY_RELEASE_TAG` job-level vars.

## Environments and release names

| Trigger                              | Environment  | Release name                            |
| ------------------------------------ | ------------ | --------------------------------------- |
| GitHub Release created               | `production` | `kiln-studio-desktop@<git-tag>`         |
| Push to `main` / `workflow_dispatch` | `staging`    | `kiln-studio-desktop@<full-commit-sha>` |

Both values are baked into `_sentry_config.py` at build time and read at
runtime from `desktop.py`. If neither env var is set during a manual frozen
build, the release falls back to `kiln-studio-desktop@<__version__>` from
`studio_server/_version.py` (auto-synced from `pyproject.toml` by the build
script) and the environment defaults to whatever Sentry assigns when
`environment=None` (currently `"production"`).

## Why no auth token

Unlike the frontend, the python side doesn't upload anything to Sentry at
build time. Tracebacks carry full file paths and line numbers, so we don't
need the source-map equivalent of `sentrySvelteKit`. `SENTRY_AUTH_TOKEN`
isn't read by anything on this side.

## CI env vars reference

Set on the build steps in both workflow files (env/release derived from
job-level `SENTRY_ENV_NAME` / `SENTRY_RELEASE_TAG`):

| Variable              | Source                             | Purpose                                                |
| --------------------- | ---------------------------------- | ------------------------------------------------------ |
| `KILN_SENTRY_DSN`     | hardcoded DSN in workflow          | Gates `sentry_sdk.init` — unset = no init, no events   |
| `KILN_SENTRY_ENV`     | `production` or `staging`          | Sentry environment tag                                 |
| `KILN_SENTRY_RELEASE` | `kiln-studio-desktop@<tag-or-sha>` | Sentry release name (baked into `_sentry_config`)      |

## Running with Sentry locally

`SENTRY_DSN`, `SENTRY_ENV`, and `SENTRY_RELEASE` are read from the generated
`_sentry_config.py`, not from the process environment at runtime. The
committed stub has them all `None`, so a plain
`uv run python -m app.desktop.desktop` won't initialize Sentry.

To exercise the wiring locally, run `build_desktop_app.sh` with the env vars
set so the codegen bakes them into `_sentry_config.py`, then launch the
resulting `Kiln.app` / `Kiln.exe` / `Kiln` binary from
`app/desktop/build/dist/`:

```
KILN_SENTRY_DSN='https://...@o.../...' \
  KILN_SENTRY_ENV=local \
  KILN_SENTRY_RELEASE="kiln-studio-desktop@local-$(git rev-parse --short HEAD)" \
  bash app/desktop/build_desktop_app.sh
```

To find your event in Sentry, filter on `environment:local` in the
`kiln-oy/desktop` project.

## Integrations

We don't pass `integrations=[...]` to `sentry_sdk.init`. Sentry's default
auto-discovery scans `sys.modules` at init time and activates the
FastAPI/Starlette integrations because uvicorn (imported at the top of
`desktop.py`) pulls both in before init runs. That's what makes distributed
traces continue from the web UI (which sets
`tracePropagationTargets: ["localhost"]`) into the local FastAPI server.
