# Phase 2: Skill Tool Implementation

## Goal
Implement the `SkillTool` that agents use to discover and load skills at runtime. Integrate into the tool registry and run config.

## Files to Create/Modify

### New: `libs/core/kiln_ai/tools/skill_tool.py`

The SkillTool follows the OpenCode pattern: available skills are listed in the tool description as XML, and agents call the tool to load a skill's content.

```python
from kiln_ai.datamodel.skill import Skill
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)
from kiln_ai.datamodel.tool_id import ToolId


class SkillTool(KilnToolInterface):
    """Tool that provides agents access to skills.
    
    Lists available skills in the tool description. Agents call it
    with a skill name to load the full instructions.
    """
    
    def __init__(self, tool_id: str, skills: list[Skill]):
        self._tool_id = tool_id
        self._skills = {s.skill_name: s for s in skills}
    
    async def id(self) -> ToolId:
        return self._tool_id
    
    async def name(self) -> str:
        return "skill"
    
    async def description(self) -> str:
        skills_xml = "\n".join(
            f'  <skill>\n    <name>{s.skill_name}</name>\n    <description>{s.skill_description}</description>\n  </skill>'
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
        
        if not skill_name:
            return ToolCallResult(output="Error: 'name' parameter is required.")
        
        skill = self._skills.get(skill_name)
        if skill is None:
            available = ", ".join(self._skills.keys())
            return ToolCallResult(
                output=f"Error: Skill '{skill_name}' not found. Available skills: {available}"
            )
        
        return ToolCallResult(output=skill.body)
```

### Modify: `libs/core/kiln_ai/datamodel/tool_id.py`

Add skill tool ID support:

```python
SKILL_TOOL_ID_PREFIX = "kiln_tool::skill::"

# Add to _check_tool_id():
if id.startswith(SKILL_TOOL_ID_PREFIX):
    skill_id = skill_id_from_tool_id(id)
    if not skill_id:
        raise ValueError(
            f"Invalid skill tool ID: {id}. Expected format: 'kiln_tool::skill::<skill_id>'."
        )
    return id

# New helper functions:
def skill_id_from_tool_id(id: str) -> str:
    parts = id.split("::")
    if not id.startswith(SKILL_TOOL_ID_PREFIX) or len(parts) != 3:
        raise ValueError(
            f"Invalid skill tool ID: {id}. Expected format: 'kiln_tool::skill::<skill_id>'."
        )
    return parts[2]

def build_skill_tool_id(skill_id: str) -> str:
    return f"{SKILL_TOOL_ID_PREFIX}{skill_id}"
```

### Modify: `libs/core/kiln_ai/tools/tool_registry.py`

Add skill tool resolution to `tool_from_id()`:

```python
from kiln_ai.datamodel.tool_id import SKILL_TOOL_ID_PREFIX, skill_id_from_tool_id

# In tool_from_id(), after the RAG tool check:
elif tool_id.startswith(SKILL_TOOL_ID_PREFIX):
    project = task.parent_project() if task is not None else None
    if project is None:
        raise ValueError(
            f"Unable to resolve tool from id: {tool_id}. Requires a parent project/task."
        )
    
    skill_id = skill_id_from_tool_id(tool_id)
    skill = Skill.from_id_and_parent_path(skill_id, project.path)
    if skill is None:
        raise ValueError(
            f"Skill not found: {skill_id} in project {project.id}"
        )
    
    return SkillTool(tool_id, [skill])
```

**Important design note**: The `tool_from_id` approach returns one tool per skill ID. But the *preferred* pattern is to have a **single SkillTool per run** that bundles all selected skills together (so the agent sees one `skill` tool with all available skills listed). This means:

- The run config stores individual skill tool IDs: `["kiln_tool::skill::123", "kiln_tool::skill::456"]`
- But at runtime, the adapter should **consolidate** these into a single SkillTool with all referenced skills
- This consolidation should happen in `BaseAdapter.available_tools()` or the LiteLlm adapter

### Modify: `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`

Add skill consolidation to `available_tools()`:

```python
async def available_tools(self) -> list[KilnToolInterface]:
    # ... existing tool resolution ...
    
    # Consolidate skill tools into a single SkillTool
    skill_tools = [t for t in tools if isinstance(t, SkillTool)]
    non_skill_tools = [t for t in tools if not isinstance(t, SkillTool)]
    
    if skill_tools:
        all_skills = []
        for st in skill_tools:
            all_skills.extend(st._skills.values())
        consolidated = SkillTool("kiln_tool::skill", all_skills)
        non_skill_tools.append(consolidated)
    
    return non_skill_tools
```

### New: `libs/core/kiln_ai/tools/test_skill_tool.py`

Tests:

1. **Tool definition tests**:
   - `toolcall_definition()` returns correct schema with name/resource params
   - `description()` includes XML listing of all skills
   - `name()` returns `"skill"`

2. **Skill loading tests**:
   - `run(name="valid-skill")` returns `skill.body` content
   - `run(name="unknown")` returns error with available skill names
   - `run()` with no name returns error

3. **Consolidation tests**:
   - Multiple skill IDs in run config are consolidated into one SkillTool
   - Consolidated tool lists all skills in description

## Key Design Notes

- The tool name is simply `"skill"` — matches both Claude Code and OpenCode conventions
- Available skills are listed in XML in the tool description (OpenCode pattern), not in the system prompt
- No `resource` parameter in V1 — add when import/export with references/assets is built
- Skill tool IDs in the run config are individual (`kiln_tool::skill::123`), but at runtime they merge into one tool
- Error messages are informative: listing available skills/resources when not found
