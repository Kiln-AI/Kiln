import filecmp
import hashlib
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnAttachmentModel, KilnBaseModel


def hash_file(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@pytest.fixture
def test_media_files() -> dict[str, Path]:
    data_dir = Path(__file__).parent.parent / "tests" / "data"
    return {
        "video": data_dir / "big_buck_bunny_sample.mp4",
        "audio": data_dir / "poacher.ogg",
        "image": data_dir / "kodim23.png",
        "document": data_dir / "1706.03762v7.pdf",
    }


@pytest.fixture
def test_media_file_paths(test_media_files) -> list[Path]:
    return [p for p in test_media_files.values()]


@pytest.fixture
def test_media_file_document(test_media_files) -> Path:
    return test_media_files["document"]


@pytest.fixture
def test_base_kiln_file(tmp_path) -> Path:
    test_file_path = tmp_path / "test_model.json"
    data = {"v": 1, "model_type": "kiln_base_model"}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


@pytest.fixture
def test_media_file(tmp_path) -> Path:
    test_file_path = tmp_path / "test_model.json"
    data = {"v": 1, "model_type": "kiln_base_model"}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


class ModelWithAttachment(KilnBaseModel):
    attachment: Optional[KilnAttachmentModel] = Field(default=None)
    attachments_list: Optional[List[KilnAttachmentModel]] = Field(default=None)
    attachments_dict: Optional[Dict[str, KilnAttachmentModel]] = Field(default=None)


def test_collect_attachments_from_fields_none(test_base_kiln_file):
    model = ModelWithAttachment(path=test_base_kiln_file)
    attachments = model.collect_attachments_from_fields()
    assert len(attachments) == 0
    assert model.attachment is None


def test_collect_attachments_from_fields_single(test_base_kiln_file):
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachment=KilnAttachmentModel(path=test_base_kiln_file),
    )
    attachments = model.collect_attachments_from_fields()
    assert len(attachments) == 1
    assert attachments[0].path == test_base_kiln_file


def test_collect_attachments_from_fields_list(test_base_kiln_file, test_media_files):
    test_files = [KilnAttachmentModel(path=p) for p in test_media_files.values()]
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachments_list=test_files,
    )
    attachments = model.collect_attachments_from_fields()
    assert len(attachments) == len(test_files)
    for attachment, test_file in zip(attachments, test_files):
        assert attachment.path == test_file.path


def test_collect_attachments_from_fields_dict(test_base_kiln_file, test_media_files):
    test_files = [KilnAttachmentModel(path=p) for p in test_media_files.values()]
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachments_dict={k: v for k, v in zip(test_media_files.keys(), test_files)},
    )
    attachments = model.collect_attachments_from_fields()
    assert len(attachments) == len(test_files)
    for attachment, test_file in zip(attachments, test_files):
        assert attachment.path == test_file.path


def test_collect_attachments_from_fields_unsupported_type(test_base_kiln_file):
    # example of a model that uses a more complex typing, that we don't support right now
    class UnsupportedModel(KilnBaseModel):
        unsupported_field: Optional[List[Dict[str, KilnAttachmentModel]]] = Field(
            default=None
        )

    model = UnsupportedModel(path=test_base_kiln_file)
    with pytest.raises(ValueError, match="Unsupported attachment type"):
        model.collect_attachments_from_fields()


