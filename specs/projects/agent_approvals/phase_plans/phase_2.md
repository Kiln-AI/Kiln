---
status: draft
---

# Phase 2: Annotation Dump CLI

## Overview

Build the CLI tool that reads an OpenAPI spec (from URL or file) and writes one JSON file per endpoint into a target folder. This enables both human inspection and CI validation of agent policy annotations.

## Steps

1. Create `libs/server/kiln_server/utils/agent_checks/dump_annotations.py` with:
   - `normalize_endpoint_filename(method: str, path: str) -> str` — path normalization for filenames
   - `load_openapi_spec(source: str) -> dict` — loads from URL (httpx) or file path (json.load)
   - `dump_annotations(source: str, target_folder: str) -> int` — main logic, returns exit code
   - `main()` — argparse entry point, calls `sys.exit(dump_annotations(...))`
   - `if __name__ == "__main__": main()` block

2. Create `libs/server/kiln_server/utils/agent_checks/test_dump_annotations.py` with tests covering:
   - Path normalization (various paths, params, edge cases)
   - Full dump with all-annotated spec (exit code 0)
   - Dump with unannotated endpoints (exit code 2, warning output)
   - Dump with invalid policy (warning, null policy in output)
   - File-based loading
   - URL-based loading (mock httpx)
   - Main entry point argparse integration
   - Empty spec edge case

## Tests

- `test_normalize_simple_path`: Basic path normalization
- `test_normalize_with_params`: Path params stripped of braces
- `test_normalize_nested_path`: Deeply nested path
- `test_dump_all_annotated`: All endpoints annotated, exit 0, correct JSON files
- `test_dump_unannotated`: Missing annotations, exit 2, warning printed
- `test_dump_invalid_policy`: Malformed policy produces null in output
- `test_load_from_file`: Load spec from local file
- `test_load_from_url`: Load spec from URL via httpx mock
- `test_main_entrypoint`: argparse integration via monkeypatched sys.argv
- `test_empty_spec`: Empty paths dict, exit 0
