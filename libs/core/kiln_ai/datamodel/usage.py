"""Backwards-compatible re-export of the usage models.

The classes live in :mod:`kiln_ai.utils.usage`, which documents the import
cycle this split breaks. This shim keeps
``from kiln_ai.datamodel.usage import Usage, MessageUsage`` working for
external callers and for any serialized reference to this path; Kiln's own
modules import from :mod:`kiln_ai.utils.usage` directly.
"""

from kiln_ai.utils.usage import MessageUsage as MessageUsage
from kiln_ai.utils.usage import Usage as Usage

__all__ = ["MessageUsage", "Usage"]
