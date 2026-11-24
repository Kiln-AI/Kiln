"""The skill-tree check: every path the skill writes resolves, every file is
reachable from `SKILL.md`, and the files follow the skill's file, front-matter
and wording rules."""

import re
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from kiln_mcp_server.skill_checks.docs_index import (
    DOCS_FOLDER,
    DOCS_INDEX_PATH,
    online_url_for,
)
from kiln_mcp_server.skill_checks.front_matter import read_front_matter
from kiln_mcp_server.skill_checks.knowledge_schema import (
    API_CATALOGUE_SUFFIX,
    API_DOCS_PREFIX,
    COMPONENT_ROOTS,
    INDEX_BLOCKS,
    Problem,
)
from kiln_mcp_server.skill_files import API_RULES_PATH, ROOT_FILE, list_tree

TREE_RULES: tuple[str, ...] = (
    "tree-path",
    "tree-relative",
    "tree-bare-name",
    "tree-call-syntax",
    "tree-banned-term",
    "tree-app-link",
    "tree-split-pointer",
    "tree-test-split",
    "tree-front-matter",
    "tree-file",
    "tree-unreachable",
)

API_DOCS_FOLDER = API_DOCS_PREFIX
KNOWLEDGE_FOLDER = "references/knowledge/"
CLIENT_GUIDANCE_FOLDER = "references/client_guidance/"
KNOWLEDGE_TREES = ("references/levers/", "references/improving_agents/")
SPLIT_RULE_FILE = "references/knowledge/train_val_test.md"
CATALOGUE_SUFFIX = API_CATALOGUE_SUFFIX

# The documents of the knowledge trees; the knowledge check owns their front
# matter. Files deeper inside these folders are sub-files, with none.
KNOWLEDGE_DOCUMENT_FOLDERS = tuple(COMPONENT_ROOTS.values())
NO_FRONT_MATTER_FILES = frozenset({DOCS_INDEX_PATH, *INDEX_BLOCKS})
SKILL_DESCRIPTION_MAX = 1024

CALL_SYNTAX = ("skill(name=", "kiln_skill")
# SKILL.md is the one file that names the skill tool, to say how to read the
# skill with it; every other file names plain paths only.
TOOL_NAME_ALLOWED = {ROOT_FILE: ("kiln_skill",)}

# Scope -> terms. "tree" is every file outside the API reference, "SKILL.md"
# is the root file, "knowledge" is the two knowledge trees, and "guidance" is
# every file outside the API reference and the help articles, which are
# copies of the public docs.
BANNED_TERMS: dict[str, tuple[str, ...]] = {
    "tree": (
        "kiln-chat",
        "model_info_featured",
        "model_search",
        "model_info",
        "compacted_digest",
        "UI-only",
        "approval-gated",
        "requires approval",
        "requires user approval",
        "experiment_batch",
        "optimize_quality",
        "optimize_performance",
    ),
    "SKILL.md": ("Kiln Assistant", "always in context", "turn 0"),
    # Kiln Harness Tuner is an MCP client too: the interactive client is a
    # chat client.
    "guidance": ("MCP client", "MCP clients", "MCP agent", "MCP agents"),
    "knowledge": (
        # The operation names of Kiln Harness Tuner's gateway.
        "ping",
        "get_task",
        "list_run_configs",
        "get_run_config",
        "list_prompts",
        "get_prompt_text",
        "list_models",
        "get_model_details",
        "list_providers",
        "list_evals",
        "get_eval",
        "get_eval_config",
        "list_specs",
        "get_spec",
        "get_train_results",
        "get_task_run",
        "list_train_items",
        "get_train_expected",
        "memory_list",
        "memory_get",
        "memory_summary",
        "memory_create",
        "memory_update",
        "list_code_tools",
        "get_code_tool",
        "list_skills",
        "get_skill",
        "get_skill_content",
        "list_available_tools",
        "get_tool_definition",
        "list_rag_configs",
        "get_rag_config",
        "rag_search",
        "list_documents",
        "get_kiln_task_tool",
        "create_run_config",
        "rename_run_config",
        "create_prompt",
        "run_task",
        "create_code_tool",
        "archive_code_tool",
        "test_code_tool",
        "trust_code_tools",
        "archive_skill",
        "create_spec",
        "create_eval",
        "add_eval_items",
        "create_eval_config",
        "set_current_eval_config",
        "test_judge",
        "run_train_eval",
        "get_val_summary",
        "compute_statistics",
        "get_answer_part",
        # Its gateway, roles and folders.
        "gateway",
        "the tuner",
        "harness-tuner",
        "kiln-harness-tuner",
        "the planner",
        "the builder",
        "the analyzer",
        "the probe",
        "scratch folder",
        # The loop's own words.
        "arm",
        "arms",
        "val gate",
        "probe",
        "probes",
        "screening round",
    ),
}
# Record strings that Kiln Harness Tuner's code writes and that hold a banned
# loop word. The knowledge quotes them exactly, as
# `references/knowledge/memory_formats/experiment_records.md` gives them.
HARNESS_TUNER_RECORD_STRINGS: tuple[str, ...] = (
    "- rejected at the val gate",
    "- blocked at the val gate",
)

