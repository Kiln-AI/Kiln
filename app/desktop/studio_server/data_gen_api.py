from typing import Literal

from fastapi import FastAPI
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.data_gen.data_gen_task import (
    DataGenCategoriesTask,
    DataGenCategoriesTaskInput,
    DataGenSampleTask,
    DataGenSampleTaskInput,
    wrap_task_with_guidance,
)
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.datamodel import DataSource, DataSourceType, PromptId, TaskRun
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_server.run_api import model_provider_from_string
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, ConfigDict, Field


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
    model_name: str = Field(description="The name of the model to use")
    provider: str = Field(description="The provider of the model to use")

    # Allows use of the model_name field (usually pydantic will reserve model_*)
    model_config = ConfigDict(protected_namespaces=())


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
    model_name: str = Field(description="The name of the model to use")
    provider: str = Field(description="The provider of the model to use")

    # Allows use of the model_name field (usually pydantic will reserve model_*)
    model_config = ConfigDict(protected_namespaces=())


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
    output_model_name: str = Field(description="The name of the model to use")
    output_provider: str = Field(description="The provider of the model to use")
    prompt_method: PromptId = Field(
        description="The prompt method used to generate the output"
    )
    guidance: str | None = Field(
        description="Optional custom guidance for generation",
        default=None,
    )
    tags: list[str] | None = Field(
        description="Tags to add to the sample",
        default=None,
    )


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

        adapter = adapter_for_task(
            categories_task,
            run_config_properties=RunConfigProperties(
                model_name=input.model_name,
                model_provider_name=model_provider_from_string(input.provider),
                prompt_id=PromptGenerators.SIMPLE,
                # We don't expose setting this manually in the UI, so pull a recommended mode from ml_model_list
                structured_output_mode=default_structured_output_mode_for_model_provider(
                    input.model_name, model_provider_from_string(input.provider)
                ),
            ),
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
            num_samples=input.num_samples,
        )

        task_input = DataGenSampleTaskInput.from_task(
            task=task,
            topic=input.topic,
            num_samples=input.num_samples,
        )

        adapter = adapter_for_task(
            sample_task,
            run_config_properties=RunConfigProperties(
                model_name=input.model_name,
                model_provider_name=model_provider_from_string(input.provider),
                prompt_id=PromptGenerators.SIMPLE,
                # We don't expose setting this manually in the UI, so pull a recommended mode from ml_model_list
                structured_output_mode=default_structured_output_mode_for_model_provider(
                    input.model_name, model_provider_from_string(input.provider)
                ),
            ),
        )

        samples_run = await adapter.invoke(task_input.model_dump())
        return samples_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/save_sample")
    async def save_sample(
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
            run_config_properties=RunConfigProperties(
                model_name=sample.output_model_name,
                model_provider_name=model_provider_from_string(sample.output_provider),
                prompt_id=sample.prompt_method,
                # We don't expose setting this manually in the UI, so pull a recommended mode from ml_model_list
                structured_output_mode=default_structured_output_mode_for_model_provider(
                    sample.output_model_name,
                    model_provider_from_string(sample.output_provider),
                ),
            ),
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

        run.save_to_file()
        return run


def topic_path_to_string(topic_path: list[str]) -> str | None:
    if topic_path and len(topic_path) > 0:
        return ">>>>>".join(topic_path)
    return None


def topic_path_from_string(topic_path: str | None) -> list[str]:
    if topic_path:
        return topic_path.split(">>>>>")
    return []
