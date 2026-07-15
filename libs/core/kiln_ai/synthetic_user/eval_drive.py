"""Eval-time re-drive of one multi-turn synthetic case.

The eval runner calls this to regenerate a conversation per run config: the
agent under test comes from the run config being evaluated; the synthetic
user (customer) comes from the eval's drive config, held constant so a
comparison varies only the agent.

Driven conversations persist as real TaskRuns: every turn saves via the
adapter with parent_task_run chaining, exactly like an SU batch drive, so
the conversation lands in the dataset — visible in the runs UI, taggable,
ratable. The eval runner tags the leaf `sei_<eval_input_id>`, letting any
eval scoring the same (eval_input, run_config) pair reuse the stored
conversation instead of re-driving it (KIL-761).
"""

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, SkillsDict
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.drive_loop import drive_case
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.models import (
    SyntheticUserDriverConfig,
    SyntheticUserInfo,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

# Identifies this code path in `input_source.properties.adapter_name` so
# anything inspecting a driven run can see who authored the user side.
_EVAL_DRIVER_ADAPTER_NAME = "kiln_synthetic_user_eval_driver"


async def drive_case_for_eval(
    *,
    seed_prompt: str,
    synthetic_user_info: SyntheticUserInfo,
    target_task: Task,
    target_run_config: KilnAgentRunConfigProperties,
    su_driver_config: SyntheticUserDriverConfig,
    turns: int,
    skills: SkillsDict,
    task_run_config_id: str | None = None,
    default_tags: list[str] | None = None,
) -> TaskRun:
    """Drive one case and return the persisted leaf TaskRun.

    The leaf's `.trace` holds the full cumulative conversation and its
    `output.source.run_config_id` carries `task_run_config_id` — the key the
    eval runner's reuse scan matches on. `default_tags` are stamped on every
    turn as it saves, so even a chain orphaned by a mid-drive failure stays
    discoverable. `skills` must be preloaded by the caller — the adapter
    raises on skill tools with no injected dict.
    """
    su_driver = SyntheticUserDriver(synthetic_user_info, su_driver_config)
    adapter = adapter_for_task(
        target_task,
        target_run_config,
        base_adapter_config=AdapterConfig(
            skills=skills,
            task_run_config_id=task_run_config_id,
            default_tags=default_tags,
        ),
    )
    input_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": su_driver_config.model_name,
            "model_provider": su_driver_config.model_provider_name.value,
            "adapter_name": _EVAL_DRIVER_ADAPTER_NAME,
        },
    )

    async def _invoker(
        *,
        input: str,
        prior_trace: list[ChatCompletionMessageParam] | None,
        parent_task_run: TaskRun | None,
    ) -> TaskRun:
        return await adapter.invoke(
            input=input,
            input_source=input_source,
            prior_trace=prior_trace,
            parent_task_run=parent_task_run,
        )

    result = await drive_case(
        seed_prompt=seed_prompt,
        target_invoker=_invoker,
        su_driver=su_driver,
        turns=turns,
    )
    return result.chain[-1]
