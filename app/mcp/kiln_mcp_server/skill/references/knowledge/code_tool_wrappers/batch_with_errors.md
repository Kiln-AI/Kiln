---
name: batch_with_errors
description: Wrapper template for one call per item - a loop that stops at the first error; runs a list and returns what was done and the errors.
---

# Wrapper template: batch_with_errors

**Failure in the trace:** One call per item, a loop that dies on the first error.

**What it does for the model:** Runs a list of operations; returns `done` and `errors` so partial success is usable.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""batch_with_errors — run a list of operations; keep going past failures.

One call per item is where the model loops, forgets where it was, and
stops at the first error. This runs them all and returns what landed and
what did not, per item, so partial success is usable.

tool_description: "Run several API operations in one call. Prefer this
over repeating call_subject_api when you have a list of ids to act on —
each item succeeds or fails on its own and you get both lists back."

parameters_schema: {"type": "object", "properties": {"operations": {
  "type": "array", "items": {"type": "object", "properties": {
    "method": {"type": "string"}, "url_path": {"type": "string"},
    "body": {"type": "object"}}, "required": ["method", "url_path"]}}},
  "required": ["operations"]}
"""

import json

MAX_OPERATIONS = 25


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


def run(operations):
    if not isinstance(operations, list) or not operations:
        return {"ok": False, "error": "operations must be a non-empty list"}
    if len(operations) > MAX_OPERATIONS:
        return {"ok": False, "error": f"at most {MAX_OPERATIONS} operations per call; "
                f"got {len(operations)} — split the list"}
    done, errors = [], []
    for index, op in enumerate(operations):
        # Validate the shape BEFORE the call: the handler below must not be
        # able to raise on the same bad item it is reporting.
        if not isinstance(op, dict) or not op.get("method") or not op.get("url_path"):
            errors.append({"index": index, "url_path": None,
                           "error": "each operation needs method and url_path"})
            continue
        response = _call(method=op["method"], url_path=op["url_path"], body=op.get("body"))
        status = response.get("status_code") if isinstance(response, dict) else None
        if status is not None and 200 <= status < 300:
            done.append({"index": index, "url_path": op["url_path"],
                         "body": _parse(response.get("body"))})
        else:
            errors.append({"index": index, "url_path": op["url_path"],
                           "status_code": status, "error": response})
    return {"ok": not errors, "done": done, "errors": errors,
            "summary": f"{len(done)} succeeded, {len(errors)} failed of {len(operations)}"}
```
