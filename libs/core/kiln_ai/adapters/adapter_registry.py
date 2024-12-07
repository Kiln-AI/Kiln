from kiln_ai import datamodel
from kiln_ai.adapters.base_adapter import BaseAdapter
from kiln_ai.adapters.langchain_adapters import LangchainAdapter
from kiln_ai.adapters.prompt_builders import BasePromptBuilder


def adapter_for_task(
    kiln_task: datamodel.Task,
    model_name: str | None = None,
    provider: str | None = None,
    prompt_builder: BasePromptBuilder | None = None,
) -> BaseAdapter:
    # We use langchain for everything right now, but can add any others here
    return LangchainAdapter(
        kiln_task,
        model_name=model_name,
        provider=provider,
        prompt_builder=prompt_builder,
    )
