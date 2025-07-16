from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.run_output import RunOutput


class ReasoningAnswerTagsParser(BaseParser):
    START_TAG = "<answer>"
    END_TAG = "</answer>"

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

        # Some models (Hunyuan) on Siliconflow allow disabling thinking, but when thinking is disabled, the output is
        # wrapped in <answer> </answer> tags inside the reasoning_content and output is an empty string.
        # This parser will extract the content between the tags and set it as the output, and nullify the reasoning_content.
        result = original_output.output
        if (
            original_output.intermediate_outputs is not None
            and "reasoning" in original_output.intermediate_outputs
        ):
            reasoning_content = original_output.intermediate_outputs["reasoning"]
            if isinstance(reasoning_content, str):
                reasoning_content = reasoning_content.strip()

            if reasoning_content.startswith(
                self.START_TAG
            ) and reasoning_content.endswith(self.END_TAG):
                result = reasoning_content[
                    len(self.START_TAG) : -len(self.END_TAG)
                ].strip()
            else:
                # should not happen, but if reasoning_content is ever malformed (e.g. missing closing tag)
                # it is better to just move everything into the output, since this format is meant to always
                # be for non-thinking models
                result = reasoning_content

        return RunOutput(
            output=result,
            intermediate_outputs=None,
        )
