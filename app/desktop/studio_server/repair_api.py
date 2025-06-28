from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.repair.repair_task import RepairTaskRun
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.utils.config import Config
from kiln_server.run_api import model_provider_from_string, task_and_run_from_id
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class RepairTaskApiInput(BaseModel):
    evaluator_feedback: str = Field(
        description="Feedback from an evaluator on how to repair the task run."
    )

    # Allows use of the model_name field (usually pydantic will reserve model_*)
    model_config = ConfigDict(protected_namespaces=())


class RepairRunPost(BaseModel):
    repair_run: TaskRun
    evaluator_feedback: str


def connect_repair_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/run_repair")
    async def run_repair(
        project_id: str, task_id: str, run_id: str, input: RepairTaskApiInput
    ) -> TaskRun:
        task, run = task_and_run_from_id(project_id, task_id, run_id)
        repair_task = RepairTaskRun(task)
        repair_task_input = RepairTaskRun.build_repair_task_input(
            original_task=task,
            task_run=run,
            evaluator_feedback=input.evaluator_feedback,
        )

        # Build the same run config properties as the original run. The persisted data has changed over time, so lots of error checks.
        source_properties = (
            run.output.source.properties
            if run.output.source and run.output.source.properties
            else {}
        )
        try:
            model_name = source_properties.get("model_name", None)
            provider = source_properties.get("model_provider", None)
            if (
                not model_name
                or not provider
                or not isinstance(model_name, str)
                or not isinstance(provider, str)
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Model name and provider must be specified.",
                )
            model_name = str(model_name)
            provider = model_provider_from_string(provider)

            sdm = source_properties.get("structured_output_mode", None)
            if sdm is None or not isinstance(sdm, str):
                sdm = default_structured_output_mode_for_model_provider(
                    model_name,
                    provider,
                )
            else:
                sdm = StructuredOutputMode(sdm)

            run_config_properties = RunConfigProperties(
                model_name=model_name,
                model_provider_name=provider,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=sdm,
            )

            temperature = source_properties.get("temperature", None)
            if temperature is not None and isinstance(temperature, float):
                run_config_properties.temperature = temperature

            top_p = source_properties.get("top_p", None)
            if top_p is not None and isinstance(top_p, float):
                run_config_properties.top_p = top_p

        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid run config properties: {e}",
            )

        adapter = adapter_for_task(
            repair_task,
            run_config_properties=run_config_properties,
        )

        repair_run = await adapter.invoke(repair_task_input.model_dump())
        return repair_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/repair")
    async def post_repair_run(
        project_id: str, task_id: str, run_id: str, input: RepairRunPost
    ) -> TaskRun:
        task, run = task_and_run_from_id(project_id, task_id, run_id)

        # manually edited runs are human but the user id is not set
        source = input.repair_run.output.source
        if not source or source.type == DataSourceType.human:
            input.repair_run.output.source = DataSource(
                type=DataSourceType.human,
                properties={"created_by": Config.shared().user_id},
            )

        # Update the run object atomically, as validation will fail setting one at a time.
        updated_data = run.model_dump()
        updated_data.update(
            {
                "repair_instructions": input.evaluator_feedback,
                "repaired_output": input.repair_run.output,
            }
        )
        updated_run = TaskRun.model_validate(updated_data)
        updated_run.path = run.path

        # Save the updated run
        updated_run.save_to_file()
        return updated_run
