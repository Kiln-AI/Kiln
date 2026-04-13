import base64
import hashlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.desktop.git_sync.oauth import (
    GITHUB_APP_NAME,
    OAUTH_TIMEOUT_SECONDS,
    OAuthError,
    OAuthFlowManager,
    build_install_url,
    exchange_code_for_token,
    generate_pkce,
    parse_github_owner_repo,
    resolve_github_owner_id,
    resolve_github_repo_id,
)


class TestGeneratePkce:
    def test_returns_verifier_and_challenge(self):
        verifier, challenge = generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 20
        assert len(challenge) > 20

    def test_challenge_matches_verifier(self):
        verifier, challenge = generate_pkce()
        expected_digest = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = (
            base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode()
        )
        assert challenge == expected_challenge

    def test_each_call_produces_unique_values(self):
        v1, c1 = generate_pkce()
        v2, c2 = generate_pkce()
        assert v1 != v2
        assert c1 != c2


class TestParseGithubOwnerRepo:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/Kiln-AI/kiln.git", ("Kiln-AI", "kiln")),
            ("git@github.com:owner/repo.git", ("owner", "repo")),
            ("ssh://git@github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo/", ("owner", "repo")),
            # Repo names with dots are legal on GitHub (e.g. octocat/hello.world)
            ("https://github.com/octocat/hello.world", ("octocat", "hello.world")),
            ("https://github.com/owner/my.repo.git", ("owner", "my.repo")),
            ("https://github.com/owner/some.tool.js", ("owner", "some.tool.js")),
            ("git@github.com:owner/my.repo.git", ("owner", "my.repo")),
        ],
    )
    def test_valid_urls(self, url, expected):
        assert parse_github_owner_repo(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/owner/repo.git",
            "https://example.com/owner/repo.git",
            "not-a-url",
            "",
            # Lookalike hosts must be rejected -- an unanchored regex would
            # happily treat these as github.com.
            "https://notgithub.com/owner/repo",
            "https://evilgithub.com/owner/repo.git",
            "https://mygithub.com/owner/repo",
            "https://subdomain.github.com/owner/repo",
            "https://api.github.com/repos/owner/repo",
            "git@subdomain.github.com:owner/repo.git",
        ],
    )
    def test_non_github_urls_return_none(self, url):
        assert parse_github_owner_repo(url) is None


class TestBuildInstallUrl:
    def test_with_both_ids(self):
        url = build_install_url(owner_id=123, repo_id=456)
        assert "suggested_target_id=123" in url
        assert "repository_ids" in url
        assert "456" in url
        assert url.startswith(
            f"https://github.com/apps/{GITHUB_APP_NAME}/installations/new/permissions"
        )

    def test_with_owner_id_only(self):
        url = build_install_url(owner_id=123)
        assert "suggested_target_id=123" in url
        assert "repository_ids" not in url

    def test_with_repo_id_only(self):
        url = build_install_url(repo_id=456)
        assert "suggested_target_id" not in url
        assert "repository_ids" in url

    def test_with_no_ids(self):
        url = build_install_url()
        assert url == f"https://github.com/apps/{GITHUB_APP_NAME}/installations/new"
        assert "?" not in url


