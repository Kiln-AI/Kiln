"""The Kiln skill tree shipped as package data: its file index, the rules that
turn an agent's `path` argument into a file, and the text served for a file."""

import functools
import importlib.resources
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    from importlib.resources.abc import Traversable
else:
    from importlib.abc import Traversable

DEFAULT_ORIGIN = "http://localhost:8757"
API_DOCS_FOLDER = "references/knowledge/api_docs"
API_CATALOGUE_SUFFIX = "_api_list.md"
API_CATALOGUE_INDEX_NAME = "api_index.md"
API_CATALOGUE_INDEX_PATH = f"{API_DOCS_FOLDER}/{API_CATALOGUE_INDEX_NAME}"
# The one hand-written file of the generated API reference folder.
API_RULES_PATH = f"{API_DOCS_FOLDER}/calling_the_kiln_api.md"

ROOT_FILE = "SKILL.md"
_RAW_MAX_CHARS = 200

HINT = "Give a path relative to the skill root, exactly as the skill's instructions wrote it, for example `references/knowledge/specs_and_evals.md`. Omit the path to read the skill's instructions."
E_ABS = "Refused: `{raw}` is an absolute path. " + HINT
E_UP = (
    "Refused: `{raw}` leaves the skill root. `..` is not allowed in a skill path. "
    + HINT
)
E_SCHEME = "Refused: `{raw}` is not a skill path. " + HINT
E_SKILL = (
    "Refused: `{raw}` names another skill. This tool serves one skill, `kiln`. " + HINT
)
E_CTRL = "Refused: the path holds a control character. " + HINT
E_MISS_END = "Copy a path exactly as the skill's instructions wrote it."
E_NO_SKILL_MD = "Kiln skill files are missing from the package (no SKILL.md)"

_QUOTES = ("`", "'", '"')
_SKILL_SCHEME = "skill://"
_SKILL_NAME = "kiln"
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")


@dataclass(frozen=True)
class SkillIndex:
    files: Mapping[str, Traversable]
    """Key: POSIX path from the skill root, such as `references/knowledge/rag.md`."""
    folders: frozenset[str]
    """Every ancestor folder of every file; `""` is the root."""


class SkillPathError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _shipped_root() -> Traversable:
    return importlib.resources.files("kiln_mcp_server").joinpath("skill")


def _walk(node: Traversable, prefix: str, files: dict[str, Traversable]) -> None:
    for child in node.iterdir():
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        key = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            _walk(child, key, files)
        elif child.is_file():
            files[key] = child


def list_tree(root: Traversable) -> dict[str, Traversable]:
    """Every file under `root` that the skill serves, keyed by its POSIX path
    from `root`. Hidden names and `__pycache__` are skipped."""
    files: dict[str, Traversable] = {}
    if root.is_dir():
        _walk(root, "", files)
    return files


def _parent(key: str) -> str:
    return key.rpartition("/")[0]


def build_index(root: Traversable | None = None) -> SkillIndex:
    """Index every file under `root` (default: the shipped skill tree).

    Raises RuntimeError when the tree has no root `SKILL.md`.
    """
    root = root if root is not None else _shipped_root()
    files = list_tree(root)
    if ROOT_FILE not in files:
        raise RuntimeError(E_NO_SKILL_MD)

    folders = {""}
    for key in files:
        folder = _parent(key)
        while folder and folder not in folders:
            folders.add(folder)
            folder = _parent(folder)
    return SkillIndex(
        files={key: files[key] for key in sorted(files)},
        folders=frozenset(folders),
    )


@functools.lru_cache(maxsize=1)
def get_index() -> SkillIndex:
    """The index of the shipped skill tree, built once per process."""
    return build_index()


def _clean_raw(raw: str) -> str:
    return _CONTROL_CHARS.sub("", raw.replace("`", ""))[:_RAW_MAX_CHARS]


def _refuse(template: str, raw: str) -> SkillPathError:
    return SkillPathError(template.format(raw=_clean_raw(raw)))


