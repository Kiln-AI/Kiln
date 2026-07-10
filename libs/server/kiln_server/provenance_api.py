"""Server-layer glue for artifact provenance.

The pure create-time lineage check lives in `kiln_ai.datamodel.provenance`
(`validate_derived_from_ids`) and raises `ValueError` — `libs/core` never imports
FastAPI. This thin wrapper runs that check and maps a failure to an HTTP 400 so the
create endpoints don't each repeat the same `try/except`.
"""

from collections.abc import Callable

from fastapi import HTTPException
from kiln_ai.datamodel.provenance import (
    KilnArtifactProvenance,
    validate_derived_from_ids,
)


def validate_provenance_or_400(
    provenance: KilnArtifactProvenance | None,
    self_id: str | None,
    sibling_exists: Callable[[str], bool],
) -> None:
    """Run the create-time `derived_from_ids` check, mapping `ValueError` → HTTP 400.

    `sibling_exists` resolves a candidate parent id among the new artifact's same-type
    siblings in the same parent scope (archived included), e.g.
    ``lambda cid: Model.from_id_and_parent_path(cid, parent.path) is not None``.
    """
    try:
        validate_derived_from_ids(provenance, self_id, sibling_exists)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
