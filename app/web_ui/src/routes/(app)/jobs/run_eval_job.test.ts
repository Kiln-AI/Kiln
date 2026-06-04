import { describe, it, expect, vi } from "vitest"
import {
  build_run_eval_params,
  can_submit_run_eval,
  eval_config_options,
  load_eval_judges,
  run_config_options,
  start_eval_job,
  type RunEvalSelection,
} from "./run_eval_job"
import type { EvalConfig, TaskRunConfig } from "$lib/types"
import type { create_job } from "$lib/stores/jobs_api"
import type { client } from "$lib/api_client"

const complete: RunEvalSelection = {
  project_id: "p_1",
  task_id: "t_1",
  eval_id: "e_1",
  eval_config_id: "ec_1",
  run_config_id: "rc_1",
}

describe("build_run_eval_params", () => {
  it("returns the create_job payload when all selections are present", () => {
    expect(build_run_eval_params(complete)).toEqual({
      project_id: "p_1",
      task_id: "t_1",
      eval_id: "e_1",
      eval_config_id: "ec_1",
      run_config_id: "rc_1",
    })
  })

  it("returns null when the task is not selected", () => {
    expect(build_run_eval_params({ ...complete, task_id: null })).toBeNull()
    expect(build_run_eval_params({ ...complete, project_id: null })).toBeNull()
  })

  it("returns null until every picker has a value", () => {
    expect(build_run_eval_params({ ...complete, eval_id: null })).toBeNull()
    expect(
      build_run_eval_params({ ...complete, eval_config_id: null }),
    ).toBeNull()
    expect(
      build_run_eval_params({ ...complete, run_config_id: null }),
    ).toBeNull()
  })
})

describe("can_submit_run_eval", () => {
  it("is true only when the selection is complete", () => {
    expect(can_submit_run_eval(complete)).toBe(true)
  })

  it("is false when no task is selected", () => {
    expect(
      can_submit_run_eval({ ...complete, project_id: null, task_id: null }),
    ).toBe(false)
  })

  it("is false until eval, judge, and run config are all chosen", () => {
    expect(can_submit_run_eval({ ...complete, eval_id: null })).toBe(false)
    expect(can_submit_run_eval({ ...complete, eval_config_id: null })).toBe(
      false,
    )
    expect(can_submit_run_eval({ ...complete, run_config_id: null })).toBe(
      false,
    )
  })
})

describe("start_eval_job", () => {
  it("calls create_job with the eval type, selected params, and project_id", async () => {
    const create_job_fn = vi.fn().mockResolvedValue({
      job_id: "j_1",
      status: "pending",
    }) as unknown as typeof create_job
    const started = await start_eval_job(create_job_fn, complete)
    expect(started).toBe(true)
    expect(create_job_fn).toHaveBeenCalledTimes(1)
    expect(create_job_fn).toHaveBeenCalledWith(
      "eval",
      {
        project_id: "p_1",
        task_id: "t_1",
        eval_id: "e_1",
        eval_config_id: "ec_1",
        run_config_id: "rc_1",
      },
      null,
      "p_1",
    )
  })

  it("does not call create_job when the selection is incomplete", async () => {
    const create_job_fn = vi.fn() as unknown as typeof create_job
    const started = await start_eval_job(create_job_fn, {
      ...complete,
      eval_config_id: null,
    })
    expect(started).toBe(false)
    expect(create_job_fn).not.toHaveBeenCalled()
  })

  it("does not call create_job when no task is selected", async () => {
    const create_job_fn = vi.fn() as unknown as typeof create_job
    const started = await start_eval_job(create_job_fn, {
      ...complete,
      project_id: null,
      task_id: null,
    })
    expect(started).toBe(false)
    expect(create_job_fn).not.toHaveBeenCalled()
  })
})

describe("eval_config_options", () => {
  const configs = [
    { id: "ec_2", name: "Beta" },
    { id: "ec_1", name: "Alpha" },
  ] as unknown as EvalConfig[]

  it("returns an empty list when there are no configs", () => {
    expect(eval_config_options(null, "ec_1", null)).toEqual([])
    expect(eval_config_options([], "ec_1", null)).toEqual([])
  })

  it("places the default judge first and badges it", () => {
    const groups = eval_config_options(configs, "ec_1", null)
    expect(groups).toHaveLength(1)
    const options = groups[0].options
    expect(options[0].value).toBe("ec_1")
    expect(options[0].badge).toBe("Default")
    expect(options[1].value).toBe("ec_2")
    expect(options[1].badge).toBeUndefined()
  })
})

