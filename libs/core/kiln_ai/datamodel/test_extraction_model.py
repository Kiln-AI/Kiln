import re
import uuid

import pytest

from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    Kind,
    OutputFormat,
    get_kind_from_mime_type,
    validate_prompt,
)
from kiln_ai.datamodel.project import Project


@pytest.fixture
def valid_extractor_config_data():
    return {
        "name": "Test Extractor Config",
        "description": "Test description",
        "extractor_type": ExtractorType.LITELLM,
        "model_provider_name": "gemini_api",
        "model_name": "gemini-2.0-flash",
        "properties": {
            "prompt_document": "Transcribe the document.",
            "prompt_audio": "Transcribe the audio.",
            "prompt_video": "Transcribe the video.",
            "prompt_image": "Describe the image.",
        },
    }


@pytest.fixture
def valid_extractor_config(valid_extractor_config_data):
    return ExtractorConfig(**valid_extractor_config_data)


def test_extractor_config_kind_coercion(valid_extractor_config):
    assert valid_extractor_config.prompt_document() == "Transcribe the document."
    assert valid_extractor_config.prompt_audio() == "Transcribe the audio."
    assert valid_extractor_config.prompt_video() == "Transcribe the video."
    assert valid_extractor_config.prompt_image() == "Describe the image."


def test_extractor_config_description_empty(valid_extractor_config_data):
    # should not raise an error when description is None
    valid_extractor_config_data["description"] = None
    valid_extractor_config = ExtractorConfig(**valid_extractor_config_data)
    assert valid_extractor_config.description is None


def test_extractor_config_valid(valid_extractor_config):
    assert valid_extractor_config.name == "Test Extractor Config"
    assert valid_extractor_config.description == "Test description"
    assert valid_extractor_config.extractor_type == ExtractorType.LITELLM
    assert valid_extractor_config.output_format == OutputFormat.MARKDOWN
    assert valid_extractor_config.model_provider_name == "gemini_api"
    assert valid_extractor_config.model_name == "gemini-2.0-flash"
    assert (
        valid_extractor_config.properties["prompt_document"]
        == "Transcribe the document."
    )
    assert valid_extractor_config.properties["prompt_audio"] == "Transcribe the audio."
    assert valid_extractor_config.properties["prompt_video"] == "Transcribe the video."
    assert valid_extractor_config.properties["prompt_image"] == "Describe the image."


def test_extractor_config_missing_model_name(valid_extractor_config):
    with pytest.raises(ValueError):
        valid_extractor_config.model_name = None

    with pytest.raises(ValueError):
        valid_extractor_config.model_provider_name = None


def test_extractor_config_missing_prompts(valid_extractor_config):
    # should not raise an error - prompts will be set to defaults
    with pytest.raises(ValueError):
        valid_extractor_config.properties = {}


def test_extractor_config_invalid_json(
    valid_extractor_config, valid_extractor_config_data
):
    class InvalidClass:
        pass

    with pytest.raises(ValueError, match="validation errors for ExtractorConfig"):
        valid_extractor_config.properties = {
            "prompt_document": valid_extractor_config_data["properties"][
                "prompt_document"
            ],
            "prompt_audio": valid_extractor_config_data["properties"]["prompt_audio"],
            "prompt_video": valid_extractor_config_data["properties"]["prompt_video"],
            "prompt_image": valid_extractor_config_data["properties"]["prompt_image"],
            "invalid_key": InvalidClass(),
        }


def test_extractor_config_invalid_prompt(valid_extractor_config):
    with pytest.raises(ValueError, match="prompt_document must be a string"):
        valid_extractor_config.properties = {
            "prompt_document": 123,
            "prompt_audio": "Transcribe the audio.",
            "prompt_video": "Transcribe the video.",
            "prompt_image": "Describe the image.",
        }


def test_extractor_config_missing_single_prompt(valid_extractor_config):
    with pytest.raises(ValueError):
        valid_extractor_config.properties = {
            "prompt_document": "Transcribe the document.",
            "prompt_audio": "Transcribe the audio.",
            "prompt_video": "Transcribe the video.",
            # missing image
        }


