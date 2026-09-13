// Source assertions for the entry page's run-config dialog. The page mounts
// the whole run-config picker (model list, tool and skill pickers, task
// stores), which a render test would have to stub down to nothing; the rules
// below are contractual either way. Reading the source is the house precedent
// for pinning facts a render test can't reach (see builder/generate_step_surface.test.ts).
import * as fs from "fs"
import * as path from "path"
import { describe, expect, it } from "vitest"

const page_source = fs.readFileSync(
  path.resolve(__dirname, "./+page.svelte"),
  "utf-8",
)

// Collapses runs of whitespace so an assertion survives Prettier rewrapping a
// long attribute across lines.
function normalize(source: string): string {
  return source.replace(/\s+/g, " ")
}

const normalized = normalize(page_source)

function contains(needle: string): boolean {
  return normalized.includes(normalize(needle))
}

// The slice of the page a claim is about, so a negative assertion is not
// answered by some unrelated part of the file.
function region(start_anchor: string, end_anchor: string): string {
  const start = page_source.indexOf(start_anchor)
  if (start < 0) {
    throw new Error(`anchor not found in +page.svelte: ${start_anchor}`)
  }
  const end = page_source.indexOf(end_anchor, start + start_anchor.length)
  if (end < 0) {
    throw new Error(
      `end anchor not found after "${start_anchor}": ${end_anchor}`,
    )
  }
  return page_source.slice(start, end + end_anchor.length)
}

const dialog = region("bind:this={run_config_dialog}", "</Dialog>")
const continue_fn = region(
  "async function continue_with_description() {",
  "\n  }",
)
const goto_builder_fn = region(
  "function goto_builder(run_config_id: string | null) {",
  "\n  }",
)
const open_dialog_fn = region("function open_run_config_dialog() {", "\n  }")

describe("the run config dialog", () => {
  it("opens on Continue instead of going straight to the builder", () => {
    // The choice is asked before the wizard starts, because everything the
    // wizard does afterwards reads the chosen config.
    expect(contains("on:click={open_run_config_dialog}")).toBe(true)
    expect(normalize(open_dialog_fn)).toContain("run_config_dialog?.show()")
  })

  it("hands over without a config when there is no task to pick from", () => {
    // A task that failed to load leaves the dialog with no picker in it, so
    // opening would show an empty box. The builder resolves the task default
    // when nothing is chosen, which is what this page did before it asked.
    expect(normalize(open_dialog_fn)).toContain(
      "if (!task) { goto_builder(null) return }",
    )
  })

  it("picks a config with the same control the run page uses", () => {
    // Same dropdown over the same component, so a config is chosen the same
    // way in both places and its tools and skills are visible while choosing.
    expect(dialog).toContain("<SavedRunConfigsDropdown")
    expect(dialog).toContain("<RunConfigComponent")
    expect(normalize(dialog)).toContain(
      "save_new_run_config={handle_save_new_run_config}",
    )
    expect(normalize(dialog)).toContain("hide_prompt_selector={true}")
    expect(normalize(dialog)).toContain(
      "show_tools_selector_in_advanced={true}",
    )
    expect(normalize(dialog)).toContain("show_name_field={false}")
  })

  it("explains what the choice decides", () => {
    expect(
      contains(
        'info_description="The run config this eval tests. Kiln uses its tools and skills to write the questions and the judge, then runs it to generate the eval data."',
      ),
    ).toBe(true)
  })
})

describe("continuing into the builder", () => {
  it("saves an edited config before proceeding", () => {
    // "Custom" is only in the picker's local state, while the wizard, the
    // drive and the saved eval all refer to the config by id. Navigating on
    // "custom" would hand the builder an id that resolves to nothing.
    const body = normalize(continue_fn)
    expect(body).toContain('if (!run_config_id || run_config_id === "custom")')
    expect(body).toContain("await handle_save_new_run_config()")
    expect(body.indexOf("handle_save_new_run_config")).toBeLessThan(
      body.indexOf("goto_builder("),
    )
  })

  it("hands the chosen config over beside the description", () => {
    expect(normalize(goto_builder_fn)).toContain(
      "`&run_config_id=${encodeURIComponent(run_config_id)}`",
    )
  })

  it("never navigates without an id", () => {
    // A saved config with no id is a broken save, not a reason to start a
    // wizard that cannot resolve its target.
    expect(normalize(continue_fn)).toContain(
      'if (!run_config_id) { throw new Error("The saved run config has no id.") }',
    )
  })
})

// The folded template list names what it holds rather than telling the reader
// to look. Pinned because it is the only thing identifying that section.
describe("the template picker's disclosure", () => {
  it("is titled after its contents", () => {
    expect(normalize(page_source)).toContain(
      '<Collapse title="LLM Judge Templates"',
    )
  })
})
