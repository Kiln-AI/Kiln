# Run a desktop server for development:
# - Auto-reload is enabled
# - Extra logging (level+colors) is enabled
import os
import resource

import uvicorn

from app.desktop.desktop_server import make_app

# Skip remote model loading when running the dev server (unless explicitly set)
os.environ.setdefault("KILN_SKIP_REMOTE_MODEL_LIST", "true")

# Increase file descriptor limit
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
target_soft = max(soft, min(hard, 16384))
resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))

# top level app object, as that's needed by auto-reload
dev_app = make_app()

os.environ["DEBUG_EVENT_LOOP"] = "true"


if __name__ == "__main__":
    uvicorn.run(
        "app.desktop.dev_server:dev_app",
        host="127.0.0.1",
        port=8757,
        reload=True,
        # Debounce when changing many files (changing branch)
        reload_delay=0.1,
    )
