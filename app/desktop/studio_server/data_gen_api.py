from fastapi import FastAPI
from kiln_ai.adapters.data_gen.data_gen_task import (
    DataGenCategoriesTask,
    DataGenCategoriesTaskInput,
    DataGenSampleTask,
    DataGenSampleTaskInput,
)
from kiln_ai.adapters.langchain_adapters import LangChainPromptAdapter
from kiln_ai.adapters.prompt_builders import prompt_builder_from_ui_name
from kiln_ai.datamodel import DataSource, DataSourceType, TaskRun
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, ConfigDict, Field


class DataGenCategoriesApiInput(BaseModel):
    node_path: list[str] = Field(
        description="Path to the node in the category tree", default=[]
    )
    num_subtopics: int = Field(description="Number of subtopics to generate", default=6)
    human_guidance: str | None = Field(
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
    human_guidance: str | None = Field(
        description="Optional human guidance for generation",
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
    prompt_method: str = Field(
        description="The prompt method used to generate the output"
    )


def connect_data_gen_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_categories")
    async def generate_categories(
        project_id: str, task_id: str, input: DataGenCategoriesApiInput
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)
        categories_task = DataGenCategoriesTask()

        task_input = DataGenCategoriesTaskInput.from_task(
            task=task,
            node_path=input.node_path,
            num_subtopics=input.num_subtopics,
            human_guidance=input.human_guidance,
            existing_topics=input.existing_topics,
        )

        adapter = LangChainPromptAdapter(
            categories_task,
            model_name=input.model_name,
            provider=input.provider,
        )

        categories_run = await adapter.invoke(task_input.model_dump())
        return categories_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/generate_samples")
    async def generate_samples(
        project_id: str, task_id: str, input: DataGenSampleApiInput
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)
        sample_task = DataGenSampleTask(target_task=task, num_samples=input.num_samples)

        task_input = DataGenSampleTaskInput.from_task(
            task=task,
            topic=input.topic,
            num_samples=input.num_samples,
            human_guidance=input.human_guidance,
        )

        adapter = LangChainPromptAdapter(
            sample_task,
            model_name=input.model_name,
            provider=input.provider,
        )

        samples_run = await adapter.invoke(task_input.model_dump())
        return samples_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/save_sample")
    async def save_sample(
        project_id: str,
        task_id: str,
        sample: DataGenSaveSamplesApiInput,
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)

        prompt_builder = prompt_builder_from_ui_name(sample.prompt_method)(task)

        adapter = LangChainPromptAdapter(
            task,
            model_name=sample.output_model_name,
            provider=sample.output_provider,
            prompt_builder=prompt_builder,
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
