"""
Large fields that a cached record keeps out of memory and reads back from its file on
demand.

A model marks a field as large with `Annotated[..., LargeField()]` and inherits
`LazyFieldsMixin`, first in its bases. A field holding one nested lazy model (optionally
`None`) is walked too, so the nested model's large fields belong to the record.

Records built in memory, or loaded with the model cache off, are ordinary models. When
the cache keeps a readonly record, `detach_large_values` takes the record's large values
out of it and hands them to the cache, which evicts them before the rest of the record.
Reading a missing field, dumping, copying, comparing or pickling the record brings them
back, from the cache or by re-reading and re-validating the file. If the file can't give
them back, the read raises `LargeFieldUnavailableError`; it never returns a stand-in value.

A detached record's `__dict__` never changes again: pydantic-core walks it while
serializing, from any thread. Restored values live in the cache, or on the state that
the record's lazy models share.
"""

import json
import os
import sys
import types
from collections.abc import Callable, Generator, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Generic,
    Protocol,
    TypeVar,
    Union,
    get_args,
    get_origin,
    overload,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    GetJsonSchemaHandler,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticUndefined
from typing_extensions import Self

from kiln_ai.datamodel.model_cache import FileIdentity
from kiln_ai.datamodel.model_cache import logger as cache_logger

FieldPath = tuple[str, ...]
"""Where a large value sits in a record, e.g. `("trace",)` or `("output", "output")`."""

M = TypeVar("M", bound=BaseModel)
T = TypeVar("T")

_PLAN_ATTR = "__lazy_field_plan__"
_SERIALIZER_NAME = "_serialize_with_large_fields"


class LargeField:
    """Marks a field as large: `input: Annotated[str, LargeField()] = Field(...)`.

    Has no effect on validation, serialization or the JSON schema. Only records the
    model cache keeps load the field lazily.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "LargeField()"


class SummaryValue(Generic[M, T]):
    """A read-only value derived from a record's large fields. Made with `@summary_value`.

    A record the cache detached returns the value computed when it was loaded, so
    reading it never reads the file. Any other record computes it from its own fields.
    It is not a pydantic field: never dumped, saved, or in the JSON schema.
    """

    def __init__(self, fn: Callable[[M], T]) -> None:
        self._fn = fn
        # Set by __set_name__ when the class body is executed.
        self.name = ""
        self.__doc__ = fn.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @overload
    def __get__(self, obj: None, owner: type | None = None) -> "SummaryValue[M, T]": ...

    @overload
    def __get__(self, obj: M, owner: type | None = None) -> T: ...

    def __get__(
        self, obj: M | None, owner: type | None = None
    ) -> "T | SummaryValue[M, T]":
        if obj is None:
            return self
        state = _lazy_state(obj)
        if state is not None and self.name in state.summary:
            return state.summary[self.name]
        return self._fn(obj)

    def compute(self, obj: M) -> T:
        """The value computed from `obj`'s own fields."""
        return self._fn(obj)


def summary_value(fn: Callable[[M], T]) -> SummaryValue[M, T]:
    """Declare a read-only summary of large fields on a `LazyFieldsMixin` model.

    Use it for small facts that list views need (a preview, a count), so they never
    read the large field itself.
    """
    return SummaryValue(fn)


def preview_text(text: str | None, max_length: int = 100) -> str | None:
    """The first `max_length` characters of `text`, ending in "…" when cut. None stays None."""
    if text is None or len(text) <= max_length:
        return text
    return text[:max_length] + "…"


class LargeFieldUnavailableError(RuntimeError):
    """A cached record's large field couldn't be read back from its file.

    Raised by reads, copies, comparisons, and `model_dump` / `model_dump_json` on the
    record. pydantic wraps errors raised while serializing, so dumping the record as
    part of something else (another model, a `TypeAdapter`, a FastAPI response) raises
    `pydantic_core.PydanticSerializationError` instead, with this error's message.
    """

    def __init__(self, path: Path, field: str, reason: str) -> None:
        super().__init__(f"Can't load '{field}' of the record at {path}: {reason}")
        self.path = path
        self.field = field


