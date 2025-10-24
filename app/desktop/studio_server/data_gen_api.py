from typing import Literal

from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.data_gen.data_gen_task import (
    DataGenCategoriesTask,
    DataGenCategoriesTaskInput,
    DataGenSampleTask,
    DataGenSampleTaskInput,
    wrap_task_with_guidance,
)
from kiln_ai.adapters.data_gen.qna_gen_task import DataGenQnaTask, DataGenQnaTaskInput
from kiln_ai.datamodel import DataSource, DataSourceType, TaskRun
from kiln_ai.datamodel.extraction import Document
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionMessageParam,
)
from kiln_ai.utils.project_utils import project_from_id
from kiln_server.task_api import task_from_id
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel, Field


class DataGenCategoriesApiInput(BaseModel):
    node_path: list[str] = Field(
        description="Path to the node in the category tree", default=[]
    )
    num_subtopics: int = Field(description="Number of subtopics to generate", default=6)
    gen_type: Literal["eval", "training"] = Field(
        description="The type of task to generate topics for"
    )
    guidance: str | None = Field(
        description="Optional human guidance for generation",
        default=None,
    )
    existing_topics: list[str] | None = Field(
        description="Optional list of existing topics to avoid",
        default=None,
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run config properties to use for topic generation"
    )


class DataGenSampleApiInput(BaseModel):
    topic: list[str] = Field(description="Topic path for sample generation", default=[])
    num_samples: int = Field(description="Number of samples to generate", default=8)
    gen_type: Literal["training", "eval"] = Field(
        description="The type of task to generate topics for"
    )
    guidance: str | None = Field(
        description="Optional custom guidance for generation",
        default=None,
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run config properties to use for input generation"
    )


class DataGenSaveSamplesApiInput(BaseModel):
    input: str | dict = Field(description="Input for this sample")
    topic_path: list[str] = Field(
        description="The path to the topic for this sample. Empty is the root topic."
    )
    input_model_name: str = Field(
        description="The name of the model used to generate the input"
    )
    input_provider: str = Field(
        description="The provider of the model used to generate the input"
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run config properties to use for output generation"
    )
    guidance: str | None = Field(
        description="Optional custom guidance for generation",
        default=None,
    )
    tags: list[str] | None = Field(
        description="Tags to add to the sample",
        default=None,
    )


class DataGenQnaApiInput(BaseModel):
    document_id: str = Field(description="Document ID for Q&A generation")
    part_text: list[str] = Field(description="Part text for Q&A generation", default=[])
    num_samples: int = Field(
        description="Number of Q&A pairs to generate for this part", default=10
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run config properties to use for the output"
    )
    guidance: str | None = Field(
        description="Optional custom guidance for generation",
        default=None,
    )
    tags: list[str] | None = Field(
        description="Tags to add to the sample",
        default=None,
    )


class SaveQnaPairInput(BaseModel):
    question: str = Field(description="The synthetic user question")
    answer: str = Field(
        description="The synthetic assistant answer/response for the given user question"
    )
    model_name: str = Field(description="Model name used to generate the Q&A pair")
    model_provider: str = Field(
        description="Model provider used to generate the Q&A pair"
    )
    tags: list[str] | None = Field(default=None, description="Optional tags")


