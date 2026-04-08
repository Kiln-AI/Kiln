# Run a desktop server for development:
# - Auto-reload is enabled
# - Extra logging (level+colors) is enabled
import os

import uvicorn

from app.desktop.desktop_server import make_app
from app.desktop.util.resource_limits import setup_resource_limits
from kiln_ai.utils.config import Config

# Skip remote model loading when running the dev server (unless explicitly set)
os.environ.setdefault("KILN_SKIP_REMOTE_MODEL_LIST", "true")

# top level app object, as that's needed by auto-reload
dev_app = make_app()

os.environ["DEBUG_EVENT_LOOP"] = "true"


if __name__ == "__main__":
    setup_resource_limits()

    # KILN_PORT env var overrides the default port from config.
    # Set as KILN_LOCAL_API_PORT so the config env_var lookup picks it up
    # in reloaded worker processes (in-memory config doesn't survive reload).
    kiln_port = os.environ.get("KILN_PORT")
    if kiln_port:
        os.environ["KILN_LOCAL_API_PORT"] = kiln_port

    uvicorn.run(
        "app.desktop.dev_server:dev_app",
        host=Config.shared().kiln_local_api_host,
        port=Config.shared().kiln_local_api_port,
        reload=True,
        # Debounce when changing many files (changing branch)
        reload_delay=0.1,
    )
