import base64
import hashlib
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# GitHub App credentials for Kiln AI.
# This is a GitHub App using the user-access-token (OAuth) flow. Embedding
# the client secret in a distributed desktop binary is standard for
# native/public clients -- the secret cannot be kept confidential on the
# user's machine, which is why PKCE protects the code exchange.
# See the GitHub Apps user-access-token flow:
# https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
GITHUB_CLIENT_ID = "Iv23liZBCgKzY3YowXCC"
GITHUB_CLIENT_SECRET = "eb76bd5e3312c42fa08a63b90b1f152c161d9b2c"

GITHUB_APP_NAME = "kiln-ai-github-sync"
CALLBACK_URL = "http://localhost:8757/api/git_sync/oauth/callback"
OAUTH_TIMEOUT_SECONDS = 300


class OAuthError(Exception):
    pass


@dataclass
class OAuthFlowState:
    state: str
    code_verifier: str
    code_challenge: str
    git_url: str
    created_at: float = field(default_factory=time.monotonic)
    oauth_token: str | None = None
    error: str | None = None
    complete: bool = False


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


_GITHUB_URL_RE = re.compile(
    r"(?:^|[@/])github\.com[:/]([^/\s]+?)/([^/\s]+?)(?:\.git)?/?$"
)


def parse_github_owner_repo(git_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL.

    Supports HTTPS and SSH formats:
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo
    - git@github.com:owner/repo.git
    - ssh://git@github.com/owner/repo.git

    Handles repo names containing dots (e.g. `owner/my.repo`), and rejects
    lookalike hosts like `notgithub.com`, `evilgithub.com`, and
    `subdomain.github.com`.

    Returns None if the URL is not a recognizable github.com URL.
    """
    match = _GITHUB_URL_RE.search(git_url)
    if match:
        return match.group(1), match.group(2)
    return None


async def resolve_github_owner_id(owner: str) -> int | None:
    """Resolve a GitHub owner (user or org) name to its numeric ID.

    Returns None on any failure (404, rate limit, network error).
    """
    try:
        async with httpx.AsyncClient(
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        ) as client:
            resp = await client.get(
                f"https://api.github.com/users/{owner}",
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("id")
            logger.warning(
                "GitHub API returned status %d when resolving owner ID for %s",
                resp.status_code,
                owner,
            )
    except Exception:
        logger.warning("Failed to resolve GitHub owner ID for %s", owner, exc_info=True)
    return None


async def resolve_github_repo_id(owner: str, repo: str) -> int | None:
    """Resolve a GitHub repo to its numeric ID.

    Returns None on any failure (404 for private repos, rate limit, network error).
    """
    try:
        async with httpx.AsyncClient(
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        ) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("id")
            logger.warning(
                "GitHub API returned status %d when resolving repo ID for %s/%s",
                resp.status_code,
                owner,
                repo,
            )
    except Exception:
        logger.warning(
            "Failed to resolve GitHub repo ID for %s/%s", owner, repo, exc_info=True
        )
    return None


def build_install_url(
    owner_id: int | None = None,
    repo_id: int | None = None,
) -> str:
    """Build the GitHub App installation URL with available pre-selection params."""
    base = f"https://github.com/apps/{GITHUB_APP_NAME}/installations/new"
    params: dict[str, str] = {}
    if owner_id is not None:
        params["suggested_target_id"] = str(owner_id)
    if repo_id is not None:
        params["repository_ids[]"] = str(repo_id)
    if params:
        return f"{base}/permissions?{urlencode(params)}"
    return base


def build_authorize_url(flow: OAuthFlowState) -> str:
    """Build the GitHub OAuth authorize URL for a given flow."""
    return "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": CALLBACK_URL,
            "state": flow.state,
            "code_challenge": flow.code_challenge,
            "code_challenge_method": "S256",
        }
    )


async def exchange_code_for_token(code: str, code_verifier: str) -> str:
    """Exchange an authorization code for a GitHub user access token.

    Raises OAuthError on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": CALLBACK_URL,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
                timeout=30.0,
            )
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            error_desc = data.get(
                "error_description", data.get("error", "Unknown error")
            )
            raise OAuthError(f"Token exchange failed: {error_desc}")
    except OAuthError:
        raise
    except Exception as e:
        raise OAuthError(f"Token exchange failed: {e}") from e


class OAuthFlowManager:
    """Manages in-progress OAuth flows. Thread-safe."""

    def __init__(self) -> None:
        self._flows: dict[str, OAuthFlowState] = {}
        self._lock: threading.Lock = threading.Lock()

    def start_flow(self, git_url: str) -> OAuthFlowState:
        """Create a new flow with generated state and PKCE values."""
        self._cleanup_expired()
        state = secrets.token_urlsafe(32)
        verifier, challenge = generate_pkce()
        flow = OAuthFlowState(
            state=state,
            code_verifier=verifier,
            code_challenge=challenge,
            git_url=git_url,
        )
        with self._lock:
            self._flows[state] = flow
        return flow

    def get_flow(self, state: str) -> OAuthFlowState | None:
        """Retrieve a pending flow by state. Returns None if expired/missing."""
        self._cleanup_expired()
        now = time.monotonic()
        with self._lock:
            flow = self._flows.get(state)
            if flow is None:
                return None
            # Defense-in-depth: re-check TTL under the lock in case the flow
            # sneaked past the sweep (e.g. crossed the boundary between
            # _cleanup_expired() and this read).
            if (now - flow.created_at) >= OAUTH_TIMEOUT_SECONDS:
                return None
            return flow

    def complete_flow(self, state: str, oauth_token: str) -> None:
        """Mark a flow as complete with the received token."""
        with self._lock:
            flow = self._flows.get(state)
            if flow is not None:
                flow.oauth_token = oauth_token
                flow.complete = True

    def fail_flow(self, state: str, error: str) -> None:
        """Mark a flow as failed with an error message."""
        with self._lock:
            flow = self._flows.get(state)
            if flow is not None:
                flow.error = error
                flow.complete = True

    def consume_flow(self, state: str) -> OAuthFlowState | None:
        """Retrieve and delete a completed flow (one-time retrieval)."""
        with self._lock:
            flow = self._flows.get(state)
            if flow is not None and flow.complete:
                del self._flows[state]
                return flow
        return None

    def _cleanup_expired(self) -> None:
        """Remove flows older than OAUTH_TIMEOUT_SECONDS."""
        now = time.monotonic()
        with self._lock:
            expired = [
                state
                for state, flow in self._flows.items()
                if (now - flow.created_at) >= OAUTH_TIMEOUT_SECONDS
            ]
            for state in expired:
                del self._flows[state]
