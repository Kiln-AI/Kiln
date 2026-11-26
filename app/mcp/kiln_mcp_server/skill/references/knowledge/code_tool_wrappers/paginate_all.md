---
name: paginate_all
description: Wrapper template for paged lists - one call per page, or a truncated list that the model never notices.
---

# Wrapper template: paginate_all

**Failure in the trace:** One call per page, or a truncated list the model never notices.

**What it does for the model:** Fetches every page up to a cap; returns `total`, `items`, `truncated`, `next_cursor`.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""paginate_all — walk a cursor-paged list to the end (or a cap) in one call.

The model used to fetch one page, read a truncated list, and answer from
it. This returns every row up to `max_pages`, says whether it stopped
early, and hands back the cursor to continue.

tool_description: "List every row of a paged endpoint in one call. Prefer
this over call_subject_api for any list that may exceed one page — it
follows next_cursor for you and tells you if it stopped at the cap."

parameters_schema: {"type": "object", "properties": {
  "url_path": {"type": "string"},
  "query_params": {"type": "object"},
  "max_pages": {"type": ["integer", "string"]}},
  "required": ["url_path"]}
"""

import json

PAGE_SIZE, MAX_PAGES = 100, 10


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


def run(url_path, query_params=None, max_pages=None):
    cap, err = _int(max_pages, MAX_PAGES, "max_pages", high=MAX_PAGES)
    if err:
        return err
    params = dict(query_params or {})
    params.setdefault("limit", PAGE_SIZE)
    items, cursor, pages = [], None, 0
    while pages < cap:
        if cursor:
            params["cursor"] = cursor
        response = _call(method="GET", url_path=url_path, query_params=params)
        if not isinstance(response, dict) or response.get("status_code") != 200:
            return {"ok": False, "error": "page fetch failed", "pages_read": pages,
                    "items_so_far": len(items), "raw": response}
        body = _parse(response.get("body"))
        items.extend(_rows(body))
        pages += 1
        cursor = body.get("next_cursor") if isinstance(body, dict) else None
        if not cursor:
            return {"ok": True, "total": len(items), "items": items,
                    "truncated": False, "next_cursor": None, "pages_read": pages}
    return {"ok": True, "total": len(items), "items": items, "truncated": True,
            "next_cursor": cursor, "pages_read": pages,
            "hint": f"stopped at {cap} pages; call again with the cursor"}
```
