import json
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from kiln_ai.adapters.adapter_registry import adapter_for_task, load_skills_for_task
from kiln_ai.adapters.data_gen.data_gen_prompts import (
    RatedSample,
    generate_guidance_refinement_prompt,
)
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
        description="Optional per-run input data guide override. Replaces the task's persisted input data guide for this run.",
        default=None,
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The run config properties to use for input generation"
    )


class SaveTaskDataGuideInput(BaseModel):
    guide: str = Field(
        default="",
        description="Markdown body of the input data guide.",
    )


class GuidePreviewSample(BaseModel):
    input: str = Field(description="Generated sample input")


class GuidePreviewInput(BaseModel):
    guide: str = Field(
        default="",
        description="Markdown body of the input data guide being previewed.",
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The model config to use for preview input generation"
    )
    num_samples: int = Field(
        description="Number of preview samples to generate",
        default=5,
        ge=1,
        le=20,
    )


class GuideRefineInput(BaseModel):
    current_guide: str = Field(
        default="",
        description="Markdown body of the current input data guide — the metaprompter rewrites it wholesale.",
    )
    feedback: str = Field(
        description="User feedback on what's wrong with the previewed inputs"
    )
    preview_samples: list[RatedSample] = Field(
        description="The previewed inputs the user is giving feedback on, each rated by the user as realistic (true) or needs work (false)"
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description="The model config to use for the metaprompter call itself."
    )


class GuideRefineOutput(BaseModel):
    """Structured output schema for the LLM refinement task — the full
    refined input data guide markdown."""

    guide: str = Field(
        description=(
            "Full refined input data guide markdown. Includes `# Reference Inputs` "
            "and `# Input Guidelines & Rules` sections as appropriate."
        ),
    )


class GuideRefineResponse(BaseModel):
    refined_guide: str = Field(
        description="The refined input data guide markdown returned by the metaprompter."
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

        # The Input Data Guide is intentionally NOT injected at the output
        # generation stage — it describes inputs only, and output behavior is
        # owned by the task's system prompt + output schema. Only per-call
        # session guidance (`sample.guidance`) flows in here.
        guidance = sample.guidance or ""
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

        if not input.guide.strip():
            raise HTTPException(
                status_code=400,
                detail="Data guide cannot be empty. Use DELETE to remove it.",
            )

        # By design there is at most one DataGuide per task. Reuse the existing
        # file if present (so git history of the guide stays in one place);
        # otherwise create the first one.
        existing = task.current_data_guide()
        if existing is not None:
            existing.guide = input.guide
            existing.save_to_file()
            return existing
        guide = DataGuide(
            parent=task,
            guide=input.guide,
        )
        guide.save_to_file()
        return guide

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        summary="Delete Task Data Guide",
        tags=["Synthetic Data"],
        openapi_extra=agent_policy_require_approval("Delete saved Data Guide?"),
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
        return await generate_input_preview_samples(
            project_id=project_id,
            task_id=task_id,
            guide=input.guide,
            run_config_properties=input.run_config_properties,
            num_samples=input.num_samples,
        )

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
        task = task_from_id(project_id, task_id)

        system_prompt = generate_guidance_refinement_prompt(
            task_instruction=task.instruction,
            current_guide=input.current_guide,
            preview_samples=input.preview_samples,
            feedback=input.feedback,
            task_description=task.description,
            task_input_json_schema=task.input_json_schema,
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

        try:
            parsed = json.loads(refine_run.output.output)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500, detail="Failed to parse refined guidance"
            )
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=500, detail="Failed to parse refined guidance"
            )

        new_guide = (parsed.get("guide") or "").strip()

        if not new_guide:
            return GuideRefineResponse(refined_guide=input.current_guide)

        return GuideRefineResponse(refined_guide=new_guide)


_DATA_GUIDE_STAGE_HINTS: dict[Literal["topics", "inputs"], str] = {
    "topics": (
        "Since this stage generates topics (subject areas, not data), use the "
        "guide only to inform what scenarios the task's inputs cover. Rules "
        "and examples about input shape and content are background context — "
        "do NOT reproduce them in the topic strings. Group tags are largely "
        "irrelevant at this stage; you are generating short topic labels."
    ),
    "inputs": (
        "Since this stage generates task **inputs**, apply rules in the "
        "`<input_structural>` and `<input_semantic>` groups. Reference inputs "
        "show what realistic inputs look like; mirror their structure and "
        "value patterns. Rules that name measurable bounds (length, sentence "
        "counts, field counts, formatting) are CEILINGS — never exceed them."
    ),
}


