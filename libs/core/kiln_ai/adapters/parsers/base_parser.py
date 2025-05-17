from kiln_ai.adapters.run_output import RunOutput


class BaseParser:
    def parse_output(self, original_output: RunOutput) -> RunOutput:
        """
        Method for parsing the output of a model. Typically overridden by subclasses.
        """
        return original_output
