---
status: draft
---

# Phase 5: CI Integration — Unannotated Endpoint Check and Annotation Diff

## Overview

Extend the existing `check_api_bindings.yml` GitHub Actions workflow to verify that all endpoints have agent policy annotations and that the checked-in annotation JSON files are up to date with the live OpenAPI spec.

## Steps

1. Modify `.github/workflows/check_api_bindings.yml` to add two new checks after the server is running:
   - Run the dump CLI against `http://localhost:8757/openapi.json` targeting a temporary directory, check exit code (non-zero means unannotated endpoints exist)
   - Diff the generated annotation files against the checked-in `libs/server/kiln_server/utils/agent_checks/annotations/` directory, fail if they differ

2. The checks should run in the same job step where the server is already started, reusing the existing server startup logic.

## Tests

- No new unit tests needed — this is CI configuration only.
- Verification: Review the workflow YAML for correctness by reading the file.
