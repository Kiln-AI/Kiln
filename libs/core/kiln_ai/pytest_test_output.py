import re
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_output_root() -> Path:
    return Path(__file__).resolve().parents[3] / "test_output"


def make_test_output_dir(request: pytest.FixtureRequest) -> Path:
    test_name = re.sub(r"[^\w\-]", "_", request.node.name)
    param_id = "default"
    if hasattr(request.node, "callspec") and request.node.callspec is not None:
        id_attr = getattr(request.node.callspec, "id", None)
        if id_attr is not None:
            param_id = re.sub(r"[^\w\-]", "_", str(id_attr))
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = test_output_root() / test_name / param_id / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir
