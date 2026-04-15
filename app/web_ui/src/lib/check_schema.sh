#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=openapi_schema.sh
source "$SCRIPT_DIR/openapi_schema.sh"

# Generate TypeScript types to a temporary file
TEMP_FILE=$(mktemp)
npx openapi-typescript "$SCHEMA_FILE" -o "$TEMP_FILE" > /dev/null 2>&1
rm "$SCHEMA_FILE"

# Compare with existing schema
if cmp -s "$TEMP_FILE" "$SCRIPT_DIR/api_schema.d.ts"; then
    echo "OpenAPI schema up to date"
    rm "$TEMP_FILE"
    exit 0
else
    echo -e "\033[31mOpenAPI schema is not current. Run generate_schema.sh to update\033[0m"
    echo -e "\033[33mDifferences:\033[0m"
    diff -u "$SCRIPT_DIR/api_schema.d.ts" "$TEMP_FILE" || true
    rm "$TEMP_FILE"
    exit 1
fi