def connect_data_gen_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_categories")
    async def generate_categories(
        project_id: str, task_id: str, input: DataGenCategoriesApiInput
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)

        categories_task = DataGenCategoriesTask(
            gen_type=input.gen_type, guidance=input.guidance
        )

        task_input = DataGenCategoriesTaskInput.from_task(
            task=task,
            node_path=input.node_path,
            num_subtopics=input.num_subtopics,
            existing_topics=input.existing_topics,
        )

        run_config_properties = input.run_config_properties.model_copy()
        # Override prompt id to simple just in case we change the default in the UI in the future.
        run_config_properties.prompt_id = PromptGenerators.SIMPLE
        adapter = adapter_for_task(
            categories_task,
            run_config_properties=run_config_properties,
        )

        categories_run = await adapter.invoke(task_input.model_dump())
        return categories_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_inputs")
    async def generate_samples(
        project_id: str, task_id: str, input: DataGenSampleApiInput
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)
        sample_task = DataGenSampleTask(
            target_task=task,
            gen_type=input.gen_type,
            guidance=input.guidance,
        )

        task_input = DataGenSampleTaskInput.from_task(
            task=task,
            topic=input.topic,
            num_samples=input.num_samples,
        )

        run_config_properties = input.run_config_properties.model_copy()
        # Override prompt id to simple just in case we change the default in the UI in the future.
        run_config_properties.prompt_id = PromptGenerators.SIMPLE
        adapter = adapter_for_task(
            sample_task,
            run_config_properties=run_config_properties,
        )

        samples_run = await adapter.invoke(task_input.model_dump())
        return samples_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/save_sample")
    async def save_sample(
        project_id: str,
        task_id: str,
        task_run: TaskRun,
    ) -> TaskRun:
        """
        Save a sample generated by the generate_sample endpoint.
        """
        task = task_from_id(project_id, task_id)
        # Set parent to task to ensure the correct path is used
        task_run.parent = task
        task_run.save_to_file()
        return task_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_sample")
    async def generate_sample(
        project_id: str,
        task_id: str,
        sample: DataGenSaveSamplesApiInput,
        session_id: str | None = None,
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)

        guidance = sample.guidance or ""
        if len(sample.topic_path) > 0:
            guidance += f"""
## Topic Path
The topic path for this sample is:
[{", ".join(f'"{topic}"' for topic in sample.topic_path)}]
"""

        if guidance.strip() != "":
            task.instruction = wrap_task_with_guidance(task.instruction, guidance)

        adapter = adapter_for_task(
            task,
            run_config_properties=sample.run_config_properties,
        )

        properties: dict[str, str | int | float] = {
            "model_name": sample.input_model_name,
            "model_provider": sample.input_provider,
            "adapter_name": "kiln_data_gen",
        }
        topic_path = topic_path_to_string(sample.topic_path)
        if topic_path:
            properties["topic_path"] = topic_path

        run = await adapter.invoke(
            input=sample.input,
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties=properties,
            ),
        )

        tags = ["synthetic"]
        if session_id:
            tags.append(f"synthetic_session_{session_id}")

        if sample.tags:
            tags.extend(sample.tags)
        run.tags = tags

        return run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_qna")
    async def generate_qna_pairs(
        project_id: str,
        task_id: str,
        input: DataGenQnaApiInput,
        session_id: str | None = None,
    ) -> TaskRun:
        project = project_from_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        task = task_from_id(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        doc = Document.from_id_and_parent_path(input.document_id, project.path)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        qna_task = DataGenQnaTask(target_task=task, guidance=input.guidance)
        task_input = DataGenQnaTaskInput(
            kiln_data_gen_document_name=doc.friendly_name,
            kiln_data_gen_part_text=input.part_text,
            kiln_data_gen_num_samples=input.num_samples,
        )
        adapter = adapter_for_task(
            qna_task,
            run_config_properties=input.run_config_properties,
        )
        qna_run = await adapter.invoke(task_input.model_dump())

        tags = ["synthetic", "qna"]
        if session_id:
            tags.append(f"synthetic_qna_session_{session_id}")

        if input.tags:
            tags.extend(input.tags)
        qna_run.tags = tags

        return qna_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/save_qna_pair")
    async def save_qna_pair(
        project_id: str,
        task_id: str,
        input: SaveQnaPairInput,
        session_id: str,
    ) -> TaskRun:
        """
        Save a single QnA pair as a TaskRun. We store the task's system prompt
        as the system message, the question as the user message, and the answer
        as the assistant message in the trace. The output is the answer.
        """
        task = task_from_id(project_id, task_id)

        # Build trace in OpenAI message format using the task instruction as system prompt
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": task.instruction,
        }
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": input.question,
        }
        assistant_msg: ChatCompletionAssistantMessageParamWrapper = {
            "role": "assistant",
            "content": input.answer,
        }
        trace: list[ChatCompletionMessageParam] = [
            system_msg,
            user_msg,
            assistant_msg,
        ]

        task_run = TaskRun(
            input=input.question,
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties=(
                    {
                        "model_name": input.model_name,
                        "model_provider": input.model_provider,
                        "adapter_name": "kiln_qna_manual_save",
                    }
                ),
            ),
            output=TaskOutput(
                output=input.answer,
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties=(
                        {
                            "model_name": input.model_name,
                            "model_provider": input.model_provider,
                            "adapter_name": "kiln_qna_manual_save",
                        }
                    ),
                ),
            ),
            tags=[
                "synthetic",
                "qna",
                f"synthetic_qna_session_{session_id}",
                *(input.tags or []),
            ],
            trace=trace,
        )

        task_run.parent = task
        task_run.save_to_file()
        return task_run


def topic_path_to_string(topic_path: list[str]) -> str | None:
    if topic_path and len(topic_path) > 0:
        return ">>>>>".join(topic_path)
    return None


def topic_path_from_string(topic_path: str | None) -> list[str]:
    if topic_path:
        return topic_path.split(">>>>>")
    return []
