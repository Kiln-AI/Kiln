#!/bin/bash
set -euo pipefail

# Parse command line arguments
ALLOW_SKIP=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --allow-skip)
            ALLOW_SKIP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# If --allow-skip is set, check if server is running
if [ "$ALLOW_SKIP" = true ]; then
    if ! curl -s -f http://localhost:8757/openapi.json > /dev/null 2>&1; then
        echo -e "\033[33mCould not check OpenAPI schema, server is not running\033[0m"
        exit 0
    fi
fi

# Generate schema to temporary file
TEMP_FILE=$(mktemp)
npx openapi-typescript http://localhost:8757/openapi.json -o "$TEMP_FILE" > /dev/null 2>&1

# Compare with existing schema
if cmp -s "$TEMP_FILE" "api_schema.d.ts"; then
    echo "OpenAPI schema up to date"
    rm "$TEMP_FILE"
    exit 0
else
    echo -e "\033[31mOpenAPI schema is not current. Run generate_schema.sh to update\033[0m"
    echo -e "\033[33mDifferences:\033[0m"
    diff -u "api_schema.d.ts" "$TEMP_FILE" || true
    rm "$TEMP_FILE"
    exit 1
fi
