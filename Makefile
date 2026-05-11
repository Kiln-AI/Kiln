.PHONY: dev ui schema annotations check package

SHELL := /bin/bash

# Shell snippet that loads nvm and selects the Node version from app/web_ui/.nvmrc.
# Use in recipes that invoke npm/npx/node. $(CURDIR) keeps the path valid after any `cd`.
NVM_USE = export NVM_DIR="$${NVM_DIR:-$$HOME/.nvm}" && . "$$NVM_DIR/nvm.sh" && nvm use "$$(cat $(CURDIR)/app/web_ui/.nvmrc)"

# Run the development API server (desktop dev server with hot reload on port 8757).
dev:
	uv run python -m app.desktop.dev_server

# Run the Vite dev server for the web UI (http://localhost:5173 by default). Uses Node version from app/web_ui/.nvmrc via nvm.
ui:
	cd app/web_ui && $(NVM_USE) && npm run dev --

# Regenerate api_schema.d.ts from the running server's OpenAPI spec (server must be up on :8757).
schema:
	cd app/web_ui/src/lib && $(NVM_USE) && ./generate_schema.sh

# Dump agent-check annotation JSON files from the running server's OpenAPI (server must be up on :8757).
annotations:
	uv run python -m kiln_server.utils.agent_checks.dump_annotations http://localhost:8757/openapi.json libs/server/kiln_server/utils/agent_checks/annotations

# Run formatting, linting, typechecking, tests, and builds via the repo checks script.
check:
	$(NVM_USE) && uv run ./checks.sh

# Package a project to a zip via kiln_ai package_project. Example: make package ARGS='~/KilnProjects/demo/project.kiln --all-tasks -o ./kiln_export.zip'
package:
	@if [ -z "$(strip $(ARGS))" ]; then \
		if [ -t 1 ]; then \
			e=$$(printf '\033'); \
			U="$${e}[1;33m"; H="$${e}[1;36m"; D="$${e}[90m"; N="$${e}[33m"; L="$${e}[34m"; R="$${e}[0m"; \
		else \
			U=; H=; D=; N=; L=; R=; \
		fi; \
		printf '%s\n' "$${U}Usage:$${R} make package ARGS='<path/to/project.kiln> [options]'"; \
		printf '%s\n' "$${H}Example:$${R}"; \
		printf '%s\n' "    $${D}make package ARGS='~/Kiln\\ Projects/demo/project.kiln --all-tasks -o /tmp/kiln_export.zip'$${R}"; \
		printf '%s\n' "    $${D}make package ARGS='~/Kiln\\ Projects/demo/project.kiln --task 314310835537 -o \"/tmp/kiln_export.zip\"'$${R}"; \
		printf '%s\n' "$${N}Note:$${R} Remember to escape spaces and apostrophes or quotes in the path."; \
		printf '%s\n' "$${L}See also:$${R} uv run kiln_ai package_project --help"; \
	fi
	uv run kiln_ai package_project $(ARGS)
