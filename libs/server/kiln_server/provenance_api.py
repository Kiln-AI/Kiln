"""Server-layer glue for artifact provenance.

The pure create-time lineage check lives in `kiln_ai.datamodel.provenance`
(`validate_derived_from_ids`) and raises `ValueError` — `libs/core` never imports
FastAPI. This thin wrapper runs that check and maps a failure to an HTTP 400 so the
create endpoints don't each repeat the same `try/except` or existence-check lambda.
"""

from pathlib import Path
from typing import Type

from fastapi import HTTPException
from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.provenance import (
    KilnArtifactProvenance,
    validate_derived_from_ids,
)


def validate_provenance_or_400(
    provenance: KilnArtifactProvenance | None,
    self_id: str | None,
    sibling_cls: Type[KilnParentedModel],
    parent_path: Path | None,
) -> None:
    """Run the create-time `derived_from_ids` check, mapping `ValueError` → HTTP 400.

    Each candidate parent id must resolve to an existing same-type sibling of the new
    artifact — a `sibling_cls` instance in the same parent scope (archived included) via
    `from_id_and_parent_path` (a `KilnParentedModel` classmethod). Callers pass the
    sibling class and its parent path instead of repeating the lookup lambda.
    """
    try:
        validate_derived_from_ids(
            provenance,
            self_id,
            lambda cid: (
                sibling_cls.from_id_and_parent_path(cid, parent_path) is not None
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
