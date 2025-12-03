import os
import shutil
from pathlib import Path
from typing import Iterator, Optional, Tuple

from .datamodel_store import DatamodelStore


class DatamodelFilestore(DatamodelStore):
    """Filesystem-based implementation of DatamodelStore."""

    def descriptive_path_names(self) -> bool:
        """Whether the store uses descriptive names for paths."""
        return True

    def load_model_data(self, path: Path) -> Tuple[str, int]:
        """Load raw model data from file."""

        with open(path, "r", encoding="utf-8") as file:
            # modified time of file for cache invalidation. From file descriptor so it's atomic w read.
            mtime_ns = os.fstat(file.fileno()).st_mtime_ns
            file_data = file.read()
            return file_data, mtime_ns

    def save_model_data(self, path: Path, data: str) -> None:
        """Save model data to file, creating directories as needed."""
        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)

    def delete_model(self, path: Path) -> None:
        """Delete model and its container directory."""
        # Delete the containing directory (e.g., {id}/ or {id}-{name}/)
        if path.is_file():
            # Path is the model file, delete parent directory
            dir_to_delete = path.parent
        else:
            # Path is already a directory
            dir_to_delete = path

        if dir_to_delete is None:
            raise ValueError("Cannot delete model because path is not set")

        shutil.rmtree(dir_to_delete)

    # HERE

    def iterate_child_models(
        self, parent_path: Optional[Path], relationship_name: str, base_filename: str
    ) -> Iterator[Path]:
        """Iterate the child model IDs in a relationship."""
        if parent_path is None:
            return []

        # Get the parent directory (handle both file and directory paths)
        if parent_path.is_file():
            parent_dir = parent_path.parent
        else:
            parent_dir = parent_path

        # Relationship folder contains child directories
        relationship_folder = parent_dir / relationship_name

        if not relationship_folder.exists():
            return []

        # Iterate through immediate subdirectories using scandir for better performance
        # Benchmark: scandir is 10x faster than glob, so worth the extra code
        with os.scandir(relationship_folder) as entries:
            for entry in entries:
                if not entry.is_dir():
                    continue

                child_file = Path(entry.path) / base_filename
                if child_file.is_file():
                    yield child_file

    def get_child_path(
        self, parent_path: Optional[Path], relationship_name: str, child_id: str
    ) -> Optional[Path]:
        """Get full path for a child model by ID."""
        if parent_path is None:
            return None

        # Get the parent directory
        if parent_path.is_file():
            parent_dir = parent_path.parent
        else:
            parent_dir = parent_path

        # Check relationship folder
        relationship_folder = parent_dir / relationship_name
        if not relationship_folder.exists():
            return None

        # Look for child directory by ID
        with os.scandir(relationship_folder) as entries:
            for entry in entries:
                if entry.is_dir():
                    dir_name = entry.name
                    # Extract ID from directory name
                    if " - " in dir_name:
                        entry_id = dir_name.split(" - ")[0]
                    else:
                        entry_id = dir_name

                    if entry_id == child_id:
                        # Return the path with the base filename
                        # Note: caller knows the base filename for their model type
                        return Path(entry.path)

        return None

    def generate_path(
        self,
        parent_path: Optional[Path],
        relationship_name: Optional[str],
        model_id: str,
        base_filename: str,
    ) -> Path:
        """Generate a path for a model.

        Args:
            parent_path: Path to parent model file or None for root models
            relationship_name: Relationship name for child models or None for root
            model_id: Model ID (may include name suffix like "123 - My Name")
            base_filename: Base filename (e.g., "task.kiln")

        Returns:
            Full path to the model file
        """
        if parent_path is None or relationship_name is None:
            # Root model - just use ID and filename
            return Path(f"{model_id}/{base_filename}")

        # Child model - build hierarchical path
        if parent_path.is_file():
            parent_dir = parent_path.parent
        else:
            parent_dir = parent_path

        # model_id may already include name suffix for child models
        child_dir = parent_dir / relationship_name / model_id
        return child_dir / base_filename
