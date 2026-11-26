---
name: normalize_inputs
description: Wrapper template for malformed inputs - wrong case, wrong id form, a display number where an id goes, a string where a number goes.
---

# Wrapper template: normalize_inputs

**Failure in the trace:** Wrong case, wrong id form, display number instead of id, string where a number goes.

**What it does for the model:** Accepts every variant, maps it, and on a value it cannot map returns the valid values instead of the API's error.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""normalize_inputs — accept every variant of an input, map it, and explain
what you could not map.

Wraps `call_subject_api` (rename to the wrapped tool's real function name).
The model's own typos no longer cause errors: enum values in any case or
spelling, display numbers ("SHP-123", "shp 123", "123") mapped to ids through
one lookup, numbers coerced and clamped. A value that cannot be mapped comes
back as the list of valid values — the API's 422 never reaches the model.

tool_description (for the model): "List shipments. Prefer this over
call_subject_api whenever you have a status word, a priority word or a
shipment NUMBER rather than an opaque id — it accepts any spelling and
tells you the valid values if yours is not one."

parameters_schema: {"type": "object", "properties": {
  "status": {"type": "string"}, "priority": {"type": "string"},
  "shipment": {"type": "string", "description": "number or id"},
  "limit": {"type": ["integer", "string"]}}}
"""

import json
import re

STATUS_VALUES = ("booked", "received", "on_hold", "cleared")
PRIORITY_VALUES = ("none", "low", "medium", "high")
DEFAULT_LIMIT, MAX_LIMIT = 20, 100


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


def _canon(value):
    """'On Hold' / 'on-hold' / ' ON_HOLD ' → 'on_hold'."""
    return re.sub(r"[\s\-]+", "_", str(value).strip().lower())


def _pick(value, allowed, field):
    canon = _canon(value)
    if canon in allowed:
        return canon, None
    return None, {
        "ok": False,
        "error": f"{field} must be one of {list(allowed)}; got {value!r}",
        "field": field,
        "valid_values": list(allowed),
    }


def _resolve_shipment(handle):
    """A display number or an id → the id. Opaque ids pass through."""
    text = str(handle).strip()
    digits = re.sub(r"(?i)^shp[\s\-_]*", "", text)
    if not digits.isdigit():
        return text, None  # already an opaque id
    listing = _call(
        method="GET",
        url_path="/api/v1/shipments",
        query_params={"number": int(digits)},
    )
    if not isinstance(listing, dict) or listing.get("status_code") != 200:
        return None, {"ok": False, "error": "shipment lookup failed", "raw": listing}
    rows = _rows(_parse(listing.get("body")))
    if len(rows) == 1:
        return rows[0].get("id"), None
    return None, {
        "ok": False,
        "error": (
            f"no shipment with number {digits}"
            if not rows
            else f"{len(rows)} shipments match number {digits}; pass the id"
        ),
        "candidates": [{"id": r.get("id"), "title": r.get("title")} for r in rows],
    }


def run(status=None, priority=None, shipment=None, limit=None):
    params = {}
    if status is not None:
        params["status"], err = _pick(status, STATUS_VALUES, "status")
        if err:
            return err
    if priority is not None:
        params["priority"], err = _pick(priority, PRIORITY_VALUES, "priority")
        if err:
            return err
    if shipment is not None:
        params["id"], err = _resolve_shipment(shipment)
        if err:
            return err
    params["limit"], err = _int(limit, DEFAULT_LIMIT, "limit", high=MAX_LIMIT)
    if err:
        return err
    result = _call(method="GET", url_path="/api/v1/shipments", query_params=params)
    if not isinstance(result, dict) or result.get("status_code") != 200:
        return {"ok": False, "params_used": params, "error": "listing failed", "raw": result}
    return {"ok": True, "params_used": params, "result": result}
```
