---
status: complete
---

# Phase 1: Provenance Submodel & Helper (Pure Core)

## Overview

This phase adds the pure-core foundation for artifact provenance: a new
`KilnArtifactProvenance` Pydantic submodel plus the pure `validate_derived_from_ids`
create-time helper. Both live in a new module `libs/core/kiln_ai/datamodel/provenance.py`
and are exported from the datamodel package. No host model gains the field and no
API/frontend code is touched in this phase — those are later phases.

The defining behavioral contract (from the functional spec §2.1 and architecture §1.1)
is **context-aware, lenient-on-load validation**: all rejection-type checks are strict on
create but skipped on load (Kiln's "load any data, create perfect data" rule). Load-vs-create
is detected by reading the Pydantic v2 validation context directly
(`info.context.get("loading_from_file")`), because the submodel is a plain `BaseModel` with
no `KilnBaseModel.loading_from_file()` helper. The `notes` whitespace-strip/empty-coercion is
the only unconditional transform.

## Steps

1. **Create `libs/core/kiln_ai/datamodel/provenance.py`** with:
   - Module constants `VALID_ORIGINS = {"human", "agent"}` and `NOTES_MAX_LENGTH = 2000`.
   - A module-level helper `_is_loading(info: ValidationInfo) -> bool` returning
     `bool(info.context and info.context.get("loading_from_file", False))`.
   - The `KilnArtifactProvenance(BaseModel)` class with three fields (verbatim descriptions
     from architecture §1.1):
     ```python
     notes: str | None = Field(default=None, description=...)
     derived_from_ids: list[ID_TYPE] = Field(default_factory=list, description=...)
     origin: str | None = Field(default=None, description=...)
     ```
     `ID_TYPE` imported from `kiln_ai.datamodel.basemodel`. No `model_config`
     (default `extra="ignore"` for forward-compat). No `Field(max_length=...)` on `notes`.
   - Three `@field_validator(..., mode="after")` classmethods:
     - `_validate_notes`: `None` → `None`; strip; empty/whitespace → `None`; on create only,
       raise `ValueError` if `len > NOTES_MAX_LENGTH` (measured after strip). Lenient on load.
     - `_validate_derived_from_ids`: on load return as-is; on create reject `None`/empty/
       whitespace-only entries and reject duplicates (`ValueError`).
     - `_validate_origin`: on load return as-is (any string or `None`); on create raise
       `ValueError` unless value is in `VALID_ORIGINS`.
   - The pure module-level function
     `validate_derived_from_ids(provenance, self_id, sibling_exists) -> None` (architecture §2.1):
     returns early if `provenance is None`; for each `parent_id` in `derived_from_ids`, raise
     `ValueError` on self-reference (`parent_id == self_id`) then on `not sibling_exists(parent_id)`.
     Pure — no FastAPI import; raises `ValueError` only.

2. **Export from `libs/core/kiln_ai/datamodel/__init__.py`**: add
   `from kiln_ai.datamodel.provenance import (KilnArtifactProvenance, validate_derived_from_ids)`
   and insert both names into `__all__` at their alphabetical positions.

## Tests

New file `libs/core/kiln_ai/datamodel/test_provenance.py`:

- **notes — create path**: strips surrounding whitespace; empty string and whitespace-only
  coerce to `None`; `None` stays `None`; a note of exactly 2000 chars is accepted; a note of
  2001 chars raises `ValidationError`; leading/trailing whitespace is stripped before the length
  is measured (2000 core chars + surrounding spaces is accepted).
- **notes — load path**: a 3000-char note loads successfully under
  `context={"loading_from_file": True}` and is still stripped.
- **derived_from_ids — create path**: valid distinct ids accepted; empty list accepted;
  a `None` entry, an empty-string entry, and a whitespace-only entry each raise; a duplicate id
  raises.
- **derived_from_ids — load path**: a list containing duplicates and empty strings loads
  as-is under load context (no raise, preserved verbatim).
- **origin — create path** (parametrized): `"human"` and `"agent"` accepted; `None`, `""`,
  `"banana"`, `"Human"` each raise.
- **origin — load path** (parametrized): `None`, `"banana"`, `"human"` all accepted under
  load context.
- **whole-object create**: a fully-specified valid provenance constructs; an object with a
  valid `notes`/`derived_from_ids` but missing `origin` raises on create.
- **round-trip**: `model_dump()` of a created provenance, re-validated under load context,
  equals the original.
- **extra keys forward-compat**: a dict with an unknown extra key loads under load context
  (ignored, not fatal).
- **validate_derived_from_ids helper**: `provenance=None` → no raise (and `sibling_exists`
  never called); all-known ids → no raise; an unknown id (`sibling_exists` returns False) →
  `ValueError`; `self_id` present in `derived_from_ids` → `ValueError` and it is detected
  before the existence check; empty `derived_from_ids` → no raise.
