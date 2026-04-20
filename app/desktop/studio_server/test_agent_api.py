from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.agent_api import (
    _dataset_stats,
    _docs_stats,
    _prompt_optimization_jobs_block,
    _prompts_block,
    _search_tools_block,
    _skills_block,
    _specs_block,
    _split_tool_and_skill_ids,
    _tool_servers_block,
    _truncate_to_words,
    connect_agent_api,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Finetune,
    Project,
    Prompt,
    PromptOptimizationJob,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import (
    FineTuneStatusType,
    StructuredOutputMode,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalOutputScore,
    EvalTemplateId,
)
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.extraction import Kind
from kiln_ai.datamodel.prompt import BasePrompt
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import DesiredBehaviourProperties
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_server.custom_errors import connect_custom_errors


# --- Fixtures ---


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_agent_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project(tmp_path):
    p = Project(
        id="proj1",
        name="Test Project",
        description="A test project",
        path=tmp_path / "project.kiln",
    )
    p.save_to_file()
    return p


@pytest.fixture
def task(project, tmp_path):
    t = Task(
        id="task1",
        name="Test Task",
        description="A test task",
        instruction="Do the thing",
        parent=project,
        path=tmp_path / "tasks" / "task1" / "task.kiln",
    )
    t.save_to_file()
    return t


# --- _truncate_to_words tests ---


class TestTruncateToWords:
    def test_under_limit(self):
        text = "hello world"
        result, truncated = _truncate_to_words(text, 10)
        assert result == "hello world"
        assert truncated is False

    def test_at_limit(self):
        text = "one two three"
        result, truncated = _truncate_to_words(text, 3)
        assert result == "one two three"
        assert truncated is False

    def test_over_limit(self):
        text = "one two three four five"
        result, truncated = _truncate_to_words(text, 3)
        assert result == "one two three \u2026"
        assert truncated is True

    def test_none(self):
        result, truncated = _truncate_to_words(None, 10)
        assert result is None
        assert truncated is False

    def test_empty(self):
        result, truncated = _truncate_to_words("", 10)
        assert result == ""
        assert truncated is False

    def test_exactly_300_words(self):
        text = " ".join(f"word{i}" for i in range(300))
        result, truncated = _truncate_to_words(text, 300)
        assert truncated is False
        assert result == text

    def test_301_words(self):
        text = " ".join(f"word{i}" for i in range(301))
        result, truncated = _truncate_to_words(text, 300)
        assert truncated is True
        words = result.rstrip(" \u2026").split()
        assert len(words) == 300
        assert result.endswith(" \u2026")


# --- _split_tool_and_skill_ids tests ---


class TestSplitToolAndSkillIds:
    def test_mixed(self):
        ids = [
            "mcp::server1::tool1",
            "kiln_tool::skill::my_skill",
            "kiln_tool::rag::rag1",
            "kiln_tool::skill::other_skill",
        ]
        tools, skills = _split_tool_and_skill_ids(ids)
        assert tools == ["mcp::server1::tool1", "kiln_tool::rag::rag1"]
        assert skills == [
            "kiln_tool::skill::my_skill",
            "kiln_tool::skill::other_skill",
        ]

    def test_all_tools(self):
        ids = ["mcp::a", "kiln_tool::rag::b"]
        tools, skills = _split_tool_and_skill_ids(ids)
        assert tools == ids
        assert skills == []

    def test_all_skills(self):
        ids = ["kiln_tool::skill::a", "kiln_tool::skill::b"]
        tools, skills = _split_tool_and_skill_ids(ids)
        assert tools == []
        assert skills == ids

    def test_empty(self):
        tools, skills = _split_tool_and_skill_ids([])
        assert tools == []
        assert skills == []


# --- _dataset_stats tests ---


class TestDatasetStats:
    def test_aggregation(self, task):
        TaskRun(
            parent=task,
            input="input1",
            output=TaskOutput(
                output="out1",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "tester"},
                ),
                rating=TaskOutputRating(type=TaskOutputRatingType.five_star, value=4.0),
            ),
            tags=["tag_a", "tag_b"],
        ).save_to_file()
        TaskRun(
            parent=task,
            input="input2",
            output=TaskOutput(
                output="out2",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test_adapter",
                    },
                ),
                rating=TaskOutputRating(type=TaskOutputRatingType.five_star, value=5.0),
            ),
            tags=["tag_a"],
        ).save_to_file()
        TaskRun(
            parent=task,
            input="input3",
            output=TaskOutput(
                output="out3",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "tester2"},
                ),
            ),
            tags=[],
        ).save_to_file()

        stats = _dataset_stats(task)
        assert stats.total_count == 3
        assert stats.by_tag == {"tag_a": 2, "tag_b": 1}
        assert stats.by_source["human"] == 2
        assert stats.by_source["synthetic"] == 1
        assert stats.by_source["file_import"] == 0
        assert stats.by_source["tool_call"] == 0
        assert stats.by_rating["4"] == 1
        assert stats.by_rating["5"] == 1
        assert stats.by_rating["unrated"] == 1

    def test_empty(self, task):
        stats = _dataset_stats(task)
        assert stats.total_count == 0
        assert stats.by_tag == {}
        for src in DataSourceType:
            assert stats.by_source[src.value] == 0
        for i in range(1, 6):
            assert stats.by_rating[str(i)] == 0
        assert stats.by_rating["unrated"] == 0

    def test_two_tags_both_counted(self, task):
        TaskRun(
            parent=task,
            input="input1",
            output=TaskOutput(
                output="out1",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "tester"},
                ),
            ),
            tags=["x", "y"],
        ).save_to_file()
        stats = _dataset_stats(task)
        assert stats.by_tag == {"x": 1, "y": 1}


