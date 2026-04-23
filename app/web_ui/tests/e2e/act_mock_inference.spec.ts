import { test, expect } from "./fixtures"

/* @act
## Goals
Sanity-check the inference mock: with a custom openai_compatible provider registered
against the localhost mock server, POSTing to /api/projects/:pid/tasks/:tid/run routes
the inference call through the mock and returns the canned content as the task's output.

This test verifies the full plumbing of Phase 1 inference mocking:
  1. mockInferenceProvider fixture: queue/reset against the mock admin surface.
  2. connectedMockProvider fixture: registers the mock via POST /api/provider/openai_compatible.
  3. Kiln backend resolves "mock::mock-chat" / openai_compatible to a litellm call whose
     base_url points at the mock, and returns the mock's canned content as TaskRun.output.output.

## Fixtures
- seededProjectWithTask
- connectedMockProvider
- mockInferenceProvider

## Assertions
- /run returns 200 with output.output equal to the queued content.
- The mock received exactly one POST /v1/chat/completions whose body.model echoes "mock-chat".
*/
test("inference mock: POST /run returns the canned response via the mock provider", async ({
  apiRequest,
  seededProjectWithTask,
  connectedMockProvider,
  mockInferenceProvider,
}) => {
  const { project, task } = seededProjectWithTask
  const cannedContent = `act-mock-${Date.now()}-hello world`

  await mockInferenceProvider.queue({ content: cannedContent })

  const runResp = await apiRequest.post(
    `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/run`,
    {
      data: {
        run_config_properties: {
          type: "kiln_agent",
          model_name: connectedMockProvider.modelName,
          model_provider_name: connectedMockProvider.modelProviderName,
          prompt_id: "simple_prompt_builder",
          structured_output_mode: "default",
        },
        plaintext_input: "Hello from the sanity test",
      },
    },
  )

  expect(
    runResp.ok(),
    `POST /run failed: ${runResp.status()} ${await runResp.text()}`,
  ).toBeTruthy()
  const body = (await runResp.json()) as { output: { output: string } }
  expect(body.output.output).toBe(cannedContent)

  const state = await mockInferenceProvider.state()
  const completions = state.requests.filter(
    (r) => r.method === "POST" && r.path === "/v1/chat/completions",
  )
  expect(completions.length, "mock received exactly one completion call").toBe(
    1,
  )
  const reqBody = completions[0].body as { model?: string }
  expect(reqBody.model).toBe(connectedMockProvider.modelId)
})
