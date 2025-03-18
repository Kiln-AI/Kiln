import json
import os
import re
import shutil
import uuid
from abc import ABCMeta
from builtins import classmethod
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    computed_field,
    model_validator,
)
from pydantic_core import ErrorDetails
from typing_extensions import Self

from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.utils.config import Config
from kiln_ai.utils.formatting import snake_case

# ID is a 12 digit random integer string.
# Should be unique per item, at least inside the context of a parent/child relationship.
# Use integers to make it easier to type for a search function.
# Allow none, even though we generate it, because we clear it in the REST API if the object is ephemeral (not persisted to disk)
ID_FIELD = Field(default_factory=lambda: str(uuid.uuid4().int)[:12])
ID_TYPE = Optional[str]
T = TypeVar("T", bound="KilnBaseModel")
PT = TypeVar("PT", bound="KilnParentedModel")


# Naming conventions:
# 1) Names are filename safe as they may be used as file names. They are informational and not to be used in prompts/training/validation.
# 2) Descrptions are for Kiln users to describe/understanding the purpose of this object. They must never be used in prompts/training/validation. Use "instruction/requirements" instead.

# Filename compatible names
NAME_REGEX = r"^[A-Za-z0-9 _-]+$"
NAME_FIELD = Field(
    min_length=1,
    max_length=120,
    pattern=NAME_REGEX,
    description="A name for this entity.",
)
SHORT_NAME_FIELD = Field(
    min_length=1,
    max_length=32,
    pattern=NAME_REGEX,
    description="A name for this entity",
)


def string_to_valid_name(name: str) -> str:
    # Replace any character not allowed by NAME_REGEX with an underscore
    valid_name = re.sub(r"[^A-Za-z0-9 _-]", "_", name)
    # Replace consecutive underscores with a single underscore
    valid_name = re.sub(r"_+", "_", valid_name)
    # Remove leading and trailing underscores or whitespace
    return valid_name.strip("_").strip()


