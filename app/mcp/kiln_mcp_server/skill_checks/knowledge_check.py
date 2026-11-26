"""The structural checks of the knowledge trees.

`check` is a pure function of the loaded documents and the set of tree keys,
so the tests can pass small trees. A check reads only what a test can prove.
The content rules that need judgement (conditions, confidence, the approval
rule for priors) belong to the audit of the `knowledge-maintenance` skill.
Reachability from `SKILL.md` is the tree check's rule, not one of these.
"""

import re
from collections.abc import Callable, Iterable

from kiln_mcp_server.skill_checks.knowledge_index import read_block, render_blocks
from kiln_mcp_server.skill_checks.knowledge_load import (
    Document,
    KnowledgeBase,
    Link,
    component_root_of,
    fence_marked,
)
from kiln_mcp_server.skill_checks.knowledge_schema import (
    BUILD_COMMAND,
    COMPONENT_ROOTS,
    EVAL_STANCES,
    ID_PATTERN,
    INDEX_BLOCKS,
    LEVER_ID_PATTERN,
    MAX_CHARS,
    MAX_ID_CHARS,
    NO_PRIORS,
    PRIOR_SOURCES,
    REQUIRED_SECTIONS,
    TASK_SHAPES,
    LeverMeta,
    Problem,
    TechniqueMeta,
)
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_NAME,
    API_CATALOGUE_SUFFIX,
    API_DOCS_FOLDER,
)

PRIOR_ITEM_RE = re.compile(r"^- ", re.MULTILINE)
PRIOR_SOURCE_RE = re.compile(
    r"Source:\s*(" + "|".join(re.escape(s) for s in PRIOR_SOURCES) + r")\b"
)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# The maintenance templates mark each value to fill in as `{{NAME}}`.
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\n]*(?:\}\})?")


class _Context:
    """What several rules need: the knowledge base, the tree keys, and the
    documents by their path."""

    def __init__(self, kb: KnowledgeBase, tree: frozenset[str]) -> None:
        self.kb = kb
        self.tree = tree
        self.by_path = {d.path: d for d in kb.documents}

    def component(self, link: Link, *kinds: str) -> Document | None:
        """The component that `link` names, when it is a primary document of
        one of `kinds`."""
        if link.resolved is None:
            return None
        doc = self.by_path.get(link.resolved)
        if doc is None or doc.kind not in kinds:
            return None
        return doc

    def components(self) -> Iterable[Document]:
        return (d for d in self.kb.documents if d.kind in COMPONENT_ROOTS)


Rule = Callable[[_Context], Iterable[Problem]]


def check(kb: KnowledgeBase, *, tree: frozenset[str]) -> list[Problem]:
    """Every problem of the knowledge trees, sorted by path, rule and message.
    `tree` is the set of every file key of the skill."""
    ctx = _Context(kb, tree)
    problems = [problem for _, rule in RULES for problem in rule(ctx)]
    return sorted(problems, key=lambda p: (p.path, p.rule, p.message))


