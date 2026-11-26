"""The skill's API reference: the files `openapi2skill` generates from Kiln's
OpenAPI document, with the MCP-blocked operations removed, plus a catalogue
index. Takes the OpenAPI document as a dict; building it is the caller's job."""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from kiln_server.utils.agent_checks import is_mcp_denied

from kiln_mcp_server.skill_checks.docs_index import table_cell
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_NAME,
    API_CATALOGUE_SUFFIX,
    API_DOCS_FOLDER,
    API_RULES_PATH,
)

ALLOWED_METHODS = ("get", "post", "patch", "delete")
GENERATOR_COMMAND: tuple[str, ...] = (sys.executable, "-m", "openapi2skill")

# Files of the folder that a person writes, not the generator: a write keeps
# them, and a diff does not report them.
HAND_WRITTEN_NAMES = frozenset({PurePosixPath(API_RULES_PATH).name})

# The OpenAPI keys of a path item that hold an operation.
_OPERATION_KEYS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)
_COLLISION_WARNINGS = ("Warning: filename collision", "Warning: tag filename collision")
# The generator iterates a set of method names, so without a fixed hash seed
# the order of a path's methods in a catalogue changes from run to run.
_GENERATOR_HASH_SEED = "0"
_UNTAGGED = "Other"
_GENERATOR_TIMEOUT_SECONDS = 300


class ApiReferenceError(Exception):
    """The API reference cannot be generated from this OpenAPI document."""


def endpoint_doc_name(method: str, path: str) -> str:
    """The file name the generator gives the doc of one operation, for example
    `get_api_projects_project_id.md` for `GET /api/projects/{project_id}`."""
    segments = re.sub(r"\{([^}]+)\}", r"\1", path.lstrip("/").lower())
    name = method.lower()
    if segments:
        name += "_" + segments.replace("/", "_")
    return f"{name}.md"


def _operations(spec: Mapping) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, path_item in spec.get("paths", {}).items()
        for method, operation in path_item.items()
        if method in _OPERATION_KEYS
    ]


def _is_blocked(operation: Mapping) -> bool:
    return is_mcp_denied(dict(operation))


def drop_blocked(spec: dict) -> dict:
    """A copy of `spec` without the MCP-blocked operations, and without the
    path items they leave empty.

    Raises ApiReferenceError when an operation that remains has a method that
    `call_kiln_api` cannot send.
    """
    result = copy.deepcopy(spec)
    paths = result.get("paths", {})
    for path in list(paths):
        path_item = paths[path]
        for method in [m for m in path_item if m in _OPERATION_KEYS]:
            if _is_blocked(path_item[method]):
                del path_item[method]
        if not any(key in _OPERATION_KEYS for key in path_item):
            del paths[path]

    unsupported = sorted(
        f"{method.upper()} {path}"
        for path, method, _ in _operations(result)
        if method not in ALLOWED_METHODS
    )
    if unsupported:
        raise ApiReferenceError(
            "call_kiln_api cannot send these operations; block them for MCP or "
            "change their method: " + ", ".join(unsupported)
        )
    return result


def normalise(spec: dict) -> dict:
    """A copy of `spec` with the parts that change at each release fixed."""
    result = copy.deepcopy(spec)
    result.setdefault("info", {})["version"] = "0.0.0"
    return result


