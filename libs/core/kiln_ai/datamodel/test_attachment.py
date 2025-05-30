import filecmp
import hashlib
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import KilnAttachmentModel, KilnBaseModel


class ModelWithAttachment(KilnBaseModel):
    attachment: KilnAttachmentModel = Field(default=None)
    attachment_list: Optional[List[KilnAttachmentModel]] = Field(default=None)
    attachment_dict: Optional[Dict[str, KilnAttachmentModel]] = Field(default=None)


class ContainerModel(BaseModel):
    indirect_attachment: Optional[KilnAttachmentModel] = Field(default=None)
    indirect_attachment_list: Optional[List[KilnAttachmentModel]] = Field(default=None)
    indirect_attachment_dict: Optional[Dict[str, KilnAttachmentModel]] = Field(
        default=None
    )


class ModelWithIndirectAttachment(KilnBaseModel):
    # this nested model contains an attachment field
    container: ContainerModel = Field(default=ContainerModel())
    container_optional: Optional[ContainerModel] = Field(default=None)


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
    attachment_path = data["attachment"]

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
        attachment_list=test_files,
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # check the paths are relative to model.path.parent
    for attachment_path in data["attachment_list"]:
        assert isinstance(attachment_path, str)
        assert not Path(attachment_path).is_absolute()

    # check all the files were persisted
    attachment_list = data["attachment_list"]
    assert len(attachment_list) == len(test_media_file_paths)

    # check the files are present and correct in model.path.parent
    for attachment_path in attachment_list:
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


def test_save_to_file_with_attachment_dict(test_base_kiln_file, test_media_file_paths):
    # we map hashes to their files, so we can find the corresponding file after the save
    file_hashes = {hash_file(p): p for p in test_media_file_paths}

    test_files = {
        f"file_{i}": KilnAttachmentModel(path=p)
        for i, p in enumerate(test_media_file_paths)
    }
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachment_dict=test_files,
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # check the paths are relative to model.path.parent
    for attachment_path in data["attachment_dict"].values():
        assert isinstance(attachment_path, str)
        assert not Path(attachment_path).is_absolute()

    # check all the files were persisted
    attachment_dict = data["attachment_dict"]
    assert len(attachment_dict) == len(test_media_file_paths)

    # check the files are present and correct in model.path.parent
    for attachment_path in attachment_dict.values():
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


def test_save_to_file_with_indirect_attachment(
    test_base_kiln_file, test_media_file_document
):
    model = ModelWithIndirectAttachment(
        path=test_base_kiln_file,
        container=ContainerModel(
            indirect_attachment=KilnAttachmentModel(path=test_media_file_document)
        ),
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # check the path is relative to model.path.parent
    assert isinstance(data["container"]["indirect_attachment"], str)
    assert not Path(data["container"]["indirect_attachment"]).is_absolute()

    # check the file is the same as the original
    assert model.path is not None
    expected_full_path = model.path.parent / data["container"]["indirect_attachment"]
    assert expected_full_path.exists()
    assert filecmp.cmp(expected_full_path, test_media_file_document)


def test_save_to_file_with_indirect_attachment_optional(
    test_base_kiln_file, test_media_file_document
):
    model = ModelWithIndirectAttachment(
        path=test_base_kiln_file,
        container_optional=ContainerModel(
            indirect_attachment=KilnAttachmentModel(path=test_media_file_document)
        ),
    )
    model.save_to_file()

    with open(test_base_kiln_file, "r") as file:
        data = json.load(file)

    # check the path is relative to model.path.parent
    assert data["container_optional"] is not None

    # check the file is the same as the original
    assert model.path is not None
    expected_full_path = (
        model.path.parent / data["container_optional"]["indirect_attachment"]
    )
    assert expected_full_path.exists()
    assert filecmp.cmp(expected_full_path, test_media_file_document)


def test_save_to_file_with_indirect_attachment_optional_none(test_base_kiln_file):
    # check we don't copy the attachment if it is None
    with patch.object(KilnAttachmentModel, "copy_file_to") as mock_save_to_file:
        mock_save_to_file.return_value = Path("fake.txt")
        model = ModelWithIndirectAttachment(
            path=test_base_kiln_file,
            container_optional=None,
        )
        model.save_to_file()

        with open(test_base_kiln_file, "r") as file:
            data = json.load(file)

        # check the path is relative to model.path.parent
        assert data["container_optional"] is None

        # check KilnAttachmentModel.copy_to() not called
        mock_save_to_file.assert_not_called()


def test_dump_dest_path(test_base_kiln_file, test_media_file):
    model = ModelWithAttachment(
        path=test_base_kiln_file,
        attachment=KilnAttachmentModel(path=test_media_file),
    )

    with pytest.raises(
        ValueError,
        match="dest_path must be a valid Path object when saving attachments",
    ):
        model.model_dump_json(context={"save_attachments": True})

    # should raise when dest_path is not a Path object
    with pytest.raises(
        ValueError,
        match="dest_path must be a valid Path object when saving attachments",
    ):
        model.model_dump_json(
            context={"save_attachments": True, "dest_path": str(test_media_file)}
        )

    # should raise when dest_path is not a directory
    with pytest.raises(
        ValueError,
        match="dest_path must be a directory when saving attachments",
    ):
        model.model_dump_json(
            context={"save_attachments": True, "dest_path": test_media_file}
        )

    # should not raise when dest_path is set
    model.model_dump_json(context={"dest_path": test_base_kiln_file.parent})


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
