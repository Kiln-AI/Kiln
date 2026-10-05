#!/usr/bin/env python3
"""Conventions gate: flags rule violations on the added lines of a change.

Usage:
    conventions_gate.py --range <git-range> [--repo <path>]   # added lines of a commit range
    conventions_gate.py --worktree [--repo <path>]            # uncommitted changes + untracked files
    conventions_gate.py --files <path>... [--repo <path>]     # whole files or directories

Prints one line per hit, ``SEV<TAB>RULE<TAB>path:line<TAB>snippet``, then a summary line.
Exit codes: 0 = no FAIL, 1 = at least one FAIL, 2 = usage, config or git error.

Settings come from ``gate_config.json`` and ``gate_allow.txt`` beside this script.
Stdlib only, so it runs with ``uv run python`` or a plain ``python3``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "gate_config.json"
ALLOW_FILENAME = "gate_allow.txt"
SNIPPET_MAX_CHARS = 160
SEVERITIES = ("FAIL", "WARN")

LANG_BY_EXTENSION = {
    ".py": "py",
    ".ts": "ts",
    ".js": "ts",
    ".svelte": "svelte",
}

# Phrases that narrate history or cite planning docs. Some history words also
# describe runtime state (a plan that stops matching what ran), so those patterns
# skip the common runtime-state phrasings.
NO_LONGER_RUNTIME_STATE = (
    r"(?:match|exist|resolve|apply|fit|count|parse|make|offer|correspond|sum|total)\w*"
    r"|valid|eligible|available|supported|present|reachable|running|selected"
    r"|relevant|current|in|on|part of|there|visible"
)
HISTORY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"(?<!can )(?<!could )\bno longer\b(?! (?:{NO_LONGER_RUNTIME_STATE})\b)",
        r"\bpreviously\b(?![- ]\w+ed\b)",
        r"\b(?:we|it|they|this|that|which|who|never) used to\b",
        r"\bformerly\b",
        r"\bvestigial\b",
        r"\bbumped (?:from|to)\b",
        r"\bswitched (?:from|to)\b",
        r"\bchanged from \S+ to\b",
        r"\bwas (?:renamed|moved|replaced)\b",
        r"\b(?:after|before) the (?:refactor|fix|migration|rewrite)\b",
        r"\bthe old (?:behaviou?r|code|implementation|approach|way|version)\b",
        r"\b(?:in|as of) this (?:pr|change|commit)\b",
        r"\bphase \d+\b(?!:)",
        r"\bfunctional[_ ]spec\b",
        r"§",
        r"\(P\d\)",
    )
)

PY_KEYWORDS = frozenset(
    "if elif else for while with try except finally def class return async await "
    "assert raise del import from match case lambda pass yield not global nonlocal".split()
)

GLOBAL_STMT = re.compile(r"^\s*global\s+\w")
BOOL_ENV = re.compile(r"(?<![\w.])bool\(\s*os\.(?:getenv|environ)")
ENV_ACCESS = re.compile(r"os\.getenv\(|os\.environ\b")
CORE_CONFIG_SHARED = re.compile(r"Config\.shared\(\)")
LIB_IMPORTS_ROUTES = re.compile(
    r"(?:\bfrom\s+|\bimport\s*\(\s*|^\s*import\s+)[\"'][^\"']*\broutes/"
)
MODULE_LEVEL_CALL = re.compile(r"^([A-Za-z_][\w.]*)\(")
MODULE_LEVEL_ASSIGN = re.compile(r"^[A-Za-z_][\w.]*\s*(?::[^=]+)?=(?!=)\s*(.+)")
MODULE_LEVEL_SUBSCRIBE = re.compile(r"^[A-Za-z_$][\w$.]*\.subscribe\(")


class GateError(Exception):
    """A usage, config or git problem; reported on stderr with exit code 2."""


@dataclass(frozen=True)
class Line:
    path: str
    lineno: int
    text: str


@dataclass(frozen=True)
class Hit:
    severity: str
    rule: str
    path: str
    lineno: int
    text: str


@dataclass(frozen=True)
class CheckConfig:
    enabled: bool
    severity: str
    paths: tuple[re.Pattern[str], ...]
    exclude: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Config:
    skip_globs: tuple[re.Pattern[str], ...]
    checks: dict[str, CheckConfig]
    env_access_allowed: tuple[re.Pattern[str], ...] = ()
    module_level_call_ignore: tuple[re.Pattern[str], ...] = ()
    module_level_construct_patterns: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True)
class AllowEntry:
    rule: str | None
    pattern: re.Pattern[str]


@dataclass
class Result:
    hits: list[Hit] = field(default_factory=list)
    allowlisted: int = 0

    @property
    def fail_count(self) -> int:
        return sum(1 for hit in self.hits if hit.severity == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for hit in self.hits if hit.severity == "WARN")


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """Compile a path glob: ``**/`` spans zero or more directories, ``*`` and ``?``
    stay within one path segment, and every other character is literal.

    Brackets are literal (unlike fnmatch) because SvelteKit route directories are
    named ``[project_id]``.
    """
    parts: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            parts.append(".*")
            i += 2
        elif glob[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(parts) + r"\Z")


def path_matches(path: str, globs: Iterable[re.Pattern[str]]) -> bool:
    return any(glob.match(path) for glob in globs)


def lang_for_path(path: str) -> str | None:
    return LANG_BY_EXTENSION.get(os.path.splitext(path)[1])


def path_in_scope(path: str, cfg: Config) -> bool:
    return lang_for_path(path) is not None and not path_matches(path, cfg.skip_globs)


HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _diff_path(header_value: str) -> str | None:
    """Path from a ``+++`` header value, or None for ``/dev/null``."""
    value = header_value.rstrip("\t")
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value == "/dev/null":
        return None
    return value[2:] if value.startswith("b/") else value


def parse_unified_diff(text: str) -> list[Line]:
    """Added lines, with their new-file line numbers, from ``git diff -U0`` output."""
    lines: list[Line] = []
    path: str | None = None
    in_file_header = False
    lineno = 0
    for raw in text.split("\n"):
        if raw.startswith("diff --git "):
            path = None
            in_file_header = True
        elif in_file_header and raw.startswith("+++ "):
            path = _diff_path(raw[4:])
        elif raw.startswith("@@"):
            in_file_header = False
            match = HUNK_HEADER.match(raw)
            if match:
                lineno = int(match.group(1))
        elif in_file_header:
            continue
        elif raw.startswith("+") and path is not None:
            lines.append(Line(path, lineno, raw[1:]))
            lineno += 1
        elif raw.startswith(" ") and path is not None:
            lineno += 1
    return lines


def _string_end(text: str, start: int, allow_triple: bool) -> int | None:
    """Index just past the string literal opening at ``start``, or None if it runs
    past the end of the line."""
    quote = text[start]
    if allow_triple and text.startswith(quote * 3, start):
        close = text.find(quote * 3, start + 3)
        return None if close == -1 else close + 3
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return None


def _split_python(text: str) -> tuple[str, str | None]:
    if "#" not in text:
        return text, None
    i = 0
    while i < len(text):
        char = text[i]
        if char == "#":
            return text[:i], text[i + 1 :].strip()
        if char in "'\"":
            end = _string_end(text, i, allow_triple=True)
            if end is None:
                return text, None
            i = end
            continue
        i += 1
    return text, None


def _split_c_like(text: str) -> tuple[str, str | None]:
    stripped = text.lstrip()
    if stripped.startswith("*"):
        body = stripped[1:]
        close = body.find("*/")
        if close == -1:
            return "", body.strip()
        return body[close + 2 :], body[:close].strip()
    if "//" not in text and "/*" not in text and "<!--" not in text:
        return text, None

    code: list[str] = []
    comments: list[str] = []
    segment_start = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char in "'\"`":
            end = _string_end(text, i, allow_triple=False)
            if end is None:
                break
            i = end
            continue
        if text.startswith("//", i) and (i == 0 or text[i - 1] != ":"):
            code.append(text[segment_start:i])
            comments.append(text[i + 2 :])
            segment_start = len(text)
            break
        if text.startswith("/*", i):
            opener, closer = "/*", "*/"
        elif text.startswith("<!--", i):
            opener, closer = "<!--", "-->"
        else:
            i += 1
            continue
        code.append(text[segment_start:i])
        close = text.find(closer, i + len(opener))
        if close == -1:
            comments.append(text[i + len(opener) :])
            segment_start = len(text)
            break
        comments.append(text[i + len(opener) : close])
        i = close + len(closer)
        segment_start = i
    code.append(text[segment_start:])
    if not comments:
        return text, None
    return "".join(code), " ".join(comment.strip() for comment in comments)


def split_code_comment(text: str, lang: str) -> tuple[str, str | None]:
    """Split one source line into (code, comment text). A per-line heuristic: string
    and comment state is not carried across lines."""
    if lang == "py":
        return _split_python(text)
    return _split_c_like(text)


def extract_comment(text: str, lang: str) -> str | None:
    return split_code_comment(text, lang)[1]


def has_history_phrase(comment: str) -> bool:
    return any(pattern.search(comment) for pattern in HISTORY_PATTERNS)


@dataclass(frozen=True)
class SourceLine:
    """A line under review, pre-split into code and comment text."""

    line: Line
    lang: str
    code: str
    comment: str | None

    @property
    def at_column_zero(self) -> bool:
        return bool(self.code) and not self.code[0].isspace()


def check_history_comment(src: SourceLine, cfg: Config) -> bool:
    return src.comment is not None and has_history_phrase(src.comment)


def check_global_stmt(src: SourceLine, cfg: Config) -> bool:
    return bool(GLOBAL_STMT.match(src.code))


def check_bool_env(src: SourceLine, cfg: Config) -> bool:
    return bool(BOOL_ENV.search(src.code))


def check_env_access(src: SourceLine, cfg: Config) -> bool:
    return bool(ENV_ACCESS.search(src.code)) and not path_matches(
        src.line.path, cfg.env_access_allowed
    )


def check_core_config_shared(src: SourceLine, cfg: Config) -> bool:
    return bool(CORE_CONFIG_SHARED.search(src.code))


def check_lib_imports_routes(src: SourceLine, cfg: Config) -> bool:
    return bool(LIB_IMPORTS_ROUTES.search(src.code))


def check_module_level_call(src: SourceLine, cfg: Config) -> bool:
    if not src.at_column_zero:
        return False
    match = MODULE_LEVEL_CALL.match(src.code)
    if not match or match.group(1).split(".")[0] in PY_KEYWORDS:
        return False
    return not any(ignore.search(src.code) for ignore in cfg.module_level_call_ignore)


def check_module_level_construct(src: SourceLine, cfg: Config) -> bool:
    if not src.at_column_zero:
        return False
    match = MODULE_LEVEL_ASSIGN.match(src.code)
    return bool(match) and any(
        pattern.search(match.group(1))
        for pattern in cfg.module_level_construct_patterns
    )


def check_module_level_subscribe(src: SourceLine, cfg: Config) -> bool:
    return src.at_column_zero and bool(MODULE_LEVEL_SUBSCRIBE.match(src.code))


@dataclass(frozen=True)
class Check:
    rule: str
    default_severity: str
    langs: frozenset[str]
    matches: Callable[[SourceLine, Config], bool]


PY = frozenset({"py"})
WEB = frozenset({"ts", "svelte"})

CHECKS: tuple[Check, ...] = (
    Check("history-comment", "FAIL", PY | WEB, check_history_comment),
    Check("global-stmt", "FAIL", PY, check_global_stmt),
    Check("bool-env", "FAIL", PY, check_bool_env),
    Check("env-access", "FAIL", PY, check_env_access),
    Check("core-config-shared", "FAIL", PY, check_core_config_shared),
    Check("lib-imports-routes", "FAIL", WEB, check_lib_imports_routes),
    Check("module-level-call", "WARN", PY, check_module_level_call),
    Check("module-level-construct", "WARN", PY, check_module_level_construct),
    Check(
        "module-level-subscribe",
        "WARN",
        frozenset({"ts"}),
        check_module_level_subscribe,
    ),
)
CHECKS_BY_RULE = {check.rule: check for check in CHECKS}


def is_allowlisted(hit: Hit, allow: Sequence[AllowEntry]) -> bool:
    subject = f"{hit.path}\t{hit.text.strip()}"
    return any(
        (entry.rule is None or entry.rule == hit.rule) and entry.pattern.search(subject)
        for entry in allow
    )


def run_checks(
    lines: Iterable[Line], cfg: Config, allow: Sequence[AllowEntry]
) -> Result:
    result = Result()
    for line in lines:
        lang = lang_for_path(line.path)
        if lang is None or path_matches(line.path, cfg.skip_globs):
            continue
        code, comment = split_code_comment(line.text, lang)
        src = SourceLine(line, lang, code, comment)
        for check in CHECKS:
            check_cfg = cfg.checks.get(check.rule)
            if check_cfg is None or not check_cfg.enabled or lang not in check.langs:
                continue
            if check_cfg.paths and not path_matches(line.path, check_cfg.paths):
                continue
            if path_matches(line.path, check_cfg.exclude):
                continue
            if not check.matches(src, cfg):
                continue
            hit = Hit(check_cfg.severity, check.rule, line.path, line.lineno, line.text)
            if is_allowlisted(hit, allow):
                result.allowlisted += 1
            else:
                result.hits.append(hit)
    result.hits.sort(key=lambda hit: (hit.path, hit.lineno, hit.rule))
    return result


def format_result(result: Result) -> str:
    out = [
        f"{hit.severity}\t{hit.rule}\t{hit.path}:{hit.lineno}\t"
        f"{hit.text.strip()[:SNIPPET_MAX_CHARS]}"
        for hit in result.hits
    ]
    out.append(
        f"conventions_gate: {result.fail_count} FAIL, {result.warn_count} WARN, "
        f"{result.allowlisted} allowlisted"
    )
    return "\n".join(out)


CONFIG_KEYS = frozenset(
    {
        "skip_globs",
        "checks",
        "env_access_allowed",
        "module_level_call_ignore",
        "module_level_construct_patterns",
    }
)
CHECK_KEYS = frozenset({"enabled", "severity", "paths", "exclude"})


def _json_object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GateError(f"{where} must be an object")
    return {str(key): item for key, item in value.items()}


def _string_list(data: dict[str, object], key: str, where: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise GateError(f"{where}: '{key}' must be a list of strings")
    return [str(item) for item in value]


def _regexes(patterns: list[str], where: str) -> tuple[re.Pattern[str], ...]:
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise GateError(f"{where}: invalid regex {pattern!r}: {exc}") from exc
    return tuple(compiled)


def _globs(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(glob_to_regex(pattern) for pattern in patterns)


def _check_config(rule: str, value: object, where: str) -> CheckConfig:
    if rule not in CHECKS_BY_RULE:
        raise GateError(f"{where}: unknown check '{rule}'")
    data = _json_object(value, f"{where}: checks.{rule}")
    unknown = set(data) - CHECK_KEYS
    if unknown:
        raise GateError(f"{where}: checks.{rule} has unknown keys {sorted(unknown)}")
    severity = data.get("severity", CHECKS_BY_RULE[rule].default_severity)
    if severity not in SEVERITIES:
        raise GateError(f"{where}: checks.{rule}.severity must be FAIL or WARN")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise GateError(f"{where}: checks.{rule}.enabled must be true or false")
    return CheckConfig(
        enabled=enabled,
        severity=str(severity),
        paths=_globs(_string_list(data, "paths", f"{where}: checks.{rule}")),
        exclude=_globs(_string_list(data, "exclude", f"{where}: checks.{rule}")),
    )


def parse_config(value: object, where: str) -> Config:
    data = _json_object(value, f"{where}: top level")
    unknown = set(data) - CONFIG_KEYS
    if unknown:
        raise GateError(f"{where}: unknown keys {sorted(unknown)}")
    checks = _json_object(data.get("checks", {}), f"{where}: 'checks'")
    return Config(
        skip_globs=_globs(_string_list(data, "skip_globs", where)),
        checks={
            rule: _check_config(rule, check, where) for rule, check in checks.items()
        },
        env_access_allowed=_globs(_string_list(data, "env_access_allowed", where)),
        module_level_call_ignore=_regexes(
            _string_list(data, "module_level_call_ignore", where), where
        ),
        module_level_construct_patterns=_regexes(
            _string_list(data, "module_level_construct_patterns", where), where
        ),
    )


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"{path}: invalid JSON: {exc}") from exc
    return parse_config(data, str(path))


def parse_allowlist(text: str, where: str) -> list[AllowEntry]:
    entries = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rule, _, rest = line.partition(":")
        if rule in CHECKS_BY_RULE:
            scope, pattern = rule, rest
        else:
            scope, pattern = None, line
        try:
            entries.append(AllowEntry(scope, re.compile(pattern)))
        except re.error as exc:
            raise GateError(
                f"{where}:{lineno}: invalid regex {pattern!r}: {exc}"
            ) from exc
    return entries


def load_allowlist(path: Path) -> list[AllowEntry]:
    if not path.exists():
        return []
    return parse_allowlist(path.read_text(encoding="utf-8"), str(path))


DIFF_ARGS = ("diff", "-U0", "--no-color", "--no-ext-diff", "--diff-filter=AMR")


def git(repo: Path | None, *args: str) -> str:
    cmd = ["git", "-c", "core.quotePath=false"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    proc = subprocess.run(
        [*cmd, *args], capture_output=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def read_whole_file(repo: Path, path: str) -> list[Line]:
    try:
        text = (repo / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows = text.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return [Line(path, lineno, row) for lineno, row in enumerate(rows, start=1)]


def read_files(repo: Path, paths: Iterable[str], cfg: Config) -> list[Line]:
    lines: list[Line] = []
    for path in paths:
        if path_in_scope(path, cfg):
            lines.extend(read_whole_file(repo, path))
    return lines


def collect_range(repo: Path, git_range: str) -> list[Line]:
    return parse_unified_diff(git(repo, *DIFF_ARGS, git_range))


def collect_worktree(repo: Path, cfg: Config) -> list[Line]:
    lines = parse_unified_diff(git(repo, *DIFF_ARGS, "HEAD"))
    untracked = git(repo, "ls-files", "-z", "--others", "--exclude-standard")
    return lines + read_files(repo, filter(None, untracked.split("\0")), cfg)


def collect_files(repo: Path, args: Sequence[str], cfg: Config) -> list[Line]:
    paths: list[str] = []
    for arg in args:
        absolute = Path(arg).resolve()
        if not absolute.exists():
            raise GateError(f"no such file or directory: {arg}")
        relative = os.path.relpath(absolute, repo)
        if absolute.is_dir():
            tracked = git(repo, "ls-files", "-z", "--", relative)
            paths.extend(filter(None, tracked.split("\0")))
        else:
            paths.append(Path(relative).as_posix())
    return read_files(repo, dict.fromkeys(paths), cfg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check added lines against the conventions rules."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--range", dest="git_range", metavar="GIT_RANGE")
    mode.add_argument("--worktree", action="store_true")
    mode.add_argument("--files", nargs="+", metavar="PATH")
    parser.add_argument("--repo", help="repository root (default: git toplevel of cwd)")
    return parser


def run(args: argparse.Namespace, config_dir: Path) -> Result:
    cfg = load_config(config_dir / CONFIG_FILENAME)
    allow = load_allowlist(config_dir / ALLOW_FILENAME)
    repo_arg = Path(args.repo) if args.repo else None
    repo = Path(git(repo_arg, "rev-parse", "--show-toplevel").strip()).resolve()
    if args.git_range:
        lines = collect_range(repo, args.git_range)
    elif args.worktree:
        lines = collect_worktree(repo, cfg)
    else:
        lines = collect_files(repo, args.files, cfg)
    return run_checks(lines, cfg, allow)


def main(argv: Sequence[str] | None = None, config_dir: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args, config_dir or Path(__file__).resolve().parent)
    except GateError as exc:
        print(f"conventions_gate: error: {exc}", file=sys.stderr)
        return 2
    print(format_result(result))
    return 1 if result.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
