import re
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from kiln_ai.adapters.adapter_registry import adapter_for_task, load_skills_for_task
from kiln_ai.adapters.data_gen.data_gen_task import (
    DataGenCategoriesTask,
    DataGenCategoriesTaskInput,
    DataGenSampleTask,
    DataGenSampleTaskInput,
    wrap_task_with_guidance,
)
from kiln_ai.adapters.data_gen.qna_gen_task import DataGenQnaTask, DataGenQnaTaskInput
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel import DataSource, DataSourceType, TaskRun, generate_model_id
from kiln_ai.datamodel.data_guide import DataGuide
from kiln_ai.datamodel.extraction import Document
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import RunConfigProperties, Task
from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionMessageParam,
)
from kiln_server.project_api import project_from_id
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
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
    data_guide: str | None = Field(
        description="Optional per-run data guide override. Sent in addition to any human guidance.",
        default=None,
    )
    existing_topics: list[str] | None = Field(
        description="Optional list of existing topics to avoid",
        default=None,
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The run config properties to use for topic generation"
    )


class DataGenSampleApiInput(BaseModel):
    topic: list[str] = Field(description="Topic path for sample generation", default=[])
    num_samples: int = Field(description="Number of samples to generate", default=8)
    gen_type: Literal["training", "eval"] = Field(
        description="The type of data generation: eval or training."
    )
    guidance: str | None = Field(
        description="Optional custom guidance for generation",
        default=None,
    )
    data_guide: str | None = Field(
        description="Optional per-run data guide override. Replaces the task's persisted data guide for this run.",
        default=None,
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The run config properties to use for input generation"
    )


class SaveTaskDataGuideInput(BaseModel):
    guide: str = Field(description="The data guide prompt string to persist")


class GuidePreviewSample(BaseModel):
    input: str = Field(description="Generated sample input")
    output: str = Field(description="Generated sample output")


class RatedGuidePreviewSample(BaseModel):
    input: str = Field(description="Generated sample input")
    output: str = Field(description="Generated sample output")
    looks_good: bool = Field(
        description="User rating: true if the sample looks realistic, false if it needs work"
    )


class GuidePreviewInput(BaseModel):
    guide: str = Field(description="The data guide prompt string")
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The model config to use for preview input generation"
    )
    output_run_config_properties: KilnAgentRunConfigProperties | None = Field(
        description=(
            "Optional model config to use for preview output generation. "
            "Defaults to the input run config when not provided."
        ),
        default=None,
    )
    num_samples: int = Field(
        description="Number of preview samples to generate", default=5
    )


class GuideRefineInput(BaseModel):
    current_guide: str = Field(description="The current data guide prompt string")
    feedback: str = Field(
        default="",
        description=(
            "User feedback on what's wrong with preview samples. Leave empty "
            "for bootstrap synthesis (initial setup with no rated samples yet)."
        ),
    )
    preview_samples: list[RatedGuidePreviewSample] = Field(
        default_factory=list,
        description=(
            "The previewed samples the user is giving feedback on, each rated "
            "as realistic (true) or needs work (false). Leave empty for "
            "bootstrap synthesis (initial setup with no preview round yet)."
        ),
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The model config to use for refinement"
    )


class GuideRefineOutput(BaseModel):
    """Structured output schema for the LLM refinement task.

    The LLM only owns the rules half of the guide. Reference examples are
    user-authored ground truth and are preserved by the endpoint; the LLM
    receives them for context but never re-emits them.
    """

    rules: str = Field(
        description=(
            "Markdown body of the `# Guidelines & Rules` section — a sequence "
            "of `## <title>` rule blocks with descriptions. Do NOT include the "
            "`# Guidelines & Rules` heading itself, do NOT include any "
            "`# Reference Examples` content, and do NOT include any other "
            "top-level headings."
        ),
    )


