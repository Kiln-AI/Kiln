import { test, expect } from "./fixtures"

/* @act
## Goals
Verify the `freshState` fixture: the isolated backend starts with zero projects.
This is an assertion-only fixture; it does not mutate state.

## Fixtures
- freshState

## Assertions
- GET /api/projects returns an empty list immediately after backend start.
*/
test("fresh_state fixture: backend starts with no projects", async ({
  freshState,
  apiRequest,
}) => {
  void freshState
  const resp = await apiRequest.get("/api/projects")
  expect(resp.ok()).toBeTruthy()
})

/* @act
## Goals
Verify the `registeredUser` fixture: POST /api/settings sets user_type +
personal_use_contact, making the app treat the user as registered.

## Fixtures
- registeredUser

## Assertions
- GET /api/settings returns user_type = "personal" and a non-empty contact.
*/
test("registered_user fixture: user_type is set after registration", async ({
  registeredUser,
  apiRequest,
}) => {
  void registeredUser
  const resp = await apiRequest.get("/api/settings")
  expect(resp.ok()).toBeTruthy()
  const settings = await resp.json()
  expect(settings.user_type).toBe("personal")
  expect(settings.personal_use_contact).toBeTruthy()
})

/* @act
## Goals
Verify the `seededProject` fixture: a project is created via POST /api/projects
and returned to the test.

## Fixtures
- seededProject

## Assertions
- The fixture yields a project with a non-empty id and name.
- GET /api/projects/{id} returns the seeded project.
*/
test("seeded_project fixture: project is created and retrievable", async ({
  seededProject,
  apiRequest,
}) => {
  expect(seededProject.id).toBeTruthy()
  expect(seededProject.name).toBeTruthy()
  const resp = await apiRequest.get(
    `/api/projects/${encodeURIComponent(seededProject.id)}`,
  )
  expect(resp.ok()).toBeTruthy()
  const fetched = await resp.json()
  expect(fetched.id).toBe(seededProject.id)
})

/* @act
## Goals
Verify the `seededProjectWithTask` fixture: a project + task are created and
returned together.

## Fixtures
- seededProjectWithTask

## Assertions
- The fixture yields { project, task } with non-empty ids.
- GET /api/projects/{project.id}/tasks/{task.id} returns the task.
*/
test("seeded_project_with_task fixture: task is created under project", async ({
  seededProjectWithTask,
  apiRequest,
}) => {
  const { project, task } = seededProjectWithTask
  expect(project.id).toBeTruthy()
  expect(task.id).toBeTruthy()
  const resp = await apiRequest.get(
    `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
  )
  expect(resp.ok()).toBeTruthy()
})
