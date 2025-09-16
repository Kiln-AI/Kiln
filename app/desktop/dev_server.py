# Run a desktop server for development:
# - Auto-reload is enabled
# - Extra logging (level+colors) is enabled
import os

import uvicorn

from app.desktop.desktop_server import make_app
from app.desktop.log_config import log_config, validate_log_level

# Skip remote model loading when running the dev server (unless explicitly set)
os.environ.setdefault("KILN_SKIP_REMOTE_MODEL_LIST", "true")

# top level app object, as that's needed by auto-reload
dev_app = make_app(
    litellm_log_filename="dev_model_calls.log",
)

os.environ["DEBUG_EVENT_LOOP"] = "true"


if __name__ == "__main__":
    uvicorn.run(
        "app.desktop.dev_server:dev_app",
        host="127.0.0.1",
        port=8757,
        reload=True,
        # Debounce when changing many files (changing branch)
        reload_delay=0.1,
        use_colors=True,
        log_config=log_config(
            log_level=validate_log_level(os.getenv("KILN_LOG_LEVEL", "INFO")),
            log_file_name="dev_kiln_desktop.log",
        ),
    )
