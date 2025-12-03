from abc import ABC, abstractmethod
from ast import Tuple
from pathlib import Path
from typing import Iterator, Optional, Tuple


class DatamodelStore(ABC):
    """Abstract interface for data model storage operations.

    This interface provides operations needed by KilnBaseModel, not a
    thin filesystem abstraction. Could be implemented with filesystem,
    database, S3, etc.
    """

    @abstractmethod
    def descriptive_path_names(self) -> bool:
        """Whether the store uses descriptive names for paths.

        Use descriptive names for paths where a user will see them. This includes part of the title in the path name.

        Disable if not user facing or we want to minimize the length of the path.
        """
        pass

    # Core model operations
    @abstractmethod
    def load_model_data(self, path: Path) -> Tuple[str, int]:
        """Load raw model data from storage.

        Returns
         - The data as string
         - a unique ID for this version of the object (for caching)
        """
        pass

    @abstractmethod
    def save_model_data(self, path: Path, data: str) -> None:
        """Save model data to storage.

        Ensures all necessary structure exists for the model to be stored.
        """
        pass

    @abstractmethod
    def delete_model(self, path: Path) -> None:
        """Delete a model and all its data from storage."""
        pass

    # Parent-child relationship operations
    @abstractmethod
    def iterate_child_models(
        self, parent_path: Optional[Path], relationship_name: str, base_filename: str
    ) -> Iterator[Path]:
        """Iterate the IDs of child models in a relationship.

        Returns list of child model IDs (not full paths).
        """
        pass

    @abstractmethod
    def get_child_path(
        self, parent_path: Optional[Path], relationship_name: str, child_id: str
    ) -> Optional[Path]:
        """Get the full path for a specific child model by ID.

        Returns None if child doesn't exist.
        """
        pass

    # Path resolution
    @abstractmethod
    def generate_path(
        self,
        parent_path: Optional[Path],
        relationship_name: Optional[str],
        model_id: str,
        base_filename: str,
    ) -> Path:
        """Generate a path for a model.

        For root models, parent_path and relationship_name will be None.
        """
        pass
