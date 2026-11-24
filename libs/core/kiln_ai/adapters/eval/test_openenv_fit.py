import pytest

from kiln_ai.adapters.eval.openenv_fit import (
    SkippedRunConfig,
    openenv_misfit,
    openenv_misfit_message,
    openenv_server_label,
    split_run_configs_by_openenv_fit,
)
from kiln_ai.datamodel.datamodel_enums import (
    StructuredOutputMode,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.eval import Eval, EvalInputSplit, EvalOutputScore
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    ToolsRunConfig,
)
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import build_openenv_tool_id

SERVER_ID = "server_1"
OWN_TOOL = build_openenv_tool_id(SERVER_ID, "append_note")
OTHER_TOOL = build_openenv_tool_id("server_2", "append_note")
PROJECT_TOOL = "kiln_tool::add_numbers"


def _run_config(tool_ids: list[str] | None, name: str = "rc") -> TaskRunConfig:
    return TaskRunConfig(
        id=f"id_{name}",
        name=name,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(tools=tool_ids)
            if tool_ids is not None
            else None,
        ),
    )


def _eval(openenv_server_id: str | None) -> Eval:
    return Eval(
        name="eval",
        splits={"test": EvalInputSplit(filter_id="all")},
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="is it accurate",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        openenv_server_id=openenv_server_id,
    )


@pytest.mark.parametrize(
    "tool_ids, expected",
    [
        # No OpenEnv tools: the cases run against the run config's own tools.
        (None, None),
        ([], None),
        ([PROJECT_TOOL], None),
        ([OWN_TOOL], None),
        ([OWN_TOOL, PROJECT_TOOL], None),
        ([OTHER_TOOL], "other_openenv_server"),
        ([OWN_TOOL, OTHER_TOOL], "other_openenv_server"),
    ],
)
def test_openenv_misfit_for_a_grounded_eval(tool_ids, expected):
    assert openenv_misfit(SERVER_ID, _run_config(tool_ids)) == expected


@pytest.mark.parametrize("tool_ids", [None, [PROJECT_TOOL], [OTHER_TOOL]])
def test_every_run_config_fits_an_ungrounded_eval(tool_ids):
    assert openenv_misfit(None, _run_config(tool_ids)) is None


def test_an_mcp_run_config_fits_with_no_openenv_tools():
    run_config = TaskRunConfig(
        name="mcp rc",
        run_config_properties=McpRunConfigProperties(
            tool_reference=MCPToolReference(tool_id="mcp::local::s::t")
        ),
    )
    assert openenv_misfit(SERVER_ID, run_config) is None


def test_openenv_misfit_message():
    assert openenv_misfit_message("other_openenv_server", "Foreign", "World") == (
        "This eval's cases run in OpenEnv server 'World'; "
        "run config 'Foreign' uses tools from another OpenEnv server."
    )


def test_openenv_server_label(tmp_path):
    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()
    server = OpenEnvServer(name="World", parent=project, url="http://127.0.0.1:1")
    server.save_to_file()

    assert openenv_server_label(server.id, project) == "World"
    assert openenv_server_label("deleted", project) == "deleted"
    assert openenv_server_label(server.id, None) == server.id


def test_split_run_configs_keeps_order_and_skips_only_other_servers():
    fits_a = _run_config([OWN_TOOL], name="a")
    plain = _run_config([PROJECT_TOOL], name="plain")
    fits_b = _run_config([OWN_TOOL, PROJECT_TOOL], name="b")
    foreign = _run_config([OTHER_TOOL], name="foreign")

    fitting, skipped = split_run_configs_by_openenv_fit(
        _eval(SERVER_ID), [fits_a, plain, fits_b, foreign], "World"
    )

    # A run config with no OpenEnv tools fits: it runs the cases on its own tools.
    assert fitting == [fits_a, plain, fits_b]
    assert skipped == [
        SkippedRunConfig(
            id="id_foreign",
            name="foreign",
            reason=openenv_misfit_message("other_openenv_server", "foreign", "World"),
        ),
    ]


def test_split_run_configs_keeps_every_run_config_of_an_ungrounded_eval():
    run_configs = [_run_config([PROJECT_TOOL], name="plain"), _run_config(None)]
    assert split_run_configs_by_openenv_fit(_eval(None), run_configs, "unused") == (
        run_configs,
        [],
    )