def test_is_attachment_type(test_media_file_document):
    class TestModel(KilnBaseModel):
        # attachment fields, non-optional
        attachment_non_optional: KilnAttachmentModel = Field(
            default=KilnAttachmentModel(path=Path(test_media_file_document))
        )
        attachment_list_non_optional: List[KilnAttachmentModel] = Field(
            default=[KilnAttachmentModel(path=Path(test_media_file_document))]
        )
        attachment_dict_non_optional: Dict[str, KilnAttachmentModel] = Field(default={})
        attachment_list_of_dicts_non_optional: List[Dict[str, KilnAttachmentModel]] = (
            Field(default=[])
        )
        attachment_dict_of_lists_non_optional: Dict[str, List[KilnAttachmentModel]] = (
            Field(default={})
        )
        attachment_dict_of_dicts_non_optional: Dict[
            str, Dict[str, KilnAttachmentModel]
        ] = Field(default={})

        # attachment fields, optional
        attachment_optional: Optional[KilnAttachmentModel] = Field(default=None)
        attachment_list_optional: Optional[List[KilnAttachmentModel]] = Field(
            default=None
        )
        attachment_dict_optional: Optional[Dict[str, KilnAttachmentModel]] = Field(
            default=None
        )
        attachment_list_of_dicts_optional: Optional[
            List[Dict[str, KilnAttachmentModel]]
        ] = Field(default=None)
        attachment_dict_of_lists_optional: Optional[
            Dict[str, List[KilnAttachmentModel]]
        ] = Field(default=None)
        attachment_dict_of_dicts_optional: Optional[
            Dict[str, Dict[str, KilnAttachmentModel]]
        ] = Field(default=None)

        # non-attachment fields, non-optional
        other_field: str = Field(default="")
        other_field_list: List[str] = Field(default=[])
        other_field_dict: Dict[str, str] = Field(default={})
        other_field_list_of_dicts: List[Dict[str, str]] = Field(default=[])
        other_field_dict_of_lists: Dict[str, List[str]] = Field(default={})
        other_field_dict_of_dicts: Dict[str, Dict[str, str]] = Field(default={})
        other_model: Optional[KilnBaseModel] = Field(default=None)

        # non-attachment fields, optional
        other_field_optional: Optional[str] = Field(default=None)
        other_field_list_optional: Optional[List[str]] = Field(default=None)
        other_field_dict_optional: Optional[Dict[str, str]] = Field(default=None)
        other_field_list_of_dicts_optional: Optional[List[Dict[str, str]]] = Field(
            default=None
        )

    # attachment fields start with attachment_
    attachment_fields = [
        field
        for name, field in TestModel().model_fields.items()
        if name.startswith("attachment_")
    ]
    assert len(attachment_fields) == 12

    # check that all the attachment fields are detected
    for field in attachment_fields:
        assert KilnAttachmentModel.is_attachment_type(field.annotation)

    non_attachment_fields = [
        field
        for name, field in TestModel().model_fields.items()
        if not name.startswith("attachment_")
    ]
    assert len(non_attachment_fields) == 16


def test_save_to_file_with_attachment_single(
    test_base_kiln_file, test_media_file_document
):
    test_file = test_media_file_document
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachment=KilnAttachmentModel(path=test_file),
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # the path after saving
    attachment_path = data["attachment"]["path"]

    # check it is a string, and not an absolute path
    assert isinstance(attachment_path, str)
    assert not Path(attachment_path).is_absolute()

    # check persisted path is relative to model.path.parent
    assert model.path is not None
    expected_full_path = model.path.parent / attachment_path
    assert expected_full_path.exists()
    assert filecmp.cmp(expected_full_path, test_file)


def test_save_to_file_with_attachment_list(test_base_kiln_file, test_media_file_paths):
    # we map hashes to their files, so we can find the corresponding file after the save
    file_hashes = {hash_file(p): p for p in test_media_file_paths}

    test_files = [KilnAttachmentModel(path=p) for p in test_media_file_paths]
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachments_list=test_files,
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # check the paths are relative to model.path.parent
    for attachment in data["attachments_list"]:
        assert isinstance(attachment["path"], str)
        assert not Path(attachment["path"]).is_absolute()

    # check all the files were persisted
    attachment_list = data["attachments_list"]
    assert len(attachment_list) == len(test_media_file_paths)

    # check the files are present and correct in model.path.parent
    for attachment in attachment_list:
        attachment_path = attachment["path"]

        # check the path is a string, and not an absolute path
        assert isinstance(attachment_path, str)
        assert not Path(attachment_path).is_absolute()

        # check the file is the same as the original
        assert model.path is not None
        expected_full_path = model.path.parent / attachment_path
        assert expected_full_path.exists()

        # find the original file it corresponds to, and check content hash is identical
        original_file = file_hashes[hash_file(expected_full_path)]
        assert filecmp.cmp(expected_full_path, original_file)


def test_attachment_file_does_not_exist(test_base_kiln_file):
    not_found_file = Path(f"/not/found/{str(uuid.uuid4())}.txt")

    # should raise when we assign a file that does not exist
    with pytest.raises(ValueError):
        KilnAttachmentModel(path=not_found_file)


def test_attachment_is_folder(test_base_kiln_file, tmp_path):
    # create folder in tmp_path
    folder = tmp_path / "test_folder"
    folder.mkdir()

    # create file in folder
    file = folder / "test_file.txt"
    file.touch()

    # should raise when we assign a folder
    with pytest.raises(ValueError):
        ModelWithAttachment(
            path=test_base_kiln_file,
            attachment=KilnAttachmentModel(path=folder),
        )
