import pytest

from kiln_ai.adapters.provider_tools import provider_warnings
from kiln_ai.utils.config import Config


def skip_if_missing_provider_keys(provider_name) -> None:
    warning = provider_warnings.get(provider_name)
    if warning is None:
        return
    missing = [
        key
        for key in warning.required_config_keys
        if not Config.shared().get_value(key)
    ]
    if missing:
        missing_list = ", ".join(missing)
        pytest.skip(
            f"Missing config keys for {provider_name}: {missing_list}. "
            "Set env vars or .env before running paid tests."
        )