class KilnBaseModel(BaseModel):
    """Base model for all Kiln data models with common functionality for persistence and versioning.

    Attributes:
        v (int): Schema version number for migration support
        id (str): Unique identifier for the model instance
        path (Path): File system path where the model is stored
        created_at (datetime): Timestamp when the model was created
        created_by (str): User ID of the creator
    """

    model_config = ConfigDict(validate_assignment=True)

    v: int = Field(default=1)  # schema_version
    id: ID_TYPE = ID_FIELD
    path: Optional[Path] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default_factory=lambda: Config.shared().user_id)

    _loaded_from_file: bool = False

    @computed_field()
    def model_type(self) -> str:
        return self.type_name()

    # if changing the model name, should keep the original name here for parsing old files
    @classmethod
    def type_name(cls) -> str:
        return snake_case(cls.__name__)

    # used as /obj_folder/base_filename.kiln
    @classmethod
    def base_filename(cls) -> str:
        return cls.type_name() + ".kiln"

    @classmethod
    def load_from_folder(cls: Type[T], folderPath: Path) -> T:
        """Load a model instance from a folder using the default filename.

        Args:
            folderPath (Path): Directory path containing the model file

        Returns:
            T: Instance of the model
        """
        path = folderPath / cls.base_filename()
        return cls.load_from_file(path)

    @classmethod
    def load_from_file(cls: Type[T], path: Path | str, readonly: bool = False) -> T:
        """Load a model instance from a specific file path.

        Args:
            path (Path): Path to the model file
            readonly (bool): If True, the model will be returned in readonly mode (cached instance, not a copy, not safe to mutate)

        Returns:
            T: Instance of the model

        Raises:
            ValueError: If the loaded model is not of the expected type or version
            FileNotFoundError: If the file does not exist
        """
        if isinstance(path, str):
            path = Path(path)
        cached_model = ModelCache.shared().get_model(path, cls, readonly=readonly)
        if cached_model is not None:
            return cached_model
        with open(path, "r", encoding="utf-8") as file:
            # modified time of file for cache invalidation. From file descriptor so it's atomic w read.
            mtime_ns = os.fstat(file.fileno()).st_mtime_ns
            file_data = file.read()
            parsed_json = json.loads(file_data)
            m = cls.model_validate(parsed_json, context={"loading_from_file": True})
            if not isinstance(m, cls):
                raise ValueError(f"Loaded model is not of type {cls.__name__}")
            m._loaded_from_file = True
            file_data = None
        m.path = path
        if m.v > m.max_schema_version():
            raise ValueError(
                f"Cannot load from file because the schema version is higher than the current version. Upgrade kiln to the latest version. "
                f"Class: {m.__class__.__name__}, id: {getattr(m, 'id', None)}, path: {path}, "
                f"version: {m.v}, max version: {m.max_schema_version()}"
            )
        if parsed_json["model_type"] != cls.type_name():
            raise ValueError(
                f"Cannot load from file because the model type is incorrect. Expected {cls.type_name()}, got {parsed_json['model_type']}. "
                f"Class: {m.__class__.__name__}, id: {getattr(m, 'id', None)}, path: {path}, "
                f"version: {m.v}, max version: {m.max_schema_version()}"
            )
        ModelCache.shared().set_model(path, m, mtime_ns)
        return m

    def loaded_from_file(self, info: ValidationInfo | None = None) -> bool:
        # Two methods of indicated it's loaded from file:
        # 1) info.context.get("loading_from_file") -> During actual loading, before we can set _loaded_from_file
        # 2) self._loaded_from_file -> After loading, set by the loader
        if self.loading_from_file(info):
            return True
        return self._loaded_from_file

    # indicates the model is currently being loaded from file (not mutating it after)
    def loading_from_file(self, info: ValidationInfo | None = None) -> bool:
        # info.context.get("loading_from_file") -> During actual loading, before we can set _loaded_from_file
        if (
            info is not None
            and info.context is not None
            and info.context.get("loading_from_file", False)
        ):
            return True
        return False

    def save_to_file(self) -> None:
        """Save the model instance to a file.

        Raises:
            ValueError: If the path is not set
        """
        path = self.build_path()
        if path is None:
            raise ValueError(
                f"Cannot save to file because 'path' is not set. Class: {self.__class__.__name__}, "
                f"id: {getattr(self, 'id', None)}, path: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        json_data = self.model_dump_json(indent=2, exclude={"path"})
        with open(path, "w", encoding="utf-8") as file:
            file.write(json_data)
        # save the path so even if something like name changes, the file doesn't move
        self.path = path
        # We could save, but invalidating will trigger load on next use.
        # This ensures everything in cache is loaded from disk, and the cache perfectly reflects what's on disk
        ModelCache.shared().invalidate(path)

    def delete(self) -> None:
        if self.path is None:
            raise ValueError("Cannot delete model because path is not set")
        dir_path = self.path.parent if self.path.is_file() else self.path
        if dir_path is None:
            raise ValueError("Cannot delete model because path is not set")
        shutil.rmtree(dir_path)
        ModelCache.shared().invalidate(self.path)
        self.path = None

    def build_path(self) -> Path | None:
        if self.path is not None:
            return self.path
        return None

    # increment for breaking changes
    def max_schema_version(self) -> int:
        return 1


class KilnParentedModel(KilnBaseModel, metaclass=ABCMeta):
    """Base model for Kiln models that have a parent-child relationship. This base class is for child models.

    This class provides functionality for managing hierarchical relationships between models,
    including parent reference handling and file system organization.

    Attributes:
        parent (KilnBaseModel): Reference to the parent model instance. Not persisted, just in memory.
    """

    # Parent is an in memory only reference to parent. If it's set we use that. If not we'll try to load it from disk based on the path.
    # We don't persist the parent reference to disk. See the accessors below for how we make it a clean api (parent accessor will lazy load from disk)
    parent: Optional[KilnBaseModel] = Field(default=None, exclude=True)

    def __getattribute__(self, name: str) -> Any:
        if name == "parent":
            return self.load_parent()
        return super().__getattribute__(name)

    def cached_parent(self) -> Optional[KilnBaseModel]:
        return object.__getattribute__(self, "parent")

    def load_parent(self) -> Optional[KilnBaseModel]:
        """Get the parent model instance, loading it from disk if necessary.

        Returns:
            Optional[KilnBaseModel]: The parent model instance or None if not set
        """
        cached_parent = self.cached_parent()
        if cached_parent is not None:
            return cached_parent

        # lazy load parent from path
        if self.path is None:
            return None
        # Note: this only works with base_filename. If we every support custom names, we need to change this.
        parent_path = (
            self.path.parent.parent.parent
            / self.__class__.parent_type().base_filename()
        )
        if parent_path is None:
            return None
        if not parent_path.exists():
            return None
        loaded_parent = self.__class__.parent_type().load_from_file(parent_path)
        self.parent = loaded_parent
        return loaded_parent

    # Dynamically implemented by KilnParentModel method injection
    @classmethod
    def relationship_name(cls) -> str:
        raise NotImplementedError("Relationship name must be implemented")

    # Dynamically implemented by KilnParentModel method injection
    @classmethod
    def parent_type(cls) -> Type[KilnBaseModel]:
        raise NotImplementedError("Parent type must be implemented")

    @model_validator(mode="after")
    def check_parent_type(self) -> Self:
        cached_parent = self.cached_parent()
        if cached_parent is not None:
            expected_parent_type = self.__class__.parent_type()
            if not isinstance(cached_parent, expected_parent_type):
                raise ValueError(
                    f"Parent must be of type {expected_parent_type}, but was {type(cached_parent)}"
                )
        return self

    def build_child_dirname(self) -> Path:
        # Default implementation for readable folder names.
        # {id} - {name}/{type}.kiln
        if self.id is None:
            # consider generating an ID here. But if it's been cleared, we've already used this without one so raise for now.
            raise ValueError("ID is not set - can not save or build path")
        path = self.id
        name = getattr(self, "name", None)
        if name is not None:
            path = f"{path} - {name[:32]}"
        return Path(path)

    def build_path(self) -> Path | None:
        # if specifically loaded from an existing path, keep that no matter what
        # this ensures the file structure is easy to use with git/version control
        # and that changes to things like name (which impacts default path) don't leave dangling files
        if self.path is not None:
            return self.path
        # Build a path under parent_folder/relationship/file.kiln
        if self.parent is None:
            return None
        parent_path = self.parent.build_path()
        if parent_path is None:
            return None
        parent_folder = parent_path.parent
        if parent_folder is None:
            return None
        return (
            parent_folder
            / self.__class__.relationship_name()
            / self.build_child_dirname()
            / self.__class__.base_filename()
        )

    @classmethod
    def iterate_children_paths_of_parent_path(cls: Type[PT], parent_path: Path | None):
        if parent_path is None:
            # children are disk based. If not saved, they don't exist
            return []

        # Determine the parent folder
        if parent_path.is_file():
            parent_folder = parent_path.parent
        else:
            parent_folder = parent_path

        parent = cls.parent_type().load_from_file(parent_path)
        if parent is None:
            raise ValueError("Parent must be set to load children")

        # Ignore type error: this is abstract base class, but children must implement relationship_name
        relationship_folder = parent_folder / Path(cls.relationship_name())  # type: ignore

        if not relationship_folder.exists() or not relationship_folder.is_dir():
            return []

        # Collect all /relationship/{id}/{base_filename.kiln} files in the relationship folder
        # manual code instead of glob for performance (5x speedup over glob)

        base_filename = cls.base_filename()
        # Iterate through immediate subdirectories using scandir for better performance
        # Benchmark: scandir is 10x faster than glob, so worth the extra code
        with os.scandir(relationship_folder) as entries:
            for entry in entries:
                if not entry.is_dir():
                    continue

                child_file = Path(entry.path) / base_filename
                if child_file.is_file():
                    yield child_file

    @classmethod
    def all_children_of_parent_path(
        cls: Type[PT], parent_path: Path | None, readonly: bool = False
    ) -> list[PT]:
        children = []
        for child_path in cls.iterate_children_paths_of_parent_path(parent_path):
            item = cls.load_from_file(child_path, readonly=readonly)
            children.append(item)
        return children

    @classmethod
    def from_id_and_parent_path(
        cls: Type[PT], id: str, parent_path: Path | None
    ) -> PT | None:
        """
        Fast search by ID using the cache. Avoids the model_copy overhead on all but the exact match.

        Uses cache so still slow on first load.
        """
        if parent_path is None:
            return None

        # Note: we're using the in-file ID. We could make this faster using the path-ID if this becomes perf bottleneck, but it's better to have 1 source of truth.
        for child_path in cls.iterate_children_paths_of_parent_path(parent_path):
            child_id = ModelCache.shared().get_model_id(child_path, cls)
            if child_id == id:
                return cls.load_from_file(child_path)
            if child_id is None:
                child = cls.load_from_file(child_path)
                if child.id == id:
                    return child
        return None


# Parent create methods for all child relationships
# You must pass in parent_of in the subclass definition, defining the child relationships
class KilnParentModel(KilnBaseModel, metaclass=ABCMeta):
    """Base model for Kiln models that can have child models.

    This class provides functionality for managing collections of child models and their persistence.
    Child relationships must be defined using the parent_of parameter in the class definition.

    Args:
        parent_of (Dict[str, Type[KilnParentedModel]]): Mapping of relationship names to child model types
    """

    @classmethod
    def _create_child_method(
        cls, relationship_name: str, child_class: Type[KilnParentedModel]
    ):
        def child_method(self, readonly: bool = False) -> list[child_class]:
            return child_class.all_children_of_parent_path(self.path, readonly=readonly)

        child_method.__name__ = relationship_name
        child_method.__annotations__ = {"return": List[child_class]}
        setattr(cls, relationship_name, child_method)

    @classmethod
    def _create_parent_methods(
        cls, targetCls: Type[KilnParentedModel], relationship_name: str
    ):
        def parent_class_method() -> Type[KilnParentModel]:
            return cls

        parent_class_method.__name__ = "parent_type"
        parent_class_method.__annotations__ = {"return": Type[KilnParentModel]}
        setattr(targetCls, "parent_type", parent_class_method)

        def relationship_name_method() -> str:
            return relationship_name

        relationship_name_method.__name__ = "relationship_name"
        relationship_name_method.__annotations__ = {"return": str}
        setattr(targetCls, "relationship_name", relationship_name_method)

    @classmethod
    def __init_subclass__(cls, parent_of: Dict[str, Type[KilnParentedModel]], **kwargs):
        super().__init_subclass__(**kwargs)
        cls._parent_of = parent_of
        for relationship_name, child_class in parent_of.items():
            cls._create_child_method(relationship_name, child_class)
            cls._create_parent_methods(child_class, relationship_name)

    @classmethod
    def validate_and_save_with_subrelations(
        cls,
        data: Dict[str, Any],
        path: Path | None = None,
        parent: KilnBaseModel | None = None,
    ):
        """Validate and save a model instance along with all its nested child relationships.

        Args:
            data (Dict[str, Any]): Model data including child relationships
            path (Path, optional): Path where the model should be saved
            parent (KilnBaseModel, optional): Parent model instance for parented models

        Returns:
            KilnParentModel: The validated and saved model instance

        Raises:
            ValidationError: If validation fails for the model or any of its children
        """
        # Validate first, then save. Don't want error half way through, and partly persisted
        # TODO P2: save to tmp dir, then move atomically. But need to merge directories so later.
        cls._validate_nested(data, save=False, path=path, parent=parent)
        instance = cls._validate_nested(data, save=True, path=path, parent=parent)
        return instance

    @classmethod
    def _validate_nested(
        cls,
        data: Dict[str, Any],
        save: bool = False,
        parent: KilnBaseModel | None = None,
        path: Path | None = None,
    ):
        # Collect all validation errors so we can report them all at once
        validation_errors = []

        try:
            instance = cls.model_validate(data)
            if path is not None:
                instance.path = path
            if parent is not None and isinstance(instance, KilnParentedModel):
                instance.parent = parent
            if save:
                instance.save_to_file()
        except ValidationError as e:
            instance = None
            for suberror in e.errors():
                validation_errors.append(suberror)

        for key, value_list in data.items():
            if key in cls._parent_of:
                parent_type = cls._parent_of[key]
                if not isinstance(value_list, list):
                    raise ValueError(
                        f"Expected a list for {key}, but got {type(value_list)}"
                    )
                for value_index, value in enumerate(value_list):
                    try:
                        if issubclass(parent_type, KilnParentModel):
                            kwargs = {"data": value, "save": save}
                            if instance is not None:
                                kwargs["parent"] = instance
                            parent_type._validate_nested(**kwargs)
                        elif issubclass(parent_type, KilnParentedModel):
                            # Root node
                            subinstance = parent_type.model_validate(value)
                            if instance is not None:
                                subinstance.parent = instance
                            if save:
                                subinstance.save_to_file()
                        else:
                            raise ValueError(
                                f"Invalid type {parent_type}. Should be KilnBaseModel based."
                            )
                    except ValidationError as e:
                        for suberror in e.errors():
                            cls._append_loc(suberror, key, value_index)
                            validation_errors.append(suberror)

        if len(validation_errors) > 0:
            raise ValidationError.from_exception_data(
                title=f"Validation failed for {cls.__name__}",
                line_errors=validation_errors,
                input_type="json",
            )

        return instance

    @classmethod
    def _append_loc(
        cls, error: ErrorDetails, current_loc: str, value_index: int | None = None
    ):
        orig_loc = error["loc"] if "loc" in error else None
        new_loc: list[str | int] = [current_loc]
        if value_index is not None:
            new_loc.append(value_index)
        if isinstance(orig_loc, tuple):
            new_loc.extend(list(orig_loc))
        elif isinstance(orig_loc, list):
            new_loc.extend(orig_loc)
        error["loc"] = tuple(new_loc)
