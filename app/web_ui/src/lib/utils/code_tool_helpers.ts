/**
 * Helpers for Code Tool UI: typed placeholder codegen, import-helper, examples.
 */

/**
 * Return a static JSON Schema for plain-text parameter mode.
 * When the user selects "Plain Text" instead of "Structured Parameter List",
 * the tool still needs a single `input` string parameter so the model knows
 * to pass text and the placeholder codegen produces `def run(input: str) -> str:`.
 */
export function plainTextParamsSchema(): { [key: string]: unknown } {
  return {
    type: "object",
    properties: {
      input: {
        type: "string",
        title: "input",
        description: "Plain text input passed to the tool.",
      },
    },
    required: ["input"],
    additionalProperties: false,
  }
}

interface JsonSchemaProperty {
  type?: string
  items?: JsonSchemaProperty
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  description?: string
}

/**
 * Map a JSON Schema type to a Python type hint string.
 */
function jsonTypeToPython(prop: JsonSchemaProperty): string {
  switch (prop.type) {
    case "string":
      return "str"
    case "integer":
      return "int"
    case "number":
      return "float"
    case "boolean":
      return "bool"
    case "array": {
      if (prop.items) {
        return `list[${jsonTypeToPython(prop.items)}]`
      }
      return "list"
    }
    case "object":
      return "dict"
    default:
      return "str"
  }
}

const PYTHON_RESERVED_WORDS = new Set([
  "False",
  "None",
  "True",
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "del",
  "elif",
  "else",
  "except",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "try",
  "while",
  "with",
  "yield",
])

/**
 * Escape a parameter name if it collides with a Python reserved word.
 */
function safePythonName(name: string): string {
  return PYTHON_RESERVED_WORDS.has(name) ? `${name}_param` : name
}

export interface CodeToolParam {
  name: string
  pythonType: string
  required: boolean
}

/**
 * Extract typed parameter info from a JSON Schema object.
 */
export function extractParams(schema: {
  [key: string]: unknown
}): CodeToolParam[] {
  const properties = schema.properties as
    | Record<string, JsonSchemaProperty>
    | undefined
  if (!properties) return []

  const required = Array.isArray(schema.required)
    ? (schema.required as string[])
    : []

  return Object.entries(properties).map(([name, prop]) => ({
    name,
    pythonType: jsonTypeToPython(prop),
    required: required.includes(name),
  }))
}

/**
 * Build the Python parameter list string for def run(...).
 * Required params come first, then optional params with `| None = None`.
 */
function buildParamList(params: CodeToolParam[]): string {
  if (params.length === 0) return ""

  const requiredParams = params.filter((p) => p.required)
  const optionalParams = params.filter((p) => !p.required)

  const parts: string[] = []
  for (const p of requiredParams) {
    parts.push(`${safePythonName(p.name)}: ${p.pythonType}`)
  }
  for (const p of optionalParams) {
    parts.push(`${safePythonName(p.name)}: ${p.pythonType} | None = None`)
  }
  return parts.join(", ")
}

/**
 * Generate a typed placeholder `def run(...)` stub from the schema.
 */
export function generateCodeToolPlaceholder(
  schema: { [key: string]: unknown },
  toolDescription: string,
): string {
  const params = extractParams(schema)
  const paramList = buildParamList(params)
  // Prevent the description from prematurely closing the triple-quoted docstring.
  // Replace any embedded """ with '' (two single-quotes) which is safe inside """.
  const safeDesc = toolDescription.replace(/"""/g, "''")

  return `def run(${paramList}) -> str:
    """${safeDesc}"""
    # TODO: implement
    return "result"
`
}

/**
 * Generate the import block to prepend when tools are selected.
 */
export function generateImportHelper(functionName: string): string {
  return `# Run tools with \`tools.${functionName}(...)\` or \`await async_tools.${functionName}(...)\`
from kiln import tools, async_tools

`
}

/**
 * Check whether the import line is already present in the code.
 */
export function shouldInsertImport(currentCode: string): boolean {
  return !currentCode.includes("from kiln import tools")
}

/**
 * Check if the code is still the original generated placeholder (or empty),
 * meaning it's safe to regenerate it after a schema change.
 */
export function isCodeUnmodified(
  currentCode: string,
  originalPlaceholder: string,
): boolean {
  return currentCode.trim() === "" || currentCode === originalPlaceholder
}

/**
 * Format a parameter value for inline preview display.
 *
 * - `null` / `undefined` → empty string (the component renders a "—" fallback)
 * - strings are returned as-is
 * - other values are JSON-serialised
 */
export function formatParamPreview(value: unknown): string {
  if (value === null || value === undefined) return ""
  return typeof value === "string" ? value : JSON.stringify(value)
}

/**
 * Generate example code snippets for the "More Examples" dialog.
 */
export function generateExamples(): { label: string; code: string }[] {
  return [
    {
      label: "Parallel with Retries",
      code: `import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from kiln import tools

def run(urls: list[str], max_retries: int = 3) -> str:
    """Fetch multiple URLs in parallel with retries."""
    results = {}

    def fetch_with_retry(url):
        for attempt in range(max_retries):
            try:
                result = tools.fetch_url(url=url)
                return url, json.loads(result)
            except Exception as e:
                if attempt == max_retries - 1:
                    return url, {"error": str(e)}
                time.sleep(0.5 * (attempt + 1))

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_with_retry, u) for u in urls]
        for future in as_completed(futures):
            url, data = future.result()
            results[url] = data

    return json.dumps(results)
`,
    },
    {
      label: "Async Fan-Out",
      code: `import json
import asyncio
from kiln import async_tools

async def run(user_ids: list[str]) -> str:
    """Fetch user details concurrently using async_tools."""
    async def fetch_user(uid):
        result = await async_tools.get_user(id=uid)
        return json.loads(result)

    users = await asyncio.gather(*(fetch_user(uid) for uid in user_ids))
    return json.dumps(users)
`,
    },
    {
      label: "Filter & Transform",
      code: `import json
from kiln import tools

def run(query: str, max_results: int = 10) -> str:
    """Search and filter results, returning only relevant fields."""
    raw = tools.search(query=query)
    results = json.loads(raw)

    filtered = [
        {"title": r["title"], "url": r["url"]}
        for r in results[:max_results]
        if "title" in r and "url" in r
    ]

    return json.dumps(filtered)
`,
    },
  ]
}
