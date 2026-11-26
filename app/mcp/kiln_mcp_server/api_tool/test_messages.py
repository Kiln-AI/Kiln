import pytest

from kiln_mcp_server.api_tool import messages


@pytest.mark.parametrize("core_text", ["Request failed.", "Request failed!"])
def test_a_core_text_that_ends_a_sentence_gets_no_second_stop(core_text):
    assert messages.request_failed(core_text, "POST").startswith(
        f"{core_text} The POST may have taken effect."
    )
    assert messages.response_unusable(core_text, "POST", 200).startswith(
        f"{core_text} The POST request itself completed"
    )


def test_a_core_text_without_a_stop_becomes_a_sentence():
    assert messages.response_unusable("jq filter error: bad", "DELETE", 204) == (
        "jq filter error: bad. The DELETE request itself completed with status "
        "204. Do not repeat it."
    )


def test_a_get_keeps_the_core_text_as_it_is():
    assert messages.request_failed("Could not connect", "GET") == "Could not connect"
