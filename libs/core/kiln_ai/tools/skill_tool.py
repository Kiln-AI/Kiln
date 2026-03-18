from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

ALLOWED_RESOURCE_PREFIXES = ("references/",)


class SkillTool(KilnToolInterface):
    """Tool that lets agents load skill instructions by name.

    Available skills and their descriptions are listed in the system prompt.
    The agent calls this tool with a skill name to retrieve its full body.
    Optionally, the agent can request a specific resource file within the skill.
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
            "(e.g. 'references/filename.md')."
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
                            "description": "Optional. Path to a specific resource file within the skill (e.g. 'references/REFERENCE.md'). If omitted, returns the skill's main instructions.",
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
        """Load a resource file from the references/ directory."""
        if not any(resource.startswith(p) for p in ALLOWED_RESOURCE_PREFIXES):
            return ToolCallResult(
                output=f"Error: Resource path must start with one of: {', '.join(ALLOWED_RESOURCE_PREFIXES)}"
            )

        if ".." in resource:
            return ToolCallResult(output="Error: Invalid resource path.")

        parts = resource.split("/", 1)
        if len(parts) != 2 or not parts[1]:
            return ToolCallResult(
                output="Error: Resource path must include a filename after the directory prefix."
            )

        _, filename = parts

        try:
            content = skill.read_reference(filename)
            return ToolCallResult(output=content)
        except FileNotFoundError:
            return ToolCallResult(output=f"Error: Resource not found: {resource}")
        except ValueError as e:
            return ToolCallResult(output=f"Error: {e}")
