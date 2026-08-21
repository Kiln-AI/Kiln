# Dev-only. The shipped desktop app must never import this: KILN_DEV_MODE turns on
# safety nets that only make sense while developing.
import os


def set_dev_env_vars() -> None:
    """The environment the dev server runs in, in one place.

    Called by the launcher (dev_server.py), so reload workers inherit these, and
    again by dev_app.py, which builds the app and so must not depend on any
    particular launcher having run first.
    """
    # Skip remote model loading when running the dev server (unless explicitly set)
    os.environ.setdefault("KILN_SKIP_REMOTE_MODEL_LIST", "true")
    os.environ["DEBUG_EVENT_LOOP"] = "true"
    os.environ["KILN_DEV_MODE"] = "true"
    # Assistant forensic debug logging on by default in dev (unless explicitly set, e.g.
    # KILN_CHAT_DEBUG_LOG=0) so the JSONL timeline already exists when an assistant issue
    # needs investigating. See chat/debug_log.py.
    os.environ.setdefault("KILN_CHAT_DEBUG_LOG", "1")