# (file, term) pairs where a banned term holds its plain meaning. The Kiln
# tools guide speaks of Kiln as an MCP client of other servers, and of the
# protocol's clients of Kiln's project-tools server.
BANNED_TERM_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("references/knowledge/tools.md", "MCP client"),
        ("references/knowledge/tools.md", "MCP clients"),
    }
)

# `/api/model_info/...` and `get_api_model_info_...` are the model info
# endpoints, not the Assistant's tool. `references/knowledge/create_spec.md`
# is a knowledge file of the skill, not the gateway operation.
_TERM_EXTRA_LOOKBEHIND = {"model_info": "/", "create_spec": "/"}

# The calls and app pages that read an eval's test split when the caller asks
# for no split: endpoint doc paths or app links. Each endpoint resolves the
# test split with no `split` argument in `app/desktop/studio_server/eval_api.py`,
# and each page makes one of those requests. `train_val_test.md` lists each
# one with the call to use for train or val.
TEST_SPLIT_READERS: tuple[str, ...] = (
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md",
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_eval_results_summary.md",
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_run_configs_eval_scores.md",
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md",
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_comparison.md",
    f"{API_DOCS_FOLDER}get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md",
    # The Compare page: the run config eval scores, and the run comparison.
    "http://localhost:8757/specs/{project_id}/{task_id}/compare",
    # A spec page and its eval pages: the score summary and the eval progress.
    "http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}",
    # The eval page of a legacy eval: the eval progress.
    "http://localhost:8757/specs/{project_id}/{task_id}/legacy/{eval_id}",
)

# (file, path) pairs that look like skill paths and are not.
IGNORED_REFS: frozenset[tuple[str, str]] = frozenset(
    {
        # The help article on skills shows the files of a user's own skill.
        ("references/docs/skills.md", "references/STYLE_GUIDE.md"),
        ("references/docs/skills.md", "references/API_RESPONSE_FORMAT.md"),
    }
)

UNREACHABLE_GROUP_OVER = 20
UNREACHABLE_GROUP_EXAMPLES = 5

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_BARE_PATH = re.compile(r"(?<![\w./-])references/[A-Za-z0-9_\-./]+")
_ROOT_ANCHORED_PATH = re.compile(
    r"(?<![\w.-])/(?:references/[A-Za-z0-9_\-./]*|SKILL\.md\b)"
)
# `./references/...`, `../references/...`, `./SKILL.md` and the like, outside a
# link target.
_DOT_RELATIVE_PATH = re.compile(
    r"(?<![\w.-])\.\.?/(?:references/[A-Za-z0-9_\-./]*|SKILL\.md\b)"
)
_PROSE_FILE_NAME = re.compile(r"(?<![\w./-])[A-Za-z0-9_.-]+\.md(?![\w/-])")
_SCHEME = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)")
_PLACEHOLDER_CHARS = frozenset("*<>{}")
_APP_PATH = re.compile(
    r"^/(specs|settings|optimize|run|generate|dataset|skills|docs|prompts|models"
    r"|tools|fine_tune|jobs)(/|\?|$)"
)
_SPLIT_WORDING = re.compile(
    r"held-out|\b(val|validation|test) (split|set|gate)\b", re.IGNORECASE
)
_TEST_SPLIT_REQUEST = re.compile(r"\bsplit=test\b|\"split\"\s*:\s*\"test\"")
_SPLIT_POINTER_FOLDERS = (CLIENT_GUIDANCE_FOLDER, *KNOWLEDGE_TREES)


