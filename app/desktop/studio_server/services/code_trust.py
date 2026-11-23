"""What an agent is told when a project's code is not trusted. Only the user
grants code trust, on an app page that the agent links to; the agent then
confirms the grant through the API."""

from urllib.parse import quote

CODE_TRUST_PAGE = "http://localhost:8757/settings/trust_code/{project_id}"
CODE_TRUST_CHECK = "GET /api/projects/{project_id}/add_code_trust"


def not_trusted_message(lead: str, project_id: str) -> str:
    """`lead` (a sentence saying what was refused), then how to get trust for
    `project_id`: the trust page link and the API call that confirms it."""
    quoted_id = quote(project_id, safe="")
    page = CODE_TRUST_PAGE.format(project_id=quoted_id)
    check = CODE_TRUST_CHECK.format(project_id=quoted_id)
    # The app's warning turns each run of non-space characters after
    # "http(s)://" into a link, so the URL is followed by a space, not a stop.
    return (
        f"{lead} Only the user can grant code trust, at {page} in the Kiln app. "
        f"Confirm with {check}, then retry."
    )
