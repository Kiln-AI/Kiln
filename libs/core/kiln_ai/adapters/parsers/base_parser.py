from kiln_ai.adapters.run_output import RunOutput


class BaseParser:
    def parse_output(self, original_output: RunOutput) -> RunOutput:
        """
        Method for parsing the output of a model. Typically overridden by subclasses.
        """

        if original_output.output is not None and isinstance(
            original_output.output, str
        ):
            original_output.output = original_output.output.strip()

        if original_output.intermediate_outputs is not None:
            for key, value in original_output.intermediate_outputs.items():
                if isinstance(value, str):
                    original_output.intermediate_outputs[key] = value.strip()

        return original_output
