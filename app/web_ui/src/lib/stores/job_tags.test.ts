import { describe, it, expect } from "vitest"
import type { JobRecord } from "$lib/stores/jobs_api"
import { back_url_for, eval_tag } from "./job_tags"

function make_job(over: Partial<JobRecord>): JobRecord {
  return {
    id: "j_x",
    type: "eval",
    status: "running",
    progress: { total: 10, success: 0, error: 0, updated_at: "now" },
    params: {},
    result: null,
    error: null,
    metadata: {},
    project_id: "p1",
    supports_pause: true,
    created_at: "now",
    updated_at: "now",
    started_at: "now",
    ended_at: null,
    run_id: "r1",
    ...over,
  } as JobRecord
}

describe("back_url_for", () => {
  it("returns null for an untagged job", () => {
    expect(back_url_for(make_job({}))).toBeNull()
  })

  it("returns null when the record has no project_id", () => {
    const job = make_job({
      project_id: null,
      metadata: {
        tag: eval_tag({
          task_id: "t1",
          spec_id: "s1",
          eval_id: "e1",
          eval_config_id: "c1",
          run_config_id: "r1",
        }),
      },
    })
    expect(back_url_for(job)).toBeNull()
  })

  it("returns the compare_run_configs URL for an eval tag with spec_id", () => {
    const job = make_job({
      project_id: "p1",
      metadata: {
        tag: eval_tag({
          task_id: "t1",
          spec_id: "s1",
          eval_id: "e1",
          eval_config_id: "c1",
          run_config_id: "r1",
        }),
      },
    })
    expect(back_url_for(job)).toBe("/specs/p1/t1/s1/e1/compare_run_configs")
  })

  it("falls back to the task page when spec_id is missing", () => {
    const job = make_job({
      project_id: "p1",
      metadata: {
        tag: eval_tag({
          task_id: "t1",
          spec_id: null,
          eval_id: "e1",
          eval_config_id: "c1",
          run_config_id: "r1",
        }),
      },
    })
    expect(back_url_for(job)).toBe("/specs/p1/t1")
  })

  it("returns null for kinds without a canonical page yet", () => {
    const rag_job = make_job({
      metadata: { tag: { kind: "rag", rag_config_id: "rcfg" } },
    })
    const ft_job = make_job({
      metadata: { tag: { kind: "finetune", finetune_id: "ft1" } },
    })
    expect(back_url_for(rag_job)).toBeNull()
    expect(back_url_for(ft_job)).toBeNull()
  })
})