class GuideRefineResponse(BaseModel):
    refined_guide: str = Field(description="The refined data guide prompt string")


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
    data_guide: str | None = Field(
        description="Optional per-run data guide override. Replaces the task's persisted data guide for this run.",
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
    run_config_properties: KilnAgentRunConfigProperties = Field(
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
    query: str = Field(description="The synthetic user query")
    answer: str = Field(
        description="The synthetic assistant answer/response for the given user query"
    )
    model_name: str = Field(description="Model name used to generate the Q&A pair")
    model_provider: str = Field(
        description="Model provider used to generate the Q&A pair"
    )
    tags: list[str] | None = Field(default=None, description="Optional tags")


def connect_data_gen_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/generate_categories",
        summary="Generate Categories",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Generate categories using LLM?"),
    )
    async def generate_categories(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: DataGenCategoriesApiInput,
    ) -> TaskRun:
        project = project_from_id(project_id)
        task = task_from_id(project_id, task_id)

        combined_guidance = _combine_guidance(
            task, input.guidance, "topics", input.data_guide
        )
        categories_task = DataGenCategoriesTask(
            gen_type=input.gen_type,
            parent_project=project,
            guidance=combined_guidance,
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
        skills = load_skills_for_task(categories_task, run_config_properties)
        adapter = adapter_for_task(
            categories_task,
            run_config_properties=run_config_properties,
            base_adapter_config=AdapterConfig(skills=skills),
        )

        categories_run = await adapter.invoke(task_input.model_dump())
        return categories_run

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/generate_inputs",
        summary="Generate Inputs",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Generate inputs using LLM?"),
    )
    async def generate_samples(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: DataGenSampleApiInput,
    ) -> TaskRun:
        project = project_from_id(project_id)
        task = task_from_id(project_id, task_id)

        combined_guidance = _combine_guidance(
            task, input.guidance, "inputs", input.data_guide
        )
        sample_task = DataGenSampleTask(
            target_task=task,
            gen_type=input.gen_type,
            parent_project=project,
            guidance=combined_guidance,
        )

        task_input = DataGenSampleTaskInput.from_task(
            task=task,
            topic=input.topic,
            num_samples=input.num_samples,
        )

        run_config_properties = input.run_config_properties.model_copy()
        # Override prompt id to simple just in case we change the default in the UI in the future.
        run_config_properties.prompt_id = PromptGenerators.SIMPLE
        skills = load_skills_for_task(sample_task, run_config_properties)
        adapter = adapter_for_task(
            sample_task,
            run_config_properties=run_config_properties,
            base_adapter_config=AdapterConfig(skills=skills),
        )

        samples_run = await adapter.invoke(task_input.model_dump())
        return samples_run

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/save_sample",
        summary="Save Sample",
        tags=["Synthetic Data"],
        openapi_extra=ALLOW_AGENT,
    )
    async def save_sample(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
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

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/generate_sample",
        summary="Generate Sample",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Generate a sample using LLM?"),
    )
    async def generate_sample(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        sample: DataGenSaveSamplesApiInput,
        session_id: Annotated[
            str | None,
            Query(description="Optional session ID to group generated samples."),
        ] = None,
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)

        combined = (
            _combine_guidance(task, sample.guidance, "outputs", sample.data_guide) or ""
        )
        guidance = combined
        if len(sample.topic_path) > 0:
            guidance += f"""
## Topic Path
The topic path for this sample is:
[{", ".join(f'"{topic}"' for topic in sample.topic_path)}]
"""

        if guidance.strip() != "":
            task.instruction = wrap_task_with_guidance(task.instruction, guidance)

        skills = load_skills_for_task(task, sample.run_config_properties)
        adapter = adapter_for_task(
            task,
            run_config_properties=sample.run_config_properties,
            base_adapter_config=AdapterConfig(allow_saving=False, skills=skills),
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

        # we do not save the TaskRun to disk, so the ID is null, but we need
        # an ID in the frontend to identify the sample before / after saving it
        run.id = generate_model_id()

        return run

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/generate_qna",
        summary="Generate Q&A Pairs",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Generate Q&A pairs using LLM?"),
    )
    async def generate_qna_pairs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: DataGenQnaApiInput,
        session_id: Annotated[
            str | None,
            Query(description="Optional session ID to group generated Q&A pairs."),
        ] = None,
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
        skills = load_skills_for_task(qna_task, input.run_config_properties)
        adapter = adapter_for_task(
            qna_task,
            run_config_properties=input.run_config_properties,
            base_adapter_config=AdapterConfig(skills=skills),
        )
        qna_run = await adapter.invoke(task_input.model_dump())

        tags = ["synthetic", "qna"]
        if session_id:
            tags.append(f"synthetic_qna_session_{session_id}")

        if input.tags:
            tags.extend(input.tags)
        qna_run.tags = tags

        return qna_run

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/save_qna_pair",
        summary="Save Q&A Pair",
        tags=["Synthetic Data"],
        openapi_extra=ALLOW_AGENT,
    )
    async def save_qna_pair(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: SaveQnaPairInput,
        session_id: Annotated[
            str, Query(description="Session ID to group saved Q&A pairs.")
        ],
    ) -> TaskRun:
        """
        Save a single QnA pair as a TaskRun. We store the task's system prompt
        as the system message, the query as the user message, and the answer
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
            "content": input.query,
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
            input=input.query,
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

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        summary="Get Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_data_gen_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> DataGuide | None:
        task = task_from_id(project_id, task_id)
        return task.current_data_guide()

    @app.put(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        summary="Save Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=ALLOW_AGENT,
    )
    async def save_data_gen_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: SaveTaskDataGuideInput,
    ) -> DataGuide:
        task = task_from_id(project_id, task_id)

        # By design there is at most one DataGuide per task. Reuse the existing
        # file if present (so git history of the guide stays in one place);
        # otherwise create the first one.
        existing = task.current_data_guide()
        if existing is not None:
            existing.guide = input.guide
            existing.save_to_file()
            return existing
        guide = DataGuide(parent=task, guide=input.guide)
        guide.save_to_file()
        return guide

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        summary="Delete Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=ALLOW_AGENT,
    )
    async def delete_data_gen_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> None:
        task = task_from_id(project_id, task_id)
        existing = task.current_data_guide()
        if existing is not None:
            existing.delete()

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        summary="Preview Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval(
            "Generate preview samples using LLM?"
        ),
    )
    async def preview_data_gen_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: GuidePreviewInput,
    ) -> list[GuidePreviewSample]:
        project = project_from_id(project_id)
        task = task_from_id(project_id, task_id)

        # Wrap the draft guide through `_combine_guidance` so the preview's
        # input-generation pass receives the same Data Guide framing (definition,
        # authority cascade, invariants, stage hint) that real `/generate_inputs`
        # uses at runtime. Without this, previewed inputs are generated under
        # different framing than saved inputs would be — defeating the purpose
        # of iterating on the guide here.
        input_combined_guidance = _combine_guidance(task, None, "inputs", input.guide)

        sample_task = DataGenSampleTask(
            target_task=task,
            gen_type="eval",
            parent_project=project,
            guidance=input_combined_guidance,
        )

        task_input = DataGenSampleTaskInput.from_task(
            task=task,
            topic=[],
            num_samples=input.num_samples,
        )

        import json

        run_config_properties = input.run_config_properties.model_copy()
        run_config_properties.prompt_id = PromptGenerators.SIMPLE
        skills = load_skills_for_task(sample_task, run_config_properties)
        adapter = adapter_for_task(
            sample_task,
            run_config_properties=run_config_properties,
            base_adapter_config=AdapterConfig(skills=skills),
        )

        samples_run = await adapter.invoke(task_input.model_dump())

        if not samples_run.output or not samples_run.output.output:
            raise HTTPException(
                status_code=500, detail="Failed to generate preview samples"
            )

        try:
            parsed = json.loads(samples_run.output.output)
            generated_samples = parsed.get("generated_samples", [])
        except (json.JSONDecodeError, AttributeError):
            raise HTTPException(
                status_code=500, detail="Failed to parse generated samples"
            )

        preview_samples: list[GuidePreviewSample] = []
        # Use the user's run config as-is for output generation. Don't override
        # prompt_id — this adapter runs the user's actual task (not a meta-task),
        # so we want to mirror the real SDG /generate_sample flow which respects
        # the chosen prompt template (few-shot, chain-of-thought, saved prompts).
        # Forcing SIMPLE here strips that and can cause empty assistant responses
        # on models that rely on the prompt structure (e.g. reasoning models).
        output_run_config = (
            input.output_run_config_properties or input.run_config_properties
        ).model_copy()

        # Condition the output generation on the (in-progress) data guide so
        # the previewed outputs reflect what real SDG would produce with this
        # guide saved — same wrapping that /generate_sample does at runtime.
        # Pass `input.guide` as the override so we use the guide being tested,
        # not whatever's currently persisted on the task.
        output_combined_guidance = (
            _combine_guidance(task, None, "outputs", input.guide) or ""
        )
        for sample_input in generated_samples[: input.num_samples]:
            # Always keep a string form for the response so the UI can display
            # the input verbatim (matches what the user sees in the preview
            # table).
            sample_input_str = (
                json.dumps(sample_input)
                if isinstance(sample_input, (dict, list))
                else str(sample_input)
            )

            # But what we hand to the adapter depends on the task's input
            # schema. Structured-input tasks must receive a parsed dict/list;
            # passing a JSON string blows up jsonschema validation with
            # "<json> is not of type 'object'". Plain-text tasks expect a
            # string. This mirrors how the real SDG flow's frontend prepares
            # the input before calling /generate_sample
            # (synth/+page.svelte: `task.input_json_schema ? JSON.parse(...) : sample.input`).
            adapter_input: str | dict | list
            if task.input_json_schema:
                if isinstance(sample_input, (dict, list)):
                    adapter_input = sample_input
                else:
                    try:
                        adapter_input = json.loads(str(sample_input))
                    except json.JSONDecodeError:
                        # Generator produced something that wasn't valid JSON
                        # for a structured-input task. Skip this sample rather
                        # than fail the whole preview.
                        preview_samples.append(
                            GuidePreviewSample(
                                input=sample_input_str,
                                output="[Skipped: generated input was not valid JSON for the task's input schema]",
                            )
                        )
                        continue
            else:
                adapter_input = sample_input_str

            task_copy = task.model_copy(deep=True)
            if output_combined_guidance.strip():
                task_copy.instruction = wrap_task_with_guidance(
                    task_copy.instruction, output_combined_guidance
                )

            skills = load_skills_for_task(task_copy, output_run_config)
            output_adapter = adapter_for_task(
                task_copy,
                run_config_properties=output_run_config,
                base_adapter_config=AdapterConfig(allow_saving=False, skills=skills),
            )
            output_run = await output_adapter.invoke(input=adapter_input)
            output_text = (
                output_run.output.output
                if output_run.output and output_run.output.output
                else ""
            )
            preview_samples.append(
                GuidePreviewSample(input=sample_input_str, output=output_text)
            )

        return preview_samples

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
        summary="Refine Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Refine guidance using LLM?"),
    )
    async def refine_data_gen_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: GuideRefineInput,
    ) -> GuideRefineResponse:
        import json

        from kiln_ai.adapters.data_gen.data_gen_prompts import (
            generate_guidance_refinement_prompt,
        )

        task = task_from_id(project_id, task_id)

        system_prompt = generate_guidance_refinement_prompt(
            task_instruction=task.instruction,
            current_guide=input.current_guide,
            preview_samples=[
                (s.input, s.output, s.looks_good) for s in input.preview_samples
            ],
            feedback=input.feedback,
            task_description=task.description,
            task_input_json_schema=task.input_json_schema,
            task_output_json_schema=task.output_json_schema,
        )

        run_config = input.run_config_properties.model_copy()
        run_config.prompt_id = PromptGenerators.SIMPLE

        refine_task = Task(
            name="guidance_refinement",
            instruction=system_prompt,
            output_json_schema=json.dumps(GuideRefineOutput.model_json_schema()),
        )

        adapter = adapter_for_task(
            refine_task,
            run_config_properties=run_config,
            base_adapter_config=AdapterConfig(allow_saving=False),
        )

        refine_run = await adapter.invoke(
            input="Please refine the input guidance based on the feedback provided in your instructions."
        )

        if not refine_run.output or not refine_run.output.output:
            raise HTTPException(status_code=500, detail="Failed to refine guidance")

        parsed = json.loads(refine_run.output.output)
        new_rules_body = (parsed.get("rules") or "").strip()

        # Defensive: if the LLM ignored the schema description and prefixed its
        # output with the heading anyway, strip every occurrence so we don't
        # double up. Use the default count (0 = unlimited) rather than count=1
        # in case the LLM emits the heading more than once.
        new_rules_body = _GUIDELINES_HEADING_RE.sub("", new_rules_body).strip()

        examples_block, existing_rules_body = _split_data_guide(input.current_guide)

        # Bootstrap mode (no rated samples + no feedback) is the first-preview
        # synthesis pass. In this mode any rules already in `current_guide`
        # were typed by the user in the setup form and must be preserved
        # verbatim — same architectural treatment as reference examples. The
        # metaprompter prompt instructs the LLM to emit ONLY augmenting rules
        # in this mode, and we stitch user_rules + new_rules below. Outside
        # bootstrap (refinement after rated samples / feedback), the LLM owns
        # the rules half wholesale, so we replace existing rules entirely.
        is_bootstrap = len(input.preview_samples) == 0 and not input.feedback.strip()
        # Key preservation off the <user_authored> provenance tag, not just
        # "is there anything in the rules section." This keeps the endpoint
        # symmetric with the prompt-side bootstrap detection (which also
        # checks for <user_authored>) and avoids falsely preserving LLM-
        # authored rules if a guide containing them is ever passed through
        # bootstrap.
        preserve_user_rules = is_bootstrap and "<user_authored>" in existing_rules_body

        if not new_rules_body:
            # LLM returned nothing useful — preserve the existing guide rather
            # than blanking out the rules section.
            return GuideRefineResponse(refined_guide=input.current_guide)

        if preserve_user_rules:
            combined_rules_body = f"{existing_rules_body}\n\n{new_rules_body}".strip()
        else:
            combined_rules_body = new_rules_body

        new_rules_block = f"# Guidelines & Rules\n\n{combined_rules_body}"
        refined_guide = (
            f"{examples_block}\n\n{new_rules_block}"
            if examples_block
            else new_rules_block
        )
        return GuideRefineResponse(refined_guide=refined_guide)


_DATA_GUIDE_STAGE_HINTS: dict[Literal["topics", "inputs", "outputs"], str] = {
    "topics": (
        "Since this stage generates topics (subject areas, not data), use the "
        "guide only to inform what scenarios the task's data covers. Rules and "
        "examples about input/output shape and content are background context — "
        "do NOT reproduce them in the topic strings. Group tags are largely "
        "irrelevant at this stage; you are generating short topic labels. "
        "Rules in `<user_authored>` still apply if they bear on what scenarios "
        "are valid for this task."
    ),
    "inputs": (
        "Since this stage generates task **inputs**, apply rules in the "
        "`<input_structural>`, `<input_semantic>`, `<both_structural>`, "
        "`<both_semantic>`, and `<user_authored>` groups. Treat rules in "
        "`<output_structural>` and `<output_semantic>` as background context "
        "(helpful for understanding what kind of inputs naturally pair with "
        "realistic outputs) — do not enforce them on this stage. Reference "
        "examples show what realistic inputs look like; mirror their "
        "structure and value patterns."
    ),
    "outputs": (
        "Since this stage generates task **outputs**, apply rules in the "
        "`<output_structural>`, `<output_semantic>`, `<both_structural>`, "
        "`<both_semantic>`, and `<user_authored>` groups. Rules in "
        "`<input_structural>` and `<input_semantic>` are background context — "
        "the input you receive already exists; you are not regenerating it. "
        "Reference examples show the kind of output you should produce. Rules "
        "that name measurable bounds (length, sentence counts, field counts, "
        "formatting) are CEILINGS — never exceed them, and compress content "
        "to fit rather than expanding the bounds. Match the sentence structure "
        "and formatting of the reference examples (terseness, prose vs "
        "bullets, key-value layout)."
    ),
}


_GUIDELINES_HEADING_RE = re.compile(r"^# Guidelines & Rules\b.*$", re.MULTILINE)


def _split_data_guide(guide: str) -> tuple[str, str]:
    """Split a Data Guide markdown into (examples_block, rules_body).

    `examples_block` is everything before the `# Guidelines & Rules` heading
    (typically the `# Reference Examples` section). `rules_body` is the
    markdown content *under* the rules heading, with the heading itself
    removed — i.e. the sequence of `## <title>` rule blocks. Either may be
    empty.

    Both blocks are content-preserving — surrounding whitespace is normalized
    via `.strip()`, but the body of each block (examples, fenced code,
    rule blocks) is returned verbatim. Internal whitespace is untouched.

    If the guide has no `# Guidelines & Rules` heading, the entire input is
    returned as `examples_block` and `rules_body` is empty. This means a
    user who manually deletes the heading via the Edit dialog will, on the
    next refinement, see the full guide treated as immutable examples and
    only the LLM's new output written under a freshly-stitched `# Guidelines
    & Rules` heading. Acceptable trade-off given that deleting the heading
    is an explicit off-script action.

    The split exists so refinement can treat reference examples as immutable
    user input (preserved by the system) and have the LLM produce only the
    rules portion of the guide.
    """
    match = _GUIDELINES_HEADING_RE.search(guide)
    if not match:
        return guide.strip(), ""
    examples_block = guide[: match.start()].strip()
    rules_body = guide[match.end() :].strip()
    return examples_block, rules_body


def _resolve_data_guide(task: Task, data_guide_override: str | None) -> str | None:
    """Return the data guide content to use for this call.

    Override semantics: an explicit override (even an empty string) replaces the
    task's persisted guide. `None` means "no override provided" and falls back
    to the task's current DataGuide if one is set.
    """
    if data_guide_override is not None:
        return data_guide_override if data_guide_override.strip() else None
    current = task.current_data_guide()
    if current:
        return current.guide
    return None


def _combine_guidance(
    task: Task,
    session_guidance: str | None,
    stage: Literal["topics", "inputs", "outputs"],
    data_guide_override: str | None = None,
) -> str | None:
    """Combine the task data guide with the per-call/template guidance.

    The data guide is wrapped with a short framing paragraph + a stage-specific
    hint so the LLM understands what it's reading and how to apply it for the
    current generation stage. Without this wrapper, the model sees the user's
    raw markdown with no context for where it came from or how to use it.
    """
    parts: list[str] = []
    data_guide_content = _resolve_data_guide(task, data_guide_override)
    if data_guide_content:
        stage_hint = _DATA_GUIDE_STAGE_HINTS[stage]
        parts.append(
            "## Task Data Guide\n\n"
            "A Task Data Guide is a recipe for what realistic data for this "
            "task looks like. It contains three things: **reference examples** "
            "(concrete `(input, output)` pairs showing what good looks like), "
            "**structural rules** (how the data is shaped — format, length, "
            "layout, formatting conventions), and **semantic rules** (what the "
            "data means — fields, valid values, relationships, domain "
            "plausibility). Treat items in `# Guidelines & Rules` as hard "
            "constraints, not suggestions.\n\n"
            "**Rule grouping.** Rules in `# Guidelines & Rules` are wrapped in "
            "XML-style group tags by scope+type. The six scope+type groups are "
            "`<input_structural>`, `<input_semantic>`, `<output_structural>`, "
            "`<output_semantic>`, `<both_structural>`, `<both_semantic>`. There "
            "is also a 7th group, `<user_authored>`, containing rules the user "
            "typed by hand in the setup form — treat its rules as binding "
            "constraints at every stage (topics, inputs, outputs), the same "
            "way you would treat `<both_*>` rules. Each group contains one or "
            "more `## <title>` rule blocks. Use the group tag to decide whether "
            "a rule applies to the stage you are generating for — see the "
            "stage hint below. Untagged rules (a `## Title` block sitting "
            "outside any group, from older guides) should be treated as "
            "`<both_semantic>`.\n\n"
            "**Authority cascade** when sources conflict (highest wins):\n"
            "1. Per-run guidance below this guide, if any.\n"
            "2. The rules and reference examples in this guide.\n"
            "3. Defaults you would otherwise pick.\n\n"
            "**Invariants — must always hold regardless of source:** logical "
            "relationships between fields, domain plausibility and accuracy, "
            "and truthfulness to the task's actual purpose.\n\n"
            f"{stage_hint}\n\n"
            "<task_data_guide>\n"
            f"{data_guide_content}\n"
            "</task_data_guide>"
        )
    if session_guidance:
        parts.append(session_guidance)
    return "\n\n".join(parts) if parts else None


def topic_path_to_string(topic_path: list[str]) -> str | None:
    if topic_path and len(topic_path) > 0:
        return ">>>>>".join(topic_path)
    return None


def topic_path_from_string(topic_path: str | None) -> list[str]:
    if topic_path:
        return topic_path.split(">>>>>")
    return []
