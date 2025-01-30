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
        # TODO
        print(f"original_output: {original_output.output}")

        # This parser only works for strings
        if not isinstance(original_output.output, str):
            raise ValueError("Response must be a string for R1 parser")
        if (
            original_output.intermediate_outputs
            and len(original_output.intermediate_outputs) > 0
        ):
            raise ValueError("Intermediate outputs must be empty for R1 parser")

        # Strip whitespace and validate basic structure
        cleaned_response = original_output.output.strip()
        if not cleaned_response.startswith(self.START_TAG):
            raise ValueError("Response must start with <think> tag")

        # Find the thinking tags
        think_start = cleaned_response.find(self.START_TAG)
        think_end = cleaned_response.find(self.END_TAG)

        if think_start == -1 or think_end == -1:
            raise ValueError("Missing thinking tags")

        # Check for multiple tags
        if (
            cleaned_response.count(self.START_TAG) > 1
            or cleaned_response.count(self.END_TAG) > 1
        ):
            raise ValueError("Multiple thinking tags found")

        # Extract thinking content
        thinking_content = cleaned_response[
            think_start + len(self.START_TAG) : think_end
        ].strip()
        if len(thinking_content) == 0:
            thinking_content = None

        # Extract result (everything after </think>)
        result = cleaned_response[think_end + len(self.END_TAG) :].strip()

        if not result or len(result) == 0:
            raise ValueError("No content found after </think> tag")

        # Parse JSON if needed
        output = result
        if self.structured_output:
            output = parse_json_string(result)

        return RunOutput(
            output=output,
            intermediate_outputs={"reasoning": thinking_content},
        )
