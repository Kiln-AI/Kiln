#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=openapi_schema.sh
source "$SCRIPT_DIR/openapi_schema.sh"

npx openapi-typescript "$SCHEMA_FILE" -o "$SCRIPT_DIR/api_schema.d.ts"
rm "$SCHEMA_FILE"