def _front_matter(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.kb.documents:
        yield from doc.problems


def _id(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.components():
        pattern, joiners = (
            (LEVER_ID_PATTERN, "'-' or '_'")
            if doc.kind == "levers"
            else (ID_PATTERN, "'-'")
        )
        if not pattern.match(doc.id) or len(doc.id) > MAX_ID_CHARS:
            yield Problem(
                "id",
                doc.path,
                f"the id {doc.id!r} must be lower-case words joined by"
                f" {joiners}, at most {MAX_ID_CHARS} characters",
            )


def _sections(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.components():
        required = REQUIRED_SECTIONS[doc.kind]
        headings = tuple(s.heading for s in doc.sections)
        if headings[: len(required)] != required:
            yield Problem(
                "sections",
                doc.path,
                f"the first sections must be {list(required)}; found {list(headings)}",
            )
            continue
        for section in doc.sections[: len(required)]:
            # A template puts a comment in each section for its author.
            if not HTML_COMMENT_RE.sub("", section.text).strip():
                yield Problem(
                    "sections", doc.path, f"the section {section.heading!r} is empty"
                )


def _placeholder(ctx: _Context) -> Iterable[Problem]:
    """A `{{` outside a fence is template text that the author did not
    replace. The front matter is read too, so a template title is found."""
    for doc in ctx.kb.documents:
        for number, (line, fenced) in enumerate(fence_marked(doc.text), 1):
            if fenced:
                continue
            for placeholder in PLACEHOLDER_RE.findall(line):
                yield Problem(
                    "placeholder",
                    doc.path,
                    f"line {number} holds the template text {placeholder!r};"
                    " replace it",
                )


def _size(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.kb.documents:
        limit = MAX_CHARS.get(doc.kind)
        if limit is not None and doc.chars > limit:
            yield Problem(
                "size",
                doc.path,
                f"{doc.chars} characters; the limit is {limit}. Split it.",
            )


def _shape(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.components():
        applies_to = getattr(doc.meta, "applies_to", "all")
        if isinstance(applies_to, list):
            for value in applies_to:
                if value not in TASK_SHAPES:
                    yield Problem(
                        "shape",
                        doc.path,
                        f"{value!r} is not a task shape; use 'all' or"
                        f" {list(TASK_SHAPES)}",
                    )


def _link(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.kb.documents:
        for link in doc.links:
            if not link.external and link.resolved is None:
                yield Problem(
                    "link",
                    doc.path,
                    f"{link.target} is not a file of the skill; write the full"
                    " path from the skill root, spelled as on disk",
                )


def _lever_ids(ctx: _Context) -> set[str]:
    return {d.id for d in ctx.kb.by_kind("levers")}


def _technique_lever_ids(ctx: _Context) -> Iterable[Problem]:
    levers = _lever_ids(ctx)
    for doc in ctx.kb.by_kind("techniques"):
        if isinstance(doc.meta, TechniqueMeta):
            for lever in doc.meta.levers:
                if lever not in levers:
                    yield Problem(
                        "technique-lever-ids",
                        doc.path,
                        f"the lever {lever!r} has no document in"
                        f" {COMPONENT_ROOTS['levers']}/",
                    )


def _lever_api_docs(ctx: _Context) -> Iterable[Problem]:
    """Each `api_docs` value is an endpoint doc of the API reference. A
    blocked endpoint has no doc, so a lever cannot name one."""
    for doc in ctx.kb.by_kind("levers"):
        if not isinstance(doc.meta, LeverMeta):
            continue
        for path in doc.meta.api_docs:
            name = path.rpartition("/")[2]
            if not path.startswith(f"{API_DOCS_FOLDER}/"):
                message = f"{path!r} is not under {API_DOCS_FOLDER}/"
            elif path not in ctx.tree:
                message = f"{path!r} is not a file of the API reference"
            elif name == API_CATALOGUE_INDEX_NAME or name.endswith(
                API_CATALOGUE_SUFFIX
            ):
                message = f"{path!r} is a catalogue; name the endpoint doc"
            else:
                continue
            yield Problem("lever-api-docs", doc.path, message)


def _technique_lever_links(ctx: _Context) -> Iterable[Problem]:
    existing = _lever_ids(ctx)
    for doc in ctx.kb.by_kind("techniques"):
        how = doc.section("How")
        if how is None or not isinstance(doc.meta, TechniqueMeta):
            continue
        named = set(doc.meta.levers)
        linked = {
            lever.id
            for link in how.links
            if (lever := ctx.component(link, "levers")) is not None
        }
        # A lever with no document is the rule `technique-lever-ids`.
        for lever in sorted((named & existing) - linked):
            yield Problem(
                "technique-lever-links",
                doc.path,
                f"How does not link the lever {lever!r} that `levers` names",
            )
        for lever in sorted(linked - named):
            yield Problem(
                "technique-lever-links",
                doc.path,
                f"How links the lever {lever!r}, which `levers` does not name",
            )


def _technique_stance(ctx: _Context) -> Iterable[Problem]:
    for doc in ctx.kb.by_kind("techniques"):
        section = doc.section("If it does not move the evals")
        if section and section.text and not section.text.startswith(EVAL_STANCES):
            yield Problem(
                "technique-stance",
                doc.path,
                f"'If it does not move the evals' must start with one of"
                f" {list(EVAL_STANCES)}",
            )


def _priors(ctx: _Context, kind: str, rule: str) -> Iterable[Problem]:
    """The `Priors` section of each `kind` document is a list of cases, each
    with a valid `Source:`, or the line `None yet.`. A document with no such
    section has no problem here: the rule `sections` decides if it needs
    one."""
    for doc in ctx.kb.by_kind(kind):
        section = doc.section("Priors")
        if section is None or not section.text or section.text == NO_PRIORS:
            continue
        items = PRIOR_ITEM_RE.split(section.text)
        if items[0].strip():
            yield Problem(
                rule,
                doc.path,
                f"Priors must be a list of cases, or the line {NO_PRIORS!r}",
            )
        for number, item in enumerate(items[1:], 1):
            if not PRIOR_SOURCE_RE.search(item):
                yield Problem(
                    rule,
                    doc.path,
                    f"prior {number} has no 'Source:' with one of"
                    f" {list(PRIOR_SOURCES)}",
                )


def _technique_priors(ctx: _Context) -> Iterable[Problem]:
    return _priors(ctx, "techniques", "technique-priors")


def _playbook_priors(ctx: _Context) -> Iterable[Problem]:
    # A playbook has no required `Priors` section; an optional one after
    # `Budget` has the form of a technique's.
    return _priors(ctx, "playbooks", "playbook-priors")


def _links_only_to(
    ctx: _Context,
    rule: str,
    kind: str,
    heading: str,
    kinds: tuple[str, ...],
    at_least_one: bool,
) -> Iterable[Problem]:
    """Each link in section `heading` of each `kind` document names a
    component of `kinds`. A link that does not resolve is the rule `link`. A
    link to the document itself (an anchor, or its own path) is not counted."""
    folders = " or ".join(f"{COMPONENT_ROOTS[k]}/" for k in kinds)
    for doc in ctx.kb.by_kind(kind):
        section = doc.section(heading)
        if section is None:
            continue
        good = 0
        for link in section.links:
            if not link.external and link.resolved is None:
                continue
            if link.resolved == doc.path:
                continue
            if ctx.component(link, *kinds) is None:
                yield Problem(
                    rule,
                    doc.path,
                    f"{heading!r} links {link.target}, which is not in {folders}",
                )
            else:
                good += 1
        if at_least_one and not good:
            yield Problem(
                rule, doc.path, f"{heading!r} must link at least one file in {folders}"
            )


def _alternatives(ctx: _Context) -> Iterable[Problem]:
    return _links_only_to(
        ctx, "alternatives", "techniques", "Alternatives", ("techniques",), False
    )


def _playbook_steps(ctx: _Context) -> Iterable[Problem]:
    return _links_only_to(
        ctx,
        "playbook-steps",
        "playbooks",
        "What to try, in order",
        ("techniques", "playbooks"),
        True,
    )


def _smell_remedies(ctx: _Context) -> Iterable[Problem]:
    return _links_only_to(
        ctx, "smell-remedies", "smells", "Remedies", ("playbooks", "techniques"), True
    )


def _in_a_subfile_folder(path: str) -> bool:
    """True when `path` is inside the folder of a component, beside its
    primary document."""
    root = component_root_of(path)
    return root is not None and path.count("/") > root.count("/") + 1


def _subfile(ctx: _Context) -> Iterable[Problem]:
    for path in ctx.kb.other_files:
        if _in_a_subfile_folder(path):
            yield Problem("subfile", path, "a sub-file must be Markdown")
    for doc in ctx.kb.by_kind("subfile"):
        root = component_root_of(doc.path)
        assert root is not None
        owner_id = doc.path[len(root) + 1 :].split("/", 1)[0]
        owner_path = f"{root}/{owner_id}.md"
        owner = ctx.by_path.get(owner_path)
        if owner is None or owner.kind not in COMPONENT_ROOTS:
            yield Problem(
                "subfile", doc.path, f"no component {owner_path} owns this folder"
            )
        elif doc.path not in {link.resolved for link in owner.links}:
            yield Problem(
                "subfile", doc.path, f"{owner_path} does not link this sub-file"
            )


def _index(ctx: _Context) -> Iterable[Problem]:
    rendered = render_blocks(ctx.kb)
    for index, blocks in INDEX_BLOCKS.items():
        doc = ctx.by_path.get(index)
        if doc is None:
            # A knowledge tree that is not in the skill yet needs no index.
            folder = index.rpartition("/")[0] + "/"
            if any(key.startswith(folder) for key in ctx.tree):
                yield Problem("index", index, "the index file is missing")
            continue
        for block in blocks:
            current = read_block(doc.text, block)
            if current is None:
                yield Problem("index", index, f"no generated block {block!r}")
            elif current != rendered[(index, block)]:
                yield Problem(
                    "index",
                    index,
                    f"the block {block!r} is stale; run `{BUILD_COMMAND}`",
                )


def _stray(ctx: _Context) -> Iterable[Problem]:
    for path in ctx.kb.other_files:
        if _in_a_subfile_folder(path):
            continue  # inside a sub-file folder: the rule `subfile`
        yield Problem(
            "stray",
            path,
            "this file is outside the layout of the knowledge trees: an index"
            " file, <component root>/<id>.md, or a sub-file of a component",
        )


RULES: tuple[tuple[str, Rule], ...] = (
    ("front-matter", _front_matter),
    ("id", _id),
    ("sections", _sections),
    ("placeholder", _placeholder),
    ("size", _size),
    ("shape", _shape),
    ("link", _link),
    ("technique-lever-ids", _technique_lever_ids),
    ("lever-api-docs", _lever_api_docs),
    ("technique-lever-links", _technique_lever_links),
    ("technique-stance", _technique_stance),
    ("technique-priors", _technique_priors),
    ("playbook-priors", _playbook_priors),
    ("alternatives", _alternatives),
    ("playbook-steps", _playbook_steps),
    ("smell-remedies", _smell_remedies),
    ("subfile", _subfile),
    ("index", _index),
    ("stray", _stray),
)

# `encoding` is reported by the loader, through the rule `front-matter`.
KNOWLEDGE_RULES: tuple[str, ...] = (*(name for name, _ in RULES), "encoding")