def run_generator(
    spec: dict, workdir: Path, *, command: Sequence[str] = GENERATOR_COMMAND
) -> dict[str, bytes]:
    """Run the generator on `spec` inside `workdir` (an empty folder) and
    return its reference files by name, UTF-8 with LF line ends.

    Raises ApiReferenceError when the generator fails, reports a file name
    collision, or writes a different number of endpoint docs than `spec` has
    operations.
    """
    spec_file = workdir / "openapi.json"
    spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = workdir / "out"
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONHASHSEED": _GENERATOR_HASH_SEED}
    try:
        completed = subprocess.run(
            [*command, "--spec", str(spec_file), "--output", str(out)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
            timeout=_GENERATOR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ApiReferenceError(
            f"the generator did not finish in {_GENERATOR_TIMEOUT_SECONDS} s"
        ) from error
    if completed.returncode != 0:
        raise ApiReferenceError(
            f"the generator exited with {completed.returncode}:\n{completed.stderr}"
        )
    collisions = [
        line
        for line in completed.stderr.splitlines()
        if line.startswith(_COLLISION_WARNINGS)
    ]
    if collisions:
        raise ApiReferenceError(
            "two endpoints or two tags get the same file name:\n"
            + "\n".join(collisions)
        )

    # The generator writes into a new folder named by the time it ran.
    outputs = list(out.iterdir()) if out.is_dir() else []
    if len(outputs) != 1:
        raise ApiReferenceError(
            f"expected one output folder from the generator, found {len(outputs)}"
        )
    reference = outputs[0] / "reference"
    if not reference.is_dir():
        raise ApiReferenceError("the generator wrote no reference folder")
    files = {
        path.name: path.read_bytes().decode("utf-8").replace("\r\n", "\n").encode()
        for path in sorted(reference.iterdir())
        if path.is_file()
    }

    endpoint_docs = [name for name in files if not name.endswith(API_CATALOGUE_SUFFIX)]
    operations = _operations(spec)
    if len(endpoint_docs) != len(operations):
        raise ApiReferenceError(
            f"the generator wrote {len(endpoint_docs)} endpoint docs for "
            f"{len(operations)} operations"
        )
    return files


def _tag_order(spec: Mapping) -> list[str]:
    """The order in which the generator lists its catalogues: the spec's tags
    array, then tags no entry of it names, in order of first use."""
    order = [tag["name"] for tag in spec.get("tags", []) if "name" in tag]
    for _, _, operation in _operations(spec):
        tags = operation.get("tags") or [_UNTAGGED]
        if tags[0] not in order:
            order.append(tags[0])
    return order


def catalogue_index(spec: dict, files: Mapping[str, bytes]) -> bytes:
    """The catalogue index: one row per catalogue in `files`, with its area,
    its count of endpoints and the description of its tag."""
    descriptions = {
        tag["name"]: tag.get("description", "")
        for tag in spec.get("tags", [])
        if "name" in tag
    }
    rows: dict[str, str] = {}
    for name in sorted(files):
        if not name.endswith(API_CATALOGUE_SUFFIX):
            continue
        lines = files[name].decode("utf-8").split("\n")
        tag = lines[0].removeprefix("# ").removesuffix(" API")
        table = [line for line in lines if line.startswith("|")]
        endpoints = max(len(table) - 2, 0)
        rows[tag] = (
            f"| `{API_DOCS_FOLDER}/{name}` | {table_cell(tag)} | {endpoints} "
            f"| {table_cell(descriptions.get(tag, ''))} |"
        )

    order = _tag_order(spec)
    ordered = [
        rows[tag]
        for tag in sorted(
            rows, key=lambda t: order.index(t) if t in order else len(order)
        )
    ]
    text = "\n".join(
        [
            "# Kiln API catalogues",
            "",
            "One catalogue per area of the Kiln API. A catalogue lists the "
            "endpoints of its area, each with the file name of its endpoint doc. "
            f"Read an endpoint doc at `{API_DOCS_FOLDER}/<file name>`.",
            "",
            "| Catalogue | Area | Endpoints | What it covers |",
            "|---|---|---|---|",
            *ordered,
            "",
        ]
    )
    return text.encode("utf-8")


def render(
    spec: dict, *, command: Sequence[str] = GENERATOR_COMMAND
) -> dict[str, bytes]:
    """Every file of the API reference folder, by name, for the OpenAPI
    document `spec`. Raises ApiReferenceError (see `drop_blocked` and
    `run_generator`)."""
    prepared = normalise(drop_blocked(spec))
    with tempfile.TemporaryDirectory(prefix="kiln_api_reference_") as workdir:
        files = run_generator(prepared, Path(workdir), command=command)
    files[API_CATALOGUE_INDEX_NAME] = catalogue_index(prepared, files)
    return dict(sorted(files.items()))


def write_folder(files: Mapping[str, bytes], target: Path) -> None:
    """Replace the folder `target` with exactly `files`, plus the hand-written
    files it already holds."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        for name in sorted(HAND_WRITTEN_NAMES - set(files)):
            if (target / name).is_file():
                shutil.copyfile(target / name, staging / name)
        for name, content in files.items():
            (staging / name).write_bytes(content)
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def diff_folder(files: Mapping[str, bytes], target: Path) -> list[str]:
    """How the folder `target` differs from `files`: one sorted line per file,
    `added x.md` (in `files` only), `removed x.md` (in `target` only) or
    `changed x.md`. The hand-written files of `target` are left out."""
    committed = (
        {
            path.name: path
            for path in target.iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and path.name not in HAND_WRITTEN_NAMES
        }
        if target.is_dir()
        else {}
    )
    lines = []
    for name in sorted(set(files) | set(committed)):
        if name not in committed:
            lines.append(f"added {name}")
        elif name not in files:
            lines.append(f"removed {name}")
        elif committed[name].read_bytes() != files[name]:
            lines.append(f"changed {name}")
    return lines
