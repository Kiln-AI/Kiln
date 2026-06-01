"""Per-turn synthetic-user driver — the OSS-side replacement for kiln_server's
removed `/respond` route.

Wraps a kiln_ai LiteLLM adapter and exposes a single async `respond()` that:
1. Filters the eval-frame conversation to `visible_message_roles`.
2. Role-swaps user/assistant so the LLM is generating the SU's reply.
3. Calls the adapter with the persona system prompt prepended as
   `prior_trace` and the latest swapped user turn as `input`.

The driver does NOT persist `TaskRun`s — it uses
`adapter.invoke_returning_run_output(...)` which builds an in-memory run
without writing to disk. The eval-dataset chain consists only of *target*
TaskRuns (created elsewhere by `adapter.invoke(...)`). The SU is an
orchestration component, not an eval-dataset row.
"""

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.synthetic_user.models import (
    SyntheticUserDriverConfig,
    SyntheticUserInfo,
)
from kiln_ai.synthetic_user.parser import parse_synthetic_user_info
from kiln_ai.synthetic_user.prompt import render_system_prompt
from kiln_ai.synthetic_user.role_swap import role_swap
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)


class SyntheticUserDriver:
    """Plays one synthetic user across multiple turns.

    Constructed once per case from the case's tagged blob + driver config;
    `respond(conversation)` is called once per turn. The adapter is built
    at construction time and reused across all turns of the case.
    """

    def __init__(
        self,
        synthetic_user_info_blob: str,
        driver_config: SyntheticUserDriverConfig,
    ):
        # Parse the blob once at construction — fail fast on a malformed case.
        self._info: SyntheticUserInfo = parse_synthetic_user_info(
            synthetic_user_info_blob
        )
        self._driver_config = driver_config
        self._system_prompt: str = render_system_prompt(self._info)

        # In-memory Task; nothing is persisted. The persona-playing system
        # prompt rides on `prior_trace[0]` each call, so this `instruction`
        # is effectively unused at runtime — kiln_ai's MultiturnFormatter
        # uses the first system message in `prior_trace` and skips the
        # task's instruction when `prior_trace` is non-empty. The Task
        # model requires a non-empty instruction, hence the placeholder.
        self._task = Task(
            name="synthetic_user_driver",
            description="In-memory SU player. Not persisted.",
            instruction=(
                "Placeholder — the persona-playing system prompt is supplied "
                "via prior_trace on every adapter call."
            ),
        )
        # Same RunConfigProperties shape used elsewhere; `structured_output_mode`
        # is `default` because SU output is free text (no JSON schema).
        self._run_config = KilnAgentRunConfigProperties(
            model_name=driver_config.model_name,
            model_provider_name=driver_config.model_provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            tools_config=ToolsRunConfig(tools=[]),
        )
        self._adapter = adapter_for_task(self._task, self._run_config)

    async def respond(self, conversation: list[ChatCompletionMessageParam]) -> str:
        """Return the SU's next message.

        `conversation` is in the eval frame and must end on an `assistant`
        (target) turn — the SU is responding to that turn. Drive-loop
        termination is the caller's concern; this just produces one reply.
        """
        # 1) Filter to visible roles (drop system/tool if present).
        visible = [
            m
            for m in conversation
            if m["role"] in self._driver_config.visible_message_roles
        ]
        # 2) Invariants this driver enforces (moved from kiln_server's
        #    removed /respond route validator).
        if not visible:
            raise ValueError("No LLM-visible messages in conversation.")
        if visible[-1]["role"] != "assistant":
            raise ValueError(
                "Conversation must end on an assistant (target) turn — the SU "
                "is responding to that turn."
            )

        # 3) Role-swap then assemble prior_trace + input. The last swapped
        #    turn becomes the LLM `input`; everything before it goes into
        #    `prior_trace` with a system message prepended.
        swapped = role_swap(visible)
        last = swapped[-1]
        user_input = last["content"]
        if not isinstance(user_input, str):
            raise RuntimeError(
                "synthetic user input must be a plain string after role_swap"
            )

        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": self._system_prompt,
        }
        prior_trace: list[ChatCompletionMessageParam] = [system_msg, *swapped[:-1]]

        # 4) Adapter call. invoke_returning_run_output returns
        #    (TaskRun, RunOutput) without writing the TaskRun to disk.
        _task_run, run_output = await self._adapter.invoke_returning_run_output(
            user_input, prior_trace=prior_trace
        )
        raw = run_output.output
        if not isinstance(raw, str):
            raise RuntimeError("synthetic user returned non-string output")

        return raw
