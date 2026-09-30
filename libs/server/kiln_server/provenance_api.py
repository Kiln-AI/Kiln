"""Server-layer glue for artifact provenance.

The pure create-time lineage check lives in `kiln_ai.datamodel.provenance`
(`validate_derived_from_ids`) and raises `ValueError` — `libs/core` never imports
FastAPI. This thin wrapper runs that check and maps a failure to an HTTP 400 so the
create endpoints don't each repeat the same `try/except` or existence-check lambda.
"""

from pathlib import Path

from fastapi import HTTPException
from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.provenance import (
    KilnArtifactProvenance,
    validate_derived_from_ids,
)


def validate_provenance_or_400(
    provenance: KilnArtifactProvenance | None,
    self_id: str | None,
    sibling_cls: type[KilnParentedModel],
    parent_path: Path | None,
) -> None:
    """Run the create-time `derived_from_ids` check, mapping `ValueError` → HTTP 400.

    Each candidate parent id must resolve to an existing same-type sibling of the new
    artifact — a `sibling_cls` instance in the same parent scope (archived included).
    All candidate ids resolve in one `from_ids_and_parent_path` scan of the parent
    directory. Callers pass the sibling class and its parent path instead of
    repeating the lookup.
    """
    if provenance is None or not provenance.derived_from_ids:
        return
    candidate_ids = {cid for cid in provenance.derived_from_ids if cid is not None}
    known_ids = sibling_cls.from_ids_and_parent_path(
        candidate_ids, parent_path, readonly=True
    ).keys()
    try:
        validate_derived_from_ids(provenance, self_id, lambda cid: cid in known_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
