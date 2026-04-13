from app.desktop.git_sync.commit_message import generate_commit_message


def test_generate_commit_message_single_file():
    msg = generate_commit_message(1, "POST /api/projects/123/tasks")
    assert (
        msg
        == "[Kiln] Auto-sync: 1 file changed\n\nContext: POST /api/projects/123/tasks"
    )


def test_generate_commit_message_multiple_files():
    msg = generate_commit_message(5, "PATCH /api/projects/abc/runs/456")
    assert msg == (
        "[Kiln] Auto-sync: 5 files changed\n\nContext: PATCH /api/projects/abc/runs/456"
    )


def test_generate_commit_message_includes_context():
    msg = generate_commit_message(2, "DELETE /api/projects/xyz/tasks/789")
    assert "Context: DELETE /api/projects/xyz/tasks/789" in msg
    assert msg.startswith("[Kiln] Auto-sync:")
