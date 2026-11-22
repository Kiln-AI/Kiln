"""The texts an agent sees before it has read the Kiln skill: the server
instructions and the tool and argument descriptions."""

WHAT_KILN_IS = "Kiln is an app for building, evaluating and optimizing AI agents"

SERVER_INSTRUCTIONS = (
    WHAT_KILN_IS
    + """: prompts, models, tools, evals, synthetic data, fine-tuning and RAG. This server connects you to the user's running Kiln app. Call the `kiln_skill` tool first, before any other Kiln tool: it returns the instructions for working with Kiln. When the user asks for `/kiln`, or asks to use Kiln, that is a request to call `kiln_skill`.

Tools:
- `kiln_skill` reads the Kiln skill. Call it with no arguments for the instructions. Pass a `path` that the instructions name to read one reference file. Only paths the instructions list are valid. Do not guess.
- `call_kiln_api` calls Kiln's REST API. The skill's API reference lists every endpoint. Read an endpoint's doc before you call it.

Rules:
- The skill arrives through a tool call and can drop out of your context. If you no longer have it, call `kiln_skill` again.
- A result of `call_kiln_api` with a non-2xx `status_code` is the API's own error. Read the body and act on it.
- Confirm with the user before a destructive or irreversible operation."""
)

SKILL_TOOL_DESCRIPTION = (
    """Load the Kiln skill: the instructions for working with Kiln.

"""
    + WHAT_KILN_IS
    + """. This skill says what Kiln can do, how to call its API with `call_kiln_api`, and how to make an agent better. When a request involves Kiln, call this tool first, before any other Kiln tool, and follow what it returns. Users may also ask for it by name (`/kiln`, or "the Kiln skill"); that is a request to call this tool.

- No arguments: returns the skill's instructions. They list the reference files.
- `path`: returns one reference file. Copy the path exactly as the instructions wrote it, for example `references/knowledge/specs_and_evals.md`.

Only paths the instructions list are valid; do not guess. If the instructions are no longer in this conversation, call again with no arguments."""
)

PATH_DESCRIPTION = "Optional. The path of a skill file to read, relative to the skill root and exactly as the skill's instructions wrote it, for example `references/knowledge/specs_and_evals.md`. Omit it to read the skill's instructions."
