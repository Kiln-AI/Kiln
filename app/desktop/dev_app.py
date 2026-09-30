# The dev server's ASGI app object, in a module of its own.
#
# Importing this module pulls in the whole Kiln app tree, which is the slow part
# of starting the dev server. Only uvicorn's reload worker imports it: the
# launcher process in dev_server.py names it by import string, and so never pays
# that cost. Keeping the app object here rather than there is what stops the
# import tree from running twice per start.
from app.desktop.dev_env import set_dev_env_vars

# Before make_app() runs — and before importing anything that reads these at
# import time — which is why the import below is not at the top of the file.
set_dev_env_vars()

from app.desktop.desktop_server import make_app  # noqa: E402

# Top level app object, as that's needed by auto-reload
dev_app = make_app()
