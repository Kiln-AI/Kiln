import json
from typing import Any, Dict


def parse_json_string(json_string: str) -> Dict[str, Any]:
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
        raise ValueError(
            f"This task requires JSON output but the model didn't return valid JSON. Search 'Troubleshooting Structured Data Issues' in our docs for more information. The model produced the following: {cleaned_string}"
        ) from e
