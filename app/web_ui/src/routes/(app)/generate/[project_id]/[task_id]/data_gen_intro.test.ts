// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

// The "Generate Eval Data" dialog refuses some evals, and every refusal is an alert()
// string the user reads and acts on. None of them was asserted anywhere, and this branch
// has already shipped user-facing copy that was wrong (f191e0574, which swapped two
// dataset descriptions and whose own message notes "None of these three strings had a
// test asserting them"). These tests pin each string and the branch that picks it.

const { mockPage, mockGoto, mockClientGET, setSpecs, setEvals } = vi.hoisted(
  () => {
    const pageValue = {
      params: { project_id: "proj1", task_id: "task1" },
      url: new URL("http://localhost/generate/proj1/task1"),
    }
    const mockPage = {
      subscribe(fn: (value: typeof pageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    }

    let specs: Record<string, unknown>[] = []
    let evals: Record<string, unknown>[] = []
    const setSpecs = (v: Record<string, unknown>[]) => {
      specs = v
    }
    const setEvals = (v: Record<string, unknown>[]) => {
      evals = v
    }

    const mockClientGET = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/specs")) {
        return Promise.resolve({ data: specs, error: null })
      }
      if (path.endsWith("/evals")) {
        return Promise.resolve({
          data: { evals, load_error_count: 0 },
          error: null,
        })
      }
      if (path.endsWith("/finetune_dataset_info")) {
        return Promise.resolve({
          data: { finetune_tags: [] },
          error: null,
        })
      }
      return Promise.resolve({ data: null, error: null })
    })

    return {
      mockPage,
      mockGoto: vi.fn(),
      mockClientGET,
      setSpecs,
      setEvals,
    }
  },
)

// `svelte` is deliberately NOT mocked here, unlike specs_page.test.ts. That file runs its
// onMount callback inline because the page stays in a loading state until it settles.
// This component's onMount only loads fine-tune info, which the eval dialog never reads —
// and running it inline throws, because the callback is registered above the `let`
// declarations it assigns to and so hits their temporal dead zone.

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  goto: mockGoto,
}))

vi.mock("$lib/api_client", () => ({
  client: { GET: mockClientGET },
}))

const DataGenIntro = (await import("./data_gen_intro.svelte")).default

// ---------------------------------------------------------------------------
// The exact strings the user reads. Kept as constants so a copy change has to be
// made here too, deliberately.
// ---------------------------------------------------------------------------

const NOT_READY =
  "This eval is not ready yet. Please configure its judge first."

const EVAL_INPUTS_BACKED =
  "We can't generate synthetic data for this eval. Its test set is made of eval " +
  "inputs, and synthetic data generation adds task runs to your dataset."

const NOT_TAG_SHAPED =
  "We can't generate synthetic data for this eval because its test set isn't " +
  "defined by a tag filter. Select an eval which uses tags to define its datasets."

let alerts: string[] = []

beforeEach(() => {
  alerts = []
  vi.stubGlobal("alert", (message: string) => alerts.push(message))
  // jsdom doesn't implement HTMLDialogElement.showModal/close.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).showModal = function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "")
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).close = function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open")
  }
  setSpecs([])
  setEvals([])
})

afterEach(() => {
  cleanup()
  mockGoto.mockClear()
  vi.unstubAllGlobals()
})

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

function button_with_text(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === text,
  )
}

/**
 * Render, open the eval dialog, and click the option named `name`.
 *
 * MultiIntro renders a desktop and a mobile copy of its buttons, so "Generate Eval Data"
 * matches twice; either one runs the same handler.
 */
async function pick_eval(name: string): Promise<void> {
  const { container } = render(DataGenIntro, {
    props: {
      generate_subtopics: () => {},
      generate_samples: () => {},
      project_id: "proj1",
      task_id: "task1",
      is_setup: false,
    },
  })

  const open = button_with_text(container, "Generate Eval Data")
  expect(open).toBeDefined()
  await fireEvent.click(open!)
  await settle()
  await tick()

  const option = button_with_text(container, name)
  expect(option).toBeDefined()
  await fireEvent.click(option!)
  await tick()
}

/** The `splits` query param of the navigation the dialog performed, if any. */
function navigated_splits(): string | null {
  expect(mockGoto).toHaveBeenCalledTimes(1)
  const url = new URL(mockGoto.mock.calls[0][0] as string, "http://localhost")
  return url.searchParams.get("splits")
}

const OUTPUT_SCORES = [{ name: "accuracy", type: "five_star" }]

