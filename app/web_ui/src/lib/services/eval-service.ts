import { client } from "$lib/api_client"
import type {
  Eval,
  EvalConfig,
  TaskRunConfig,
  EvalResultSummary,
} from "$lib/types"
import { createKilnError } from "$lib/utils/error_handlers"
import type { components } from "$lib/api_schema"
import { KilnError } from "$lib/utils/error_handlers"

export async function getEval(
  projectId: string,
  taskId: string,
  evalId: string,
): Promise<{ data: Eval | null; error: KilnError | null }> {
  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
            eval_id: evalId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { data, error: null }
  } catch (error) {
    return { data: null, error: createKilnError(error) }
  }
}

export async function getEvalConfigs(
  projectId: string,
  taskId: string,
  evalId: string,
): Promise<{ data: EvalConfig[] | null; error: KilnError | null }> {
  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
            eval_id: evalId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { data, error: null }
  } catch (error) {
    return { data: null, error: createKilnError(error) }
  }
}

export async function getTaskRunConfigs(
  projectId: string,
  taskId: string,
): Promise<{ data: TaskRunConfig[] | null; error: KilnError | null }> {
  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/task_run_configs",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { data, error: null }
  } catch (error) {
    return { data: null, error: createKilnError(error) }
  }
}

export async function getScoreSummary(
  projectId: string,
  taskId: string,
  evalId: string,
  evalConfigId: string | null,
): Promise<{ data: EvalResultSummary | null; error: KilnError | null }> {
  if (!evalConfigId) {
    return {
      data: null,
      error: new KilnError("No evaluation method selected", null),
    }
  }

  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/score_summary",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
            eval_id: evalId,
            eval_config_id: evalConfigId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { data, error: null }
  } catch (error) {
    return { data: null, error: createKilnError(error) }
  }
}

export async function setCurrentRunConfig(
  projectId: string,
  taskId: string,
  evalId: string,
  runConfigId: string,
): Promise<{ data: Eval | null; error: KilnError | null }> {
  if (!runConfigId) {
    return { data: null, error: null }
  }

  try {
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/set_current_run_config/{run_config_id}",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
            eval_id: evalId,
            run_config_id: runConfigId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { data, error: null }
  } catch (error) {
    return { data: null, error: createKilnError(error) }
  }
}

export async function deleteTaskRunConfig(
  projectId: string,
  taskId: string,
  runConfigId: string,
): Promise<{ success: boolean; error: KilnError | null }> {
  if (!runConfigId) {
    return { success: false, error: null }
  }

  try {
    const { error } = await client.DELETE(
      "/api/projects/{project_id}/tasks/{task_id}/task_run_config/{run_config_id}",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
            run_config_id: runConfigId,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    return { success: true, error: null }
  } catch (error) {
    const errorMessage =
      error && typeof error === "object" && "message" in error
        ? String(error.message)
        : "Unknown error"
    return {
      success: false,
      error: new KilnError("Failed to delete run method", [errorMessage]),
    }
  }
}

export async function addTaskRunConfig(
  projectId: string,
  taskId: string,
  runConfigProperties: components["schemas"]["CreateTaskRunConfigRequest"]["run_config_properties"],
): Promise<{ error: Error | null }> {
  try {
    const { error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/task_run_config",
      {
        params: {
          path: {
            project_id: projectId,
            task_id: taskId,
          },
        },
        body: {
          run_config_properties: runConfigProperties,
        },
      },
    )
    if (error) {
      throw error
    }
    return { error: null }
  } catch (error) {
    return { error: createKilnError(error) }
  }
}

export async function getFinetuneBaseModel(
  modelName: string,
): Promise<{ baseModelId: string | null; error: KilnError | null }> {
  try {
    const parts = modelName.split("::")
    if (parts.length !== 3) {
      return { baseModelId: null, error: null }
    }

    const [ftProjectId, ftTaskId, finetuneId] = parts

    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}",
      {
        params: {
          path: {
            project_id: ftProjectId,
            task_id: ftTaskId,
            finetune_id: finetuneId,
          },
        },
      },
    )

    if (error || !data) {
      return { baseModelId: null, error: createKilnError(error) }
    }

    return { baseModelId: data.finetune.base_model_id, error: null }
  } catch (error) {
    return { baseModelId: null, error: createKilnError(error) }
  }
}