class TestOAuthFlowManager:
    def test_start_flow(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        assert flow.state
        assert flow.code_verifier
        assert flow.code_challenge
        assert flow.git_url == "https://github.com/owner/repo.git"
        assert not flow.complete
        assert flow.oauth_token is None
        assert flow.error is None

    def test_get_flow(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        retrieved = mgr.get_flow(flow.state)
        assert retrieved is flow

    def test_get_flow_missing(self):
        mgr = OAuthFlowManager()
        assert mgr.get_flow("nonexistent") is None

    def test_complete_flow(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        mgr.complete_flow(flow.state, "ghu_token123")
        assert flow.complete
        assert flow.oauth_token == "ghu_token123"

    def test_fail_flow(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        mgr.fail_flow(flow.state, "User denied access")
        assert flow.complete
        assert flow.error == "User denied access"

    def test_consume_flow(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        mgr.complete_flow(flow.state, "ghu_token123")
        consumed = mgr.consume_flow(flow.state)
        assert consumed is not None
        assert consumed.oauth_token == "ghu_token123"
        assert mgr.get_flow(flow.state) is None

    def test_consume_flow_incomplete_returns_none(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        assert mgr.consume_flow(flow.state) is None

    def test_consume_flow_missing_returns_none(self):
        mgr = OAuthFlowManager()
        assert mgr.consume_flow("nonexistent") is None

    def test_get_most_recent_pending_flow(self):
        mgr = OAuthFlowManager()
        mgr.start_flow("https://github.com/owner/repo1.git")
        flow2 = mgr.start_flow("https://github.com/owner/repo2.git")
        result = mgr.get_most_recent_pending_flow()
        assert result is flow2

    def test_get_most_recent_pending_flow_skips_completed(self):
        mgr = OAuthFlowManager()
        flow1 = mgr.start_flow("https://github.com/owner/repo1.git")
        flow2 = mgr.start_flow("https://github.com/owner/repo2.git")
        mgr.complete_flow(flow2.state, "token")
        result = mgr.get_most_recent_pending_flow()
        assert result is flow1

    def test_get_most_recent_pending_flow_empty(self):
        mgr = OAuthFlowManager()
        assert mgr.get_most_recent_pending_flow() is None

    def test_cleanup_expired(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        flow.created_at = time.monotonic() - OAUTH_TIMEOUT_SECONDS - 1
        mgr._cleanup_expired()
        assert mgr.get_flow(flow.state) is None

    def test_non_expired_flow_not_cleaned(self):
        mgr = OAuthFlowManager()
        flow = mgr.start_flow("https://github.com/owner/repo.git")
        mgr._cleanup_expired()
        assert mgr.get_flow(flow.state) is flow

    def test_complete_nonexistent_flow_is_noop(self):
        mgr = OAuthFlowManager()
        mgr.complete_flow("nonexistent", "token")

    def test_fail_nonexistent_flow_is_noop(self):
        mgr = OAuthFlowManager()
        mgr.fail_flow("nonexistent", "error")


def _mock_httpx_client(method="get", response=None, side_effect=None):
    """Create a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if side_effect is not None:
        setattr(mock_client, method, AsyncMock(side_effect=side_effect))
    else:
        setattr(mock_client, method, AsyncMock(return_value=response))
    return mock_client


def _mock_response(status_code=200, json_data=None):
    """Create a MagicMock httpx response (json() is sync, not async)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class TestResolveGithubOwnerId:
    @pytest.mark.asyncio
    async def test_success(self):
        resp = _mock_response(200, {"id": 12345, "login": "owner"})
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("get", response=resp)
            assert await resolve_github_owner_id("owner") == 12345

    @pytest.mark.asyncio
    async def test_not_found(self):
        resp = _mock_response(404, {"message": "Not Found"})
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("get", response=resp)
            assert await resolve_github_owner_id("nonexistent") is None

    @pytest.mark.asyncio
    async def test_network_error(self):
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client(
                "get", side_effect=httpx.ConnectError("Connection refused")
            )
            assert await resolve_github_owner_id("owner") is None


class TestResolveGithubRepoId:
    @pytest.mark.asyncio
    async def test_success(self):
        resp = _mock_response(200, {"id": 67890, "full_name": "owner/repo"})
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("get", response=resp)
            assert await resolve_github_repo_id("owner", "repo") == 67890

    @pytest.mark.asyncio
    async def test_private_repo_returns_none(self):
        resp = _mock_response(404, {"message": "Not Found"})
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("get", response=resp)
            assert await resolve_github_repo_id("owner", "private-repo") is None


class TestExchangeCodeForToken:
    @pytest.mark.asyncio
    async def test_success(self):
        resp = _mock_response(
            200, {"access_token": "ghu_abc123", "token_type": "bearer"}
        )
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("post", response=resp)
            assert (
                await exchange_code_for_token("code123", "verifier123") == "ghu_abc123"
            )

    @pytest.mark.asyncio
    async def test_error_response(self):
        resp = _mock_response(
            200,
            {
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            },
        )
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client("post", response=resp)
            with pytest.raises(OAuthError, match="incorrect or expired"):
                await exchange_code_for_token("bad_code", "verifier123")

    @pytest.mark.asyncio
    async def test_network_error(self):
        with patch("app.desktop.git_sync.oauth.httpx.AsyncClient") as cls:
            cls.return_value = _mock_httpx_client(
                "post", side_effect=httpx.ConnectError("Connection refused")
            )
            with pytest.raises(OAuthError, match="Token exchange failed"):
                await exchange_code_for_token("code123", "verifier123")