RefSource = Literal["link", "code", "bare", "catalogue"]


@dataclass(frozen=True)
class PathRef:
    """A skill path written in a file."""

    line: int
    raw: str
    """As written."""
    path: str
    """Normalised: no anchor, no trailing punctuation or `/`."""
    is_folder: bool
    source: RefSource


@dataclass(frozen=True)
class _Scan:
    refs: list[PathRef]
    link_targets: list[tuple[int, str]]
    code_spans: list[tuple[int, str]]
    prose: list[tuple[int, str]]
    """Each line with link targets, code spans and the labels of links to
    skill paths blanked out."""


def tree_paths(root: Path) -> frozenset[str]:
    """The keys of every file the skill serves from `root`."""
    return frozenset(list_tree(root))


def _folders_of(tree: Iterable[str]) -> frozenset[str]:
    folders = set()
    for key in tree:
        parts = key.split("/")[:-1]
        for end in range(1, len(parts) + 1):
            folders.add("/".join(parts[:end]))
    return frozenset(folders)


def _is_api_reference(key: str) -> bool:
    """A generated file of the API reference: an endpoint doc, a catalogue or
    the catalogue index. They follow no wording rule of the hand-written
    files."""
    return key.startswith(API_DOCS_FOLDER) and key != API_RULES_PATH


def _is_skill_path(text: str) -> bool:
    return text.startswith("references/") or text == ROOT_FILE


def _is_root_anchored(path: str) -> bool:
    return path.startswith("/references/") or path == "/" + ROOT_FILE


def _is_placeholder(path: str) -> bool:
    return bool(_PLACEHOLDER_CHARS & set(path)) or path.endswith("X.md")


def _unwrap_angle_brackets(target: str) -> str:
    """A CommonMark link destination written as `<...>`, without the brackets."""
    if len(target) > 1 and target.startswith("<") and target.endswith(">"):
        return target[1:-1]
    return target


def _normalise(raw: str) -> tuple[str, bool]:
    path = raw.split("#", 1)[0].rstrip(".,;:)")
    is_folder = path.endswith("/")
    return path.rstrip("/"), is_folder


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _catalogue_names(lines: Sequence[str]) -> Iterator[tuple[int, str]]:
    for number, line in enumerate(lines, start=1):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and _NAME.match(cells[-1]) and cells[-1].endswith(".md"):
            yield number, cells[-1]


def _scan(text: str, file: str, folders: frozenset[str]) -> _Scan:
    refs: list[PathRef] = []
    link_targets: list[tuple[int, str]] = []
    code_spans: list[tuple[int, str]] = []
    prose: list[tuple[int, str]] = []

    def add(number: int, raw: str, source: RefSource, followed_by: str = "") -> None:
        path, is_folder = _normalise(raw)
        if not path or _is_placeholder(path) or followed_by in _PLACEHOLDER_CHARS:
            return
        if (file, path) in IGNORED_REFS:
            return
        refs.append(PathRef(number, raw, path, is_folder or path in folders, source))

    lines = text.split("\n")
    for number, line in enumerate(lines, start=1):
        rest = line
        for match in _LINK_TARGET.finditer(line):
            target = _unwrap_angle_brackets(match.group(1))
            link_targets.append((number, target))
            rest = _blank(rest, match.start(), match.end())
            if _is_skill_path(target):
                add(number, target, "link")
                label_start = line.rfind("[", 0, match.start())
                if label_start >= 0:
                    rest = _blank(rest, label_start, match.start())
        for match in _CODE_SPAN.finditer(rest):
            span = match.group(1).strip()
            code_spans.append((number, span))
            if _is_skill_path(span):
                add(number, span, "code")
        rest = _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), rest)
        for match in _BARE_PATH.finditer(rest):
            add(number, match.group(0), "bare", rest[match.end() : match.end() + 1])
        prose.append((number, rest))

    if file.startswith(API_DOCS_FOLDER) and file.endswith(CATALOGUE_SUFFIX):
        for number, name in _catalogue_names(lines):
            refs.append(
                PathRef(number, name, API_DOCS_FOLDER + name, False, "catalogue")
            )
    return _Scan(refs, link_targets, code_spans, prose)


