---
name: preview_and_cap
description: Wrapper template for a list result that floods the context - the total, the first rows with the fields the task needs, and how to get more.
---

# Wrapper template: preview_and_cap

**Failure in the trace:** A list result floods the context.

**What it does for the model:** Returns `total`, the first N rows projected to the fields the task needs, and how to get more.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""preview_and_cap — a list result as total + a small projected preview.

A 700-row listing used to land in the context whole. This returns the
count, the first N rows with only the fields the task needs, and how to
get more. N is capped whatever the model asks for.

tool_description: "Count and preview a list. Prefer this over
call_subject_api for any listing — it returns the total and the first few
rows with the fields that matter, instead of the whole table."

parameters_schema: {"type": "object", "properties": {
  "url_path": {"type": "string"},
  "query_params": {"type": "object"},
  "preview": {"type": ["integer", "string"]},
  "fields": {"type": "array", "items": {"type": "string"}}},
  "required": ["url_path"]}
"""

import json

PREVIEW_ROWS, MAX_PREVIEW = 5, 25


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


def _project(row, fields):
    if not fields or not isinstance(row, dict):
        return row
    return {k: row.get(k) for k in fields if k in row}


def run(url_path, query_params=None, preview=None, fields=None):
    n, err = _int(preview, PREVIEW_ROWS, "preview", high=MAX_PREVIEW)
    if err:
        return err
    response = _call(method="GET", url_path=url_path, query_params=query_params or {})
    if not isinstance(response, dict) or response.get("status_code") != 200:
        return {"ok": False, "error": "listing failed", "raw": response}
    body = _parse(response.get("body"))
    rows = _rows(body)
    total = body.get("total", len(rows)) if isinstance(body, dict) else len(rows)
    return {
        "ok": True,
        "total": total,
        "preview": [_project(r, fields) for r in rows[:n]],
        "shown": min(n, len(rows)),
        "how_to_get_more": (
            "narrow with query_params (status, date range, assignee) or ask for a "
            "specific id; the full list is not returned by design"
        ),
    }
```
