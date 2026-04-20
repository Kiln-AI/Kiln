import { test as base, expect, type APIRequestContext } from "@playwright/test"
import { randomUUID } from "crypto"

export const API_BASE_URL = "http://localhost:6535"

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
  freshState: void
  registeredUser: void
  seededProject: SeededProject
  seededProjectWithTask: { project: SeededProject; task: SeededTask }
}

export const test = base.extend<Fixtures>({
  apiRequest: async ({ playwright }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: API_BASE_URL,
    })
    await use(ctx)
    await ctx.dispose()
  },

  freshState: async ({ apiRequest }, use) => {
    const resp = await apiRequest.get("/api/projects")
    expect(resp.ok(), "GET /api/projects").toBeTruthy()
    const body = await resp.json()
    const count = Array.isArray(body)
      ? body.length
      : body?.projects?.length ?? 0
    expect(count, "expected zero seeded projects at test start").toBe(0)
    await use()
  },

  registeredUser: async ({ apiRequest }, use) => {
    const resp = await apiRequest.post("/api/settings", {
      data: {
        user_type: "personal",
        personal_use_contact: `act+${randomUUID()}@example.com`,
      },
    })
    expect(resp.ok(), "POST /api/settings register").toBeTruthy()
    await use()
    await apiRequest
      .post("/api/settings", {
        data: { user_type: null, personal_use_contact: null },
      })
      .catch(() => {})
  },

  seededProject: async ({ apiRequest }, use) => {
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
    { apiRequest, seededProject: project },
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
    await use({ project, task })
    await apiRequest
      .delete(
        `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
      )
      .catch(() => {})
  },
})

export { expect }