def paths_in(text: str, *, file: str, tree: frozenset[str]) -> list[PathRef]:
    """The skill paths written in `text`, the content of the tree file `file`,
    with placeholders and ignored references left out. `tree` is the set of
    file keys; it tells a folder path from a file path."""
    return _scan(text, file, _folders_of(tree)).refs


class _TreeChecker:
    def __init__(
        self, root: Path, tree: frozenset[str], test_split_readers: Sequence[str]
    ) -> None:
        self.root = root
        self.tree = tree
        self.folders = _folders_of(tree)
        self.test_split_readers = test_split_readers
        names = Counter(PurePosixPath(key).name for key in tree)
        self.unique_names = {
            PurePosixPath(key).name: key
            for key in sorted(tree)
            if names[PurePosixPath(key).name] == 1
            and PurePosixPath(key).name != ROOT_FILE
        }
        self.lowered: dict[str, str] = {}
        for key in sorted(tree):
            self.lowered.setdefault(key.lower(), key)
        self.banned = {
            scope: [(term, _term_pattern(term)) for term in terms]
            for scope, terms in BANNED_TERMS.items()
        }
        self.problems: list[Problem] = []
        self.edges: dict[str, set[str]] = defaultdict(set)

    def problem(self, rule: str, path: str, message: str) -> None:
        self.problems.append(Problem(rule, path, message))

    def run(self) -> list[Problem]:
        for key in sorted(self.tree):
            text = self.read(key)
            if text is not None:
                self.check_file(key, text)
        self.check_reachable()
        return self.problems

    def read(self, key: str) -> str | None:
        segments = key.split("/")
        bad = [segment for segment in segments if not _NAME.match(segment)]
        if bad:
            self.problem(
                "tree-file",
                key,
                f"name `{bad[0]}` has a character outside [A-Za-z0-9_.-]",
            )
        if not key.endswith(".md"):
            self.problem("tree-file", key, "is not a Markdown (.md) file")
        try:
            text = (self.root / key).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            self.problem("tree-file", key, "is not UTF-8")
            return None
        if "\r" in text:
            self.problem("tree-file", key, "has a carriage return; use LF line ends")
        return text

    def check_file(self, key: str, text: str) -> None:
        scan = _scan(text, key, self.folders)
        self.check_refs(key, scan.refs)
        self.check_relative(key, scan)
        self.check_call_syntax(key, text)
        self.check_front_matter(key, text)
        if not _is_api_reference(key):
            self.check_bare_names(key, scan)
            self.check_banned_terms(key, text)
        if not _is_api_reference(key) and not key.startswith(DOCS_FOLDER):
            self.check_app_links(key, scan)
            self.check_test_split(key, text)
        if key.startswith(_SPLIT_POINTER_FOLDERS):
            self.check_split_pointer(key, text)

    def check_refs(self, key: str, refs: Sequence[PathRef]) -> None:
        for ref in refs:
            if ref.path in self.tree and not ref.is_folder:
                self.edges[key].add(ref.path)
            elif ref.path in self.folders:
                readme = f"{ref.path}/README.md"
                if readme in self.tree:
                    self.edges[key].add(readme)
            else:
                message = (
                    f"line {ref.line}: `{ref.raw}` is not a file or folder of the skill"
                )
                case_match = self.lowered.get(ref.path.lower())
                if case_match is not None:
                    message += f"; did you mean `{case_match}`?"
                self.problem("tree-path", key, message)

    def check_relative(self, key: str, scan: _Scan) -> None:
        found: list[tuple[int, str]] = []
        for number, target in scan.link_targets:
            if _SCHEME.match(target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if _is_placeholder(path):
                continue
            partial = path.endswith(".md") and not _is_skill_path(path)
            if "./" in target or partial or _is_root_anchored(path):
                found.append((number, target))
        found.extend(
            (number, span)
            for number, span in scan.code_spans
            if _is_root_anchored(span.split("#", 1)[0])
            or _DOT_RELATIVE_PATH.match(span)
        )
        for number, line in scan.prose:
            for pattern in (_ROOT_ANCHORED_PATH, _DOT_RELATIVE_PATH):
                found.extend(
                    (number, m.group(0).rstrip(".,;:")) for m in pattern.finditer(line)
                )
        for number, written in sorted(found):
            self.problem(
                "tree-relative",
                key,
                f"line {number}: `{written}` is not a full path from the skill root; "
                "write it as `references/...`, with no leading `/`, `./` or `../`",
            )

    def check_bare_names(self, key: str, scan: _Scan) -> None:
        found = list(scan.code_spans)
        for number, line in scan.prose:
            found.extend((number, m.group(0)) for m in _PROSE_FILE_NAME.finditer(line))
        for number, name in found:
            full = self.unique_names.get(name)
            if full is not None:
                self.problem(
                    "tree-bare-name",
                    key,
                    f"line {number}: `{name}` is a bare file name; write the full path `{full}`",
                )

    def check_call_syntax(self, key: str, text: str) -> None:
        allowed = TOOL_NAME_ALLOWED.get(key, ())
        for number, line in enumerate(text.split("\n"), start=1):
            for needle in CALL_SYNTAX:
                if needle in line and needle not in allowed:
                    self.problem(
                        "tree-call-syntax",
                        key,
                        f"line {number}: `{needle}`: write a plain skill path, never a call of the skill tool",
                    )

    def check_banned_terms(self, key: str, text: str) -> None:
        scopes = ["tree"]
        if not key.startswith(DOCS_FOLDER):
            scopes.append("guidance")
        if key == ROOT_FILE:
            scopes.append("SKILL.md")
        if key.startswith(KNOWLEDGE_TREES):
            scopes.append("knowledge")
        for number, line in enumerate(text.split("\n"), start=1):
            for scope in scopes:
                scanned = (
                    _without_record_strings(line) if scope == "knowledge" else line
                )
                for term, pattern in self.banned[scope]:
                    if (key, term) in BANNED_TERM_EXCEPTIONS:
                        continue
                    if pattern.search(scanned):
                        self.problem(
                            "tree-banned-term",
                            key,
                            f"line {number}: banned term `{term}`",
                        )

    def check_app_links(self, key: str, scan: _Scan) -> None:
        for number, text in [*scan.code_spans, *scan.link_targets]:
            if _APP_PATH.match(text):
                self.problem(
                    "tree-app-link",
                    key,
                    f"line {number}: app path `{text}` has no address; write `http://localhost:8757{text}`",
                )

    def check_split_pointer(self, key: str, text: str) -> None:
        if SPLIT_RULE_FILE in text:
            return
        for number, line in enumerate(text.split("\n"), start=1):
            if _SPLIT_WORDING.search(line):
                self.problem(
                    "tree-split-pointer",
                    key,
                    f"line {number}: split wording, and the file does not name `{SPLIT_RULE_FILE}`",
                )
                return

    def check_test_split(self, key: str, text: str) -> None:
        lines = text.split("\n")
        for number, line in enumerate(lines, start=1):
            if _TEST_SPLIT_REQUEST.search(line):
                self.problem(
                    "tree-test-split",
                    key,
                    f"line {number}: asks for the test split; use train or val (`{SPLIT_RULE_FILE}`)",
                )
        if key == SPLIT_RULE_FILE or SPLIT_RULE_FILE in text:
            return
        for number, line in enumerate(lines, start=1):
            for reader in self.test_split_readers:
                if reader in line:
                    self.problem(
                        "tree-test-split",
                        key,
                        f"line {number}: `{reader}` reads the test split when no split is asked for, and the file does not name `{SPLIT_RULE_FILE}`",
                    )

    def check_front_matter(self, key: str, text: str) -> None:
        for message in _front_matter_problems(key, text):
            self.problem("tree-front-matter", key, message)

    def check_reachable(self) -> None:
        if ROOT_FILE not in self.tree:
            self.problem("tree-unreachable", ROOT_FILE, "the tree has no SKILL.md")
        reached = {ROOT_FILE}
        queue = deque([ROOT_FILE])
        while queue:
            for target in sorted(self.edges[queue.popleft()]):
                if target not in reached:
                    reached.add(target)
                    queue.append(target)

        by_folder: dict[str, list[str]] = defaultdict(list)
        for key in sorted(self.tree - reached):
            by_folder[key.rpartition("/")[0]].append(key)
        for folder, keys in sorted(by_folder.items()):
            if len(keys) > UNREACHABLE_GROUP_OVER:
                examples = ", ".join(keys[:UNREACHABLE_GROUP_EXAMPLES])
                self.problem(
                    "tree-unreachable",
                    f"{folder}/",
                    f"{len(keys)} files are not reached from SKILL.md, for example {examples}",
                )
            else:
                for key in keys:
                    self.problem("tree-unreachable", key, "not reached from SKILL.md")


def _without_record_strings(line: str) -> str:
    for record in HARNESS_TUNER_RECORD_STRINGS:
        line = line.replace(record, "")
    return line


def _term_pattern(term: str) -> re.Pattern[str]:
    before = "A-Za-z0-9_\\-" + re.escape(_TERM_EXTRA_LOOKBEHIND.get(term, ""))
    return re.compile(
        rf"(?<![{before}]){re.escape(term)}(?![A-Za-z0-9_\-])", re.IGNORECASE
    )


def _expected_front_matter(
    key: str,
) -> Literal["skill", "name_and_description", "help_article", "none", "unchecked"]:
    if key == ROOT_FILE:
        return "skill"
    if not key.endswith(".md"):
        return "unchecked"
    if key in NO_FRONT_MATTER_FILES or key.startswith(API_DOCS_FOLDER):
        return "none"
    if key.startswith(DOCS_FOLDER):
        return "help_article"
    if key.startswith((CLIENT_GUIDANCE_FOLDER, KNOWLEDGE_FOLDER)):
        return "name_and_description"
    for folder in KNOWLEDGE_DOCUMENT_FOLDERS:
        if key.startswith(folder + "/"):
            return "unchecked" if key.count("/") == folder.count("/") + 1 else "none"
    return "unchecked"


def _front_matter_problems(key: str, text: str) -> list[str]:
    expected = _expected_front_matter(key)
    if expected == "unchecked":
        return []
    front = read_front_matter(text)
    data = front.data
    if expected == "none":
        return ["must have no front matter"] if front.present else []
    if not front.present:
        return ["has no front matter"]
    if front.error is not None:
        return [front.error]

    description = data.get("description")
    description = description.strip() if isinstance(description, str) else ""
    if expected == "skill":
        problems = []
        if data.get("name") != "kiln":
            problems.append("`name` must be `kiln`")
        if not 1 <= len(description) <= SKILL_DESCRIPTION_MAX:
            problems.append(
                f"`description` must have 1 to {SKILL_DESCRIPTION_MAX} characters"
            )
        return problems
    if expected == "help_article":
        url = online_url_for(key)
        return (
            [] if data.get("online_url") == url else [f"`online_url` must be `{url}`"]
        )

    problems = []
    if set(data) != {"name", "description"}:
        problems.append("front matter must have exactly `name` and `description`")
    stem = PurePosixPath(key).stem
    if data.get("name") != stem:
        problems.append(f"`name` must be the file stem, `{stem}`")
    if not description:
        problems.append("`description` must be a text that is not empty")
    return problems


def check_tree(
    root: Path, *, test_split_readers: Sequence[str] = TEST_SPLIT_READERS
) -> list[Problem]:
    """Every problem of the skill tree at `root`, in file order."""
    return _TreeChecker(root, tree_paths(root), test_split_readers).run()
