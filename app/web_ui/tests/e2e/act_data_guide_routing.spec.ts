import { test, expect } from "./fixtures"

/* @act
## Goals
With no saved data guide, navigating directly to /data_guide must redirect to
/data_guide_setup. The saved-guide page renders only when a guide exists; for
an empty task, it forwards to the setup wizard so deep-links / bookmarks land
somewhere usable.

## Fixtures
- seededProjectWithTask

## Hints
- Guard lives in data_guide/+page.svelte: if both examples_md and rules_md
  are empty/whitespace, goto /data_guide_setup with replaceState.
- No backend write needed — a fresh task has no data guide.

## Assertions
- After page.goto on /data_guide, the final URL ends with /data_guide_setup.
*/
test("/data_guide redirects to setup when no guide exists", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/generate/${project.id}/${task.id}/data_guide`)
  await expect(page).toHaveURL(
    `/generate/${project.id}/${task.id}/data_guide_setup`,
  )
})

/* @act
## Goals
A direct hit on /data_guide/refine without the in-memory handoff store seeded
must redirect to /data_guide. The refine flow only makes sense as a
continuation of the saved-guide page's "Test Data Guide" action, so a deep
link / bookmark / hard refresh on /refine should bounce back rather than
showing an empty refine UI.

## Fixtures
- seededProjectWithTask
- apiRequest

## Hints
- Pre-seed a guide via PUT /api/projects/:pid/tasks/:tid/data_gen_guide so
  the redirect target /data_guide doesn't bounce again to setup (which
  happens when the guide is empty).
- Guard is in data_guide/refine/+page.svelte onMount: if get(handoff_store)
  is null, goto /data_guide.

## Assertions
- After page.goto on /data_guide/refine, the final URL ends with /data_guide.
*/
test("/data_guide/refine direct hit redirects to /data_guide", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  const putResp = await apiRequest.put(
    `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/data_gen_guide`,
    {
      data: {
        examples_md:
          "## Example 1\n```input\nHello\n```\n\n```output\nHi there\n```",
        rules_md: "Be concise and friendly.",
      },
    },
  )
  expect(
    putResp.ok(),
    `PUT /data_gen_guide failed: ${putResp.status()} ${await putResp.text()}`,
  ).toBeTruthy()

  await page.goto(`/generate/${project.id}/${task.id}/data_guide/refine`)
  await expect(page).toHaveURL(`/generate/${project.id}/${task.id}/data_guide`)
})
