---
name: actionable_errors
description: Wrapper template for raw 4xx bodies that the model cannot act on - rewrites them into what to do.
---

# Wrapper template: actionable_errors

**Failure in the trace:** Raw 4xx bodies the model cannot act on.

**What it does for the model:** Rewrites 400/404/405/422/429 into "what to do": valid values, nearest matches, "GET takes no body", "wait N s".

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""actionable_errors — the same tool, with errors the model can act on.

A raw 4xx body tells the model what the server thought; this tells it what
to do. 404 on an id path runs a search and names the nearest matches. 422
lists the field errors and, where the body names them, the valid values.
400/405 on a GET with a body says to move filters to query_params. 429
says to wait, with the server's own number when it gives one. Successes
pass through unchanged.

tool_description: same as the wrapped tool's, plus: "Errors come back as
plain instructions (valid values, nearest matches, what to change)."

parameters_schema: same as the wrapped tool's — read it from the
clone-source GET (`GET /api/projects/{project_id}/code_tools/{code_tool_id}`)
for a code tool, or from the tool definition call for an MCP, built-in,
Kiln task or RAG tool; typically
{"type": "object", "properties": {
  "method": {"type": "string"}, "url_path": {"type": "string"},
  "query_params": {"type": "object"}, "body": {"type": "object"}},
  "required": ["method", "url_path"]}
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


def _split_id_path(url_path):
    """`/anything/<collection>/<id>` → (collection path, id); None otherwise."""
    path = str(url_path).split("?", 1)[0].rstrip("/")
    collection, _, handle = path.rpartition("/")
    if not collection or not handle:
        return None
    return collection, handle


def _nearest(collection, handle):
    listing = _call(method="GET", url_path=collection, query_params={"q": handle, "limit": 5})
    if not isinstance(listing, dict) or listing.get("status_code") != 200:
        return []
    return [{"id": r.get("id"), "name": r.get("name") or r.get("title")}
            for r in _rows(_parse(listing.get("body"))) if isinstance(r, dict)]


def _field_errors(body):
    """FastAPI/pydantic-style `detail: [{loc, msg, ctx}]` → readable lines."""
    lines = []
    for item in (body or {}).get("detail") or []:
        if not isinstance(item, dict):
            continue
        field = ".".join(str(p) for p in item.get("loc", []) if p != "body") or "?"
        msg = item.get("msg", "invalid")
        expected = (item.get("ctx") or {}).get("expected")
        lines.append(f"{field}: {msg}" + (f" (valid: {expected})" if expected else ""))
    return lines


def run(method, url_path, query_params=None, body=None):
    response = _call(method=method, url_path=url_path, query_params=query_params, body=body)
    status = response.get("status_code") if isinstance(response, dict) else None
    if status is not None and 200 <= status < 300:
        return response
    raw = _parse(response.get("body")) if isinstance(response, dict) else response
    if status == 404:
        parts = _split_id_path(url_path)
        near = _nearest(*parts) if parts else []
        return {"ok": False, "status_code": 404,
                "error": f"{url_path} does not exist" + (
                    f"; nearest matches: {near}" if near else "; check the id with a search first")}
    if status == 422:
        lines = _field_errors(raw if isinstance(raw, dict) else {})
        return {"ok": False, "status_code": 422,
                "error": "the request body was rejected: " + ("; ".join(lines) if lines else str(raw))}
    if status in (400, 405) and str(method).upper() == "GET" and body:
        return {"ok": False, "status_code": status,
                "error": "GET takes no body — put filters in query_params"}
    if status == 429:
        wait = raw.get("retry_after") if isinstance(raw, dict) else None
        advice = f"wait {wait} s, then retry once" if wait else "wait briefly, then retry once"
        return {"ok": False, "status_code": 429, "error": f"rate limited; {advice}"}
    return {"ok": False, "status_code": status, "error": raw}
```
