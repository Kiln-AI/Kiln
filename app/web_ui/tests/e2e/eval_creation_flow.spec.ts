import { test, expect } from "./fixtures"

/**
 * The eval creation flow:
 *   workflow gate -> template -> judge picker -> create form
 *
 * Only the desired behaviour and issue templates offer a judge choice; every
 * other template's judge is implied (LLM judge, except tool call) and skips
 * the picker. A non-LLM judge creates an eval with no spec: the judge never
 * reads a written rubric, so no spec fields are asked for.
 */

test("manual workflow: template -> judge picker -> non-LLM judge creates a spec-less eval", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Create Eval always lands on the workflow gate, even without Kiln Pro
  await page.goto(`/specs/${project.id}/${task.id}`)
  await page.getByRole("button", { name: "Create Eval" }).first().click()
  await expect(page).toHaveURL(/select_workflow/)
  await expect(
    page.getByRole("button", { name: "Create Manually", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Use Kiln Pro", exact: true }),
  ).toBeVisible()

  await page
    .getByRole("button", { name: "Create Manually", exact: true })
    .click()
  await expect(page).toHaveURL(/select_template\?workflow=manual/)

  // The issue template is one of the two that shows the judge picker
  await page.getByText("Issue", { exact: true }).first().click()
  await expect(page).toHaveURL(/select_judge\?type=issue&workflow=manual/)
  await expect(page.getByText("LLM as Judge", { exact: true })).toBeVisible()

  // A non-LLM judge: name + the judge's own config, and nothing else
  await page.getByText("Pattern Match").first().click()
  await expect(page).toHaveURL(/spec_builder\?.*judge=pattern_match/)
  await expect(
    page.getByText("Judge Configuration", { exact: true }),
  ).toBeVisible()
  await expect(page.getByLabel("Eval Name")).toBeVisible()
  await expect(page.getByRole("button", { name: "Save Eval" })).toBeVisible()

  // No spec is created for this flow, so no spec fields are asked for, and the
  // Kiln Pro path is absent because the user chose Manual.
  await expect(page.getByText("Issue Description")).toHaveCount(0)
  await expect(page.getByText("Issue Examples")).toHaveCount(0)
  await expect(page.getByRole("button", { name: /Kiln Pro/ })).toHaveCount(0)

  await page.getByLabel("Eval Name").fill("No Hate Regex")
  await page.locator("#pattern_match_pattern").fill("\\bhate\\b")
  await page.getByRole("button", { name: "Save Eval" }).click()

  // Lands on the eval's detail page under the spec-less ("legacy") route
  await expect(page).toHaveURL(
    new RegExp(`/specs/${project.id}/${task.id}/legacy/[^/?]+$`),
    { timeout: 15000 },
  )

  // No spec was created
  const specs = await (
    await apiRequest.get(`/api/projects/${project.id}/tasks/${task.id}/specs`)
  ).json()
  expect(specs.length).toBe(0)

  // The eval carries the template, generated filters, and priority/status
  const evals = await (
    await apiRequest.get(`/api/projects/${project.id}/tasks/${task.id}/evals`)
  ).json()
  expect(evals.length).toBe(1)
  const evaluator = evals[0]
  expect(evaluator.template).toBe("kiln_issue")
  expect(evaluator.priority).toBe(1)
  expect(evaluator.status).toBe("active")
  expect(evaluator.eval_set_filter_id).toBe("tag::eval_no_hate_regex")
  expect(evaluator.train_set_filter_id).toBe("tag::train_no_hate_regex")

  // The judge was created with the eval and set as its default, so the eval
  // is ready to run rather than "Not Ready - Configure".
  const configs = await (
    await apiRequest.get(
      `/api/projects/${project.id}/tasks/${task.id}/evals/${evaluator.id}/eval_configs`,
    )
  ).json()
  expect(configs.length).toBe(1)
  expect(configs[0].properties.type).toBe("pattern_match")
  expect(configs[0].properties.pattern).toBe("\\bhate\\b")
  expect(evaluator.current_config_id).toBe(configs[0].id)

  // The list page shows the spec-less eval with an editable priority/status
  // and "None" in the template column (never "Legacy").
  await page.goto(`/specs/${project.id}/${task.id}`)
  const row = page.getByRole("row", { name: /No Hate Regex/ })
  await expect(row.getByText("None", { exact: true }).first()).toBeVisible()
  await expect(row.getByLabel("Priority")).toHaveText(/P1/)
  await expect(row.getByLabel("Status")).toHaveText(/Active/)
  await expect(page.getByText("Legacy")).toHaveCount(0)
})

test("rubric templates skip the judge picker and go to the LLM judge spec form", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(
    `/specs/${project.id}/${task.id}/select_template?workflow=manual`,
  )
  await page.getByText("Toxicity", { exact: true }).first().click()

  // Straight to the full template form: only issue and desired behaviour
  // templates offer a judge choice; the rest are LLM judged.
  await expect(page).toHaveURL(/spec_builder\?.*judge=llm_judge/)
  await expect(page).toHaveURL(/type=toxicity/)
  await expect(
    page.getByText("Toxicity Examples", { exact: true }),
  ).toBeVisible()
})

