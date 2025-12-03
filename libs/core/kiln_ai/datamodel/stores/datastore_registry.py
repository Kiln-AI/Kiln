from typing import Optional

from .datamodel_store import DatamodelStore
from .filesystem_store import DatamodelFilestore


class DatastoreRegistry:
    """Registry for managing DatamodelStore instances."""

    _shared_instance = None

    def __init__(self):
        self._stores = {"default": DatamodelFilestore()}
        self._default = "default"

    @classmethod
    def shared(cls) -> "DatastoreRegistry":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    def get_store(self, name: Optional[str] = None) -> DatamodelStore:
        if name is None:
            name = self._default
        return self._stores[name]
