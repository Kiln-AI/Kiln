"""Shared storage for user-authored code kept in a sibling `.py` file.

Two Kiln datamodels store a user's Python source beside their `.kiln` file
instead of inline in the JSON: `CodeTool.code` -> `tool.py` and
`CodeEvalProperties.code` -> `scorer.py`. Both need the same behavior — read the
sibling file into the in-memory `code` string on load (before field validation),
and write it back out on disk-save while omitting `code` from the `.kiln` JSON.

This module is that single, shared mechanism, called from each model's thin
before-validator / wrap-serializer. It is also the ONE audited place for path
containment: each caller passes a fixed, bare filename (a module constant), and
the file is only ever `<folder-from-context>/<filename>` — no traversal, no
absolute paths, and never an import/exec of the file. stdlib-only.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


def _require_bare_filename(filename: str) -> None:
    """Guard the containment invariant: `filename` must be a bare filename.

    Callers only ever pass module constants (`tool.py` / `scorer.py`), so this
    never triggers in practice. It exists so this module remains the audited
    boundary: a sibling file is always a single path component joined to the
    artifact folder, never something that could escape it (a separator, a parent
    reference, or an absolute path).

    Checked host-OS-agnostically: the name must be a bare component under BOTH
    POSIX and Windows semantics, so a backslash is rejected even on POSIX (where
    `Path` would treat it as a literal) and a forward slash even on Windows.
    """
    if (
        not filename
        or filename != PurePosixPath(filename).name
        or filename != PureWindowsPath(filename).name
    ):
        raise ValueError(
            f"Code sibling filename must be a bare filename, got: {filename!r}"
        )


def read_code_from_sibling_file(
    data: Any,
    ctx: dict[str, Any],
    *,
    filename: str,
    kiln_filename: str,
    model_label: str,
) -> Any:
    """Inject `code` from the sibling `.py` file during a file load.

    Intended as the body of a `mode="before"` model validator. When the model is
    being loaded from disk (`ctx["loading_from_file"]`), `data` is a dict, and it
    does not already carry a `code` key, read `<source_dir>/<filename>` into a
    copy of `data` as `data["code"]` so the model's existing code validators run
    against the loaded string unchanged.

    Copy-on-write: the caller's `data` dict is never mutated.

    Lenient by design: if `data` already carries `code` (an inline `.kiln` or an
    in-memory dict), it is used as-is and no file is read. Any other case (not a
    dict, not loading from file) passes `data` through unchanged.

    Args:
        data: The raw before-validation input (a dict when loading from file).
        ctx: The pydantic validation context (`info.context or {}`).
        filename: Bare sibling filename, e.g. `tool.py` / `scorer.py`.
        kiln_filename: The `.kiln` filename used in the unreadable-file error,
            e.g. `code_tool.kiln` / `eval_config.kiln`.
        model_label: Model name used in the missing-`source_dir` error.

    Raises:
        ValueError: If `source_dir` is missing from the load context, or the
            sibling file cannot be read.
    """
    _require_bare_filename(filename)
    if ctx.get("loading_from_file") and isinstance(data, dict) and "code" not in data:
        src = ctx.get("source_dir")
        if src is None:
            raise ValueError(
                f"Cannot load {model_label}: source_dir missing from load context"
            )
        code_path = Path(src) / filename
        try:
            # Binary read + explicit decode: avoid universal-newline translation
            # (Path.read_text would collapse CRLF/CR to LF), so the file's exact
            # bytes round-trip and the byte-for-byte contract holds (functional
            # spec §1.1). OSError still surfaces the missing/unreadable message
            # below; a non-UTF-8 file still raises UnicodeDecodeError, unchanged.
            code = code_path.read_bytes().decode("utf-8")
        except OSError as e:
            raise ValueError(
                f"{kiln_filename} at {src} is missing its {filename} "
                f"(expected at {code_path}): {e}"
            ) from e
        # Copy-on-write: don't mutate the caller's input dict.
        data = {**data, "code": code}
    return data


def write_code_to_sibling_file(
    data: dict[str, Any],
    ctx: dict[str, Any],
    *,
    filename: str,
    code: str,
) -> dict[str, Any]:
    """Write `code` to the sibling `.py` file during a disk-save, drop it from JSON.

    Intended as the tail of a `mode="wrap"` model serializer (the caller passes
    the already-serialized `data` dict from the wrap handler). When saving to
    disk (`ctx` carries `save_attachments` + `dest_path`), write `code` verbatim
    (UTF-8) to `<dest_path>/<filename>` and return a copy of `data` without the
    `code` key. Without that context — normal `model_dump` / API responses — the
    original `data` is returned unchanged and no file is written, so the API
    contract keeps returning `code`.

    Copy-on-write: the caller's `data` dict is never mutated.

    Args:
        data: The serialized model dict from the wrap handler.
        ctx: The pydantic serialization context (`info.context or {}`).
        filename: Bare sibling filename, e.g. `tool.py` / `scorer.py`.
        code: The in-memory source string to persist.

    Raises:
        ValueError: If `dest_path` is present but is not an existing directory.
    """
    _require_bare_filename(filename)
    if ctx.get("save_attachments") and ctx.get("dest_path"):
        dest = Path(ctx["dest_path"])
        if not dest.is_dir():
            raise ValueError(
                f"dest_path must be an existing directory when saving code, got: {dest}"
            )
        # Binary write of the UTF-8 bytes: avoid universal-newline translation
        # (Path.write_text would rewrite LF to os.linesep), so the exact bytes
        # are persisted, save is byte-idempotent, and the round-trip is
        # byte-for-byte (functional spec §1.1 / §2.1), cross-platform.
        (dest / filename).write_bytes(code.encode("utf-8"))
        # Copy-on-write: code lives in the sibling file, not the .kiln JSON.
        data = {key: value for key, value in data.items() if key != "code"}
    return data
