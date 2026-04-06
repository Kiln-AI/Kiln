#!/bin/bash
# Shared helper for schema scripts.
# Exports SCHEMA_FILE pointing to a file containing the current OpenAPI schema JSON.
#
# If KILN_PORT is set and a server is responding, fetches from it.
# Otherwise, generates the schema directly from Python (no server needed).
#
# Usage: source this file, then use $SCHEMA_FILE.

set -euo pipefail

_SCHEMA_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

SCHEMA_FILE=$(mktemp)

if [ -n "${KILN_PORT:-}" ] && curl -s -f "http://localhost:${KILN_PORT}/openapi.json" -o "$SCHEMA_FILE" 2>/dev/null; then
    echo "Using remote schema from KILN_PORT: $KILN_PORT"
    return 0
fi

# Generate schema directly from the FastAPI app — no server needed.
echo "Generating schema directly from the FastAPI app"
KILN_SKIP_REMOTE_MODEL_LIST=true uv run --directory "$_SCHEMA_REPO_ROOT" python -c "
import json
from app.desktop.desktop_server import make_app
print(json.dumps(make_app().openapi(), ensure_ascii=False))
" > "$SCHEMA_FILE"
