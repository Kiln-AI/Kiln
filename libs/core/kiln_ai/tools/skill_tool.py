from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

ALLOWED_RESOURCE_PREFIXES = ("references/", "assets/")


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
            "may help solve the user's task. Skills use progressive disclosure: "
            "call skill(name) first to load the skill's instruction page. That "
            "page is the only place a skill's resource files are listed. If it "
            "points at a file you need, call skill(name, resource) and copy the "
            "path exactly as the instructions wrote it. Resource paths always "
            "start with references/ or assets/, but never guess or assemble one: "
            "a path the instructions do not list does not exist, and many skills "
            "ship no resource files at all."
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
                            "description": "The name of the skill to load, exactly as listed in the system prompt.",
                        },
                        "resource": {
                            "type": "string",
                            "description": "Optional. Leave unset on the first call: that returns the skill's instructions, which list its resource files if it has any. Set this only to a path those instructions listed, copied verbatim (paths start with references/ or assets/). Never guess a path; unlisted paths do not exist.",
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
        """Load a resource file from an allowed subdirectory (references/ or assets/)."""
        if not any(resource.startswith(p) for p in ALLOWED_RESOURCE_PREFIXES):
            return ToolCallResult(
                output=f"Error: Resource path must start with one of: {', '.join(ALLOWED_RESOURCE_PREFIXES)}"
            )

        try:
            return ToolCallResult(output=skill.read_resource_text(resource))
        except FileNotFoundError:
            return ToolCallResult(output=f"Error: Resource not found: {resource}")
        except ValueError as e:
            return ToolCallResult(output=f"Error: {e}")
