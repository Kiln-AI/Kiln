---
name: composite_resolve_fetch
description: Wrapper template for the resolve-then-fetch idiom - search, disambiguate and fetch a record from a human handle in one call.
---

# Wrapper template: composite_resolve_fetch

**Failure in the trace:** Resolve-then-fetch idiom the model gets wrong.

**What it does for the model:** One call: search, disambiguate, fetch.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""composite_resolve_fetch — resolve a human handle to a record in one call.

Users hand the model display numbers and names; the API's path segments
need opaque ids; the baseline guessed. Search, disambiguate, fetch.

tool_description: "Resolve a display number, name, or other human-facing
handle to its record: searches, disambiguates, and fetches in one call.
Prefer this over call_subject_api whenever the user gave anything other
than an opaque id."

parameters_schema: {"type": "object", "properties": {
  "query": {"type": "string"}}, "required": ["query"]}
"""

import json


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


def run(query):
    listing = _call(method="GET", url_path="/api/v1/records", query_params={"q": query})
    if not isinstance(listing, dict) or listing.get("status_code") != 200:
        return {"found": False, "error": listing}
    matches = _rows(_parse(listing.get("body")))
    if not matches:
        return {"found": False, "hint": f"no record matches {query!r}; try a shorter fragment"}
    if len(matches) > 1:
        return {"found": False, "ambiguous": [
            {"id": m.get("id"), "display": m.get("display_number"), "name": m.get("name")}
            for m in matches]}
    record = _call(method="GET", url_path=f"/api/v1/records/{matches[0].get('id')}")
    if not isinstance(record, dict) or record.get("status_code") != 200:
        return {"found": False, "error": record}
    return {"found": True, "record": _parse(record.get("body"))}
```