def test_extractor_config_invalid_config_type(valid_extractor_config):
    # Create an invalid config type using string
    with pytest.raises(ValueError):
        valid_extractor_config.extractor_type = "invalid_type"


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        [OutputFormat.TEXT],
        [OutputFormat.MARKDOWN],
        [OutputFormat.TEXT, OutputFormat.MARKDOWN],
    ],
)
def test_valid_passthrough_mimetypes(
    valid_extractor_config_data, passthrough_mimetypes
):
    config_data = valid_extractor_config_data.copy()
    config_data["passthrough_mimetypes"] = passthrough_mimetypes
    config = ExtractorConfig(**config_data)
    assert config.passthrough_mimetypes == passthrough_mimetypes


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        ["invalid_format"],
        ["another_invalid"],
        [OutputFormat.TEXT, "invalid_format"],
    ],
)
def test_invalid_passthrough_mimetypes(
    valid_extractor_config_data, passthrough_mimetypes
):
    config_data = valid_extractor_config_data.copy()
    config_data["passthrough_mimetypes"] = passthrough_mimetypes
    with pytest.raises(ValueError):
        ExtractorConfig(**config_data)


def test_validate_prompt_valid():
    # should not raise an error
    validate_prompt("Transcribe the document.", "prompt_document")


@pytest.mark.parametrize(
    "value, expected_error",
    [
        (123, "prompt_document must be a string"),
        ("", "prompt_document cannot be empty"),
    ],
)
def test_validate_prompt_errors(value, expected_error):
    with pytest.raises(ValueError, match=expected_error):
        validate_prompt(value, "prompt_document")


@pytest.fixture
def mock_project(tmp_path):
    project_root = tmp_path / str(uuid.uuid4())
    project_root.mkdir()
    project = Project(
        name="Test Project",
        description="Test description",
        path=project_root / "project.kiln",
    )
    project.save_to_file()
    return project


@pytest.fixture
def mock_extractor_config_factory(mock_project):
    def _create_mock_extractor_config():
        name = f"Test Extractor Config {uuid.uuid4()!s}"
        extractor_config = ExtractorConfig(
            name=name,
            description="Test description",
            model_provider_name="gemini_api",
            model_name="gemini-2.0-flash",
            extractor_type=ExtractorType.LITELLM,
            properties={
                "prompt_document": "Transcribe the document.",
                "prompt_audio": "Transcribe the audio.",
                "prompt_video": "Transcribe the video.",
                "prompt_image": "Describe the image.",
            },
            parent=mock_project,
        )
        extractor_config.save_to_file()
        return extractor_config

    return _create_mock_extractor_config


@pytest.fixture
def mock_attachment_factory(tmp_path):
    def _create_mock_attachment():
        filename = f"test_{uuid.uuid4()!s}.txt"
        with open(tmp_path / filename, "w") as f:
            f.write("test")
        return KilnAttachmentModel.from_file(tmp_path / filename)

    return _create_mock_attachment


@pytest.fixture
def mock_document_factory(mock_project, mock_attachment_factory):
    def _create_mock_document():
        name = f"Test Document {uuid.uuid4()!s}"
        document = Document(
            name=name,
            description=f"Test description {uuid.uuid4()!s}",
            kind=Kind.DOCUMENT,
            original_file=FileInfo(
                filename=f"test_{name}.txt",
                size=100,
                mime_type="text/plain",
                attachment=mock_attachment_factory(),
            ),
            parent=mock_project,
        )
        document.save_to_file()
        return document

    return _create_mock_document


def test_relationships(
    mock_project,
    mock_extractor_config_factory,
    mock_document_factory,
    mock_attachment_factory,
):
    # create extractor configs
    initial_extractor_configs = mock_project.extractor_configs()
    assert len(initial_extractor_configs) == 0

    extractor_configs = []
    for i in range(3):
        extractor_configs.append(mock_extractor_config_factory())

    # check can get extractor configs from project
    extractor_configs = mock_project.extractor_configs()
    assert len(extractor_configs) == 3

    # check extractor configs are associated with the correct project
    for extractor_config in extractor_configs:
        assert extractor_config.parent_project().id == mock_project.id

    # check can get documents from project
    documents = mock_project.documents()
    assert len(documents) == 0

    documents = []
    for i in range(5):
        document = mock_document_factory()
        documents.append(document)

    # check can get documents from project
    documents = mock_project.documents()
    assert len(documents) == 5

    # check documents are associated with the correct project
    for document in documents:
        assert document.parent_project().id == mock_project.id

    # create extractions for the first 3 documents
    for document in [documents[0], documents[1], documents[2]]:
        for extractor_config in extractor_configs:
            extraction = Extraction(
                source=ExtractionSource.PROCESSED,
                extractor_config_id=extractor_config.id,
                output=mock_attachment_factory(),
                parent=document,
            )
            extraction.save_to_file()

    # check extractions are associated with the correct document
    for document in [documents[0], documents[1], documents[2]]:
        assert len(document.extractions()) == 3
        for extraction in document.extractions():
            assert extraction.parent_document().id == document.id

    # check no extractions for the last 2 documents
    for document in [documents[3], documents[4]]:
        assert len(document.extractions()) == 0

    # check can retrieve a document by id
    document_0 = Document.from_id_and_parent_path(documents[0].id, mock_project.path)
    assert document_0 is not None
    assert document_0.parent_project().id == mock_project.id
    assert document_0.id == documents[0].id

    # check can retrieve extractions for a document
    document_0_extractions = document_0.extractions()
    assert document_0_extractions is not None
    assert len(document_0_extractions) == 3
    for extraction in document_0_extractions:
        assert extraction.parent_document().id == document_0.id

    # check can retrieve all documents
    all_documents = Document.all_children_of_parent_path(mock_project.path)

    # check can retrieve all documents
    assert (
        [d.id for d in all_documents]
        == [d.id for d in mock_project.documents()]
        == [d.id for d in documents]
    )

    # check all documents are retrieved
    for document_retrieved, document_original in zip(all_documents, documents):
        assert document_retrieved.parent_project().id == mock_project.id
        assert document_retrieved.id == document_original.id


