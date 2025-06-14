from unittest.mock import patch

import pytest

from kiln_ai.adapters.extractors.extraction_prompt_builder import (
    ExtractionPromptBuilder,
)
from kiln_ai.datamodel.extraction import Kind, OutputFormat


@pytest.mark.parametrize(
    "kind,output_format",
    [
        (Kind.AUDIO, OutputFormat.MARKDOWN),
        (Kind.IMAGE, OutputFormat.MARKDOWN),
        (Kind.DOCUMENT, OutputFormat.MARKDOWN),
        (Kind.VIDEO, OutputFormat.TEXT),
    ],
)
def test_extraction_prompt_builder_formats(kind, output_format):
    prompt_method = f"prompt_{kind.value.lower()}"
    with patch.object(
        ExtractionPromptBuilder,
        prompt_method,
        wraps=getattr(ExtractionPromptBuilder, prompt_method),
    ) as mock_prompt:
        prompt = ExtractionPromptBuilder.prompt_for_kind(kind, output_format)
        mock_prompt.assert_called_with(output_format)

        # Simple format check based on output_format
        if output_format == OutputFormat.MARKDOWN:
            assert "text/markdown" in prompt
            assert "text/plain" not in prompt
        else:
            assert "text/plain" in prompt
            assert "text/markdown" not in prompt


def test_extraction_prompt_builder_invalid_kind():
    with pytest.raises(
        ValueError, match="Cannot build prompt for unknown kind: 'invalid-kind'"
    ):
        ExtractionPromptBuilder.prompt_for_kind("invalid-kind", OutputFormat.TEXT)