# --- _docs_stats tests ---


class TestDocsStats:
    def test_aggregation(self, project):
        doc1 = MagicMock()
        doc1.kind = Kind.DOCUMENT
        doc1.tags = ["t1", "t2"]
        doc2 = MagicMock()
        doc2.kind = Kind.IMAGE
        doc2.tags = ["t1"]

        with patch.object(Project, "documents", return_value=[doc1, doc2]):
            stats = _docs_stats(project)
            assert stats.doc_count == 2
            assert stats.by_kind["document"] == 1
            assert stats.by_kind["image"] == 1
            assert stats.by_kind["video"] == 0
            assert stats.by_kind["audio"] == 0
            assert stats.by_tag == {"t1": 2, "t2": 1}

    def test_empty(self, project):
        stats = _docs_stats(project)
        assert stats.doc_count == 0
        assert stats.by_tag == {}
        for k in Kind:
            assert stats.by_kind[k.value] == 0


# --- Archive filtering tests ---


class TestSearchToolsBlock:
    def test_filters_archived(self, project):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        active_rag = MagicMock()
        active_rag.is_archived = False
        active_rag.id = "rag1"
        active_rag.name = "active_rag"
        active_rag.tool_name = "search_active"
        active_rag.tool_description = "Active search"
        active_rag.description = None
        active_rag.tags = None
        active_rag.created_at = datetime.now(tz=timezone.utc)

        archived_rag = MagicMock()
        archived_rag.is_archived = True

        with patch.object(
            Project, "rag_configs", return_value=[active_rag, archived_rag]
        ):
            block = _search_tools_block(project)
            assert len(block.items) == 1
            assert block.items[0].name == "active_rag"
            assert block.archived_search_tool_count == 1


class TestToolServersBlock:
    def test_filters_archived(self, project):
        ExternalToolServer(
            parent=project,
            name="active_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "is_archived": False,
            },
        ).save_to_file()
        ExternalToolServer(
            parent=project,
            name="archived_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "is_archived": True,
            },
        ).save_to_file()

        block = _tool_servers_block(project)
        assert len(block.items) == 1
        assert block.items[0].name == "active_server"
        assert block.archived_tool_server_count == 1


class TestSkillsBlock:
    def test_filters_archived(self, project):
        Skill(
            parent=project,
            name="active-skill",
            description="An active skill",
            is_archived=False,
        ).save_to_file()
        Skill(
            parent=project,
            name="archived-skill",
            description="An archived skill",
            is_archived=True,
        ).save_to_file()

        block = _skills_block(project)
        assert len(block.items) == 1
        assert block.items[0].name == "active-skill"
        assert block.archived_skill_count == 1


class TestSpecsBlock:
    def test_filters_archived(self, task):
        eval_obj = Eval(
            parent=task,
            name="Test Eval",
            eval_set_filter_id="all",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="score1",
                    type=TaskOutputRatingType.five_star,
                )
            ],
            template=EvalTemplateId.desired_behaviour,
        )
        eval_obj.save_to_file()

        Spec(
            parent=task,
            name="Active Spec",
            definition="Active definition",
            properties=DesiredBehaviourProperties(
                spec_type="desired_behaviour",
                desired_behaviour_description="Active definition",
            ),
            status=SpecStatus.active,
            eval_id=eval_obj.id,
        ).save_to_file()
        Spec(
            parent=task,
            name="Archived Spec",
            definition="Archived definition",
            properties=DesiredBehaviourProperties(
                spec_type="desired_behaviour",
                desired_behaviour_description="Archived definition",
            ),
            status=SpecStatus.archived,
            eval_id=eval_obj.id,
        ).save_to_file()

        block = _specs_block(task)
        assert len(block.items) == 1
        assert block.items[0].name == "Active Spec"
        assert block.archived_spec_count == 1


