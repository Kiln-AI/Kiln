from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)


class SkillTool(KilnToolInterface):
    """Tool that provides agents access to skills.

    Lists available skills in the tool description. Agents call it
    with a skill name to load the full instructions.
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
        skills_xml = "\n".join(
            f"  <skill>\n    <name>{s.name}</name>\n    <description>{s.description}</description>\n  </skill>"
            for s in self._skills.values()
        )
        return (
            "Load an agent skill by name. Skills provide specialized instructions "
            "for specific tasks. Call this tool with the skill name to load its "
            "full instructions.\n\n"
            f"<available_skills>\n{skills_xml}\n</available_skills>"
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
                    },
                    "required": ["name"],
                },
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        skill_name = kwargs.get("name")

        if not isinstance(skill_name, str) or not skill_name:
            return ToolCallResult(output="Error: 'name' parameter is required.")

        skill = self._skills.get(skill_name)
        if skill is None:
            available = ", ".join(self._skills.keys())
            return ToolCallResult(
                output=f"Error: Skill '{skill_name}' not found. Available skills: {available}"
            )

        return ToolCallResult(output=skill.body)
