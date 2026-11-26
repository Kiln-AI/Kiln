# Calling the Kiln API

These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them.

`call_kiln_api` takes `method`, `url_path`, and optionally `body`, `query_params`, `jq_filter`, `body_limit` and `save_to_tmpfile`. Kiln Harness Tuner loop agents do not have this tool: they reach Kiln through the loop gateway.

**Making a call:**

- **`method` and `url_path` are the two things you look up.** Take them from the catalogue row exactly as printed, substituting ids inline: `call_kiln_api(method="GET", url_path="/api/projects/{project_id}/tasks/{task_id}/runs")`.
- **Query arguments go in `query_params`**, never as `?key=value` in `url_path`: `call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/runs", query_params={"page_size": "50"})`. App links in your reply still use `?` normally.
- **`body` is the request body**, a dict shaped by the endpoint doc. Do not guess a body from an endpoint's name.
- **`jq_filter` is raw jq** applied to the response — see below.
- **A non-2xx answer is data.** A result with a `status_code` of 400 or more is the API's own error. Read the body and act on it; it is not a failure of the tool.
- **An event stream that ends does not mean the work succeeded.** A streaming endpoint returns when its stream ends. Then read the status of the job or the resource, and its errors.

**Finding the endpoint:**

1. Route by intent in `references/knowledge/api_docs/api_index.md` and read the catalogue it names. Each knowledge file also lists the docs of its workflows.
2. Pick the row whose path and method match what you want. Its **last column** names that endpoint's doc.
3. **Read `references/knowledge/api_docs/<file name>` before you call.** Every endpoint doc sits directly in that one flat folder. Parameters, body fields, enums and the response shape live only there — never in the catalogue row and never in this file.

Calling from memory of a catalogue row, or from this file, is the failure mode the endpoint docs exist to prevent. One extra read costs less than one wrong call. When no catalogue lists a path, the endpoint does not exist; say so instead of guessing. Never guess a request body, a response field or a path.

**Writing a `jq_filter`:** responses are large — run, model and document payloads especially. Filter every call down to the fields you actually need; the paging and filter parameters of the endpoint, and `save_to_tmpfile` (a file path in place of the body), help too. List before detail: pull the IDs and names first, then drill into one item.

- **Quote the endpoint doc's 200-response shape before writing the filter.** `array of X` → `.[] | {fields}`. A named wrapper (`data`, `items`) → `.wrapper[]`. Never write `.items[]` unless the documented shape has that key.
- `jq_filter` is raw jq inside a JSON string. Do not wrap it in shell quotes and do not quote field paths — `".output.output"` becomes a literal string. Correct: `{id, output: .output.output}`.

**Diagnose before you retry.** A failed call is a **reading** problem, not a phrasing problem. Literal-string output, a filter echoed back at you, `Cannot index array with string '…'`, or a null where you expected a value all mean the shape you assumed is not the shape the endpoint returns. The same entity can carry different field paths on different endpoints — an aggregate snapshot is not the full entity list. **Before re-issuing a failed call, quote in your reasoning the specific line of that endpoint's doc that names the correct field path.** A retry without that cite is a violation whether or not the file is already in context; the cite is what makes "re-read the doc" observable rather than a no-op. A second guess from memory is banned, and so is abandoning this tool for a shell after one failure.

**Also:**

- **Reuse what you have.** A response already in the conversation stays valid until something changed it. Call again only when the data may have changed (a write since, an error, or the user asks about the current state).
- **Rate limits.** A provider `429` or "rate limit exceeded" is a transient error and a signal to slow down. Run fewer calls at once and retry. It is never a reason to switch the model or the provider: the user may be held to one provider, and a switch changes what you measure.
