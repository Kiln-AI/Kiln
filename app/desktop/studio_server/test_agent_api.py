from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.agent_api import (
    _dataset_stats,
    _docs_stats,
    _fine_tunes_block,
    _prompt_optimization_jobs_block,
    _prompts_block,
    _run_configs_block,
    _search_tools_block,
    _skills_block,
    _specs_block,
    _split_tool_and_skill_ids,
    _tool_servers_block,
    _top_n_by_recency,
    connect_agent_api,
)
from kiln_ai.utils.formatting import AGENT_TRUNCATION_SENTINEL
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
        assert skills == ["my_skill", "other_skill"]

    def test_all_tools(self):
        ids = ["mcp::a", "kiln_tool::rag::b"]
        tools, skills = _split_tool_and_skill_ids(ids)
        assert tools == ids
        assert skills == []

    def test_all_skills(self):
        ids = ["kiln_tool::skill::a", "kiln_tool::skill::b"]
        tools, skills = _split_tool_and_skill_ids(ids)
        assert tools == []
        assert skills == ["a", "b"]

    def test_empty(self):
        tools, skills = _split_tool_and_skill_ids([])
        assert tools == []
        assert skills == []


# --- _top_n_by_recency tests ---


class TestTopNByRecency:
    def test_selects_top_n(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
        dt3 = datetime(2024, 3, 1, tzinfo=timezone.utc)
        items = [("a", dt1), ("b", dt2), ("c", dt3)]
        result = _top_n_by_recency(items, key=lambda x: (x[1], x[0]), cap=2)
        assert result == [("c", dt3), ("b", dt2)]

    def test_cap_exceeds_length(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        items = [("a", dt1)]
        result = _top_n_by_recency(items, key=lambda x: (x[1], x[0]), cap=5)
        assert result == [("a", dt1)]

    def test_tiebreak_by_id(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        items = [("a", dt), ("c", dt), ("b", dt)]
        result = _top_n_by_recency(items, key=lambda x: (x[1], x[0]), cap=2)
        assert result == [("c", dt), ("b", dt)]

    def test_empty(self):
        result = _top_n_by_recency([], key=lambda x: (x[0], x[1]), cap=5)
        assert result == []


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
        active_rag = MagicMock()
        active_rag.is_archived = False
        active_rag.id = "rag1"
        active_rag.name = "active_rag"
        active_rag.tool_name = "search_active"
        active_rag.tool_description = "Active search"
        active_rag.description = None
        active_rag.tags = None

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


# --- _prompts_block tests ---


class TestPromptsBlock:
    def test_excludes_generators_includes_real_prompts(self, task, project):
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

        result = _prompts_block(task, project, task.run_configs())

        ids = [p.id for p in result.items]

        assert not any(p.id == "simple_prompt_builder" for p in result.items), (
            "Built-in generators must not appear in items"
        )
        assert not any(p.id == "few_shot_prompt_builder" for p in result.items), (
            "Built-in generators must not appear in items"
        )

        saved_ids = [pid for pid in ids if pid.startswith("id::")]
        assert len(saved_ids) == 1
        assert saved_ids[0] == f"id::{saved_prompt.id}"

        ft_ids = [pid for pid in ids if pid.startswith("fine_tune_prompt::")]
        assert len(ft_ids) == 1
        assert ft.id in ft_ids[0]

        rc_ids = [pid for pid in ids if pid.startswith("task_run_config::")]
        assert len(rc_ids) == 1
        assert rc_with_prompt.id in rc_ids[0]

        assert result.total == 3
        assert result.showing == "3 of 3"
        assert result.generators_from_task_instruction_count > 0

        for p in result.items:
            assert p.type is not None
            assert len(p.type) > 0

    def test_generators_from_task_instruction_count(self, task, project):
        from kiln_server.prompt_api import prompt_generators

        result = _prompts_block(task, project, [])
        assert result.generators_from_task_instruction_count == len(prompt_generators)

    def test_capped_at_5(self, task, project):
        for i in range(8):
            Prompt(
                parent=task,
                name=f"Prompt {i}",
                prompt=f"Do thing {i}",
                generator_id=None,
            ).save_to_file()

        result = _prompts_block(task, project, [])
        assert result.total == 8
        assert len(result.items) == 5
        assert result.showing == "5 of 8"

    def test_selects_most_recent(self, task, project):
        prompts_created = []
        for i in range(8):
            p = Prompt(
                parent=task,
                name=f"Prompt {i}",
                prompt=f"Do thing {i}",
                generator_id=None,
            )
            p.save_to_file()
            prompts_created.append(p)

        result = _prompts_block(task, project, [])

        all_prompts_sorted = sorted(
            prompts_created, key=lambda p: (p.created_at, str(p.id)), reverse=True
        )
        expected_ids = {f"id::{p.id}" for p in all_prompts_sorted[:5]}
        actual_ids = {p.id for p in result.items}
        assert actual_ids == expected_ids

    def test_empty_pool(self, task, project):
        result = _prompts_block(task, project, [])
        assert result.total == 0
        assert result.items == []
        assert result.showing == "0 of 0"
        assert result.generators_from_task_instruction_count > 0


# --- _run_configs_block tests ---


class TestRunConfigsBlock:
    def _make_rc(self, task, name, starred, created_at=None):
        rc = TaskRunConfig(
            parent=task,
            name=name,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name="openai",
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.default,
            ),
            starred=starred,
        )
        rc.save_to_file()
        if created_at is not None:
            rc.created_at = created_at
        return rc

    def test_all_starred_over_5(self, task):
        rcs = [self._make_rc(task, f"starred_{i}", True) for i in range(8)]
        unstarred = [self._make_rc(task, f"unstarred_{i}", False) for i in range(5)]

        result = _run_configs_block(task, rcs + unstarred)
        assert result.total == 13
        assert len(result.items) == 8
        assert all(item.starred for item in result.items)

    def test_starred_plus_padded(self, task):
        starred = [self._make_rc(task, f"starred_{i}", True) for i in range(2)]
        unstarred = [self._make_rc(task, f"unstarred_{i}", False) for i in range(10)]

        result = _run_configs_block(task, starred + unstarred)
        assert result.total == 12
        assert len(result.items) == 5
        starred_items = [item for item in result.items if item.starred]
        unstarred_items = [item for item in result.items if not item.starred]
        assert len(starred_items) == 2
        assert len(unstarred_items) == 3

    def test_no_starred(self, task):
        unstarred = [self._make_rc(task, f"unstarred_{i}", False) for i in range(3)]

        result = _run_configs_block(task, unstarred)
        assert result.total == 3
        assert len(result.items) == 3
        assert result.showing == "3 of 3"

    def test_starred_under_5_no_unstarred(self, task):
        starred = [self._make_rc(task, f"starred_{i}", True) for i in range(4)]

        result = _run_configs_block(task, starred)
        assert result.total == 4
        assert len(result.items) == 4
        assert result.showing == "4 of 4"

    def test_ordering_within_groups(self, task):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
        dt3 = datetime(2024, 3, 1, tzinfo=timezone.utc)

        s1 = self._make_rc(task, "starred_old", True, dt1)
        s2 = self._make_rc(task, "starred_new", True, dt3)
        u1 = self._make_rc(task, "unstarred_old", False, dt1)
        u2 = self._make_rc(task, "unstarred_new", False, dt2)

        result = _run_configs_block(task, [s1, s2, u1, u2])
        assert result.items[0].name == "starred_new"
        assert result.items[1].name == "starred_old"
        assert result.items[2].name == "unstarred_new"
        assert result.items[3].name == "unstarred_old"

    def test_empty(self, task):
        result = _run_configs_block(task, [])
        assert result.total == 0
        assert result.items == []
        assert result.showing == "0 of 0"
        assert result.default_run_config_id is None

    def test_showing_format(self, task):
        rcs = [self._make_rc(task, f"rc_{i}", False) for i in range(7)]
        result = _run_configs_block(task, rcs)
        assert result.showing == f"{len(result.items)} of {result.total}"


# --- _fine_tunes_block tests ---


class TestFineTunesBlock:
    def test_returns_count(self, task):
        Finetune(
            parent=task,
            name="FT 1",
            provider="openai",
            base_model_id="gpt-4o-mini-2024-07-18",
            fine_tune_model_id="ft:abc",
            dataset_split_id="split1",
            system_message="msg",
            latest_status=FineTuneStatusType.completed,
        ).save_to_file()
        Finetune(
            parent=task,
            name="FT 2",
            provider="openai",
            base_model_id="gpt-4o-mini-2024-07-18",
            fine_tune_model_id=None,
            dataset_split_id="split2",
            system_message="msg",
            latest_status=FineTuneStatusType.running,
        ).save_to_file()

        result = _fine_tunes_block(task)
        assert result.total_count == 2

    def test_empty(self, task):
        result = _fine_tunes_block(task)
        assert result.total_count == 0


# --- _prompt_optimization_jobs_block tests ---


class TestPromptOptimizationJobsBlock:
    def test_returns_count(self, task):
        PromptOptimizationJob(
            parent=task,
            name="Job 1",
            job_id="j1",
            target_run_config_id="rc1",
            latest_status="succeeded",
        ).save_to_file()

        result = _prompt_optimization_jobs_block(task)
        assert result.total_count == 1

    def test_empty(self, task):
        result = _prompt_optimization_jobs_block(task)
        assert result.total_count == 0


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
            assert "created_at" not in data["project"]
            assert data["task"]["id"] == "task1"
            assert data["task"]["name"] == "Test Task"
            assert data["task"]["instruction"] == "Do the thing"
            assert "instruction_truncated" not in data["task"]
            assert "thinking_instruction" not in data["task"]
            assert "thinking_instruction_truncated" not in data["task"]
            assert "created_at" not in data["task"]
            assert data["dataset"]["total_count"] == 0
            assert data["docs"]["doc_count"] == 0
            assert data["search_tools"]["items"] == []
            assert data["search_tools"]["archived_search_tool_count"] == 0
            assert isinstance(data["prompts"], dict)
            assert data["prompts"]["total"] == 0
            assert data["prompts"]["items"] == []
            assert data["prompts"]["generators_from_task_instruction_count"] > 0
            assert data["specs"]["items"] == []
            assert data["specs"]["archived_spec_count"] == 0
            assert data["evals"] == []
            assert data["tool_servers"]["items"] == []
            assert data["tool_servers"]["archived_tool_server_count"] == 0
            assert data["run_configs"]["default_run_config_id"] is None
            assert data["run_configs"]["items"] == []
            assert data["run_configs"]["total"] == 0
            assert data["fine_tunes"] == {"total_count": 0}
            assert data["prompt_optimization_jobs"] == {"total_count": 0}
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

    def test_instruction_truncation_at_70(self, client, project, tmp_path):
        instruction_70 = " ".join(f"w{i}" for i in range(70))
        t = Task(
            id="task70",
            name="Task 70",
            instruction=instruction_70,
            parent=project,
            path=tmp_path / "tasks" / "task70" / "task.kiln",
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
            response = client.get("/api/projects/proj1/tasks/task70/agent_overview")
            data = response.json()
            assert AGENT_TRUNCATION_SENTINEL not in data["task"]["instruction"]
            assert data["task"]["instruction"] == instruction_70

    def test_instruction_truncation_at_71(self, client, project, tmp_path):
        instruction_71 = " ".join(f"w{i}" for i in range(71))
        t = Task(
            id="task71",
            name="Task 71",
            instruction=instruction_71,
            parent=project,
            path=tmp_path / "tasks" / "task71" / "task.kiln",
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
            response = client.get("/api/projects/proj1/tasks/task71/agent_overview")
            data = response.json()
            assert data["task"]["instruction"].endswith(AGENT_TRUNCATION_SENTINEL)
            assert data["task"]["instruction"].count(AGENT_TRUNCATION_SENTINEL) == 1
            words_before_sentinel = (
                data["task"]["instruction"]
                .removesuffix(f" {AGENT_TRUNCATION_SENTINEL}")
                .split()
            )
            assert len(words_before_sentinel) == 70

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
            assert rc_data["skill_ids"] == ["my_skill"]
            assert rc_data["starred"] is True
            assert "created_at" not in rc_data
            assert data["run_configs"]["total"] == 1
            assert data["run_configs"]["showing"] == "1 of 1"

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
            assert "created_at" not in ev
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
