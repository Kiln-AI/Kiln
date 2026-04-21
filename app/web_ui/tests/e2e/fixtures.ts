import { test as base, expect, type APIRequestContext } from "@playwright/test"
import { randomUUID } from "crypto"
import { BACKEND_URL, KILN_SERVER_MOCK_URL, MOCK_PROVIDER_URL } from "./ports"
import {
  MockProviderClient,
  MOCK_MODEL_ID,
  MOCK_MODEL_NAME,
  MOCK_PROVIDER_NAME,
} from "./mock_provider/client"
import {
  COPILOT_TEST_API_KEY,
  MockKilnServerClient,
} from "./mock_kiln_server/client"

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

export type ConnectedMockProvider = {
  providerName: string
  modelId: string
  modelName: string
  modelProviderName: "openai_compatible"
}

type Fixtures = {
  apiRequest: APIRequestContext
  cleanBackend: void
  registeredUser: void
  seededProject: SeededProject
  seededProjectWithTask: { project: SeededProject; task: SeededTask }
  mockInferenceProvider: MockProviderClient
  connectedMockProvider: ConnectedMockProvider
  mockKilnServer: MockKilnServerClient
  seededCopilotKey: string
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

  mockInferenceProvider: async ({ playwright }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: MOCK_PROVIDER_URL,
    })
    const client = new MockProviderClient(ctx)
    await client.reset()
    await use(client)
    await client.reset()
    await ctx.dispose()
  },

  connectedMockProvider: async ({ apiRequest, mockInferenceProvider }, use) => {
    void mockInferenceProvider
    // DELETE-then-POST keeps this idempotent across tests that share a backend.
    await apiRequest
      .delete(
        `/api/provider/openai_compatible?name=${encodeURIComponent(MOCK_PROVIDER_NAME)}`,
      )
      .catch(() => {})
    const resp = await apiRequest.post("/api/provider/openai_compatible", {
      data: {
        name: MOCK_PROVIDER_NAME,
        base_url: `${MOCK_PROVIDER_URL}/v1`,
        api_key: "NA",
      },
    })
    expect(
      resp.ok(),
      "POST /api/provider/openai_compatible register mock",
    ).toBeTruthy()

    await use({
      providerName: MOCK_PROVIDER_NAME,
      modelId: MOCK_MODEL_ID,
      modelName: MOCK_MODEL_NAME,
      modelProviderName: "openai_compatible",
    })

    await apiRequest
      .delete(
        `/api/provider/openai_compatible?name=${encodeURIComponent(MOCK_PROVIDER_NAME)}`,
      )
      .catch(() => {})
  },

  mockKilnServer: async ({ playwright }, use) => {
    const ctx = await playwright.request.newContext({
      baseURL: KILN_SERVER_MOCK_URL,
    })
    const client = new MockKilnServerClient(ctx)
    await client.reset()
    await use(client)
    await client.reset()
    await ctx.dispose()
  },

  // Writes a stable test API key to Config.kiln_copilot_api_key so the backend
  // will treat the user as "copilot-connected" and route authenticated calls
  // through the mock kiln-server. Bypasses the real OAuth/Kinde signup flow.
  seededCopilotKey: async ({ apiRequest }, use) => {
    const resp = await apiRequest.post("/api/settings", {
      data: { kiln_copilot_api_key: COPILOT_TEST_API_KEY },
    })
    expect(resp.ok(), "POST /api/settings seed copilot key").toBeTruthy()
    await use(COPILOT_TEST_API_KEY)
    await apiRequest
      .post("/api/settings", { data: { kiln_copilot_api_key: null } })
      .catch(() => {})
  },
})

export { expect }