@dataclass(frozen=True)
class LazyFieldPlan:
    """Where a lazy model class keeps its large fields and summary values."""

    paths: tuple[FieldPath, ...]
    """Every large field, through nested lazy models."""
    large_names: tuple[str, ...]
    """This class's own large fields."""
    nested_names: tuple[str, ...]
    """This class's fields that hold one nested lazy model."""
    summaries: tuple["SummaryValue[Any, Any]", ...]
    """This class's summary values, inherited ones included."""

    @classmethod
    def for_class(cls, model_cls: type[BaseModel]) -> "LazyFieldPlan":
        """The plan for `model_cls`, built on first use.

        Raises:
            TypeError: if a large field sits inside a container, where it can't load lazily.
        """
        # A subclass inherits its parent's attribute but may add fields, so read the
        # class's own namespace.
        plan = model_cls.__dict__.get(_PLAN_ATTR)
        if not isinstance(plan, LazyFieldPlan):
            plan = _build_plan(model_cls)
            setattr(model_cls, _PLAN_ATTR, plan)
        return plan


def _build_plan(model_cls: type[BaseModel]) -> LazyFieldPlan:
    paths: list[FieldPath] = []
    large_names: list[str] = []
    nested_names: list[str] = []
    for name, field in model_cls.model_fields.items():
        if any(isinstance(item, LargeField) for item in field.metadata):
            large_names.append(name)
            paths.append((name,))
            continue
        nested_cls = _single_lazy_model(field.annotation)
        if nested_cls is not None:
            nested_names.append(name)
            paths.extend(
                (name, *path) for path in LazyFieldPlan.for_class(nested_cls).paths
            )
        elif _hides_large_field(field.annotation):
            raise TypeError(
                f"{model_cls.__name__}.{name} holds a large field inside a list, dict, "
                "union or other container, where it can't load lazily. Mark the "
                "container field itself with LargeField."
            )
    summaries: dict[str, SummaryValue[Any, Any]] = {}
    for klass in reversed(model_cls.__mro__):
        for attr_name, attr in vars(klass).items():
            if isinstance(attr, SummaryValue):
                summaries[attr_name] = attr
    return LazyFieldPlan(
        paths=tuple(paths),
        large_names=tuple(large_names),
        nested_names=tuple(nested_names),
        summaries=tuple(summaries.values()),
    )


def _strip_annotated(annotation: Any) -> Any:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


def _single_lazy_model(annotation: Any) -> "type[LazyFieldsMixin] | None":
    """The lazy model class `annotation` holds, allowing `None`; else None."""
    annotation = _strip_annotated(annotation)
    if get_origin(annotation) in (Union, types.UnionType):
        members = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(members) != 1:
            return None
        annotation = _strip_annotated(members[0])
    if isinstance(annotation, type) and issubclass(annotation, LazyFieldsMixin):
        return annotation
    return None


def _annotation_parts(annotation: Any) -> Generator[Any, None, None]:
    """Every type argument and `Annotated` metadata item inside `annotation`."""
    pending = list(get_args(annotation))
    while pending:
        part = pending.pop()
        yield part
        pending.extend(get_args(part))


def _hides_large_field(annotation: Any) -> bool:
    return any(
        isinstance(part, LargeField)
        or (
            isinstance(part, type)
            and issubclass(part, LazyFieldsMixin)
            and bool(LazyFieldPlan.for_class(part).paths)
        )
        for part in _annotation_parts(annotation)
    )


def declares_large_field(model_cls: type[BaseModel]) -> bool:
    """Whether any field of `model_cls` is marked with `LargeField`, at any depth of its type."""
    return any(
        any(isinstance(item, LargeField) for item in field.metadata)
        or any(
            isinstance(part, LargeField) for part in _annotation_parts(field.annotation)
        )
        for field in model_cls.model_fields.values()
    )


