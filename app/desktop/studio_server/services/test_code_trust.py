import re

from app.desktop.studio_server.services.code_trust import not_trusted_message

# The pattern the app's Warning component uses to turn URLs into links.
LINK_PATTERN = re.compile(r"https?://\S+")


def test_not_trusted_message_uses_the_real_project_id():
    message = not_trusted_message("Code refused.", "123456")

    assert message == (
        "Code refused. Only the user can grant code trust, at "
        "http://localhost:8757/settings/trust_code/123456 in the Kiln app. "
        "Confirm with GET /api/projects/123456/add_code_trust, then retry."
    )
    assert "{project_id}" not in message


def test_not_trusted_message_link_is_the_bare_trust_page_url():
    message = not_trusted_message("Code refused.", "123456")

    assert LINK_PATTERN.findall(message) == [
        "http://localhost:8757/settings/trust_code/123456"
    ]


def test_not_trusted_message_encodes_the_project_id():
    message = not_trusted_message("Code refused.", 'a"<b> c')

    assert "trust_code/a%22%3Cb%3E%20c in the Kiln app" in message
    assert "/api/projects/a%22%3Cb%3E%20c/add_code_trust" in message
    assert "<" not in message and '"' not in message
