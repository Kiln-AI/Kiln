from pathlib import Path

from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

ALLOWED_RESOURCE_PREFIXES = ("references/", "assets/")
_RESOURCE_ROOTS = ("references", "assets")


class SkillTool(KilnToolInterface):
    """Tool that lets agents load skill instructions by name.

    Available skills and their descriptions are listed in the system prompt.
    The agent calls this tool with a skill name to retrieve its full body.
    Optionally, the agent can request a specific resource file within the skill,
    or list a resource directory's contents.
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
        return "skill"

    async def description(self) -> str:
        return (
            "Load an agent skill by name. Use this tool when a specialized skill "
            "may help solve the user's task. Calling the tool with a skill name loads that skill's "
            "full instructions. If the skill references additional files "
            "relevant to the task, load them by passing a 'resource' path "
            "(e.g. 'references/guide.md', 'references/subdir/notes.txt', or 'assets/template.csv'). "
            "Pass a directory path ('references/', 'references/subdir', 'assets/') to list its contents with line counts."
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
                            "description": "The name of the skill to load.",
                        },
                        "resource": {
                            "type": "string",
                            "description": "Optional. Path to a resource within the skill. A file path (e.g. 'references/guide.md', 'assets/data.csv') returns the file contents. A directory path (e.g. 'references/', 'references/subdir', 'assets/') returns a tree listing with line counts. If omitted, returns the skill's main instructions.",
                        },
                    },
                    "required": ["name"],
                },
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        skill_name = kwargs.get("name")
        resource = kwargs.get("resource")

        if not isinstance(skill_name, str) or not skill_name:
            return ToolCallResult(output="Error: 'name' parameter is required.")

        skill = self._skills.get(skill_name)
        if skill is None:
            available = ", ".join(self._skills.keys())
            return ToolCallResult(
                output=f"Error: Skill '{skill_name}' not found. Available skills: {available}"
            )

        if resource:
            return self._load_resource(skill, resource)

        try:
            body = skill.body()
        except Exception as e:
            return ToolCallResult(
                output=f"Error: Failed to load skill '{skill_name}': {e}"
            )
        return ToolCallResult(output=body)

    def _load_resource(self, skill: Skill, resource: str) -> ToolCallResult:
        """Load a file or render a directory listing under references/ or assets/."""
        root, rest = self._split_resource(resource)
        if root not in _RESOURCE_ROOTS:
            return ToolCallResult(
                output=f"Error: Resource path must start with one of: {', '.join(ALLOWED_RESOURCE_PREFIXES)}"
            )

        base_dir = (
            skill.references_dir() if root == "references" else skill.assets_dir()
        )

        try:
            base_resolved = base_dir.resolve()
            target = (base_dir / rest).resolve() if rest else base_resolved
            target.relative_to(base_resolved)
        except ValueError:
            return ToolCallResult(output="Error: Path traversal is not allowed")

        if not target.exists():
            return ToolCallResult(output=f"Error: Resource not found: {resource}")

        if target.is_dir():
            return ToolCallResult(
                output=self._render_directory_listing(skill, root, target)
            )

        try:
            if root == "references":
                content = skill.read_reference(rest)
            else:
                content = skill.read_asset(rest)
            return ToolCallResult(output=content)
        except FileNotFoundError:
            return ToolCallResult(output=f"Error: Resource not found: {resource}")
        except ValueError as e:
            return ToolCallResult(output=f"Error: {e}")

    @staticmethod
    def _split_resource(resource: str) -> tuple[str, str]:
        parts = resource.split("/", 1)
        root = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        return root, rest

    @staticmethod
    def _render_directory_listing(skill: Skill, root: str, dir_path: Path) -> str:
        """Render a tree listing of dir_path with per-markdown-file line counts.

        root: 'references' or 'assets'.
        dir_path: resolved absolute path to the directory being listed.
        """
        base_dir = (
            skill.references_dir() if root == "references" else skill.assets_dir()
        ).resolve()
        rel_dir = dir_path.relative_to(base_dir)
        display_root = (
            f"{root}/" if rel_dir == Path(".") else f"{root}/{rel_dir.as_posix()}/"
        )

        top_entries = sorted(
            dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())
        )
        if not top_entries:
            return f"Directory: {display_root}\n\n(empty)\nTotal: 0 files, 0 lines."

        tree_lines: list[str] = []
        totals = {"md_files": 0, "md_lines": 0}

        def walk(path: Path, prefix: str) -> None:
            entries = sorted(
                path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())
            )
            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                child_prefix = prefix + ("    " if is_last else "│   ")
                if entry.is_dir():
                    file_count = sum(1 for p in entry.rglob("*") if p.is_file())
                    tree_lines.append(
                        f"{prefix}{connector}{entry.name}/ ({file_count} files)"
                    )
                    walk(entry, child_prefix)
                elif entry.suffix == ".md":
                    rel = entry.relative_to(base_dir).as_posix()
                    try:
                        line_count = skill.count_file_lines(root, rel)
                        tree_lines.append(
                            f"{prefix}{connector}{entry.name} ({line_count} lines)"
                        )
                        totals["md_files"] += 1
                        totals["md_lines"] += line_count
                    except (ValueError, OSError, UnicodeDecodeError):
                        tree_lines.append(f"{prefix}{connector}{entry.name}")
                else:
                    tree_lines.append(f"{prefix}{connector}{entry.name}")

        walk(dir_path, "")

        output = [
            f"Directory: {display_root}",
            "",
            display_root,
            *tree_lines,
            "",
            f"Total: {totals['md_files']} markdown files, {totals['md_lines']} lines.",
            "",
            f'Tip: read a file with skill(name="{skill.name}", resource="{root}/..."). '
            f'Search with skill_search(name="{skill.name}", pattern="...").',
        ]
        return "\n".join(output)