describe("data gen intro — eval refusals", () => {
  it("refuses an eval whose judge never loaded, by name", async () => {
    // A spec naming an eval the /evals response doesn't carry: the eval exists as a
    // spec but has no judge configured, so nothing can be generated for it yet.
    setSpecs([{ id: "spec1", name: "Unconfigured Spec", eval_id: "missing" }])
    setEvals([])

    await pick_eval("Unconfigured Spec")

    expect(alerts).toEqual([NOT_READY])
    expect(mockGoto).not.toHaveBeenCalled()
  })

  it("refuses an eval-input-backed test split, naming the store as the problem", async () => {
    // Generation appends TaskRuns to the dataset, so there is no tag on an EvalInput
    // split for it to target. Telling this user to switch to tag filters would be
    // useless advice — the store is the problem, not the filter's form.
    setEvals([
      {
        id: "eval1",
        name: "Inputs Eval",
        splits: { test: { source: "eval_input", filter_id: "tag::inputs" } },
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Inputs Eval")

    expect(alerts).toEqual([EVAL_INPUTS_BACKED])
    expect(mockGoto).not.toHaveBeenCalled()
  })

  it("refuses a test split whose filter isn't a tag, naming the filter as the problem", async () => {
    setEvals([
      {
        id: "eval1",
        name: "Filtered Eval",
        splits: { test: { source: "task_run", filter_id: "high_rating" } },
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Filtered Eval")

    expect(alerts).toEqual([NOT_TAG_SHAPED])
    expect(mockGoto).not.toHaveBeenCalled()
  })

  it("refuses an empty tag filter, which names no tag to write onto a run", async () => {
    // "tag::" is a valid-looking prefix with nothing after it. The helper treats it as
    // not tag-shaped for exactly that reason, and the same message applies.
    setEvals([
      {
        id: "eval1",
        name: "Empty Tag Eval",
        splits: { test: { source: "task_run", filter_id: "tag::" } },
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Empty Tag Eval")

    expect(alerts).toEqual([NOT_TAG_SHAPED])
  })

  it("MISLEADING COPY: an eval with no test split at all is told its filter isn't a tag", async () => {
    // KNOWN WRONG MESSAGE, DOCUMENTED NOT FIXED.
    //
    // build_eval_generation_splits returns undefined for more than one reason — no test
    // split, and a test split that isn't tag-shaped — and this dialog picks its message
    // by branch order rather than by cause. The eval_input branch runs first and catches
    // its own case, so the remaining two both land on the not-tag-shaped wording. An eval
    // with no test split therefore reads "its test set isn't defined by a tag filter" and
    // is told to "select an eval which uses tags", when the truth is that it has no test
    // set at all and needs one created.
    //
    // This shape should be unreachable from the server (Eval.validate_splits requires a
    // test split), so the wrong wording is latent rather than live — but the dispatch is
    // one reordering away from also mis-diagnosing the eval_input case, which IS
    // reachable. Reported, not fixed: this is a test-only change.
    setEvals([
      {
        id: "eval1",
        name: "No Test Split Eval",
        splits: {},
        eval_set_filter_id: null,
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("No Test Split Eval")

    expect(alerts).toEqual([NOT_TAG_SHAPED])
    expect(mockGoto).not.toHaveBeenCalled()
  })

  it("keeps the two refusals distinct, so neither can absorb the other's case", async () => {
    expect(EVAL_INPUTS_BACKED).not.toEqual(NOT_TAG_SHAPED)
    // The eval-inputs message must not offer the tag advice; that is the whole reason
    // it is a separate string.
    expect(EVAL_INPUTS_BACKED).not.toContain("tag")
  })
})

describe("data gen intro — evals it accepts", () => {
  it("sends a tag-backed eval to the synth page with an allocation over every split", async () => {
    setEvals([
      {
        id: "eval1",
        name: "Good Eval",
        splits: {
          test: { source: "task_run", filter_id: "tag::test_x" },
          train: { source: "task_run", filter_id: "tag::train_x" },
          val: { source: "task_run", filter_id: "tag::val_x" },
        },
        eval_configs_filter_id: "tag::golden_x",
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Good Eval")

    expect(alerts).toEqual([])
    expect(mockGoto.mock.calls[0][0]).toContain(
      "/generate/proj1/task1/synth?reason=eval",
    )
    expect(navigated_splits()).toBe(
      "train_x:0.4,val_x:0.25,test_x:0.25,golden_x:0.1",
    )
  })

  it("accepts a legacy eval whose test split is still in the flat field", async () => {
    // The server migrates the flat field into `splits` on load, so this shape shouldn't
    // reach the client — but eval_split falls back to it, and a refusal here would block
    // data generation for every pre-existing eval if that fallback ever broke.
    setEvals([
      {
        id: "eval1",
        name: "Legacy Eval",
        splits: {},
        eval_set_filter_id: "tag::test_x",
        eval_configs_filter_id: "tag::golden_x",
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Legacy Eval")

    expect(alerts).toEqual([])
    // Only test and golden can receive data, so their weights (25 and 10) are rescaled
    // to the whole allocation rather than leaving 65% unspent.
    expect(navigated_splits()).toBe("test_x:0.71,golden_x:0.29")
  })

  it("sends a rag eval to the QnA page instead of the synth page", async () => {
    setEvals([
      {
        id: "eval1",
        name: "Rag Eval",
        template: "rag",
        splits: { test: { source: "task_run", filter_id: "tag::test_x" } },
        eval_configs_filter_id: "tag::golden_x",
        output_scores: OUTPUT_SCORES,
      },
    ])

    await pick_eval("Rag Eval")

    expect(alerts).toEqual([])
    expect(mockGoto.mock.calls[0][0]).toContain("/generate/proj1/task1/qna?")
    // Rag has no human-ratings step, so its golden tag gets nothing.
    expect(navigated_splits()).toBe("test_x:1")
  })
})
