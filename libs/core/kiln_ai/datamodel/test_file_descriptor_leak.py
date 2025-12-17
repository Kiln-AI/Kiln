import os
import tempfile
from pathlib import Path

import pytest

from kiln_ai.datamodel import Project, Task


def count_open_fds():
    """Count the number of open file descriptors for the current process."""
    try:
        proc_fd_dir = Path(f"/proc/{os.getpid()}/fd")
        if proc_fd_dir.exists():
            return len(list(proc_fd_dir.iterdir()))
    except (PermissionError, FileNotFoundError):
        pass

    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        fd_count = 0
        for fd in range(0, min(soft, 1024)):
            try:
                os.fstat(fd)
                fd_count += 1
            except OSError:
                pass
        return fd_count
    except ImportError:
        pass

    return None


@pytest.fixture
def project_with_tasks(tmp_path):
    """Create a project with multiple tasks for testing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    tasks = []
    for i in range(10):
        task = Task(
            name=f"Task {i}",
            description=f"Test task {i}",
            instruction="Test instruction",
            parent=project,
        )
        task.save_to_file()
        tasks.append(task)

    return project, tasks


def test_no_file_descriptor_leak_when_looking_up_tasks(project_with_tasks):
    """Test that looking up tasks by ID doesn't leak file descriptors.

    This tests the fix for the issue where from_id_and_parent_path would
    return early from the iterator without closing the os.scandir context manager.
    """
    project, tasks = project_with_tasks

    initial_fd_count = count_open_fds()
    if initial_fd_count is None:
        pytest.skip("Unable to count file descriptors on this platform")

    for _ in range(100):
        for task in tasks:
            found_task = Task.from_id_and_parent_path(task.id, project.path)
            assert found_task is not None
            assert found_task.id == task.id

    final_fd_count = count_open_fds()

    fd_increase = final_fd_count - initial_fd_count
    assert fd_increase < 20, (
        f"File descriptor leak detected: {fd_increase} new FDs opened (initial: {initial_fd_count}, final: {final_fd_count})"
    )


def test_no_file_descriptor_leak_with_attachment_from_data():
    """Test that creating attachments from data doesn't leak file descriptors.

    This tests the fix for the issue where NamedTemporaryFile wasn't using
    a context manager in KilnAttachmentModel.from_data.
    """
    from kiln_ai.datamodel.basemodel import KilnAttachmentModel

    initial_fd_count = count_open_fds()
    if initial_fd_count is None:
        pytest.skip("Unable to count file descriptors on this platform")

    temp_files = []
    for i in range(100):
        attachment = KilnAttachmentModel.from_data(
            f"test data {i}".encode("utf-8"), "text/plain"
        )
        assert attachment.input_path is not None
        temp_files.append(attachment.input_path)

    final_fd_count = count_open_fds()

    for temp_file in temp_files:
        if temp_file.exists():
            temp_file.unlink()

    fd_increase = final_fd_count - initial_fd_count
    assert fd_increase < 20, (
        f"File descriptor leak detected: {fd_increase} new FDs opened (initial: {initial_fd_count}, final: {final_fd_count})"
    )
