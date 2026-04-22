import json
from pathlib import Path

from kiln_server.utils.agent_checks.policy import AgentPolicy


class AgentPolicyError(Exception):
    """Raised when an endpoint has no known policy (fail-safe block)."""


class AgentPolicyLookup:
    def __init__(self, annotations_dir: str | Path):
        self._annotations_dir = Path(annotations_dir)
        self._cache: dict[tuple[str, str], AgentPolicy] | None = None

    def preload(self) -> None:
        if not self._annotations_dir.is_dir():
            raise FileNotFoundError(
                f"Annotations directory not found: {self._annotations_dir}"
            )
        self._cache = {}
        for filepath in self._annotations_dir.glob("*.json"):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            method = data["method"].lower()
            path = data["path"]
            policy_data = data.get("agent_policy")
            if policy_data is not None:
                self._cache[(method, path)] = AgentPolicy(**policy_data)

    def _load(self) -> None:
        warnings.warn(
            "_load is deprecated and will be removed in a future version. "
            "Please use preload() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.preload()
    def get_policy(self, method: str, path: str) -> AgentPolicy:
        if self._cache is None:
            self.preload()
        assert self._cache is not None
        key = (method.lower(), path)
        if key not in self._cache:
            raise AgentPolicyError(
                f"No agent policy found for {method.upper()} {path}. "
                "Endpoint is blocked by default (fail-safe)."
            )
        return self._cache[key]
