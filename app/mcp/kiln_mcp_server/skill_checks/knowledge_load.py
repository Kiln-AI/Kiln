"""Read the knowledge trees of the skill into objects.

`load` never raises for a bad document: what it cannot parse becomes a
`Problem` on that document, so that one check run reports every broken file.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from kiln_mcp_server.skill_checks.front_matter import read_front_matter
from kiln_mcp_server.skill_checks.knowledge_schema import (
    COMPONENT_ROOTS,
    INDEX_BLOCKS,
    META_MODELS,
    CommonMeta,
    Problem,
    default_root,
)
from kiln_mcp_server.skill_files import list_tree

# Inline Markdown links. Reference-style links are not used in the trees.
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_SCHEME_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")

# The folders that hold the component roots. A file directly in one of them is
# a stray unless it is an index file.
KNOWLEDGE_PARENTS = ("references", "references/improving_agents")
KNOWLEDGE_AREAS = ("references/levers/", "references/improving_agents/")


@dataclass(frozen=True)
class Link:
    target: str
    """As written in the file, without the `<>` of a CommonMark destination."""
    resolved: str | None
    """A tree key; None when the link is external or names no file of the tree."""
    external: bool = False
    """The target has a scheme."""


@dataclass(frozen=True)
class Section:
    heading: str
    text: str
    links: tuple[Link, ...]


@dataclass(frozen=True)
class Document:
    path: str
    """From the skill root."""
    kind: str
    """A COMPONENT_ROOTS key (a file directly in that folder), "subfile"
    (deeper), or "index" (an INDEX_BLOCKS file)."""
    id: str
    meta: CommonMeta | None
    """None when the front matter did not parse, and for an index or a sub-file."""
    sections: tuple[Section, ...]
    links: tuple[Link, ...]
    chars: int
    text: str
    problems: tuple[Problem, ...]

    def section(self, heading: str) -> Section | None:
        return next((s for s in self.sections if s.heading == heading), None)


@dataclass(frozen=True)
class KnowledgeBase:
    root: Path
    """The skill folder."""
    documents: tuple[Document, ...]
    other_files: tuple[str, ...] = ()
    """Files of the knowledge trees that are not documents: a file that is not
    Markdown, or a file outside the layout."""

    def by_kind(self, kind: str) -> tuple[Document, ...]:
        return tuple(d for d in self.documents if d.kind == kind)

    def get(self, kind: str, id: str) -> Document | None:
        return next((d for d in self.by_kind(kind) if d.id == id), None)


def resolve_link(target: str, tree: frozenset[str]) -> str | None:
    """The tree key that `target` names, or None. A target is written as the
    full path from the skill root, so the lookup is exact: a `.` or `..` part,
    or another letter case, does not resolve."""
    if any(part in (".", "..") for part in target.split("/")):
        return None
    return target if target in tree else None


def load(root: Path | None = None) -> KnowledgeBase:
    root = (root or default_root()).resolve()
    tree = frozenset(list_tree(root))
    documents: list[Document] = []
    other_files: list[str] = []
    for key in sorted(tree):
        kind = document_kind(key)
        if kind is not None:
            documents.append(_load_document(root, key, kind, tree))
        elif _in_knowledge_area(key):
            other_files.append(key)
    return KnowledgeBase(root, tuple(documents), tuple(other_files))


def document_kind(key: str) -> str | None:
    """The kind of the document at tree key `key`, or None when it is not a
    document of the knowledge trees."""
    if key in INDEX_BLOCKS:
        return "index"
    if not key.endswith(".md"):
        return None
    for kind, folder in COMPONENT_ROOTS.items():
        if key.startswith(folder + "/"):
            return kind if key.count("/") == folder.count("/") + 1 else "subfile"
    return None


def component_root_of(key: str) -> str | None:
    """The component root that `key` is inside, at any depth."""
    return next(
        (folder for folder in COMPONENT_ROOTS.values() if key.startswith(folder + "/")),
        None,
    )


def _in_knowledge_area(key: str) -> bool:
    parent = PurePosixPath(key).parent.as_posix()
    return parent in KNOWLEDGE_PARENTS or key.startswith(KNOWLEDGE_AREAS)


def _load_document(root: Path, key: str, kind: str, tree: frozenset[str]) -> Document:
    stem = PurePosixPath(key).stem
    raw = (root / key).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        problem = Problem("encoding", key, f"not UTF-8: {exc}")
        return Document(key, kind, stem, None, (), (), len(raw), "", (problem,))
    problems: list[Problem] = []
    meta: CommonMeta | None = None
    body = text
    if kind in META_MODELS:
        meta, body, problem = _front_matter(text, kind, key)
        if problem:
            problems.append(problem)
    links: list[Link] = []
    sections: list[Section] = []
    heading: str | None = None
    lines: list[str] = []
    section_links: list[Link] = []

    def close() -> None:
        if heading is not None:
            sections.append(
                Section(heading, "\n".join(lines).strip(), tuple(section_links))
            )

    for line, fenced in fence_marked(body):
        if fenced:  # text of the section, but never a heading or a link
            lines.append(line)
            continue
        if line.startswith("## "):
            close()
            heading, lines, section_links = line[3:].strip(), [], []
            continue
        found = [_link(key, t, tree) for _, t in inline_links(line)]
        links.extend(found)
        section_links.extend(found)
        lines.append(line)
    close()
    return Document(
        path=key,
        kind=kind,
        id=stem,
        meta=meta,
        sections=tuple(sections),
        links=tuple(links),
        chars=len(text),
        text=text,
        problems=tuple(problems),
    )


def fence_marked(text: str) -> list[tuple[str, bool]]:
    """Each line of `text`, with True when it is part of a fenced block (its
    fence lines included).

    As in CommonMark, a fence closes only on a line of the same character, at
    least as long as the opening fence, with nothing after it."""
    out: list[tuple[str, bool]] = []
    closing: re.Pattern[str] | None = None
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if closing is None and match:
            fence = match.group(1)
            closing = re.compile(rf"[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*")
            out.append((line, True))
        elif closing is not None:
            if closing.fullmatch(line):
                closing = None
            out.append((line, True))
        else:
            out.append((line, False))
    return out


def inline_links(line: str) -> Iterator[tuple[re.Match[str], str]]:
    """Each inline link of `line`: the match of its `](...)` part, and its
    target without the `<>` of a CommonMark destination."""
    for match in _LINK_RE.finditer(line):
        target = match.group(1)
        if len(target) > 1 and target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        yield match, target


def has_scheme(target: str) -> bool:
    """An external target, such as `https://...` or `//host/...`."""
    return _SCHEME_RE.match(target) is not None


def _link(source: str, target: str, tree: frozenset[str]) -> Link:
    if has_scheme(target):
        return Link(target, None, external=True)
    bare = target.split("#", 1)[0]
    if not bare:  # a link to a heading of the same file
        return Link(target, source)
    return Link(target, resolve_link(bare, tree))


def _front_matter(
    text: str, kind: str, path: str
) -> tuple[CommonMeta | None, str, Problem | None]:
    front = read_front_matter(text)
    if not front.present:
        return None, text, Problem("front-matter", path, "no front matter")
    if front.error is not None:
        return None, front.body, Problem("front-matter", path, front.error)
    try:
        return META_MODELS[kind].model_validate(front.data), front.body, None
    except ValidationError as exc:
        message = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'front matter'}: {e['msg']}"
            for e in exc.errors()
        )
        return None, front.body, Problem("front-matter", path, message)
