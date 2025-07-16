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

            if not reasoning_content:
                raise RuntimeError(
                    "The response is malformed, missing or empty reasoning content"
                )

            if reasoning_content.count(self.START_TAG) > 1:
                raise RuntimeError(
                    f"The response is malformed, multiple {self.START_TAG} tags found in the reasoning content"
                )

            if reasoning_content.count(self.END_TAG) > 1:
                raise RuntimeError(
                    f"The response is malformed, multiple {self.END_TAG} tags found in the reasoning content"
                )

            if not reasoning_content.endswith(self.END_TAG):
                raise RuntimeError(
                    f"The response is malformed, missing the end {self.END_TAG} tag in the reasoning content"
                )

            result = reasoning_content
            if reasoning_content.startswith(
                self.START_TAG
            ) and reasoning_content.endswith(self.END_TAG):
                result = reasoning_content[
                    len(self.START_TAG) : -len(self.END_TAG)
                ].strip()

            # we tolerate a case where the start tag is missing
            result = result.replace(self.END_TAG, "")

        return RunOutput(
            output=result,
            intermediate_outputs=None,
        )
