from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.repair.repair_task import RepairTaskRun
from kiln_ai.datamodel import TaskRun
from kiln_server.run_api import model_provider_from_string, task_and_run_from_id
from pydantic import BaseModel, ConfigDict, Field


class RepairTaskApiInput(BaseModel):
    evaluator_feedback: str = Field(
        description="Feedback from an evaluator on how to repair the task run."
    )
    model_name: str | None = Field(
        description="The name of the model to use for the repair task. Optional, if not specified, the model of the original task will be used.",
        default=None,
    )
    provider: str | None = Field(
        description="The provider of the model to use for the repair task. Optional, if not specified, the provider of the original task will be used.",
        default=None,
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

        source_properties = (
            run.output.source.properties
            if run.output.source and run.output.source.properties
            else {}
        )
        model_name = input.model_name or source_properties.get("model_name")
        provider = input.provider or source_properties.get("model_provider")
        if (
            not model_name
            or not provider
            or not isinstance(model_name, str)
            or not isinstance(provider, str)
        ):
            raise HTTPException(
                status_code=400,
                detail="Model name and provider must be specified.",
            )

        adapter = adapter_for_task(
            repair_task,
            model_name=model_name,
            provider=model_provider_from_string(provider),
        )

        repair_run = await adapter.invoke(repair_task_input.model_dump())
        return repair_run

    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/repair")
    async def post_repair_run(
        project_id: str, task_id: str, run_id: str, input: RepairRunPost
    ) -> TaskRun:
        task, run = task_and_run_from_id(project_id, task_id, run_id)
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
