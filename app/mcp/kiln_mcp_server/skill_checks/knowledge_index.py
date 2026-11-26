"""The generated blocks of the two knowledge index files.

A block is the text between two markers in an index file:

    <!-- BEGIN GENERATED: <name> -->
    ...
    <!-- END GENERATED: <name> -->

A person writes the rest of the file. `render_blocks` is a pure function of
the documents, with a fixed sort, so two runs give the same bytes, and the
rule `index` compares it with the files.
"""

import re
from collections.abc import Callable
from pathlib import Path

from kiln_mcp_server.skill_checks.knowledge_load import Document, KnowledgeBase
from kiln_mcp_server.skill_checks.knowledge_schema import (
    INDEX_BLOCKS,
    PLAYBOOK_KINDS,
    LeverMeta,
    PlaybookMeta,
    SmellMeta,
    TechniqueMeta,
)

EMPTY_BLOCK = "None yet."


def _markers(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- BEGIN GENERATED: {re.escape(name)} -->)(.*?)"
        rf"(<!-- END GENERATED: {re.escape(name)} -->)",
        re.DOTALL,
    )


def read_block(text: str, name: str) -> str | None:
    """The text between the markers of block `name`, or None when the file
    has no such block."""
    match = _markers(name).search(text)
    return match.group(2) if match else None


def replace_block(text: str, name: str, content: str) -> str:
    """`text` with the block `name` set to `content`. Text outside the
    markers is kept byte for byte."""
    return _markers(name).sub(
        lambda m: m.group(1) + content + m.group(3), text, count=1
    )


def _shapes(applies_to: str | list[str]) -> str:
    return applies_to if isinstance(applies_to, str) else ", ".join(applies_to)


def _path(doc: Document) -> str:
    return f"`{doc.path}`"


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return f"\n{EMPTY_BLOCK}\n"
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]
    return "\n" + "\n".join(lines) + "\n"


def _documents(kb: KnowledgeBase, kind: str) -> list[Document]:
    """The documents of `kind` whose front matter parsed, sorted by id. A
    document with bad front matter has no row: the check reports it."""
    return sorted((d for d in kb.by_kind(kind) if d.meta), key=lambda d: d.id)


def _levers(kb: KnowledgeBase) -> str:
    rows = []
    for doc in _documents(kb, "levers"):
        meta = doc.meta
        assert isinstance(meta, LeverMeta)
        api_docs = ", ".join(f"`{path}`" for path in meta.api_docs) or "none"
        rows.append((_path(doc), api_docs, meta.description))
    return _table(("Lever", "API docs", "Description"), rows)


def _smells(kb: KnowledgeBase) -> str:
    rows = []
    for doc in _documents(kb, "smells"):
        meta = doc.meta
        assert isinstance(meta, SmellMeta)
        rows.append((_path(doc), _shapes(meta.applies_to), meta.description))
    return _table(("Smell", "Applies to", "Description"), rows)


def _playbooks_of(kind: str) -> Callable[[KnowledgeBase], str]:
    def render(kb: KnowledgeBase) -> str:
        rows = []
        for doc in _documents(kb, "playbooks"):
            meta = doc.meta
            assert isinstance(meta, PlaybookMeta)
            if meta.kind == kind:
                rows.append((_path(doc), _shapes(meta.applies_to), meta.description))
        return _table(("Playbook", "Applies to", "Description"), rows)

    return render


def _techniques(kb: KnowledgeBase) -> str:
    rows = []
    for doc in _documents(kb, "techniques"):
        meta = doc.meta
        assert isinstance(meta, TechniqueMeta)
        if meta.status == "active":
            rows.append(
                (
                    _path(doc),
                    ", ".join(meta.levers),
                    _shapes(meta.applies_to),
                    meta.cost,
                    meta.description,
                )
            )
    return _table(("Technique", "Levers", "Applies to", "Cost", "Description"), rows)


def _techniques_dormant(kb: KnowledgeBase) -> str:
    rows = []
    for doc in _documents(kb, "techniques"):
        meta = doc.meta
        assert isinstance(meta, TechniqueMeta)
        if meta.status == "dormant":
            rows.append((_path(doc), meta.description))
    return _table(("Technique", "Description"), rows)


RENDERERS: dict[str, Callable[[KnowledgeBase], str]] = {
    "levers": _levers,
    "smells": _smells,
    "techniques": _techniques,
    "techniques-dormant": _techniques_dormant,
    **{f"playbooks-{kind}": _playbooks_of(kind) for kind in PLAYBOOK_KINDS},
}


def render_blocks(kb: KnowledgeBase) -> dict[tuple[str, str], str]:
    """(index file, block name) -> the text between the markers."""
    return {
        (index, block): RENDERERS[block](kb)
        for index, blocks in INDEX_BLOCKS.items()
        for block in blocks
    }


def write_blocks(kb: KnowledgeBase) -> list[Path]:
    """Rewrite the blocks of each index file in place. A file or a block that
    is missing is left as it is, for the check to report. Returns the files
    that changed."""
    changed: list[Path] = []
    rendered = render_blocks(kb)
    for index, blocks in INDEX_BLOCKS.items():
        path = kb.root / index
        if not path.is_file():
            continue
        try:
            before = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # load reports it; the check lists it
        after = before
        for block in blocks:
            after = replace_block(after, block, rendered[(index, block)])
        if after != before:
            path.write_bytes(after.encode("utf-8"))
            changed.append(path)
    return changed
