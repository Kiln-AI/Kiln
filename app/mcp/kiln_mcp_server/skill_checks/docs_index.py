"""The copied Kiln help articles under `references/docs/`, and their generated
index `references/docs/docs_index.md`."""

from pathlib import Path, PurePosixPath

from kiln_mcp_server.skill_checks.front_matter import read_front_matter
from kiln_mcp_server.skill_checks.knowledge_load import fence_marked
from kiln_mcp_server.skill_checks.knowledge_schema import BUILD_COMMAND, Problem
from kiln_mcp_server.skill_files import list_tree

DOCS_FOLDER = "references/docs/"
DOCS_INDEX_PATH = "references/docs/docs_index.md"
PUBLIC_DOCS_URL = "https://docs.kiln.tech/docs/"
DOCS_INDEX_RULE = "docs-index"

_HEADER = """\
# Kiln help articles

Copies of Kiln's public help pages. When you point the user at a page, give them the public URL.

| Article | Public URL | What it covers |
|---|---|---|
"""


def online_url_for(path: str) -> str:
    """The public URL of the help article at skill path `path`: for example
    `references/docs/evals.md` -> `https://docs.kiln.tech/docs/evals`, and
    `references/docs/guides/README.md` -> `https://docs.kiln.tech/docs/guides`
    (`references/docs/README.md` -> `https://docs.kiln.tech/docs/`).

    Raises ValueError for a path outside `references/docs/` or not ending in `.md`.
    """
    if not path.startswith(DOCS_FOLDER) or not path.endswith(".md"):
        raise ValueError(f"not a help article path: {path}")
    page = path[len(DOCS_FOLDER) : -len(".md")]
    folder, _, name = page.rpartition("/")
    return PUBLIC_DOCS_URL + (folder if name == "README" else page)


def _articles(tree_root: Path) -> list[str]:
    return sorted(
        key
        for key in list_tree(tree_root)
        if key.startswith(DOCS_FOLDER)
        and key.endswith(".md")
        and key != DOCS_INDEX_PATH
    )


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _title(body: str, path: str) -> str:
    for line, fenced in fence_marked(body):
        if not fenced and line.startswith("# "):
            return line[2:].strip()
    return PurePosixPath(path).stem


def render_docs_index(tree_root: Path) -> str:
    """The whole text of `docs_index.md` for the skill folder `tree_root`: one
    row per help article, sorted by path."""
    rows = []
    for path in _articles(tree_root):
        text = (tree_root / path).read_bytes().decode("utf-8", errors="replace")
        front = read_front_matter(text)
        description = front.data.get("description")
        cells = (
            f"[{_cell(_title(front.body, path))}]({path})",
            online_url_for(path),
            _cell(description) if isinstance(description, str) else "",
        )
        rows.append("| " + " | ".join(cells) + " |\n")
    return _HEADER + "".join(rows)


def _wants_index(tree_root: Path) -> bool:
    return bool(_articles(tree_root)) or (tree_root / DOCS_INDEX_PATH).is_file()


def write_docs_index(tree_root: Path) -> Path | None:
    """Rewrite `docs_index.md` when the skill has help articles. Returns the
    file when it changed."""
    if not _wants_index(tree_root):
        return None
    path = tree_root / DOCS_INDEX_PATH
    rendered = render_docs_index(tree_root).encode("utf-8")
    if path.is_file() and path.read_bytes() == rendered:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)
    return path


def docs_index_problems(tree_root: Path) -> list[Problem]:
    """A problem when the skill has help articles and `docs_index.md` is
    missing or differs from `render_docs_index`."""
    if not _wants_index(tree_root):
        return []
    path = tree_root / DOCS_INDEX_PATH
    if path.is_file() and path.read_bytes() == render_docs_index(tree_root).encode(
        "utf-8"
    ):
        return []
    state = "is stale" if path.is_file() else "is missing"
    return [
        Problem(DOCS_INDEX_RULE, DOCS_INDEX_PATH, f"{state}; run `{BUILD_COMMAND}`")
    ]
