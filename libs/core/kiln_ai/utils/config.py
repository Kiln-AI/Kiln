import getpass
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


class ConfigProperty:
    def __init__(
        self,
        type_: type,
        default: Any = None,
        env_var: Optional[str] = None,
        default_lambda: Optional[Callable[[], Any]] = None,
        sensitive: bool = False,
        sensitive_keys: Optional[List[str]] = None,
    ):
        self.type = type_
        self.default = default
        self.env_var = env_var
        self.default_lambda = default_lambda
        self.sensitive = sensitive
        self.sensitive_keys = sensitive_keys


class Config:
    _shared_instance = None

    def __init__(self, properties: Dict[str, ConfigProperty] | None = None):
        self._properties: Dict[str, ConfigProperty] = properties or {
            "user_id": ConfigProperty(
                str,
                env_var="KILN_USER_ID",
                default_lambda=_get_user_id,
            ),
            "autosave_runs": ConfigProperty(
                bool,
                env_var="KILN_AUTOSAVE_RUNS",
                default=True,
            ),
            "open_ai_api_key": ConfigProperty(
                str,
                env_var="OPENAI_API_KEY",
                sensitive=True,
            ),
            "groq_api_key": ConfigProperty(
                str,
                env_var="GROQ_API_KEY",
                sensitive=True,
            ),
            "ollama_base_url": ConfigProperty(
                str,
                env_var="OLLAMA_BASE_URL",
            ),
            "bedrock_access_key": ConfigProperty(
                str,
                env_var="AWS_ACCESS_KEY_ID",
                sensitive=True,
            ),
            "bedrock_secret_key": ConfigProperty(
                str,
                env_var="AWS_SECRET_ACCESS_KEY",
                sensitive=True,
            ),
            "open_router_api_key": ConfigProperty(
                str,
                env_var="OPENROUTER_API_KEY",
                sensitive=True,
            ),
            "fireworks_api_key": ConfigProperty(
                str,
                env_var="FIREWORKS_API_KEY",
                sensitive=True,
            ),
            "fireworks_account_id": ConfigProperty(
                str,
                env_var="FIREWORKS_ACCOUNT_ID",
            ),
            "anthropic_api_key": ConfigProperty(
                str,
                env_var="ANTHROPIC_API_KEY",
                sensitive=True,
            ),
            "gemini_api_key": ConfigProperty(
                str,
                env_var="GEMINI_API_KEY",
                sensitive=True,
            ),
            "projects": ConfigProperty(
                list,
                default_lambda=lambda: [],
            ),
            "azure_openai_api_key": ConfigProperty(
                str,
                env_var="AZURE_OPENAI_API_KEY",
                sensitive=True,
            ),
            "azure_openai_endpoint": ConfigProperty(
                str,
                env_var="AZURE_OPENAI_ENDPOINT",
            ),
            "huggingface_api_key": ConfigProperty(
                str,
                env_var="HUGGINGFACE_API_KEY",
                sensitive=True,
            ),
            "vertex_project_id": ConfigProperty(
                str,
                env_var="VERTEX_PROJECT_ID",
            ),
            "vertex_location": ConfigProperty(
                str,
                env_var="VERTEX_LOCATION",
            ),
            "together_api_key": ConfigProperty(
                str,
                env_var="TOGETHERAI_API_KEY",
                sensitive=True,
            ),
            "wandb_api_key": ConfigProperty(
                str,
                env_var="WANDB_API_KEY",
                sensitive=True,
            ),
            "wandb_base_url": ConfigProperty(
                str,
                env_var="WANDB_BASE_URL",
            ),
            "custom_models": ConfigProperty(
                list,
                default_lambda=lambda: [],
            ),
            "openai_compatible_providers": ConfigProperty(
                list,
                default_lambda=lambda: [],
                sensitive_keys=["api_key"],
            ),
        }
        self._settings = self.load_settings()

    @classmethod
    def shared(cls):
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    # Get a value, mockable for testing
    def get_value(self, name: str) -> Any:
        try:
            return self.__getattr__(name)
        except AttributeError:
            return None

    def __getattr__(self, name: str) -> Any:
        if name == "_properties":
            return super().__getattribute__("_properties")
        if name not in self._properties:
            return super().__getattribute__(name)

        property_config = self._properties[name]

        # Check if the value is in settings
        if name in self._settings:
            value = self._settings[name]
            return value if value is None else property_config.type(value)

        # Check environment variable
        if property_config.env_var and property_config.env_var in os.environ:
            value = os.environ[property_config.env_var]
            return property_config.type(value)

        # Use default value or default_lambda
        if property_config.default_lambda:
            value = property_config.default_lambda()
        else:
            value = property_config.default

        return None if value is None else property_config.type(value)

    def __setattr__(self, name, value):
        if name in ("_properties", "_settings"):
            super().__setattr__(name, value)
        elif name in self._properties:
            self.update_settings({name: value})
        else:
            raise AttributeError(f"Config has no attribute '{name}'")

    @classmethod
    def settings_dir(cls, create=True):
        settings_dir = os.path.join(Path.home(), ".kiln_ai")
        if create and not os.path.exists(settings_dir):
            os.makedirs(settings_dir)
        return settings_dir

    @classmethod
    def settings_path(cls, create=True):
        settings_dir = cls.settings_dir(create)
        return os.path.join(settings_dir, "settings.yaml")

    @classmethod
    def load_settings(cls):
        if not os.path.isfile(cls.settings_path(create=False)):
            return {}
        with open(cls.settings_path(), "r") as f:
            settings = yaml.safe_load(f.read()) or {}
        return settings

    def settings(self, hide_sensitive=False) -> Dict[str, Any]:
        if not hide_sensitive:
            return self._settings

        settings = {
            k: "[hidden]"
            if k in self._properties and self._properties[k].sensitive
            else v
            for k, v in self._settings.items()
        }
        # Hide sensitive keys in lists. Could generalize this if we every have more types, but right not it's only needed for root elements of lists
        for key, value in settings.items():
            if key in self._properties and self._properties[key].sensitive_keys:
                sensitive_keys = self._properties[key].sensitive_keys or []
                for sensitive_key in sensitive_keys:
                    if isinstance(value, list):
                        for item in value:
                            if sensitive_key in item:
                                item[sensitive_key] = "[hidden]"

        return settings

    def save_setting(self, name: str, value: Any):
        self.update_settings({name: value})

    def update_settings(self, new_settings: Dict[str, Any]):
        # Lock to prevent race conditions in multi-threaded scenarios
        with threading.Lock():
            # Fresh load to avoid clobbering changes from other instances
            current_settings = self.load_settings()
            current_settings.update(new_settings)
            # remove None values
            current_settings = {
                k: v for k, v in current_settings.items() if v is not None
            }
            with open(self.settings_path(), "w") as f:
                yaml.dump(current_settings, f)
            self._settings = current_settings


def _get_user_id():
    try:
        return getpass.getuser() or "unknown_user"
    except Exception:
        return "unknown_user"
