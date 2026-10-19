class GitSyncError(Exception):
    """Base class for git sync errors."""

    pass


class SyncConflictError(GitSyncError):
    """Rebase conflict could not be auto-resolved."""

    pass


class RemoteUnreachableError(GitSyncError):
    """Cannot reach git remote."""

    pass


class WriteLockTimeoutError(GitSyncError):
    """Write lock acquisition timed out."""

    pass


class GitAuthError(GitSyncError):
    """Git authentication failed or expired (bad/expired token, 401/403)."""

    pass


class CorruptRepoError(GitSyncError):
    """Git repo is in unexpected state after recovery attempt."""

    pass
