from typing import Dict

import langchain
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

import kiln_ai.datamodel as datamodel

from .base_adapter import AdapterInfo, BaseAdapter, BasePromptBuilder, RunOutput
from .ml_model_list import langchain_model_from

LangChainModelType = BaseChatModel | Runnable[LanguageModelInput, Dict | BaseModel]


langchain.debug = True

from langchain.globals import set_verbose

set_verbose(True)

from langchain.globals import set_debug

set_debug(True)

import os

os.environ["GROQ_LOG"] = "debug"


class DetailedDebugHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        print("\n\n=== LLM Start ===")
        print("=== Raw Messages ===")
        for msg in kwargs.get("messages", []):
            print(f"\nMessage Type: {msg.__class__.__name__}")
            print(f"Content: {msg.content}")
            # Print additional message attributes (like function call schemas)
            for key, value in msg.additional_kwargs.items():
                print(f"{key}: {value}")

        print("\n=== Prompts ===")
        print(f"Prompts: {prompts}")
        print(f"Serialized: {serialized}")

    def on_llm_end(self, response, **kwargs):
        print("\n=== LLM End ===")
        print(f"Response: {response}")


class LangchainAdapter(BaseAdapter):
    _model: LangChainModelType | None = None

    def __init__(
        self,
        kiln_task: datamodel.Task,
        custom_model: BaseChatModel | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        prompt_builder: BasePromptBuilder | None = None,
    ):
        super().__init__(kiln_task, prompt_builder=prompt_builder)
        if custom_model is not None:
            self._model = custom_model

            # Attempt to infer model provider and name from custom model
            self.model_provider = "custom.langchain:" + custom_model.__class__.__name__
            self.model_name = "custom.langchain:unknown_model"
            if hasattr(custom_model, "model_name") and isinstance(
                getattr(custom_model, "model_name"), str
            ):
                self.model_name = "custom.langchain:" + getattr(
                    custom_model, "model_name"
                )
            if hasattr(custom_model, "model") and isinstance(
                getattr(custom_model, "model"), str
            ):
                self.model_name = "custom.langchain:" + getattr(custom_model, "model")
        elif model_name is not None:
            self.model_name = model_name
            self.model_provider = provider or "custom.langchain.default_provider"
        else:
            raise ValueError(
                "model_name and provider must be provided if custom_model is not provided"
            )

    def adapter_specific_instructions(self) -> str | None:
        if self.has_structured_output():
            return "Always respond with a tool call. Never respond with a human readable message."
        return None

    async def model(self) -> LangChainModelType:
        # cached model
        if self._model:
            return self._model

        self._model = await langchain_model_from(self.model_name, self.model_provider)

        if self.has_structured_output():
            if not hasattr(self._model, "with_structured_output") or not callable(
                getattr(self._model, "with_structured_output")
            ):
                raise ValueError(
                    f"model {self._model} does not support structured output, cannot use output_json_schema"
                )
            # Langchain expects title/description to be at top level, on top of json schema
            output_schema = self.kiln_task.output_schema()
            if output_schema is None:
                raise ValueError(
                    f"output_json_schema is not valid json: {self.kiln_task.output_json_schema}"
                )
            output_schema["title"] = "task_response"
            output_schema["description"] = "A response from the task"
            # TODO: not universal for all BaseModels models
            self._model = self._model.with_structured_output(
                output_schema, include_raw=True, method="json_mode"
            )
        return self._model

    async def _run(self, input: Dict | str) -> RunOutput:
        model = await self.model()
        chain = model
        intermediate_outputs = {}

        prompt = self.build_prompt()
        user_msg = self.prompt_builder.build_user_message(input)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=user_msg),
        ]

        # COT with structured output
        cot_prompt = self.prompt_builder.chain_of_thought_prompt()
        if cot_prompt and self.has_structured_output():
            # Base model (without structured output) used for COT message
            base_model = await langchain_model_from(
                self.model_name, self.model_provider
            )
            messages.append(
                SystemMessage(content=cot_prompt),
            )

            cot_messages = [*messages]
            cot_response = await base_model.ainvoke(cot_messages)
            intermediate_outputs["chain_of_thought"] = cot_response.content
            messages.append(AIMessage(content=cot_response.content))
            messages.append(
                SystemMessage(content="Considering the above, return a final result.")
            )
        elif cot_prompt:
            messages.append(SystemMessage(content=cot_prompt))

        # Add debug logging to see the final chain configuration
        if hasattr(chain, "prompt"):
            print("Chain Prompt Template:", chain.prompt)

        # Add debug logging right before invocation
        print("Final Messages being sent to LLM:", messages)

        # Add the callback handler
        callback_handler = DetailedDebugHandler()

        # Handle both traditional LangChain models and Runnables
        if isinstance(chain, BaseChatModel):
            chain.callbacks = [callback_handler]
            response = await chain.ainvoke(messages)
        else:
            # For Runnables, pass callbacks through invoke
            response = await chain.ainvoke(messages, callbacks=[callback_handler])

        if self.has_structured_output():
            if (
                not isinstance(response, dict)
                or "parsed" not in response
                or not isinstance(response["parsed"], dict)
            ):
                raise RuntimeError(f"structured response not returned: {response}")
            structured_response = response["parsed"]
            return RunOutput(
                output=self._munge_response(structured_response),
                intermediate_outputs=intermediate_outputs,
            )
        else:
            if not isinstance(response, BaseMessage):
                raise RuntimeError(f"response is not a BaseMessage: {response}")
            text_content = response.content
            if not isinstance(text_content, str):
                raise RuntimeError(f"response is not a string: {text_content}")
            return RunOutput(
                output=text_content,
                intermediate_outputs=intermediate_outputs,
            )

    def adapter_info(self) -> AdapterInfo:
        return AdapterInfo(
            model_name=self.model_name,
            model_provider=self.model_provider,
            adapter_name="kiln_langchain_adapter",
            prompt_builder_name=self.prompt_builder.__class__.prompt_builder_name(),
        )

    def _munge_response(self, response: Dict) -> Dict:
        # Mistral Large tool calling format is a bit different. Convert to standard format.
        if (
            "name" in response
            and response["name"] == "task_response"
            and "arguments" in response
        ):
            return response["arguments"]
        return response