class LargeValueSource(Protocol):
    """Where a detached record's large values are kept. Implemented by `ModelCache`.

    `owner` is the token in `DetachedValues.owner`. It stands for one detached record
    and its copies, and tells that record apart from a newer load of the same file.
    """

    def large_values_for(
        self, path: Path, owner: object
    ) -> Mapping[FieldPath, Any] | None:
        """The record's large values if they're in memory; marks them recently used."""
        ...

    def store_restored_values(
        self,
        path: Path,
        owner: object,
        identity: FileIdentity,
        values: Mapping[FieldPath, Any],
        size: int,
    ) -> bool:
        """Keep values re-read from the file; False if they weren't kept."""
        ...

    def is_current_entry(self, path: Path, owner: object) -> bool:
        """Whether the source still holds this record for `path`."""
        ...

    def drop_entry(self, path: Path, owner: object) -> None:
        """Stop holding this record, if the source holds it for `path`."""
        ...


@dataclass(frozen=True)
class DetachedValues:
    """The large values `detach_large_values` took out of a record."""

    values: Mapping[FieldPath, Any]
    size: int
    """Estimated in-memory bytes of `values`."""
    owner: object
    """Identifies the record (and its copies) to the `LargeValueSource`."""


@dataclass(frozen=True, slots=True)
class _LocalValues:
    identity: FileIdentity
    """The identity of the file version the values were read from."""
    values: Mapping[FieldPath, Any]


class _LazyRoot:
    """What every lazy model of one detached record shares, copies included.

    It never references a record, so a detached record forms no reference cycle and is
    freed as soon as its last holder drops it.
    """

    __slots__ = (
        "detached_paths",
        "identity",
        "local",
        "path",
        "revalidate",
        "source",
    )

    def __init__(
        self,
        path: Path,
        identity: FileIdentity,
        source: LargeValueSource,
        revalidate: Callable[[Any], BaseModel],
        detached_paths: tuple[FieldPath, ...],
    ) -> None:
        self.path = path
        self.identity = identity
        self.source = source
        self.revalidate = revalidate
        self.detached_paths = detached_paths
        # Values restored after the source stopped holding the record. They belong to
        # whoever still holds it. Only ever replaced whole, so readers see all or none.
        self.local: _LocalValues | None = None

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        return self


@dataclass(frozen=True, slots=True)
class _LazyState:
    """One lazy model's view of its detached record."""

    root: _LazyRoot
    prefix: FieldPath
    """This model's path in the record: `()` for the record itself."""
    missing: frozenset[str]
    """Field names taken out of this model's `__dict__`."""
    summary: Mapping[str, Any]
    """Summary values computed from the complete record."""
    scrubbed: Mapping[str, FieldPath]
    """Private attributes removed because they held a detached value, and its path."""

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        return self


def _lazy_state(obj: object) -> "_LazyState | None":
    try:
        private = object.__getattribute__(obj, "__pydantic_private__")
    except AttributeError:
        return None
    if not private:
        return None
    return private.get("_lazy")


def _lazy_instances(
    record: "LazyFieldsMixin",
) -> list[tuple[FieldPath, "LazyFieldsMixin"]]:
    """The record and each lazy model nested in it, with its path; the record first."""
    found: list[tuple[FieldPath, LazyFieldsMixin]] = []
    seen: set[int] = set()
    pending: list[tuple[FieldPath, LazyFieldsMixin]] = [((), record)]
    while pending:
        prefix, instance = pending.pop()
        if id(instance) in seen:
            continue
        seen.add(id(instance))
        found.append((prefix, instance))
        for name in LazyFieldPlan.for_class(type(instance)).nested_names:
            nested = instance.__dict__.get(name)
            if isinstance(nested, LazyFieldsMixin):
                pending.append(((*prefix, name), nested))
    return found


