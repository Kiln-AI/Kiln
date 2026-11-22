"""The copied Kiln help articles under `references/docs/`."""

DOCS_FOLDER = "references/docs/"
DOCS_INDEX_PATH = "references/docs/docs_index.md"
PUBLIC_DOCS_URL = "https://docs.kiln.tech/docs/"


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