async def generate_input_preview_samples(
    project_id: str,
    task_id: str,
    guide: str,
    run_config_properties: KilnAgentRunConfigProperties,
    num_samples: int,
) -> list[GuidePreviewSample]:
    """Generate preview *inputs* for a draft input data guide.

    Reused by both the manual `/data_gen_guide_preview` endpoint and the
    copilot `/copilot/analyze_input_data_guide` proxy so they go through the
    same input-generation framing the runtime SDG uses.
    """
    project = project_from_id(project_id)
    task = task_from_id(project_id, task_id)

    # Wrap the draft guide through `_combine_guidance` so the preview's
    # input-generation pass receives the same Input Data Guide framing
    # (definition, authority cascade, invariants, stage hint) that real
    # `/generate_inputs` uses at runtime.
    input_combined_guidance = _combine_guidance(task, None, "inputs", guide)

    sample_task = DataGenSampleTask(
        target_task=task,
        gen_type="eval",
        parent_project=project,
        guidance=input_combined_guidance,
    )

    task_input = DataGenSampleTaskInput.from_task(
        task=task,
        topic=[],
        num_samples=num_samples,
    )

    rcp = run_config_properties.model_copy()
    rcp.prompt_id = PromptGenerators.SIMPLE
    skills = load_skills_for_task(sample_task, rcp)
    adapter = adapter_for_task(
        sample_task,
        run_config_properties=rcp,
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
        raise HTTPException(status_code=500, detail="Failed to parse generated samples")
    if not isinstance(generated_samples, list):
        raise HTTPException(status_code=500, detail="Failed to parse generated samples")

    preview_samples: list[GuidePreviewSample] = []
    for sample_input in generated_samples[:num_samples]:
        sample_input_str = (
            json.dumps(sample_input)
            if isinstance(sample_input, (dict, list))
            else str(sample_input)
        )
        preview_samples.append(GuidePreviewSample(input=sample_input_str))

    return preview_samples


def _resolve_data_guide(task: Task, data_guide_override: str | None) -> str | None:
    """Return the data guide content to use for this call.

    Override semantics: an explicit override (even an empty string) replaces the
    task's persisted guide. `None` means "no override provided" and falls back
    to the task's current DataGuide if one is set.
    """
    if data_guide_override is not None:
        return data_guide_override if data_guide_override.strip() else None
    current = task.current_data_guide()
    if current and current.guide.strip():
        return current.guide
    return None


def _combine_guidance(
    task: Task,
    session_guidance: str | None,
    stage: Literal["topics", "inputs"],
    data_guide_override: str | None = None,
) -> str | None:
    """Combine the task input data guide with the per-call/template guidance.

    The guide is wrapped with a short framing paragraph + a stage-specific
    hint so the LLM understands what it's reading and how to apply it for the
    current generation stage. Without this wrapper, the model sees the user's
    raw markdown with no context for where it came from or how to use it.

    The Input Data Guide is consumed only at the topic and input generation
    stages — never at output generation. Output behavior is owned by the
    task's system prompt + output schema, not this guide.
    """
    parts: list[str] = []
    data_guide_content = _resolve_data_guide(task, data_guide_override)
    if data_guide_content:
        stage_hint = _DATA_GUIDE_STAGE_HINTS[stage]
        parts.append(
            "# Task Input Data Guide\n\n"
            "A Task Input Data Guide is a recipe for what realistic *inputs* "
            "to this task look like. It contains: **reference inputs** "
            "(concrete example inputs showing what realistic input looks "
            "like), **structural rules** (how inputs are shaped — format, "
            "length, layout, formatting conventions), and **semantic rules** "
            "(what inputs mean — fields, valid values, relationships, domain "
            "plausibility). Treat items in `# Input Guidelines & Rules` as "
            "hard constraints, not suggestions.\n\n"
            "**Rule grouping.** Rules in `# Input Guidelines & Rules` are "
            "wrapped in XML-style group tags. The two valid groups are "
            "`<input_structural>` and `<input_semantic>`. Each group contains "
            "one or more `## <title>` rule blocks. Untagged rules (a `## "
            "Title` block sitting outside any group, from older guides) "
            "should be treated as `<input_semantic>`.\n\n"
            "**Authority cascade** when sources conflict (highest wins):\n"
            "1. Per-run guidance below this guide, if any.\n"
            "2. The rules and reference inputs in this guide.\n"
            "3. Defaults you would otherwise pick.\n\n"
            "**Invariants — must always hold regardless of source:** logical "
            "relationships between fields, domain plausibility and accuracy, "
            "and truthfulness to the task's actual purpose.\n\n"
            f"{stage_hint}\n\n"
            "<task_input_data_guide>\n"
            f"{data_guide_content}\n"
            "</task_input_data_guide>"
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
