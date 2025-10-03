import asyncio

from mcp.client.session import ClientSession

from kiln_ai.utils.logging import logging

logger = logging.getLogger(__name__)


class MCPSessionCache:
    """
    Simple cache for MCP ClientSession by ExternalToolServer ID.

    This cache provides manual lifecycle management - sessions must be
    explicitly closed via close_session() or close_all(). Sessions remain alive until explicitly
    removed or cleared.
    """

    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
        self._lock = asyncio.Lock()

    async def _cleanup_session(self, session: ClientSession) -> None:
        """Helper to clean up a session"""
        try:
            await session.__aexit__(None, None, None)
        except Exception as e:
            # Ignore errors during cleanup so we don't cause MCPSessionManager to throw
            logger.error(f"Error cleaning up ClientSession: {e}")
            pass

    async def get(self, server_id: str) -> ClientSession | None:
        async with self._lock:
            return self._sessions.get(server_id)

    async def set(self, server_id: str, session: ClientSession) -> None:
        # Close old session if it exists to prevent memory leak
        async with self._lock:
            old_session = self._sessions.get(server_id)
            self._sessions[server_id] = session

        # Clean up old session, no lock needed
        if old_session is not None:
            await self._cleanup_session(old_session)

    async def close_session(self, server_id: str) -> None:
        """
        Close and remove a specific session from the cache.
        """
        async with self._lock:
            session = self._sessions.pop(server_id, None)

        if session is not None:
            await self._cleanup_session(session)

    async def close_all(self) -> None:
        """
        Close all cached sessions and clear the cache.
        """
        # Get all server IDs first since close_session modifies the cache dictionary
        server_ids = list(self._sessions.keys())
        for server_id in server_ids:
            await self.close_session(server_id)
