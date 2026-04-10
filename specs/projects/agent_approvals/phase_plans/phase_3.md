---
status: draft
---

# Phase 3: Policy Lookup Helper

## Overview

Implement `AgentPolicyLookup` class and `AgentPolicyError` exception in `policy_lookup.py`. This class loads dumped annotation JSON files and answers policy questions at runtime, with lazy loading and fail-safe blocking for unknown/unannotated endpoints. Update `__init__.py` to export the new symbols.

## Steps

1. Create `libs/server/kiln_server/utils/agent_checks/policy_lookup.py` with:
   - `AgentPolicyError(Exception)` custom exception
   - `AgentPolicyLookup` class with `__init__(self, annotations_dir: str | Path)`, lazy `_load()`, and `get_policy(self, method: str, path: str) -> AgentPolicy`

2. Update `libs/server/kiln_server/utils/agent_checks/__init__.py` to add exports for `AgentPolicyLookup` and `AgentPolicyError`

## Tests

- `test_get_policy_happy_path`: Load dir with valid annotated files, verify correct AgentPolicy returned
- `test_get_policy_unknown_endpoint`: Lookup endpoint not in annotations, verify AgentPolicyError
- `test_get_policy_unannotated_endpoint`: Annotation file with null policy, verify AgentPolicyError
- `test_lazy_loading`: Verify _cache is None before first get_policy call, populated after
- `test_method_case_insensitivity`: GET vs get both work for same endpoint
- `test_multiple_endpoints`: Load dir with multiple files, verify each returns correct policy
- `test_missing_annotations_dir`: Verify error when dir doesn't exist
- `test_require_approval_policy`: Verify approval policies are loaded correctly with description
