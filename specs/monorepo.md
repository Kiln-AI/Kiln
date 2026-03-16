# Monorepo Layout

This repository contains multiple projects.

## Sub-Projects

| Path | Description |
|------|-------------|
| `libs/core/` | Python library with the core functionality of Kiln (evals, synthetic data gen, fine tuning, RAG, etc.) |
| `libs/server/` | FastAPI REST server wrapping the core library |
| `app/web_ui/` | Svelte web app frontend for Kiln |
| `app/desktop/` | Python desktop app — PyInstaller app that runs a FastAPI server, hosts the pre-compiled web app, and launches a browser for UI |

Projects that span multiple sub-projects should be spec'd at the repo root's `/specs/projects/`.
Projects scoped to a single sub-project should be spec'd within that sub-project's `/specs/projects/`.
