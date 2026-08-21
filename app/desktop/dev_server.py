# Run a desktop server for development:
# - Auto-reload is enabled
# - Extra logging (level+colors) is enabled
#
# The app object lives in app/desktop/dev_app.py and is named here by import
# string, so only uvicorn's reload worker imports the Kiln app tree. Importing it
# here too would double the (slow) import cost of every start.
#
# The tradeoff: an app that fails to import now fails in that worker, so uvicorn
# prints the traceback and waits for a file change instead of this process
# exiting non-zero. Fix the import and it reloads on its own.
import os

import uvicorn
from kiln_ai.utils.config import Config

from app.desktop.dev_env import set_dev_env_vars
from app.desktop.util.resource_limits import setup_resource_limits

# Set here as well as in dev_app.py so that reload workers inherit them.
set_dev_env_vars()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    setup_resource_limits()

    # KILN_PORT env var overrides the default port from config.
    # Set as KILN_LOCAL_API_PORT so the config env_var lookup picks it up
    # in reloaded worker processes (in-memory config doesn't survive reload).
    kiln_port = os.environ.get("KILN_PORT")
    if kiln_port:
        os.environ["KILN_LOCAL_API_PORT"] = kiln_port

    uvicorn.run(
        "app.desktop.dev_app:dev_app",
        host=Config.shared().kiln_local_api_host,
        port=Config.shared().kiln_local_api_port,
        reload=True,
        # Debounce when changing many files (changing branch)
        reload_delay=0.1,
        # Bound the graceful-shutdown wait on reload. The UI holds the jobs SSE
        # stream open; uvicorn waits for in-flight requests to finish BEFORE it
        # runs lifespan shutdown (which closes the stream), so without a bound a
        # reload would hang on the open SSE. After this many seconds uvicorn
        # cancels the lingering request task instead.
        timeout_graceful_shutdown=1,
    )
