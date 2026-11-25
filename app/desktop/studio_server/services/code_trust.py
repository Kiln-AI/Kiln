"""What an agent is told when a project's code is not trusted. Only the user
grants code trust, on an app page that the agent links to; the agent then
confirms the grant through the API."""

from urllib.parse import quote

from kiln_mcp_server.skill_files import DEFAULT_ORIGIN

CODE_TRUST_PAGE_PATH = "/settings/trust_code/{project_id}"
CODE_TRUST_CHECK = "GET /api/projects/{project_id}/add_code_trust"

# Published API texts are static, so they name the app at its default address.
# The Kiln skill serves its API reference with that address replaced by the
# bound one.
CODE_TRUST_PAGE_DOC = DEFAULT_ORIGIN + CODE_TRUST_PAGE_PATH


def not_trusted_message(lead: str, project_id: str, app_origin: str) -> str:
    """`lead` (a sentence saying what was refused), then how to get trust for
    `project_id`: the trust page link at `app_origin` (the app's address as
    users see it) and the API call that confirms it."""
    quoted_id = quote(project_id, safe="")
    page = app_origin + CODE_TRUST_PAGE_PATH.format(project_id=quoted_id)
    check = CODE_TRUST_CHECK.format(project_id=quoted_id)
    # The app's warning turns each run of non-space characters after
    # "http(s)://" into a link, so the URL is followed by a space, not a stop.
    return (
        f"{lead} Only the user can grant code trust, at {page} in the Kiln app. "
        f"Confirm with {check}, then retry."
    )
