import { test as base, expect, type APIRequestContext } from "@playwright/test"
import { randomUUID } from "crypto"
import { BACKEND_URL } from "./ports"

export type SeededProject = {
  id: string
  name: string
  description: string | null
  path?: string
}

export type SeededTask = {
  id: string
  name: string
  instruction: string
}

type Fixtures = {
  apiRequest: APIRequestContext
  cleanBackend: void
  registeredUser: void
  seededProject: SeededProject
  seededProjectWithTask: { project: SeededProject; task: SeededTask }
}

export const test = base.extend<Fixtures>({
  apiRequest: async ({ playwright }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: BACKEND_URL,
    })
    await use(ctx)
    await ctx.dispose()
  },

  cleanBackend: async ({ apiRequest }, use) => {
    const listResp = await apiRequest.get("/api/projects")
    if (listResp.ok()) {
      const projects = (await listResp.json()) as Array<{ id: string }>
      for (const p of projects) {
        await apiRequest
          .delete(`/api/delete_project/${encodeURIComponent(p.id)}`)
          .catch(() => {})
      }
    }
    await apiRequest
      .post("/api/settings", {
        data: {
          user_type: null,
          personal_use_contact: null,
          work_use_contact: null,
        },
      })
      .catch(() => {})

    const verify = await apiRequest.get("/api/projects")
    expect(verify.ok(), "GET /api/projects after reset").toBeTruthy()
    const remaining = (await verify.json()) as unknown[]
    expect(
      remaining.length,
      "projects should be empty after cleanBackend",
    ).toBe(0)

    await use()
  },

  registeredUser: async ({ apiRequest, cleanBackend }, use) => {
    void cleanBackend
    const resp = await apiRequest.post("/api/settings", {
      data: {
        user_type: "personal",
        personal_use_contact: `act+${randomUUID()}@example.com`,
      },
    })
    expect(resp.ok(), "POST /api/settings register").toBeTruthy()
    await use()
  },

  seededProject: async ({ apiRequest, cleanBackend }, use) => {
    void cleanBackend
    const name = `Act Test Project ${randomUUID().slice(0, 8)}`
    const resp = await apiRequest.post("/api/projects", {
      data: { name, description: "ActRight fixture project" },
    })
    expect(resp.ok(), "POST /api/projects").toBeTruthy()
    const project = (await resp.json()) as SeededProject
    await use(project)
    await apiRequest
      .delete(`/api/delete_project/${encodeURIComponent(project.id)}`)
      .catch(() => {})
  },

  seededProjectWithTask: async (
    { apiRequest, page, seededProject: project },
    use,
  ) => {
    const taskName = `Act Task ${randomUUID().slice(0, 8)}`
    const resp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks`,
      {
        data: {
          name: taskName,
          instruction: "ActRight fixture task instruction.",
        },
      },
    )
    expect(resp.ok(), "POST /api/projects/:id/tasks").toBeTruthy()
    const task = (await resp.json()) as SeededTask

    await page.addInitScript(
      ([pid, tid]) => {
        localStorage.setItem(
          "ui_state",
          JSON.stringify({
            current_project_id: pid,
            current_task_id: tid,
            selected_model: null,
          }),
        )
      },
      [project.id, task.id] as const,
    )

    await use({ project, task })
    await apiRequest
      .delete(
        `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
      )
      .catch(() => {})
  },
})

export { expect }
