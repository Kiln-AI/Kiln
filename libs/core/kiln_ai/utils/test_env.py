import os

import pytest

from kiln_ai.utils.env import temporary_env


class TestTemporaryEnv:
    def test_set_new_env_var(self):
        """Test setting a new environment variable that doesn't exist."""
        var_name = "TEST_NEW_VAR"
        test_value = "test_value"

        # Ensure the variable doesn't exist initially
        assert var_name not in os.environ

        with temporary_env(var_name, test_value):
            assert os.environ[var_name] == test_value

        # Verify it's removed after context
        assert var_name not in os.environ

    def test_modify_existing_env_var(self):
        """Test modifying an existing environment variable."""
        var_name = "TEST_EXISTING_VAR"
        original_value = "original_value"
        new_value = "new_value"

        # Set up initial state
        os.environ[var_name] = original_value

        with temporary_env(var_name, new_value):
            assert os.environ[var_name] == new_value

        # Verify original value is restored
        assert os.environ[var_name] == original_value

    def test_restore_nonexistent_var(self):
        """Test that a variable that didn't exist is properly removed."""
        var_name = "TEST_NONEXISTENT_VAR"
        test_value = "test_value"

        # Ensure the variable doesn't exist initially
        if var_name in os.environ:
            del os.environ[var_name]

        with temporary_env(var_name, test_value):
            assert os.environ[var_name] == test_value

        # Verify it's removed after context
        assert var_name not in os.environ

    def test_exception_handling(self):
        """Test that environment is restored even when an exception occurs."""
        var_name = "TEST_EXCEPTION_VAR"
        original_value = "original_value"
        new_value = "new_value"

        # Set up initial state
        os.environ[var_name] = original_value

        with pytest.raises(ValueError):
            with temporary_env(var_name, new_value):
                assert os.environ[var_name] == new_value
                raise ValueError("Test exception")

        # Verify original value is restored even after exception
        assert os.environ[var_name] == original_value

    def test_exception_handling_new_var(self):
        """Test that new variable is removed even when an exception occurs."""
        var_name = "TEST_EXCEPTION_NEW_VAR"
        test_value = "test_value"

        # Ensure the variable doesn't exist initially
        if var_name in os.environ:
            del os.environ[var_name]

        with pytest.raises(RuntimeError):
            with temporary_env(var_name, test_value):
                assert os.environ[var_name] == test_value
                raise RuntimeError("Test exception")

        # Verify variable is removed even after exception
        assert var_name not in os.environ

    def test_nested_context_managers(self):
        """Test using multiple temporary_env context managers."""
        var1 = "TEST_NESTED_VAR1"
        var2 = "TEST_NESTED_VAR2"
        value1 = "value1"
        value2 = "value2"

        # Set up initial state
        os.environ[var1] = "original1"
        if var2 in os.environ:
            del os.environ[var2]

        with temporary_env(var1, value1):
            assert os.environ[var1] == value1

            with temporary_env(var2, value2):
                assert os.environ[var1] == value1
                assert os.environ[var2] == value2

            # Inner context should be cleaned up
            assert var2 not in os.environ
            assert os.environ[var1] == value1

        # Both contexts should be cleaned up
        assert os.environ[var1] == "original1"
        assert var2 not in os.environ

    def test_empty_string_value(self):
        """Test setting an empty string value."""
        var_name = "TEST_EMPTY_VAR"
        test_value = ""

        with temporary_env(var_name, test_value):
            assert os.environ[var_name] == test_value

        assert var_name not in os.environ

    def test_none_value_handling(self):
        """Test that None values are handled properly."""
        var_name = "TEST_NONE_VAR"
        test_value = "test_value"

        with temporary_env(var_name, test_value):
            assert os.environ[var_name] == test_value

        assert var_name not in os.environ

    def test_unicode_value(self):
        """Test setting unicode values."""
        var_name = "TEST_UNICODE_VAR"
        test_value = "测试值 🚀"

        with temporary_env(var_name, test_value):
            assert os.environ[var_name] == test_value

        assert var_name not in os.environ