@pytest.fixture
def valid_document(mock_document_factory):
    return mock_document_factory()


@pytest.mark.parametrize(
    "tags, expected_tags",
    [
        (["test", "document"], ["test", "document"]),
        (["test", "document", "new"], ["test", "document", "new"]),
        ([], []),
    ],
)
def test_document_tags(valid_document, tags, expected_tags):
    valid_document.tags = tags
    assert valid_document.tags == expected_tags


def test_invalid_tags(valid_document):
    with pytest.raises(ValueError, match="Tags cannot be empty strings"):
        valid_document.tags = ["test", ""]
    with pytest.raises(
        ValueError, match=r"Tags cannot contain spaces. Try underscores."
    ):
        valid_document.tags = ["test", "document new"]


@pytest.mark.parametrize(
    "filename, mime_type",
    [
        ("file.pdf", "application/pdf"),
        ("file.txt", "text/plain"),
        ("file.md", "text/markdown"),
        ("file.html", "text/html"),
        ("file.png", "image/png"),
        ("file.jpeg", "image/jpeg"),
        ("file.mp4", "video/mp4"),
        ("file.mov", "video/quicktime"),
        ("file.wav", "audio/wav"),
        ("file.mp3", "audio/mpeg"),
        ("file.ogg", "audio/ogg"),
    ],
)
def test_document_valid_mime_type(
    mock_project, mock_attachment_factory, filename, mime_type
):
    document = Document(
        name="Test Document",
        description="Test description",
        kind=Kind.DOCUMENT,
        original_file=FileInfo(
            filename=filename,
            size=100,
            mime_type=mime_type,
            attachment=mock_attachment_factory(),
        ),
        parent=mock_project,
    )
    assert document.original_file.mime_type == mime_type


@pytest.mark.parametrize(
    "filename, mime_type",
    [
        # these are a handful of mime types not currently supported by the extractors
        (
            "file.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "file.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "file.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "file.svg",
            "image/svg+xml",
        ),
        (
            "file.avi",
            "video/x-msvideo",
        ),
        (
            "file.csv",
            "text/csv",
        ),
    ],
)
def test_document_invalid_mime_type(
    mock_project, mock_attachment_factory, filename, mime_type
):
    with pytest.raises(
        ValueError, match=f"MIME type is not supported: {re.escape(mime_type)}"
    ):
        Document(
            name="Test Document",
            description="Test description",
            kind=Kind.DOCUMENT,
            original_file=FileInfo(
                filename=filename,
                size=100,
                mime_type=mime_type,
                attachment=mock_attachment_factory(),
            ),
            parent=mock_project,
        )


@pytest.mark.parametrize(
    "mime_type, expected_kind",
    [
        ("application/pdf", Kind.DOCUMENT),
        ("text/plain", Kind.DOCUMENT),
        ("text/markdown", Kind.DOCUMENT),
        ("text/html", Kind.DOCUMENT),
        ("image/png", Kind.IMAGE),
        ("image/jpeg", Kind.IMAGE),
        ("video/mp4", Kind.VIDEO),
        ("video/quicktime", Kind.VIDEO),
        ("audio/mpeg", Kind.AUDIO),
        ("audio/wav", Kind.AUDIO),
        ("audio/ogg", Kind.AUDIO),
    ],
)
def test_get_kind_from_mime_type(mime_type, expected_kind):
    assert get_kind_from_mime_type(mime_type) == expected_kind
