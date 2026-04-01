---
status: draft
---

# Phase 1: Policy Model, Constants, and Constructor

## Overview

Create the foundational `AgentPolicy` Pydantic model with validation, module-level constants (`DENY_AGENT`, `ALLOW_AGENT`), and the `agent_policy_require_approval` constructor function. This phase establishes the annotation schema that all subsequent phases depend on.

## Steps

1. Create `libs/server/kiln_server/utils/agent_checks/__init__.py` with exports for `AgentPolicy`, `DENY_AGENT`, `ALLOW_AGENT`, `agent_policy_require_approval`. (PolicyLookup and AgentPolicyError exports will be added in Phase 3.)

2. Create `libs/server/kiln_server/utils/agent_checks/policy.py`:
   - `AgentPolicy(BaseModel)` with fields `permission: Literal["allow", "deny"]`, `requires_approval: bool`, `approval_description: str | None = None`
   - `@model_validator(mode="after")` enforcing:
     - deny + requires_approval -> ValueError
     - requires_approval without description -> ValueError
     - description without requires_approval -> ValueError
   - Constants `DENY_AGENT` and `ALLOW_AGENT` as dicts with `"x-agent-policy"` key
   - Function `agent_policy_require_approval(description: str) -> dict` that validates non-empty description

3. Create `libs/server/kiln_server/utils/agent_checks/test_policy.py` with tests

## Tests

- `test_allow_policy_valid`: AgentPolicy with permission="allow", requires_approval=False creates successfully
- `test_deny_policy_valid`: AgentPolicy with permission="deny", requires_approval=False creates successfully
- `test_approval_policy_valid`: AgentPolicy with all three fields set correctly
- `test_deny_with_approval_raises`: deny + requires_approval=True -> ValueError
- `test_approval_without_description_raises`: requires_approval=True, no description -> ValueError
- `test_description_without_approval_raises`: requires_approval=False with description set -> ValueError
- `test_deny_agent_constant`: Verify DENY_AGENT dict structure
- `test_allow_agent_constant`: Verify ALLOW_AGENT dict structure
- `test_require_approval_valid`: agent_policy_require_approval with valid description
- `test_require_approval_empty_string_raises`: empty string -> ValueError
- `test_require_approval_whitespace_raises`: whitespace-only -> ValueError
