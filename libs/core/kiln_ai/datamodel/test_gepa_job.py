from kiln_ai.datamodel import GepaJob, Project, Task


def test_gepa_job_creation(tmp_path):
    """Test basic GepaJob creation."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test GEPA Job",
        description="Test description",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-123",
        latest_status="pending",
        parent=task,
    )

    assert gepa_job.name == "Test GEPA Job"
    assert gepa_job.description == "Test description"
    assert gepa_job.job_id == "remote-job-123"
    assert gepa_job.token_budget == "medium"
    assert gepa_job.target_run_config_id == "config-123"
    assert gepa_job.latest_status == "pending"
    assert gepa_job.optimized_prompt is None
    assert gepa_job.created_prompt_id is None


def test_gepa_job_parent_task(tmp_path):
    """Test that parent_task() returns the correct parent task."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test GEPA Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-123",
        parent=task,
    )

    parent_task = gepa_job.parent_task()
    assert parent_task is not None
    assert parent_task.name == "Test Task"
    assert parent_task.id == task.id


def test_gepa_job_parent_task_none():
    """Test that parent_task() returns None when parent is None."""
    gepa_job = GepaJob(
        name="Test GEPA Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-123",
    )

    parent_task = gepa_job.parent_task()
    assert parent_task is None


def test_gepa_job_with_result(tmp_path):
    """Test GepaJob with optimized prompt and created prompt ID."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test GEPA Job",
        job_id="remote-job-123",
        token_budget="heavy",
        target_run_config_id="config-123",
        latest_status="succeeded",
        optimized_prompt="This is the optimized prompt",
        created_prompt_id="prompt-123",
        parent=task,
    )

    assert gepa_job.latest_status == "succeeded"
    assert gepa_job.optimized_prompt == "This is the optimized prompt"
    assert gepa_job.created_prompt_id == "prompt-123"


def test_gepa_job_save_and_load(tmp_path):
    """Test that GepaJob can be saved and loaded from file."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test GEPA Job",
        description="Test description",
        job_id="remote-job-123",
        token_budget="light",
        target_run_config_id="config-123",
        latest_status="running",
        parent=task,
    )
    gepa_job.save_to_file()

    loaded_jobs = task.gepa_jobs()
    assert len(loaded_jobs) == 1
    assert loaded_jobs[0].name == "Test GEPA Job"
    assert loaded_jobs[0].description == "Test description"
    assert loaded_jobs[0].job_id == "remote-job-123"
    assert loaded_jobs[0].token_budget == "light"
    assert loaded_jobs[0].latest_status == "running"