# --- Endpoint tests ---


class TestAgentOverviewEndpoint:
    def test_happy_path(self, client, task, project):
        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task1/agent_overview")
            assert response.status_code == 200
            data = response.json()

            assert data["project"]["id"] == "proj1"
            assert data["project"]["name"] == "Test Project"
            assert data["task"]["id"] == "task1"
            assert data["task"]["name"] == "Test Task"
            assert data["task"]["instruction"] == "Do the thing"
            assert data["task"]["instruction_truncated"] is False
            assert data["dataset"]["total_count"] == 0
            assert data["docs"]["doc_count"] == 0
            assert data["search_tools"]["items"] == []
            assert data["search_tools"]["archived_search_tool_count"] == 0
            assert isinstance(data["prompts"], list)
            assert data["specs"]["items"] == []
            assert data["specs"]["archived_spec_count"] == 0
            assert data["evals"] == []
            assert data["tool_servers"]["items"] == []
            assert data["tool_servers"]["archived_tool_server_count"] == 0
            assert data["run_configs"]["default_run_config_id"] is None
            assert data["run_configs"]["items"] == []
            assert data["fine_tunes"] == []
            assert data["prompt_optimization_jobs"] == []
            assert data["skills"]["items"] == []
            assert data["skills"]["archived_skill_count"] == 0
            assert data["connected_providers"] == {}

    def test_not_found_project(self, client):
        response = client.get("/api/projects/nonexistent/tasks/task1/agent_overview")
        assert response.status_code == 404

    def test_not_found_task(self, client, project):
        with patch(
            "app.desktop.studio_server.agent_api.task_from_id",
            side_effect=HTTPException(status_code=404, detail="Task not found"),
        ):
            response = client.get(
                "/api/projects/proj1/tasks/nonexistent/agent_overview"
            )
            assert response.status_code == 404

    def test_instruction_truncation_at_300(self, client, project, tmp_path):
        instruction_300 = " ".join(f"w{i}" for i in range(300))
        t = Task(
            id="task300",
            name="Task 300",
            instruction=instruction_300,
            parent=project,
            path=tmp_path / "tasks" / "task300" / "task.kiln",
        )
        t.save_to_file()

        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=t,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task300/agent_overview")
            data = response.json()
            assert data["task"]["instruction_truncated"] is False
            assert data["task"]["instruction"] == instruction_300

    def test_instruction_truncation_at_301(self, client, project, tmp_path):
        instruction_301 = " ".join(f"w{i}" for i in range(301))
        t = Task(
            id="task301",
            name="Task 301",
            instruction=instruction_301,
            parent=project,
            path=tmp_path / "tasks" / "task301" / "task.kiln",
        )
        t.save_to_file()

        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=t,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task301/agent_overview")
            data = response.json()
            assert data["task"]["instruction_truncated"] is True
            assert data["task"]["instruction"].endswith(" \u2026")
            words = data["task"]["instruction"].rstrip(" \u2026").split()
            assert len(words) == 300

    def test_with_run_configs(self, client, task, project, tmp_path):
        rc = TaskRunConfig(
            id="rc1",
            name="Test RC",
            description="A test run config",
            parent=task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name="openai",
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.default,
                tools_config=ToolsRunConfig(
                    tools=[
                        "mcp::remote::server1::tool1",
                        "kiln_tool::skill::my_skill",
                    ]
                ),
            ),
            starred=True,
        )
        rc.save_to_file()

        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[rc],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task1/agent_overview")
            data = response.json()
            rc_data = data["run_configs"]["items"][0]
            assert rc_data["id"] == "rc1"
            assert rc_data["name"] == "Test RC"
            assert rc_data["type"] == "kiln_agent"
            assert rc_data["model_name"] == "gpt-4"
            assert rc_data["model_provider"] == "openai"
            assert rc_data["tool_ids"] == ["mcp::remote::server1::tool1"]
            assert rc_data["skill_ids"] == ["kiln_tool::skill::my_skill"]
            assert rc_data["starred"] is True

    def test_with_evals(self, client, task, project):
        eval_obj = Eval(
            parent=task,
            name="Test Eval",
            description="An eval",
            eval_set_filter_id="all",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="Accuracy",
                    type=TaskOutputRatingType.five_star,
                ),
                EvalOutputScore(
                    name="Hallucination",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            template=EvalTemplateId.desired_behaviour,
            favourite=True,
        )
        eval_obj.save_to_file()

        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task1/agent_overview")
            data = response.json()
            assert len(data["evals"]) == 1
            ev = data["evals"][0]
            assert ev["name"] == "Test Eval"
            assert ev["description"] == "An eval"
            assert ev["template"] == "desired_behaviour"
            assert ev["favourite"] is True
            assert len(ev["output_scores"]) == 2
            assert ev["output_scores"][0]["name"] == "Accuracy"
            assert ev["output_scores"][0]["type"] == "five_star"
            assert ev["output_scores"][1]["name"] == "Hallucination"
            assert ev["output_scores"][1]["type"] == "pass_fail"

    def test_connected_providers(self, client, task, project):
        async def mock_provider_enabled(name):
            return name.value in ("openai", "anthropic")

        with (
            patch(
                "app.desktop.studio_server.agent_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.agent_api.get_all_run_configs",
                return_value=[],
            ),
            patch(
                "app.desktop.studio_server.agent_api.provider_enabled",
                side_effect=mock_provider_enabled,
            ),
        ):
            response = client.get("/api/projects/proj1/tasks/task1/agent_overview")
            data = response.json()
            assert "openai" in data["connected_providers"]
            assert "anthropic" in data["connected_providers"]
            assert data["connected_providers"]["openai"] == {}
            assert data["connected_providers"]["anthropic"] == {}
            assert "groq" not in data["connected_providers"]


