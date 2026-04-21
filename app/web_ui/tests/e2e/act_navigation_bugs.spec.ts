import { test, expect } from "./fixtures"

/* @act
## Goals
Regression guard for KIL-521: opening a deeplink to a prompt that was created after
the prompts store was populated must still render the prompt's details. Today, only
the parent /prompts/:pid/:tid page force-refreshes the current_task_prompts store;
a deeplink straight to /prompts/:pid/:tid/saved/:prompt_id relies on whatever the
store happens to hold, so a prompt created via the chat/API after initial load is
missing and the page shows "Prompt not found."

Reproduction (direct, no chat UI): load the parent prompts page to populate the
store, create a new prompt via POST /api/projects/:pid/tasks/:tid/prompts, then
client-side-navigate (anchor click, not page.goto which would remount and re-load
the store fresh) to the new prompt's deeplink.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- POST /api/projects/:pid/tasks/:tid/prompts returns a Prompt whose .id is a bare
  UUID. The saved-prompt URL expects the "id::<uuid>" PromptId form, URL-encoded.
- The parent /prompts/:pid/:tid page calls load_task_prompts(..., force=true) on
  mount; the saved detail page does not.
- page.goto() would force a full reload and bypass the stale-store bug, so we
  must navigate via an <a> click so SvelteKit keeps the existing store state.
- The saved detail page renders "Prompt not found." when the store lacks the id.

## Assertions
- After the client-side navigation, the prompt's name is visible on the page.
- "Prompt not found." is NOT visible.
*/
test("KIL-521: deeplink to newly-created prompt resolves without first visiting parent page", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Prime the prompts store by visiting the parent prompts page.
  await page.goto(`/prompts/${project.id}/${task.id}`)
  await expect(
    page.getByRole("heading", { name: "Prompts", exact: true }),
  ).toBeVisible()

  // Create a new prompt via API AFTER the store has been populated.
  const promptName = `ActRight Deeplink ${Date.now()}`
  const createResp = await apiRequest.post(
    `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
    {
      data: {
        name: promptName,
        description: "Prompt created after store was populated.",
        prompt: "You are a helpful assistant. Answer the question.",
      },
    },
  )
  expect(
    createResp.ok(),
    `POST /prompts failed: ${createResp.status()} ${await createResp.text()}`,
  ).toBeTruthy()
  const created = (await createResp.json()) as { id: string }
  const promptUrlId = encodeURIComponent(`id::${created.id}`)
  const deeplink = `/prompts/${project.id}/${task.id}/saved/${promptUrlId}`

  // Client-side navigation: inject an <a> and click it so SvelteKit does an
  // in-app transition instead of a full reload. A full reload would clear the
  // store and re-fetch prompts, hiding the bug.
  await page.evaluate((href) => {
    const a = document.createElement("a")
    a.setAttribute("href", href)
    a.setAttribute("id", "act-kil521-link")
    a.textContent = "go"
    document.body.appendChild(a)
  }, deeplink)
  await page.locator("#act-kil521-link").click()

  await expect(page).toHaveURL(deeplink)
  await expect(page.getByText("Prompt not found.")).toHaveCount(0)
  await expect(page.getByText(promptName).first()).toBeVisible()
})

/* @act
## Goals
Regression guard for KIL-516: clicking a link from one spec detail page to another
spec detail page must load the second spec. Today the spec detail page fetches its
spec in onMount only (not in a reactive block keyed on $page.params.spec_id), so
when SvelteKit reuses the component for same-route navigation the page keeps
showing the first spec.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- POST /api/projects/:pid/tasks/:tid/specs with {name, definition, properties}
  creates a spec. Valid property shape for spec_type="tone":
    {spec_type, core_requirement, tone_description}
  For "toxicity":
    {spec_type, core_requirement, toxicity_examples}
- The spec detail page title is `Spec: <name>` (rendered as an h-level heading
  via AppPage). Use getByRole("heading", { name: `Spec: <name>` }) to wait.
- Same-route client-side nav must go through an <a> click — page.goto would
  remount the component and mask the bug.

## Assertions
- Visiting specA first shows "Spec: specA.name".
- After client-side nav to specB's URL, the URL updates and the heading becomes
  "Spec: specB.name" (and the old specA heading is gone).
*/
test("KIL-516: spec-to-spec in-app link updates the loaded spec", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  const specA = await createSpec(apiRequest, project.id, task.id, {
    name: `ActToneA_${Date.now()}`,
    definition: "Responses should be professional and friendly.",
    properties: {
      spec_type: "tone",
      core_requirement: "Be professional.",
      tone_description: "Professional and friendly.",
    },
  })
  const specB = await createSpec(apiRequest, project.id, task.id, {
    name: `ActToxB_${Date.now()}`,
    definition: "Responses should not contain toxic content.",
    properties: {
      spec_type: "toxicity",
      core_requirement: "Avoid toxicity.",
      toxicity_examples: "Slurs, insults, threats.",
    },
  })

  await page.goto(`/specs/${project.id}/${task.id}/${specA.id}`)
  await expect(
    page.getByRole("heading", { name: `Spec: ${specA.name}` }),
  ).toBeVisible()

  const specBHref = `/specs/${project.id}/${task.id}/${specB.id}`
  await page.evaluate((href) => {
    const a = document.createElement("a")
    a.setAttribute("href", href)
    a.setAttribute("id", "act-kil516-spec-link")
    a.textContent = "go"
    document.body.appendChild(a)
  }, specBHref)
  await page.locator("#act-kil516-spec-link").click()

  await expect(page).toHaveURL(specBHref)
  await expect(
    page.getByRole("heading", { name: `Spec: ${specB.name}` }),
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: `Spec: ${specA.name}` }),
  ).toHaveCount(0)
})

/* @act
## Goals
Regression guard for KIL-516 (compare view variant): while on the specs compare
page, navigating to the same route with a different query string (?columns=N)
must re-read the URL params. Today initializeFromURL() runs only in onMount, so
a client-side same-route navigation with a new ?columns= keeps the previous
column count.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- /specs/:pid/:tid/compare reads ?columns (2..6) once in onMount via
  initializeFromURL(). The model-selection header has inline
  `style="grid-template-columns: 200px repeat({columns}, 1fr);"` which directly
  reflects the current `columns` value.
- The "Add Column" button only appears after loading finishes; wait on it.
- Use <a> click (not page.goto) so SvelteKit stays in-app.

## Assertions
- At ?columns=2, a cell's style attribute contains "repeat(2, 1fr)".
- After in-app nav to ?columns=4, the URL ends with columns=4 AND the style
  still says "repeat(2, 1fr)" — i.e. today's bug — OR, once fixed, it updates
  to "repeat(4, 1fr)". We assert the fixed behavior so the test fails today and
  passes after the fix.
*/
test("KIL-516: compare view re-reads ?columns on client-side nav", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  const baseHref = `/specs/${project.id}/${task.id}/compare`
  await page.goto(`${baseHref}?columns=2`)
  await expect(page.getByRole("button", { name: "Add Column" })).toBeVisible()

  const gridRow = page
    .locator('[style*="grid-template-columns"]')
    .filter({ hasText: /.*/ })
    .first()
  await expect(gridRow).toHaveAttribute("style", /repeat\(2,\s*1fr\)/)

  const fourHref = `${baseHref}?columns=4`
  await page.evaluate((href) => {
    const a = document.createElement("a")
    a.setAttribute("href", href)
    a.setAttribute("id", "act-kil516-compare-link")
    a.textContent = "go"
    document.body.appendChild(a)
  }, fourHref)
  await page.locator("#act-kil516-compare-link").click()

  await expect(page).toHaveURL(fourHref)
  await expect(gridRow).toHaveAttribute("style", /repeat\(4,\s*1fr\)/)
})

type SpecProperties =
  | {
      spec_type: "tone"
      core_requirement: string
      tone_description: string
    }
  | {
      spec_type: "toxicity"
      core_requirement: string
      toxicity_examples: string
    }

type CreateSpecInput = {
  name: string
  definition: string
  properties: SpecProperties
}

async function createSpec(
  apiRequest: import("@playwright/test").APIRequestContext,
  projectId: string,
  taskId: string,
  input: CreateSpecInput,
): Promise<{ id: string; name: string }> {
  const resp = await apiRequest.post(
    `/api/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/specs`,
    { data: input },
  )
  expect(
    resp.ok(),
    `POST /specs failed: ${resp.status()} ${await resp.text()}`,
  ).toBeTruthy()
  return (await resp.json()) as { id: string; name: string }
}
