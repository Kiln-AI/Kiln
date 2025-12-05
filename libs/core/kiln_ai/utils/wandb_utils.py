import httpx


class AuthenticationError(Exception):
    """Raised when authentication fails or credentials are invalid."""

    pass


async def get_wandb_default_entity(
    key: str, base_url: str | None
) -> str | None | AuthenticationError:
    """Get the default entity for a W&B API key.

    Args:
        key: The W&B API key to authenticate with
        custom_entity: Optional custom entity name (currently unused)
        base_url: Optional custom W&B API base URL, defaults to https://api.wandb.ai

    Returns:
        The default entity name if found, None if not set, or an AuthenticationError if the API key is invalid or authentication fails
    """
    try:
        api_url = base_url or "https://api.wandb.ai"
        headers = {
            "Content-Type": "application/json",
        }
        # Use GraphQL to validate API key with the viewer.id query.
        # Also fetch the default entity name
        post_args = {
            "query": "query { viewer { id, username, defaultEntity { id, name } } }",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_url}/graphql",
                timeout=5.0,
                json=post_args,
                headers=headers,
                auth=("api_key", key),
            )

            if response.status_code == 401:
                return AuthenticationError(
                    "Failed to connect to W&B. Invalid API key (401)."
                )

            json_data = response.json()

            if (
                "data" in json_data
                and "viewer" in json_data["data"]
                and json_data["data"]["viewer"] is None
            ):
                return AuthenticationError(
                    "Failed to connect to W&B. Invalid API key (no viewer)."
                )

            if (
                "data" in json_data
                and "viewer" in json_data["data"]
                and json_data["data"]["viewer"] is not None
                and json_data["data"]["viewer"]["defaultEntity"] is not None
                and json_data["data"]["viewer"]["defaultEntity"]["name"] is not None
            ):
                return json_data["data"]["viewer"]["defaultEntity"]["name"]

            return None
    except Exception as e:
        return AuthenticationError(f"Failed to connect to W&B. Unexpected error: {e!s}")
