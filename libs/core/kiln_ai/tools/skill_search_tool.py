import re
from dataclasses import dataclass, field

import yaml

from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

REFERENCES_PREFIX = "references/"

DEFAULT_CONTEXT = 0
DEFAULT_MAX_MATCHES_PER_FILE = 10
DEFAULT_MAX_FILES = 20
DEFAULT_MAX_LINE_LENGTH = 240

CONTEXT_RANGE = (0, 10)
MAX_MATCHES_PER_FILE_RANGE = (1, 100)
MAX_FILES_RANGE = (1, 100)
MAX_LINE_LENGTH_RANGE = (40, 1000)

_H1_SEARCH_LINES = 10


@dataclass
class _Hunk:
    start: int
    end: int
    match_lines: set[int] = field(default_factory=set)


class SkillSearchTool(KilnToolInterface):
    """Regex search across a skill's markdown references.

    The agent calls ``skill_search(name, pattern)`` to find candidate files
    by content before reading any of them in full via ``skill(name, resource=...)``.
    Matches are case-insensitive and line-by-line. Only markdown files
    under ``references/`` are searched; assets are not indexed.
    """

    def __init__(self, tool_id: str, skills: list[Skill]):
        self._tool_id = tool_id
        self._skills = {s.name: s for s in skills}

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return "skill_search"

    async def description(self) -> str:
        return (
            "Search a skill's markdown reference files with a regex pattern. "
            "Use this when you don't know which reference file discusses a given concept — "
            "it returns matching lines grouped by file so you can then open specific files "
            "with skill(name, resource=...). Matches are case-insensitive and line-by-line. "
            "Scope the search with 'path_prefix' (e.g. 'references/knowledge/') or target one "
            "file with 'resource'. Use 'context_before'/'context_after' (or the 'context_lines' "
            "shorthand) to see surrounding lines."
        )

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The name of the skill to search.",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Python regex, matched line-by-line with re.IGNORECASE.",
                        },
                        "resource": {
                            "type": "string",
                            "description": (
                                "Optional. Search only inside this single markdown file "
                                "(e.g. 'references/modes/improve_task.md'). Mutually exclusive "
                                "with 'path_prefix'. Must start with 'references/' and end with '.md'."
                            ),
                        },
                        "path_prefix": {
                            "type": "string",
                            "description": (
                                "Optional. Subdirectory scope (e.g. 'references/knowledge/'). "
                                "Mutually exclusive with 'resource'. Must start with 'references/'. "
                                "Defaults to the whole references tree."
                            ),
                        },
                        "context_before": {
                            "type": "integer",
                            "description": (
                                f"Optional. Context lines before each match. Default {DEFAULT_CONTEXT}. "
                                f"Clamped to [{CONTEXT_RANGE[0]}, {CONTEXT_RANGE[1]}]."
                            ),
                        },
                        "context_after": {
                            "type": "integer",
                            "description": (
                                f"Optional. Context lines after each match. Default {DEFAULT_CONTEXT}. "
                                f"Clamped to [{CONTEXT_RANGE[0]}, {CONTEXT_RANGE[1]}]."
                            ),
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": (
                                "Optional shorthand. Sets both context_before and context_after. "
                                "Mutually exclusive with either of those. "
                                f"Clamped to [{CONTEXT_RANGE[0]}, {CONTEXT_RANGE[1]}]."
                            ),
                        },
                        "max_matches_per_file": {
                            "type": "integer",
                            "description": (
                                f"Optional. Default {DEFAULT_MAX_MATCHES_PER_FILE}. "
                                f"Clamped to [{MAX_MATCHES_PER_FILE_RANGE[0]}, {MAX_MATCHES_PER_FILE_RANGE[1]}]."
                            ),
                        },
                        "max_files": {
                            "type": "integer",
                            "description": (
                                f"Optional. Overall result cap. Default {DEFAULT_MAX_FILES}. "
                                f"Clamped to [{MAX_FILES_RANGE[0]}, {MAX_FILES_RANGE[1]}]."
                            ),
                        },
                        "max_line_length": {
                            "type": "integer",
                            "description": (
                                f"Optional. Per-line truncation. Default {DEFAULT_MAX_LINE_LENGTH}. "
                                f"Clamped to [{MAX_LINE_LENGTH_RANGE[0]}, {MAX_LINE_LENGTH_RANGE[1]}]."
                            ),
                        },
                    },
                    "required": ["name", "pattern"],
                },
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        skill_name = kwargs.get("name")
        pattern = kwargs.get("pattern")
        resource = kwargs.get("resource")
        path_prefix = kwargs.get("path_prefix")
        context_lines_arg = kwargs.get("context_lines")
        context_before_arg = kwargs.get("context_before")
        context_after_arg = kwargs.get("context_after")
        max_matches_per_file_arg = kwargs.get("max_matches_per_file")
        max_files_arg = kwargs.get("max_files")
        max_line_length_arg = kwargs.get("max_line_length")

        if not isinstance(skill_name, str) or not skill_name:
            return ToolCallResult(output="Error: 'name' parameter is required.")

        skill = self._skills.get(skill_name)
        if skill is None:
            available = ", ".join(self._skills.keys())
            return ToolCallResult(
                output=f"Error: Skill '{skill_name}' not found. Available skills: {available}"
            )

        if not isinstance(pattern, str) or not pattern:
            return ToolCallResult(output="Error: 'pattern' parameter is required.")

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolCallResult(output=f"Error: Invalid regex: {e}")

        if resource and path_prefix:
            return ToolCallResult(
                output="Error: Provide either 'resource' or 'path_prefix', not both."
            )

        if context_lines_arg is not None and (
            context_before_arg is not None or context_after_arg is not None
        ):
            return ToolCallResult(
                output="Error: Use either 'context_lines' or 'context_before'/'context_after', not both."
            )

        if context_lines_arg is not None:
            before = self._resolve_int(
                context_lines_arg, DEFAULT_CONTEXT, CONTEXT_RANGE
            )
            after = before
        else:
            before = self._resolve_int(
                context_before_arg, DEFAULT_CONTEXT, CONTEXT_RANGE
            )
            after = self._resolve_int(context_after_arg, DEFAULT_CONTEXT, CONTEXT_RANGE)

        max_matches_per_file = self._resolve_int(
            max_matches_per_file_arg,
            DEFAULT_MAX_MATCHES_PER_FILE,
            MAX_MATCHES_PER_FILE_RANGE,
        )
        max_files = self._resolve_int(max_files_arg, DEFAULT_MAX_FILES, MAX_FILES_RANGE)
        max_line_length = self._resolve_int(
            max_line_length_arg, DEFAULT_MAX_LINE_LENGTH, MAX_LINE_LENGTH_RANGE
        )

        corpus: list[tuple[str, str]]
        scope_label: str | None

        if resource is not None:
            if not isinstance(resource, str) or not resource.startswith(
                REFERENCES_PREFIX
            ):
                return ToolCallResult(
                    output="Error: 'resource' must start with 'references/'"
                )
            if not resource.endswith(".md"):
                return ToolCallResult(
                    output="Error: Only markdown files (.md) are searchable"
                )
            rel = resource[len(REFERENCES_PREFIX) :]
            if not rel:
                return ToolCallResult(
                    output="Error: 'resource' must be a file path. Use 'path_prefix' to search a directory."
                )
            base_dir = skill.references_dir()
            try:
                base_resolved = base_dir.resolve()
                target = (base_dir / rel).resolve()
                target.relative_to(base_resolved)
            except ValueError:
                return ToolCallResult(output="Error: Path traversal is not allowed")
            if not target.exists():
                return ToolCallResult(output=f"Error: Resource not found: {resource}")
            if target.is_dir():
                return ToolCallResult(
                    output="Error: 'resource' must be a file path. Use 'path_prefix' to search a directory."
                )
            try:
                content = skill.read_reference(rel)
            except FileNotFoundError:
                return ToolCallResult(output=f"Error: Resource not found: {resource}")
            except ValueError as e:
                return ToolCallResult(output=f"Error: {e}")
            corpus = [(rel, content)]
            scope_label = resource
        else:
            if path_prefix is not None:
                if not isinstance(path_prefix, str) or not path_prefix.startswith(
                    REFERENCES_PREFIX
                ):
                    return ToolCallResult(
                        output="Error: 'path_prefix' must start with 'references/'"
                    )
                prefix_rel = path_prefix[len(REFERENCES_PREFIX) :].rstrip("/") or None
                scope_label = path_prefix
            else:
                prefix_rel = None
                scope_label = None
            try:
                corpus = list(skill.iter_markdown_references(prefix=prefix_rel))
            except ValueError as e:
                return ToolCallResult(output=f"Error: {e}")

        file_blocks: list[str] = []
        files_matched = 0
        truncated_files = 0
        total_matches_shown = 0

        for rel_path, text in corpus:
            lines = text.splitlines()
            match_indices = [i for i, line in enumerate(lines) if regex.search(line)]
            if not match_indices:
                continue

            files_matched += 1

            if len(file_blocks) >= max_files:
                truncated_files += 1
                continue

            truncated_per_file = max(0, len(match_indices) - max_matches_per_file)
            shown_match_indices = match_indices[:max_matches_per_file]
            hunks = self._merge_hunks(shown_match_indices, before, after, len(lines))
            frontmatter = self._parse_frontmatter(text)
            block = self._render_file_block(
                rel_path=rel_path,
                lines=lines,
                hunks=hunks,
                frontmatter=frontmatter,
                raw_text=text,
                max_line_length=max_line_length,
                truncated_per_file=truncated_per_file,
            )
            file_blocks.append(block)
            total_matches_shown += len(shown_match_indices)

        if files_matched == 0:
            return ToolCallResult(
                output=self._no_match_message(pattern, skill_name, scope_label)
            )

        footer = self._build_footer(
            skill_name=skill_name,
            files_shown=len(file_blocks),
            truncated_files=truncated_files,
            total_matches_shown=total_matches_shown,
        )
        return ToolCallResult(output="\n\n".join(file_blocks) + "\n\n" + footer)

    @staticmethod
    def _resolve_int(value: object, default: int, clamp_range: tuple[int, int]) -> int:
        lo, hi = clamp_range
        if value is None:
            v = default
        else:
            try:
                v = int(value)  # type: ignore[call-overload]
            except (TypeError, ValueError):
                v = default
        return max(lo, min(hi, v))

    @staticmethod
    def _merge_hunks(
        match_indices: list[int], before: int, after: int, total: int
    ) -> list[_Hunk]:
        if not match_indices or total == 0:
            return []
        hunks: list[_Hunk] = []
        for m in match_indices:
            start = max(0, m - before)
            end = min(total - 1, m + after)
            if hunks and start <= hunks[-1].end + 1:
                prev = hunks[-1]
                prev.end = max(prev.end, end)
                prev.match_lines.add(m)
            else:
                hunks.append(_Hunk(start=start, end=end, match_lines={m}))
        return hunks

    @staticmethod
    def _parse_frontmatter(text: str) -> dict[str, str]:
        if not text.startswith("---\n"):
            return {}
        try:
            end_idx = text.index("\n---\n", 3)
        except ValueError:
            return {}
        fm_text = text[4:end_idx]
        try:
            data = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            return {}
        if not isinstance(data, dict):
            return {}
        result: dict[str, str] = {}
        for key in ("name", "description"):
            value = data.get(key)
            if value is None:
                continue
            result[key] = " ".join(str(value).split())
        return result

    @staticmethod
    def _extract_first_h1(raw_text: str) -> str | None:
        body = raw_text
        if body.startswith("---\n"):
            try:
                end_idx = body.index("\n---\n", 3)
                body = body[end_idx + 5 :]
            except ValueError:
                pass
        body = body.lstrip("\n")
        for i, line in enumerate(body.splitlines()):
            if i >= _H1_SEARCH_LINES:
                break
            if line.startswith("# "):
                return line
        return None

    @staticmethod
    def _render_file_block(
        rel_path: str,
        lines: list[str],
        hunks: list[_Hunk],
        frontmatter: dict[str, str],
        raw_text: str,
        max_line_length: int,
        truncated_per_file: int,
    ) -> str:
        out: list[str] = [f"=== references/{rel_path} ({len(lines)} lines) ==="]

        if "name" in frontmatter:
            out.append(f"name: {frontmatter['name']}")
        if "description" in frontmatter:
            out.append(f"description: {frontmatter['description']}")

        if not frontmatter:
            h1 = SkillSearchTool._extract_first_h1(raw_text)
            if h1:
                out.append(h1)

        for hi, hunk in enumerate(hunks):
            if hi > 0:
                out.append("")
            for i in range(hunk.start, hunk.end + 1):
                sep = ":" if i in hunk.match_lines else "-"
                line_str = lines[i] if i < len(lines) else ""
                if len(line_str) > max_line_length:
                    line_str = line_str[: max_line_length - 1] + "…"
                out.append(f"  {i + 1}{sep} {line_str}")

        if truncated_per_file > 0:
            out.append(
                f"  ... (truncated: {truncated_per_file} more matches in this file)"
            )

        return "\n".join(out)

    @staticmethod
    def _build_footer(
        skill_name: str,
        files_shown: int,
        truncated_files: int,
        total_matches_shown: int,
    ) -> str:
        file_part = f"Found {files_shown} files"
        if truncated_files > 0:
            file_part += f" (+{truncated_files} more truncated)"
        return (
            f"{file_part}, {total_matches_shown} matches shown. "
            f'Read a full file with skill(name="{skill_name}", resource="references/...").'
        )

    @staticmethod
    def _no_match_message(
        pattern: str, skill_name: str, scope_label: str | None
    ) -> str:
        if scope_label:
            return (
                f"No matches for pattern '{pattern}' in skill '{skill_name}' "
                f"under '{scope_label}'."
            )
        return f"No matches for pattern '{pattern}' in skill '{skill_name}'."
