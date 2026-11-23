"""What an agent is told when a project's code is not trusted. Only the user
grants code trust, on an app page that the agent links to; the agent then
confirms the grant through the API."""

CODE_TRUST_PAGE = "http://localhost:8757/settings/trust_code/{project_id}"
CODE_TRUST_CHECK = "GET /api/projects/{project_id}/add_code_trust"


def not_trusted_message(lead: str) -> str:
    """`lead` (a sentence saying what was refused), then how to get trust."""
    return (
        f"{lead} Only the user can grant code trust, at {CODE_TRUST_PAGE}. "
        f"Confirm with {CODE_TRUST_CHECK}, then retry."
    )
