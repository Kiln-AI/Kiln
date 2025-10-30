import logging

from kiln_ai.datamodel import TaskRun
from kiln_ai.tools.tool_registry import tool_from_id

logger = logging.getLogger(__name__)


class EvalUtils:
    @staticmethod
    async def formatted_available_tools_from_task_run(task_run: TaskRun) -> str | None:
        """Get the formatted available tools from a task run.
        Args:
            task_run: The task run to get the available tools from.

        Returns:
            The formatted available tools. If we failed to get the available tools, return None.
            If there are no available tools, return an empty string.
            If we failed to get the tool definition for a tool, log an error and continue.
        """
        if (
            not task_run.parent_task()
            or not task_run.output.source
            or not task_run.output.source.run_config
            or not task_run.output.source.run_config.tools_config
        ):
            return None

        available_tools = task_run.output.source.run_config.tools_config.tools
        if not available_tools:
            return ""

        available_tools_str = ""

        for index, tool in enumerate(available_tools):
            tool_object = tool_from_id(tool, task_run.parent_task())
            try:
                tool_definition = await tool_object.toolcall_definition()
                tool_name = tool_definition["function"]["name"]
                tool_description = tool_definition["function"]["description"]
                if index > 0:
                    available_tools_str += "\n\n"
                available_tools_str += f"<tool>\n<tool_name>\n{tool_name}</tool_name>\n<tool_description>\n{tool_description}\n</tool_description>\n</tool>"
            except Exception as e:
                logger.error(
                    f"Failed to get tool definition for tool: {tool}. Error: {e}",
                    exc_info=True,
                )
                continue

        return available_tools_str