def detach_large_values(
    record: "LazyFieldsMixin",
    *,
    source: LargeValueSource,
    path: Path,
    identity: FileIdentity,
    revalidate: Callable[[Any], BaseModel],
) -> DetachedValues:
    """Take the large values out of a freshly loaded record, before anyone else sees it.

    Summary values are computed first, from the complete record. Real `None` values
    stay in the record. Private attributes holding the same objects as detached values
    are removed too, so the values can be freed.

    Args:
        record: the record, not yet shared with any other code.
        source: where the values will be kept, and asked for later.
        path: the file the record was parsed from.
        identity: the identity of the bytes the record was parsed from.
        revalidate: turns the file's parsed JSON into a fresh record, exactly as a load
            does. Used to restore evicted values.
    """
    instances = _lazy_instances(record)
    summaries = [
        {s.name: s.compute(instance) for s in _plan_of(instance).summaries}
        for _, instance in instances
    ]
    values: dict[FieldPath, Any] = {}
    removed_names: list[frozenset[str]] = []
    for prefix, instance in instances:
        own = instance.__dict__
        removed = [
            name for name in _plan_of(instance).large_names if own.get(name) is not None
        ]
        for name in removed:
            values[(*prefix, name)] = own.pop(name)
        removed_names.append(frozenset(removed))

    lazy_root = _LazyRoot(path, identity, source, revalidate, tuple(values))
    if values or any(summaries):
        # Scalars are shared singletons (True, small ints), so matching them by identity
        # would remove unrelated attributes such as `_readonly`.
        paths_by_id = {
            id(value): value_path
            for value_path, value in values.items()
            if not isinstance(value, (bool, int, float))
        }
        for (prefix, instance), summary, removed in zip(
            instances, summaries, removed_names
        ):
            scrubbed = _scrub_references(instance, paths_by_id)
            # The record always gets a state, so `mutable_copy` sees it is detached.
            if not prefix or removed or summary or scrubbed:
                instance._lazy = _LazyState(
                    lazy_root, prefix, removed, summary, scrubbed
                )
    return DetachedValues(
        values=values, size=approx_value_size(values), owner=lazy_root
    )


def _plan_of(instance: BaseModel) -> LazyFieldPlan:
    return LazyFieldPlan.for_class(type(instance))


def _scrub_references(
    instance: BaseModel, paths_by_id: Mapping[int, FieldPath]
) -> dict[str, FieldPath]:
    """Remove non-field attributes that hold a detached value; returns each one's path.

    Declared private attributes live in `__pydantic_private__`. Undeclared underscore
    names that validators set (like `TaskRun._last_validated_input`) live in `__dict__`.
    """
    scrubbed: dict[str, FieldPath] = {}
    private = instance.__pydantic_private__ or {}
    for name, value in list(private.items()):
        if name != "_lazy" and id(value) in paths_by_id:
            scrubbed[name] = paths_by_id[id(value)]
            del private[name]
    fields = type(instance).model_fields
    own = instance.__dict__
    for name, value in list(own.items()):
        if name not in fields and id(value) in paths_by_id:
            scrubbed[name] = paths_by_id[id(value)]
            del own[name]
    return scrubbed


def _tree_values(state: _LazyState, reading: FieldPath) -> Mapping[FieldPath, Any]:
    """Every detached value of `state`'s record, from wherever they are now.

    `reading` names the value the caller wants, for the error message.
    """
    root = state.root
    if root.local is not None:
        return root.local.values
    values = root.source.large_values_for(root.path, root)
    if values is not None:
        return values

    values, identity = _restore(root, reading)
    if identity != root.identity:
        cache_logger.debug(
            "%s changed on disk after it was cached; reading its large fields from "
            "the new version, alongside the other fields from the cached version",
            root.path,
        )
        root.source.drop_entry(root.path, root)
        root.local = _LocalValues(identity, values)
    elif not root.source.store_restored_values(
        root.path, root, identity, values, approx_value_size(values)
    ):
        # Kept on the record only after the source has dropped it: values kept on a
        # record the source still holds would grow it past its budget, uncounted.
        if not root.source.is_current_entry(root.path, root):
            root.local = _LocalValues(identity, values)
    cache_logger.debug("Restored the large fields of %s from disk", root.path)
    return values


