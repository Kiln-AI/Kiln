---
status: complete
---

# Agent Approvals

I want to implement a new project. We’re adding a agentic chat client which can call this FastAPI API (/app/desktop/server and which includes the API in /libs/server as well). We want to control what the agent can run, can’t run, and when it requires user approval. 

## API-Side

### Technical Means for Annotating Endpoints

We want to use openapi_extra style API annotation (just a rough example):
```
@app.post("/payments/", tags=["payments"], openapi_extra={"x-agent-policy": {"approval": "required", "reason": "financial transaction"}} )
```

### Annotations

Approx tags/states:
- `permission` - allow or deny. If deny, the agent can’t call this API.
- `requires-approval` - agents can initiate this, but the user must hit approve
- `approval-explanation` - a string to use in the UI, we can show this user. “Running the Prompt Optimizer costs $75, are you sure you want to proceed?”. Only applies when the endpoint requires approval. Constructors should error if you set this without `requires-approval`, or if this is missing when that flag is set.

This is rough, propose ideal design in functional spec.

### Constructors

While openapi_extra is just `dict[str, Any]` we don’t want to risk typos. We want some constructors/helpers to ensure getting it right.

Rough idea, but actual annotations are wrong/just examples:
```
from pydantic import BaseModel
from typing import Literal

class AgentPolicy(BaseModel):
    approval: Literal["required", "none"] = "none"
    permission: Literal["allow", "deny"] = "allow"
    reason: str | None = None

def agent_policy(**kwargs) -> dict:
    return {"x-agent-policy": AgentPolicy(**kwargs).model_dump(exclude_none=True)}
```

Refactor this into one matching this spec, including proper names, better structured, validators (explanation required, etc), etc.

The endpoints use clean constants, or constructors with no chance of passing the wrong values, for example:
- `openapi_extra=DENY_AGENT` // permission=deny constant.
- `openapi_extra=ALLOW_AGENT` // permission=allow, approval=false
- `openapi_extra=agent_policy_require_approval('approval reason')`
- need more? That might be it.

This should live in `libs/server/kiln_server/utils/agent_checks/...`. 

Import it and use it across `libs/server/...` API, and the `app/desktop/server/...` API.

## Annotation Checking

We’re going to keep adding removing APIs over time. The APIs live on the client, but the server is running the agent. This leads to a painful reality: there may be several versions of the client live at any time, and the server may need to know about any number of URLs/endpoints.

We want to:
- Build a CLI that dumps information about our APIs 
- build a helper method that can return annotation information from a url

### Annotation Dumping

Build a CLI that dumps information about our APIs into a folder of JSON objects. It reads a openapi.json file (pass it a URL), and generates a json annotation per API into a target folder (passed via CLI).

Why folder of small JSON objects: it’s durable for adding/removing APIs. We want old APIs to stick around, new APIs to be added, and changes to trigger git conflicts. 1 file per endpoint gives us that.

The json data should have 
- a name derived from the endpoint: `[method]_[endpoint].json`, which will be consistent unless endpoint/method change, and normalize any unallowed chars.
- Contents of JSON:
  - Method: get, put, patch, delete, etc
  - URL: eg `/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start` (confirm the best format)
  - permissions: a set of flags that align to our annotations.
- Error checking: check for invalid states.

The CLI should warn if endpoints are missing annotation, and list them so the user can fix it. It should return exit code 345 if there are unannotated endpoints.

Write this CLI in `/libs/desktop/server/agent_checks/...`. It will be run offline by our devs, but this is a good place for it. The actual the target folder will be saved in the server, not that it matters for the implementation/tests. 

### Helper to get Annotations

We need a helper to take a http method (GET/DELETE/POST/PATCH) and URL, then returns what permissions are allow (allowed, deny, requires approval w explanation, etc).

- Initialize an instance, pointing to the folder of JSONs
- Cache json in memory so we don’t keep making disk-reads. Lazy load is fine.
- Fail safe: it should fully block any APIs it’s not aware of (no annotation), raising an exception.

Write this CLI in `/libs/desktop/server/agent_checks/...`. It will be imported and used by our server, but it can live and be tested here so we implement the project in a single repo.

## Policy/Backfill

As a later step of this project: run our CLI, see missing endpoints, and do a loop annotating them until there are no-unannotated endpoints.

- DELETE endpoints: deny by default
- GET/POST endpoints: allow by default:
- PATCH endpoints: approve by default, with message “Allow agent to edit [NAME]? Ensure you backup your project before allowing agentic edits.”
- "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start" - approve with message “Running prompt optimizer uses many credits

## CI

We have existing CI for checking openapi.json (“check-api-binding”), extend it to look for unannotated endpoints using the CLI, and checking the exit code.
