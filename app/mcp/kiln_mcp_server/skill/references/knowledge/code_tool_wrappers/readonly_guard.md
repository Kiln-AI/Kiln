---
name: readonly_guard
description: Wrapper template for spurious writes on a read scenario - a read-only variant of a read-write tool.
---

# Wrapper template: readonly_guard

**Failure in the trace:** A read scenario produces a spurious write.

**What it does for the model:** A read-only variant of a read-write tool; rejects every non-GET with the name of the write tool.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""readonly_guard — the read-only variant of a read-write tool.

For a read scenario on a write-capable run config, a spurious POST is an
experiment-invalidating side effect. This variant forwards GET and refuses
everything else with the name of the tool that does writes, so the model
knows where writes go and that this tool is not it.

tool_description: "Read-only access to the subject API (GET only). Use
this for every lookup; writes are refused here — use <write tool name>
only when the user asked for a change."

parameters_schema: {"type": "object", "properties": {
  "method": {"type": "string"}, "url_path": {"type": "string"},
  "query_params": {"type": "object"}}, "required": ["method", "url_path"]}
"""

import json

WRITE_TOOL_NAME = "call_subject_api"


def _parse(r):
    """Nested results arrive parsed OR as a JSON string; the body inside can
    be a string again. Everything that is not JSON becomes a body."""
    if isinstance(r, str):
        try:
            return json.loads(r)
        except Exception:
            return {"status_code": -1, "body": r}
    return r


def _call(**kw):
    """One nested call. A crashed inner tool RAISES out of the bridge; the
    model cannot use a traceback, so a raise becomes an error envelope."""
    from kiln import tools

    try:
        return _parse(tools.call_subject_api(**kw))
    except Exception as exc:
        return {"status_code": -1, "body": f"{type(exc).__name__}: {exc}"}


def _rows(body):
    """The list inside a listing body: a bare array, or `results`/`items`."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return body.get("results") or body.get("items") or []
    return []


def _int(value, default, field, low=1, high=None):
    """Coerce a model-supplied number (int, or a string of digits) and clamp
    it. Returns (value, None) or (None, error envelope)."""
    if value in (None, ""):
        n = default
    else:
        try:
            n = int(str(value).strip())
        except ValueError:
            return None, {"ok": False, "error": f"{field} must be a whole number; got {value!r}"}
    n = max(low, n)
    if high is not None:
        n = min(n, high)
    return n, None


def run(method, url_path, query_params=None):
    verb = str(method).upper()
    if verb != "GET":
        return {"ok": False, "refused": True,
                "error": f"{verb} is not allowed through this read-only tool; "
                         f"use {WRITE_TOOL_NAME} for changes, and only when the user asked for one"}
    return _call(method="GET", url_path=url_path, query_params=query_params)
```
