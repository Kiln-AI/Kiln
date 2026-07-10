"""Artifact provenance: why a compiled/tunable artifact exists and what it was derived from.

`KilnArtifactProvenance` is a plain value-object submodel (mirrors `DataSource` — no
`id`/`v`/`path`/`model_type`) embedded as one optional field on each host model. Its
validators are context-aware and lenient-on-load per Kiln's "load any data, create perfect
data" rule: every rejection-type check is strict on create but skipped on load, so the
submodel never breaks loading an imperfect or future-written file.
"""

from collections.abc import Callable

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from kiln_ai.datamodel.basemodel import ID_TYPE

VALID_ORIGINS = {"human", "agent"}
NOTES_MAX_LENGTH = 2000


def _is_loading(info: ValidationInfo) -> bool:
    """True when the host is being loaded from disk (lenient-on-load path).

    The submodel is a plain `BaseModel`, so it can't use `KilnBaseModel.loading_from_file()`.
    Pydantic v2 propagates the host's `model_validate(..., context={"loading_from_file": True})`
    into this nested submodel's field validators, so we read the context directly.
    """
    return bool(info.context and info.context.get("loading_from_file", False))


class KilnArtifactProvenance(BaseModel):
    """Why this artifact exists and what it was derived from.

    Written once at creation; immutable thereafter (enforced at the API layer).
    Compile-time metadata for future agent sessions and humans — never shown to
    runtime models (not part of any tool/prompt surface)."""

    notes: str | None = Field(
        default=None,
        description=(
            "Why this artifact exists: the problem/hypothesis it addresses, what "
            "changed vs. the derived_from_ids parents, what validation/evidence "
            "supports it (cite eval/run_config/trace IDs inline), and known limits. "
            "First line = one-sentence summary. Record observations with conditions, "
            "never universal rules. Max ~2000 chars."
        ),
    )
    derived_from_ids: list[ID_TYPE] = Field(
        default_factory=list,
        description=(
            "IDs of same-type sibling artifacts this one was derived from. Ordered: "
            "first = primary parent (the artifact this replaces or is a new version "
            "of); further entries = additional sources merged in. Empty = not derived. "
            "IDs resolve among siblings in the same parent scope only."
        ),
    )
    origin: str | None = Field(
        default=None,
        # Run the validator even when origin is omitted so a create that never sets
        # it fails loud (required-when-present). On load the validator is lenient, so
        # a file whose provenance lacks origin still loads with origin=None.
        validate_default=True,
        description=(
            "Whose judgment created this artifact. 'human': a person authored it "
            "directly OR an agent created it fulfilling a direct human request. "
            "'agent': an agent created it autonomously. None: unknown/legacy. Required "
            "when this provenance is created; consumers must tolerate unknown values."
        ),
    )

    @field_validator("notes", mode="after")
    @classmethod
    def _validate_notes(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Cap is a create-time write-discipline check; lenient on load so a
        # future longer note never breaks loading an existing file.
        if not _is_loading(info) and len(v) > NOTES_MAX_LENGTH:
            raise ValueError(f"notes must be <= {NOTES_MAX_LENGTH} characters")
        return v

    @field_validator("derived_from_ids", mode="after")
    @classmethod
    def _validate_derived_from_ids(
        cls, v: list[ID_TYPE], info: ValidationInfo
    ) -> list[ID_TYPE]:
        if _is_loading(info):
            return v  # accept any historical/future list as-is
        seen: set[str] = set()
        for entry in v:
            if entry is None or not str(entry).strip():
                raise ValueError("derived_from_ids entries must be non-empty ids")
            if entry in seen:
                raise ValueError(f"duplicate id in derived_from_ids: {entry}")
            seen.add(entry)
        return v

    @field_validator("origin", mode="after")
    @classmethod
    def _validate_origin(cls, v: str | None, info: ValidationInfo) -> str | None:
        if _is_loading(info):
            return v  # any string or None accepted from disk (forward/back-compat)
        if v not in VALID_ORIGINS:
            raise ValueError(f"origin is required and must be one of {VALID_ORIGINS}")
        return v


def validate_derived_from_ids(
    provenance: KilnArtifactProvenance | None,
    self_id: str | None,
    sibling_exists: Callable[[str], bool],
) -> None:
    """Create-time semantic check for derived_from_ids lineage.

    Pure data-model utility (no FastAPI import): the server is its only consumer and maps
    the raised `ValueError` to an HTTP 400. Existence is delegated to an injected predicate so
    core never assumes a lookup strategy. This is a standalone function, not a model validator,
    so existence checks here are fine (Kiln's "no existence checks in validators" rule is about
    validators, which run on load).

    Raises:
        ValueError: on self-reference or an unknown parent id.
    """
    if provenance is None:
        return
    for parent_id in provenance.derived_from_ids:
        # Self-reference is P3/defensive: server-generated ids make it near-impossible.
        # Cheap to keep; safe to drop.
        if parent_id == self_id:
            raise ValueError("derived_from_ids cannot reference this artifact itself")
        # ID_TYPE is Optional[str]; the create-time submodel validator already rejects
        # None/empty entries, so parent_id is a real id here. Guard None anyway (a None
        # can't resolve to a sibling) — this also narrows the type for sibling_exists.
        if parent_id is None or not sibling_exists(parent_id):
            raise ValueError(
                f"derived_from_ids references unknown sibling: {parent_id}"
            )
