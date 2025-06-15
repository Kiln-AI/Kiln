# Run a desktop server for development:
# - Auto-reload is enabled
# - Extra logging (level+colors) is enabled
import os

import uvicorn

from app.desktop.desktop_server import make_app

# top level app object, as that's needed by auto-reload
dev_app = make_app()

os.environ["DEBUG_EVENT_LOOP"] = "true"


if __name__ == "__main__":
    uvicorn.run(
        "app.desktop.dev_server:dev_app",
        host="127.0.0.1",
        port=8757,
        reload=True,
    )
