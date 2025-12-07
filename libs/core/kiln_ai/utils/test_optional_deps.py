import pytest

from kiln_ai.utils.optional_deps import (
    EXTRA_INSTALL_COMMANDS,
    MissingDependencyError,
    lazy_import,
)


class TestMissingDependencyError:
    def test_is_import_error_subclass(self):
        """MissingDependencyError should be a subclass of ImportError."""
        assert issubclass(MissingDependencyError, ImportError)

    def test_can_be_raised_and_caught_as_import_error(self):
        """MissingDependencyError can be caught as ImportError."""
        with pytest.raises(ImportError):
            raise MissingDependencyError("test message")


class TestLazyImport:
    def test_successful_import_returns_module(self):
        """lazy_import returns the module when it exists."""
        module = lazy_import("os.path", "rag")
        assert hasattr(module, "join")
        assert hasattr(module, "exists")

    def test_successful_nested_import(self):
        """lazy_import works with nested module paths."""
        module = lazy_import("json", "rag")
        assert hasattr(module, "dumps")
        assert hasattr(module, "loads")

    def test_missing_module_raises_error(self):
        """lazy_import raises MissingDependencyError for missing modules."""
        with pytest.raises(MissingDependencyError):
            lazy_import("nonexistent_package_xyz", "rag")

    def test_error_message_contains_package_name(self):
        """Error message includes the top-level package name."""
        with pytest.raises(MissingDependencyError) as exc_info:
            lazy_import("nonexistent_package.submodule.deep", "rag")

        assert "nonexistent_package" in str(exc_info.value)

    def test_error_message_contains_known_install_command(self):
        """Error message includes correct install command for known extras."""
        with pytest.raises(MissingDependencyError) as exc_info:
            lazy_import("nonexistent_package", "rag")

        assert EXTRA_INSTALL_COMMANDS["rag"] in str(exc_info.value)

    def test_error_message_uses_fallback_for_unknown_extra(self):
        """Error message uses fallback format for unknown extras."""
        with pytest.raises(MissingDependencyError) as exc_info:
            lazy_import("nonexistent_package", "unknown_extra")

        assert "kiln-ai[unknown_extra]" in str(exc_info.value)

    def test_chains_original_exception(self):
        """The original ImportError is chained to MissingDependencyError."""
        with pytest.raises(MissingDependencyError) as exc_info:
            lazy_import("nonexistent_package", "rag")

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ImportError)


class TestExtraInstallCommands:
    def test_rag_extra_defined(self):
        """The rag extra is defined."""
        assert "rag" in EXTRA_INSTALL_COMMANDS

    def test_vertex_extra_defined(self):
        """The vertex extra is defined."""
        assert "vertex" in EXTRA_INSTALL_COMMANDS