def _restore(
    root: _LazyRoot, reading: FieldPath
) -> tuple[dict[FieldPath, Any], FileIdentity]:
    """Re-read and re-validate the file; returns its detached values and identity.

    Uses the same validation as a load, so load-time transforms apply to the values
    exactly as they did when the record was cached.
    """
    field = ".".join(reading)
    try:
        with open(root.path, "r", encoding="utf-8") as file:
            identity = FileIdentity.from_stat(os.fstat(file.fileno()))
            raw = json.loads(file.read())
        fresh = root.revalidate(raw)
    except FileNotFoundError as e:
        raise LargeFieldUnavailableError(
            root.path, field, "the file no longer exists"
        ) from e
    except OSError as e:
        raise LargeFieldUnavailableError(
            root.path, field, "the file can't be read"
        ) from e
    except json.JSONDecodeError as e:
        raise LargeFieldUnavailableError(
            root.path, field, "the file isn't valid JSON"
        ) from e
    except ValueError as e:
        raise LargeFieldUnavailableError(
            root.path, field, "the file no longer holds a valid record"
        ) from e

    values: dict[FieldPath, Any] = {}
    for value_path in root.detached_paths:
        container: Any = fresh
        for depth, name in enumerate(value_path[:-1]):
            container = getattr(container, name)
            if container is None:
                missing = ".".join(value_path[: depth + 1])
                raise LargeFieldUnavailableError(
                    root.path,
                    field,
                    f"'{missing}' is no longer set in the file; reload the record",
                )
        values[value_path] = getattr(container, value_path[-1])
    return values, identity


