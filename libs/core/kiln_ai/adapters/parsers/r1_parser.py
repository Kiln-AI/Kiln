from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.parsers.json_parser import parse_json_string
from kiln_ai.adapters.run_output import RunOutput


class R1ThinkingParser(BaseParser):
    START_TAG = "<think>"
    END_TAG = "</think>"

    def parse_output(self, original_output: RunOutput) -> RunOutput:
        """
        Parse the <think> </think> tags from the response into the intermediate and final outputs.

        Args:
            original_output: RunOutput containing the raw response string

        Returns:
            ParsedOutput containing the intermediate content (thinking content) and final result

        Raises:
            ValueError: If response format is invalid (missing tags, multiple tags, or no content after closing tag)
        """

        # The upstream providers (litellm, openrouter, fireworks) all keep changing their response formats, sometimes adding reasoning parsing where it didn't previously exist.
        # If they do it already, great just return. If not we parse it ourselves. Not ideal, but better than upstream changes breaking the app.
        if (
            original_output.intermediate_outputs is not None
            and "reasoning" in original_output.intermediate_outputs
        ):
            return original_output

        # This parser only works for strings
        if not isinstance(original_output.output, str):
            raise ValueError("Response must be a string for R1 parser")

        # Strip whitespace and validate basic structure
        cleaned_response = original_output.output.strip()

        # Find the thinking tags
        think_end = cleaned_response.find(self.END_TAG)
        if think_end == -1:
            raise ValueError("Missing </think> tag")

        think_tag_start = cleaned_response.find(self.START_TAG)
        if think_tag_start == -1:
            # We allow no start <think>, thinking starts on first char. QwQ does this.
            think_start = 0
        else:
            think_start = think_tag_start + len(self.START_TAG)

        # Check for multiple tags
        if (
            cleaned_response.count(self.START_TAG) > 1
            or cleaned_response.count(self.END_TAG) > 1
        ):
            raise ValueError("Multiple thinking tags found")

        # Extract thinking content
        thinking_content = cleaned_response[think_start:think_end].strip()

        # Extract result (everything after </think>)
        result = cleaned_response[think_end + len(self.END_TAG) :].strip()

        if not result or len(result) == 0:
            raise ValueError("No content found after </think> tag")

        # Add thinking content to intermediate outputs if it exists
        intermediate_outputs = original_output.intermediate_outputs or {}
        intermediate_outputs["reasoning"] = thinking_content

        return RunOutput(
            output=result,
            intermediate_outputs=intermediate_outputs,
        )
