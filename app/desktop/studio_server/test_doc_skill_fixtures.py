from unittest.mock import MagicMock

from kiln_ai.datamodel.extraction import (
    Document,
    ExtractorType,
)

LITELLM_PROPERTIES = {
    "extractor_type": ExtractorType.LITELLM,
    "prompt_document": "Transcribe.",
    "prompt_audio": "Transcribe.",
    "prompt_video": "Transcribe.",
    "prompt_image": "Describe.",
}


def make_mock_document(name, doc_id="doc1", name_override=None, tags=None):
    doc = MagicMock(spec=Document)
    doc.name = name
    doc.name_override = name_override
    doc.id = doc_id
    doc.tags = tags or []
    return doc