test("tool call template skips the tool dialog and the judge picker", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(
    `/specs/${project.id}/${task.id}/select_template?workflow=manual`,
  )
  await page.getByText("Appropriate Tool Use", { exact: true }).first().click()

  // Straight to the builder with the tool call judge prefilled: the judge carries
  // its own expected-tool list, so there's nothing to pick up front.
  await expect(page).toHaveURL(/spec_builder\?.*judge=tool_call_check/)
  await expect(page.getByText("Tool for this Eval")).toHaveCount(0)
  await expect(
    page.getByText("Judge Configuration", { exact: true }),
  ).toBeVisible()
  await expect(page.getByText("Expected Tools", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Save Eval" })).toBeVisible()
})

test("kiln pro without an account routes to the connect page", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/specs/${project.id}/${task.id}/select_workflow`)
  await page.getByRole("button", { name: "Use Kiln Pro", exact: true }).click()
  await expect(page).toHaveURL(/\/specs\/pro_auth/)

  // A malformed workflow param must fall back to manual, never surfacing Kiln Pro
  await page.goto(
    `/specs/${project.id}/${task.id}/spec_builder?type=toxicity&workflow=GARBAGE`,
  )
  await expect(page.getByRole("button", { name: "Create Eval" })).toBeVisible()
  await expect(page.getByRole("button", { name: /Kiln Pro/ })).toHaveCount(0)

  // The judge picker with no template bounces back to the template list
  await page.goto(
    `/specs/${project.id}/${task.id}/select_judge?workflow=manual`,
  )
  await expect(page).toHaveURL(/select_template/)
})

/**
 * The create form arrives pre-filled (autofilled name, judge defaults), so the
 * unsaved-changes guard has to key off real user edits -- otherwise just
 * opening the page and going back warns.
 */
function trackDialogs(page: import("@playwright/test").Page): string[] {
  const dialogs: string[] = []
  page.on("dialog", async (d) => {
    dialogs.push(d.message())
    await d.accept()
  })
  return dialogs
}

test("leaving an untouched create form does not warn about unsaved changes", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask
  const dialogs = trackDialogs(page)

  await page.goto(
    `/specs/${project.id}/${task.id}/select_judge?type=issue&workflow=manual`,
  )
  await page.getByText("Pattern Match").first().click()
  await expect(page.getByRole("button", { name: "Save Eval" })).toBeVisible()

  await page.goBack()
  await page.waitForTimeout(750)
  await expect(page).toHaveURL(/select_judge/)
  expect(dialogs, "must not warn when nothing was touched").toEqual([])
})

test("leaving after editing the judge warns about unsaved changes", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask
  const dialogs = trackDialogs(page)

  await page.goto(
    `/specs/${project.id}/${task.id}/select_judge?type=issue&workflow=manual`,
  )
  await page.getByText("Pattern Match").first().click()
  await page.locator("#pattern_match_pattern").fill("^ok$")

  await page.goBack()
  await page.waitForTimeout(750)
  expect(dialogs.length, "must warn after editing the judge").toBe(1)
  expect(dialogs[0]).toContain("unsaved changes")
})

test("code judge: untouched does not warn, edited code does", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask
  const dialogs = trackDialogs(page)

  // The code editor doesn't emit bubbling input events, so it's tracked by value.
  await page.goto(
    `/specs/${project.id}/${task.id}/select_judge?type=issue&workflow=manual`,
  )
  await page.getByText("Code", { exact: true }).first().click()
  await expect(page.getByRole("button", { name: "Save Eval" })).toBeVisible()
  await page.goBack()
  await page.waitForTimeout(750)
  expect(dialogs, "must not warn when the code is untouched").toEqual([])

  await page.goForward()
  await expect(page.getByRole("button", { name: "Save Eval" })).toBeVisible()
  await page.locator(".cm-content").click()
  await page.keyboard.type("# scoring")
  await page.goBack()
  await page.waitForTimeout(750)
  expect(dialogs.length, "must warn after a code edit").toBe(1)
})