def resolve_path(raw: str | None, index: SkillIndex) -> str | None:
    """Turn the agent's `path` argument into a key of `index.files`.

    Returns None for the root instructions. Raises SkillPathError with the
    text for the agent when the path is refused or names no file.
    """
    if raw is None:
        return None
    p = raw.strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in _QUOTES:
        p = p[1:-1].strip()
    if p == "":
        return None
    if _CONTROL_CHARS.search(p):
        raise SkillPathError(E_CTRL)

    if p.lower().startswith(_SKILL_SCHEME):
        skill_name, _, p = p[len(_SKILL_SCHEME) :].partition("/")
        if skill_name.lower() != _SKILL_NAME:
            raise _refuse(E_SKILL, raw)
    elif _URL_SCHEME.match(p):
        raise _refuse(E_SCHEME, raw)

    p = p.replace("\\", "/").split("#", 1)[0].split("?", 1)[0]
    if p.startswith(("/", "~")) or _WINDOWS_DRIVE.match(p):
        raise _refuse(E_ABS, raw)

    segments = [segment for segment in p.split("/") if segment not in ("", ".")]
    if ".." in segments:
        raise _refuse(E_UP, raw)

    key = "/".join(segments)
    if key in ("", ROOT_FILE):
        return None
    if key in index.files:
        return key
    raise SkillPathError(_not_found_message(raw, key, index))


def _nearest_folder(key: str, index: SkillIndex) -> str:
    segments = key.split("/")
    for length in range(len(segments), 0, -1):
        candidate = "/".join(segments[:length])
        if candidate in index.folders:
            return candidate
    return ""


def _file_lines(folder: str, index: SkillIndex) -> list[str]:
    files = [key for key in index.files if _parent(key) == folder]
    if folder != API_DOCS_FOLDER:
        return files or ["(none)"]

    # The full listing of endpoint docs would flood the agent's context; the
    # catalogues are the way to find one.
    listed = [
        key
        for key in files
        if key in (API_CATALOGUE_INDEX_PATH, API_RULES_PATH)
        or key.endswith(API_CATALOGUE_SUFFIX)
    ]
    lines = listed or ["(none)"]
    unlisted = len(files) - len(listed)
    if unlisted:
        lines.append(
            f"Plus {unlisted} endpoint docs, not listed. Find an endpoint doc through a catalogue."
        )
    return lines


def _not_found_message(raw: str, key: str, index: SkillIndex) -> str:
    first_line = f"No skill file at `{_clean_raw(raw)}`."
    lowered = key.lower()
    case_match = next((k for k in index.files if k.lower() == lowered), None)
    if case_match is not None:
        first_line += f" Did you mean `{case_match}`?"
    if key in index.folders:
        first_line += f" `{key}` is a folder, not a file."

    folder = _nearest_folder(key, index)
    where = f"`{folder}`" if folder else "the skill root"
    lines = [first_line, f"Files in {where}:", *_file_lines(folder, index)]
    sub_folders = sorted(f for f in index.folders if f and _parent(f) == folder)
    if sub_folders:
        lines.append(f"Folders in {where}:")
        lines.extend(f"{sub_folder}/" for sub_folder in sub_folders)
    lines.append(E_MISS_END)
    return "\n".join(lines)


def read_file(key: str, index: SkillIndex) -> str:
    return index.files[key].read_bytes().decode("utf-8")


def strip_front_matter(text: str) -> str:
    """Drop a leading `---` block and the blank lines after it. Text without a
    closed block is returned unchanged."""
    lines = text.split("\n")
    if lines[0] != "---":
        return text
    for end in range(1, len(lines)):
        if lines[end] == "---":
            rest = lines[end + 1 :]
            while rest and rest[0].strip() == "":
                rest.pop(0)
            return "\n".join(rest)
    return text


def apply_origin(text: str, origin: str) -> str:
    """Point the app links in `text` at `origin`. The skill is written with
    the default address."""
    if origin == DEFAULT_ORIGIN:
        return text
    return text.replace(DEFAULT_ORIGIN, origin)


def read_skill(raw: str | None, origin: str, index: SkillIndex | None = None) -> str:
    """The text served for the agent's `path` argument.

    Raises SkillPathError when the path is refused or names no file.
    """
    index = index if index is not None else get_index()
    key = resolve_path(raw, index)
    if key is None:
        text = strip_front_matter(read_file(ROOT_FILE, index))
    else:
        text = read_file(key, index)
    return apply_origin(text, origin)
