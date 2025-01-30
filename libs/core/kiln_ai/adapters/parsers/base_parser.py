import json
from typing import Any, Dict

from kiln_ai.adapters.run_output import RunOutput


class BaseParser:
    def __init__(self, structured_output: bool = False):
        self.structured_output = structured_output

    def parse_output(self, original_output: RunOutput) -> RunOutput:
        """
        Method for parsing the output of a model. Typically overridden by subclasses.
        """
        return original_output

    def parse_json_string(self, json_string: str) -> Dict[str, Any]:
        """
        Parse a JSON string into a dictionary. Handles multiple formats:
        - Plain JSON
        - JSON wrapped in ```json code blocks
        - JSON wrapped in ``` code blocks

        Args:
            json_string: String containing JSON data, possibly wrapped in code blocks

        Returns:
            Dict containing parsed JSON data

        Raises:
            ValueError: If JSON parsing fails
        """
        # Remove code block markers if present
        cleaned_string = json_string.strip()
        if cleaned_string.startswith("```"):
            # Split by newlines and remove first/last lines if they contain ```
            lines = cleaned_string.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_string = "\n".join(lines)

        try:
            return json.loads(cleaned_string)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {str(e)}") from e
