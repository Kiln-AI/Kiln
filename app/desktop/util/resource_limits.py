import logging
import sys

logger = logging.getLogger(__name__)

has_setup_resource_limits = False


def setup_resource_limits():
    """
    Setup resource limits for the current process.

    Scoped to MacOS for now to limit bug risk, and because MacOS is really quite low by default (256)
    """
    global has_setup_resource_limits
    if has_setup_resource_limits:
        return
    has_setup_resource_limits = True

    try:
        if sys.platform == "darwin":
            import resource

            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)

            # Can't exceed hard limit, and don't ever set it below existing soft limit
            target_soft = max(soft, min(hard, 16384))
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
    except Exception as e:
        logger.error(f"Error setting resource limits: {e}")