def _complete_parts(
    model: BaseModel,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """`model`'s `__dict__` and private attributes as they'd be with nothing detached.

    A model without lazy state gets its own back. Otherwise these are new dicts:
    missing fields filled in, in field order (so dumps keep their key order), scrubbed
    attributes put back, and `_lazy` cleared. May read the file.
    """
    state = _lazy_state(model)
    own = model.__dict__
    private = model.__pydantic_private__
    if state is None:
        return own, private

    absent = [name for name in state.missing if name not in own]
    values: Mapping[FieldPath, Any] = {}
    if absent:
        values = _tree_values(state, (*state.prefix, absent[0]))
    elif state.scrubbed:
        values = _tree_values(state, next(iter(state.scrubbed.values())))

    fields: dict[str, Any] = {}
    for name in type(model).model_fields:
        if name in own:
            fields[name] = own[name]
        elif name in state.missing:
            fields[name] = values[(*state.prefix, name)]
    for name, value in own.items():
        fields.setdefault(name, value)

    restored_private = {
        name: value
        for name, value in (private or {}).items()
        if value is not PydanticUndefined
    }
    restored_private["_lazy"] = None
    private_names = type(model).__private_attributes__
    for name, value_path in state.scrubbed.items():
        target = restored_private if name in private_names else fields
        target.setdefault(name, values[value_path])
    return fields, restored_private


def _read_detached_values(record: "LazyFieldsMixin") -> None:
    """Read every detached value in `record` that its models are missing, if any.

    pydantic wraps errors raised while serializing, so reading first makes a direct dump
    raise `LargeFieldUnavailableError` itself. The values read are kept as usual.
    """
    for _, instance in _lazy_instances(record):
        state = _lazy_state(instance)
        if state is None:
            continue
        absent = next((n for n in state.missing if n not in instance.__dict__), None)
        if absent is not None:
            _tree_values(state, (*state.prefix, absent))


def _instance_with(
    model: M,
    fields: dict[str, Any],
    private: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> M:
    """A new instance of `model`'s class holding these parts, built without validation."""
    cls = type(model)
    instance = cls.__new__(cls)
    object.__setattr__(instance, "__dict__", fields)
    object.__setattr__(instance, "__pydantic_extra__", extra)
    object.__setattr__(
        instance, "__pydantic_fields_set__", set(model.__pydantic_fields_set__)
    )
    object.__setattr__(instance, "__pydantic_private__", private)
    return instance


def _same_field_values(
    first: Mapping[str, Any], second: Mapping[str, Any], names: Iterable[str]
) -> bool:
    for name in names:
        if (name in first) != (name in second):
            return False
        if name in first and first[name] != second[name]:
            return False
    return True


def reload_path_for_editable_copy(model: BaseModel) -> Path | None:
    """The file to reload an editable copy of `model` from, instead of copying it.

    That is the file of a detached record that changed on disk since it was loaded.
    None for any other model, and when the file is gone: there is nothing to reload,
    and copying the record gives one consistent version of it.

    Raises:
        LargeFieldUnavailableError: if the file is gone and the record already read its
            large fields from a newer version of the file, so a copy would mix versions.
    """
    state = _lazy_state(model)
    if state is None or state.prefix:
        return None
    root = state.root
    current = FileIdentity.from_path(root.path)
    if current is None:
        if root.local is not None and root.local.identity != root.identity:
            raise LargeFieldUnavailableError(
                root.path,
                ".".join(root.detached_paths[0]),
                "the file no longer exists, and the record's large fields were read "
                "from a newer version of it than its other fields",
            )
        return None
    return None if current == root.identity else root.path


_NUMBER_TYPES = frozenset({float, int, bool})


def approx_value_size(value: Any) -> int:
    """Estimated in-memory bytes of `value`, for decoded JSON-like values and models.

    Walks containers with an explicit stack, so deeply nested values are safe.
    """
    total = 0
    pending: list[Any] = [value]
    while pending:
        item = pending.pop()
        # The exact JSON types first. They are nearly every item in a trace or an
        # embedding, and the isinstance chain below tests several types per item.
        kind = type(item)
        if kind is str:
            total += 49 + len(item)
        elif kind is dict:
            total += 64 + 40 * len(item)
            pending.extend(item.keys())
            pending.extend(item.values())
        elif kind is list:
            total += 56 + 8 * len(item)
            # An embedding vector is thousands of floats: size them in one C-level pass.
            if set(map(type, item)) <= _NUMBER_TYPES:
                total += 28 * len(item)
            else:
                pending.extend(item)
        elif kind is float or kind is int or kind is bool or item is None:
            total += 28
        elif isinstance(item, str):
            total += 49 + len(item)
        elif isinstance(item, (int, float)):
            total += 28
        elif isinstance(item, (list, tuple)):
            total += 56 + 8 * len(item)
            pending.extend(item)
        elif isinstance(item, dict):
            total += 64 + 40 * len(item)
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, bytes):
            total += 33 + len(item)
        elif isinstance(item, BaseModel):
            total += 56
            pending.extend(item.__dict__.values())
        else:
            total += sys.getsizeof(item)
    return total


_VALIDATOR_SCHEMA_TYPES = ("function-after", "function-before", "function-wrap")


def _without_own_serializer(schema: Any, cls: type) -> Any:
    """A core schema with the serializer of `cls`'s own model node removed.

    Model validators wrap the model node in function schemas, and pydantic passes the
    outermost of them to `__get_pydantic_json_schema__`, so the model node can sit below.
    Only the nodes on the way down are copied; `schema` itself is never modified.
    """
    if schema["type"] == "model" and schema["cls"] is cls:
        return {key: value for key, value in schema.items() if key != "serialization"}
    if schema["type"] in _VALIDATOR_SCHEMA_TYPES and "schema" in schema:
        return {**schema, "schema": _without_own_serializer(schema["schema"], cls)}
    return schema


class _NotLoaded:
    def __repr__(self) -> str:
        return "<not loaded>"


class LazyFieldsMixin(BaseModel):
    """Base for models with `LargeField` fields or nested lazy models. Put it first in the bases.

    Records built in memory, or loaded with the model cache off, behave exactly like
    plain models. On a record the cache detached, reading a large field, dumping,
    copying, comparing, iterating and pickling all see every field, reading the file
    when its values were evicted.
    """

    model_config = ConfigDict(ignored_types=(SummaryValue,))

    _lazy: _LazyState | None = PrivateAttr(default=None)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        own_serializer = LazyFieldsMixin.__pydantic_decorators__.model_serializers[
            _SERIALIZER_NAME
        ].func
        if any(
            serializer.func is not own_serializer
            for serializer in cls.__pydantic_decorators__.model_serializers.values()
        ):
            raise TypeError(
                f"{cls.__name__} defines a model_serializer, but LazyFieldsMixin needs "
                "its own to fill in detached fields. Use field serializers instead."
            )
        if cls.__pydantic_complete__:
            LazyFieldPlan.for_class(cls)

    def has_unloaded_fields(self) -> bool:
        """Whether any large value of this record, nested models included, is detached."""
        for _, instance in _lazy_instances(self):
            state = _lazy_state(instance)
            if state is not None and any(
                name not in instance.__dict__ for name in state.missing
            ):
                return True
        return False

    if not TYPE_CHECKING:
        # Python calls this only after normal lookup fails, so present fields cost
        # nothing extra. Kept from type checkers, like pydantic's own, so they don't
        # treat every attribute as Any.
        def __getattr__(self, name: str) -> Any:
            if not name.startswith("_"):
                state = _lazy_state(self)
                if state is not None and name in state.missing:
                    value_path = (*state.prefix, name)
                    return _tree_values(state, value_path)[value_path]
                return super().__getattr__(name)
            try:
                return super().__getattr__(name)
            except AttributeError:
                state = _lazy_state(self)
                if state is None or name not in state.scrubbed:
                    raise
                value_path = state.scrubbed[name]
                return _tree_values(state, value_path)[value_path]

    @model_serializer(mode="wrap")
    def _serialize_with_large_fields(
        self, handler: SerializerFunctionWrapHandler
    ) -> Any:
        state = _lazy_state(self)
        if state is None or all(name in self.__dict__ for name in state.missing):
            return handler(self)
        # A short-lived complete stand-in, so the shared record is never written to.
        fields, private = _complete_parts(self)
        return handler(_instance_with(self, fields, private, self.__pydantic_extra__))

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler, /
    ) -> JsonSchemaValue:
        # A wrap model_serializer makes pydantic describe this model's serialized form
        # as any value. Without it, the schema comes from the fields, as it does for a
        # model without the mixin. Nested models keep their own serializers.
        return handler(_without_own_serializer(core_schema, cls))

    if not TYPE_CHECKING:
        # Kept from type checkers, so callers see pydantic's typed signatures.
        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            _read_detached_values(self)
            return super().model_dump(**kwargs)

        def model_dump_json(self, **kwargs: Any) -> str:
            _read_detached_values(self)
            return super().model_dump_json(**kwargs)

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        copied = super().model_copy(update=update, deep=deep)
        state = _lazy_state(copied)
        if update and state is not None and state.summary:
            plan = _plan_of(self)
            # Summary values are computed from large fields and nested lazy models.
            if not update.keys().isdisjoint((*plan.large_names, *plan.nested_names)):
                copied._lazy = replace(state, summary={})
        return copied  # type: ignore[return-value]

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        if _lazy_state(self) is None:
            return super().__deepcopy__(memo)  # type: ignore[return-value]
        memo = {} if memo is None else memo
        fields, private = _complete_parts(self)
        return _instance_with(
            self,
            deepcopy(fields, memo),
            deepcopy(private, memo),
            deepcopy(self.__pydantic_extra__, memo),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseModel):
            return NotImplemented
        if _lazy_state(self) is None and _lazy_state(other) is None:
            return super().__eq__(other)
        if type(self) is not type(other):
            return False
        # Compares what pydantic does: field values, private attributes and extras.
        self_fields, self_private = _complete_parts(self)
        other_fields, other_private = _complete_parts(other)
        if (
            self_private != other_private
            or self.__pydantic_extra__ != other.__pydantic_extra__
        ):
            return False
        return _same_field_values(self_fields, other_fields, type(self).model_fields)

    def __iter__(self) -> Generator[tuple[str, Any], None, None]:
        if _lazy_state(self) is None:
            yield from super().__iter__()
            return
        fields, _ = _complete_parts(self)
        yield from ((k, v) for k, v in fields.items() if not k.startswith("_"))
        if self.__pydantic_extra__:
            yield from self.__pydantic_extra__.items()

    def __getstate__(self) -> dict[Any, Any]:
        if _lazy_state(self) is None:
            return super().__getstate__()
        fields, private = _complete_parts(self)
        return {
            "__dict__": fields,
            "__pydantic_extra__": self.__pydantic_extra__,
            "__pydantic_fields_set__": self.__pydantic_fields_set__,
            "__pydantic_private__": private,
        }

    def __repr_args__(self) -> Iterable[tuple[str | None, Any]]:
        yield from super().__repr_args__()
        state = _lazy_state(self)
        if state is None:
            return
        for name in type(self).model_fields:
            if name in state.missing and name not in self.__dict__:
                yield name, _NotLoaded()
