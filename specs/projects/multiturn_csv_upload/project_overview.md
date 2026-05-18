---
status: complete
---

# Multiturn CSV Upload

## What

Extend Kiln's existing CSV bulk upload (`/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload`) to support **multiturn tasks**. Today the endpoint only accepts single-turn rows (`input`, `output`, `reasoning`, `chain_of_thought`, `tags`) and produces one `TaskRun` per row. For multiturn tasks, a single conversation spans multiple user/assistant turns and is represented in the datamodel as a chain of `TaskRun`s linked via `parent_task_run_id`, with the full message history stored in `trace`.

The feature lets users upload a CSV containing multi-turn conversations and have it materialize as the appropriate chain(s) of `TaskRun`s, mirroring the structure produced by the live multiturn run pathway.

## Who / Why

Users who already have conversation datasets (e.g., from another tool, exported chat logs, hand-authored eval sets) and want to bring them into Kiln for evals, fine-tuning prep, or as seed data. Without this, the only way to get multiturn data into Kiln is to run conversations live through a model — there's no bulk import path.

This pairs with the recently shipped multiturn task feature (KIL-632) which added the data model, run flow, conversation rendering, and trace forking UI but left dataset import as the missing piece.

## Constraints from the existing system

- **Multiturn tasks have no structured schemas** — `input_json_schema` and `output_json_schema` are forbidden on `turn_mode=multiturn` tasks. CSV upload is plaintext only.
- **TaskRun chain shape** — Each conversation becomes N `TaskRun`s where N = number of assistant turns. Each run holds the cumulative `trace` and points at its parent via `parent_task_run_id`. The final (leaf) run is the only one surfaced by default — intermediate runs are filtered out of dataset views, exports, and finetune sets via `filter_runs(include_intermediate_runs=False)`.
- **Trace shape** — `trace: list[ChatCompletionMessageParam]`, OpenAI-format messages with `role ∈ {user, assistant, tool, system, developer}` plus Kiln-specific per-message fields (`latency_ms`, `usage`, `kiln_task_tool_data`, etc.).
- **`input` / `output` on each run** — represent the *current turn's* user input and assistant output (plaintext), not the whole conversation.

## Out of scope (v1, unless flagged otherwise during specing)

- Tool-call turns in imported conversations (only user/assistant messages)
- Importing per-message `usage`, `latency_ms`, or `cost` fields (these are runtime telemetry, not authored data)
- Branching conversations from a single CSV file (one linear chain per conversation)
- Reverse direction: exporting multiturn runs to CSV