# --- _prompts_block tests ---


class TestPromptsBlock:
    def test_all_prompt_sources(self, task, project):
        saved_prompt = Prompt(
            parent=task,
            name="Saved Prompt",
            prompt="Do something",
            generator_id="simple_prompt_builder",
        )
        saved_prompt.save_to_file()

        ft = Finetune(
            parent=task,
            name="My Fine Tune",
            provider="openai",
            base_model_id="gpt-4o-mini-2024-07-18",
            fine_tune_model_id="ft:gpt-4o-mini:org::abc123",
            dataset_split_id="split1",
            system_message="You are a helpful assistant.",
            latest_status=FineTuneStatusType.completed,
        )
        ft.save_to_file()

        rc_with_prompt = TaskRunConfig(
            parent=task,
            name="Frozen RC",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name="openai",
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.default,
            ),
            prompt=BasePrompt(
                name="Frozen Prompt",
                prompt="Frozen instructions",
                generator_id="simple_prompt_builder",
            ),
        )
        rc_with_prompt.save_to_file()

        prompts = _prompts_block(task)

        ids = [p.id for p in prompts]

        assert any(p.id == "simple_prompt_builder" for p in prompts)
        assert any(p.id == "few_shot_prompt_builder" for p in prompts)

        saved_ids = [pid for pid in ids if pid.startswith("id::")]
        assert len(saved_ids) == 1
        assert saved_ids[0] == f"id::{saved_prompt.id}"

        ft_ids = [pid for pid in ids if pid.startswith("fine_tune_prompt::")]
        assert len(ft_ids) == 1
        assert ft.id in ft_ids[0]

        rc_ids = [pid for pid in ids if pid.startswith("task_run_config::")]
        assert len(rc_ids) == 1
        assert rc_with_prompt.id in rc_ids[0]

        for p in prompts:
            assert p.type is not None
            assert len(p.type) > 0


# --- _prompt_optimization_jobs_block tests ---


class TestPromptOptimizationJobsBlock:
    def test_resolves_run_config(self, task):
        rc = TaskRunConfig(
            parent=task,
            name="Target RC",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="claude-3-5-sonnet",
                model_provider_name="anthropic",
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.default,
            ),
        )
        rc.save_to_file()

        job = PromptOptimizationJob(
            parent=task,
            name="Opt Job",
            job_id="remote_job_1",
            target_run_config_id=str(rc.id),
            latest_status="succeeded",
            created_prompt_id="id::prompt_abc",
        )
        job.save_to_file()

        run_configs_by_id = {str(rc.id): rc}
        result = _prompt_optimization_jobs_block(task, run_configs_by_id)

        assert len(result) == 1
        entry = result[0]
        assert entry.model_name == "claude-3-5-sonnet"
        assert entry.model_provider == "anthropic"
        assert entry.latest_status == "succeeded"
        assert entry.created_prompt_id == "id::prompt_abc"

    def test_missing_run_config(self, task):
        job = PromptOptimizationJob(
            parent=task,
            name="Orphan Job",
            job_id="remote_job_2",
            target_run_config_id="nonexistent_rc",
            latest_status="pending",
        )
        job.save_to_file()

        result = _prompt_optimization_jobs_block(task, {})
        assert len(result) == 1
        assert result[0].model_name is None
        assert result[0].model_provider is None