describe("run_config_options", () => {
  const configs = [
    {
      id: "rc_2",
      name: "Zeta",
      run_config_properties: { type: "mcp" },
    },
    {
      id: "rc_1",
      name: "Alpha",
      run_config_properties: { type: "mcp" },
    },
  ] as unknown as TaskRunConfig[]

  it("returns an empty list when there are no configs", () => {
    expect(run_config_options(null, "rc_1", null)).toEqual([])
    expect(run_config_options([], "rc_1", null)).toEqual([])
  })

  it("places the default run config first, badges it, then sorts by name", () => {
    const groups = run_config_options(configs, "rc_1", null)
    expect(groups).toHaveLength(1)
    const options = groups[0].options
    expect(options[0].value).toBe("rc_1")
    expect(options[0].badge).toBe("Default")
    expect(options[1].value).toBe("rc_2")
  })

  it("sorts by name when there is no default", () => {
    const groups = run_config_options(configs, null, null)
    const options = groups[0].options
    expect(options.map((o) => o.value)).toEqual(["rc_1", "rc_2"])
  })
})

describe("load_eval_judges", () => {
  // A controllable promise so a test can resolve responses out of order.
  function deferred<T>() {
    let resolve!: (value: T) => void
    const promise = new Promise<T>((r) => {
      resolve = r
    })
    return { promise, resolve }
  }

  const params = { project_id: "p_1", task_id: "t_1", eval_id: "e_1" }

  function stub_get(responses: {
    evaluator: unknown
    configs: unknown
  }): typeof client.GET {
    return vi.fn((url: string) => {
      if (url.endsWith("/eval_configs")) {
        return Promise.resolve(responses.configs)
      }
      return Promise.resolve(responses.evaluator)
    }) as unknown as typeof client.GET
  }

  it("returns the eval's default judge and selects it", async () => {
    const get = stub_get({
      evaluator: {
        data: { id: "e_1", current_config_id: "ec_2" },
        error: undefined,
      },
      configs: {
        data: [{ id: "ec_1" }, { id: "ec_2" }],
        error: undefined,
      },
    })
    const result = await load_eval_judges(get, params, () => true)
    expect(result.stale).toBe(false)
    if (result.stale) throw new Error("unexpected stale")
    expect(result.default_eval_config_id).toBe("ec_2")
    expect(result.selected_eval_config_id).toBe("ec_2")
    expect(result.eval_configs.map((c) => c.id)).toEqual(["ec_1", "ec_2"])
  })

  it("falls back to the first judge when the eval has no default", async () => {
    const get = stub_get({
      evaluator: {
        data: { id: "e_1", current_config_id: null },
        error: undefined,
      },
      configs: {
        data: [{ id: "ec_1" }, { id: "ec_2" }],
        error: undefined,
      },
    })
    const result = await load_eval_judges(get, params, () => true)
    if (result.stale) throw new Error("unexpected stale")
    expect(result.default_eval_config_id).toBeNull()
    expect(result.selected_eval_config_id).toBe("ec_1")
  })

  it("bails out as stale when the eval changes during the first GET", async () => {
    let is_current = true
    const evaluator = deferred<unknown>()
    const get = vi.fn(() => evaluator.promise) as unknown as typeof client.GET
    const pending = load_eval_judges(get, params, () => is_current)
    // User switches evals before the first response resolves.
    is_current = false
    evaluator.resolve({
      data: { id: "e_1", current_config_id: "ec_2" },
      error: undefined,
    })
    const result = await pending
    expect(result.stale).toBe(true)
    // The second GET must not even be issued once we know we are stale.
    expect(get).toHaveBeenCalledTimes(1)
  })

  it("bails out as stale when the eval changes during the configs GET", async () => {
    let is_current = true
    const configs = deferred<unknown>()
    const get = vi.fn((url: string) => {
      if (url.endsWith("/eval_configs")) {
        return configs.promise
      }
      return Promise.resolve({
        data: { id: "e_1", current_config_id: "ec_2" },
        error: undefined,
      })
    }) as unknown as typeof client.GET
    const pending = load_eval_judges(get, params, () => is_current)
    // Let the first (evaluator) GET resolve, then switch evals.
    await Promise.resolve()
    await Promise.resolve()
    is_current = false
    configs.resolve({ data: [{ id: "ec_1" }], error: undefined })
    const result = await pending
    expect(result.stale).toBe(true)
  })

  it("throws when an in-flight (still current) request errors", async () => {
    const get = stub_get({
      evaluator: { data: undefined, error: { message: "boom" } },
      configs: { data: [], error: undefined },
    })
    await expect(load_eval_judges(get, params, () => true)).rejects.toEqual({
      message: "boom",
    })
  })
})
