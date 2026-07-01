// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import { writable } from "svelte/store"
import type { AvailableModels } from "$lib/types"

// ---------------------------------------------------------------------------
// Mock available_models store
// ---------------------------------------------------------------------------
const mockAvailableModels = writable<AvailableModels[]>([])

vi.mock("$lib/stores", () => ({
  available_models: mockAvailableModels,
}))

vi.mock("$lib/ui/provider_image", () => ({
  get_provider_image: () => "/fake-image.png",
}))

vi.mock(
  "$lib/ui/run_config_component/available_models_dropdown.svelte",
  async () => {
    const StubModule = await import(
      "./__tests__/available_models_dropdown_stub.svelte"
    )
    return { default: StubModule.default }
  },
)

const LlmJudgeForm = (await import("./llm_judge_form.svelte")).default

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeModel(
  id: string,
  name: string,
  opts: {
    supports_logprobs?: boolean
    suggested_for_evals?: boolean
    supports_structured_output?: boolean
  } = {},
) {
  return {
    id,
    name,
    supports_structured_output: opts.supports_structured_output ?? true,
    supports_data_gen: false,
    suggested_for_data_gen: false,
    supports_logprobs: opts.supports_logprobs ?? false,
    suggested_for_evals: opts.suggested_for_evals ?? false,
    supports_function_calling: false,
    uncensored: false,
    suggested_for_uncensored_data_gen: false,
    supports_vision: false,
    supports_doc_extraction: false,
    suggested_for_doc_extraction: false,
    multimodal_capable: false,
    multimodal_mime_types: null,
    structured_output_mode: "json_mode" as const,
    available_thinking_levels: null,
    default_thinking_level: null,
    untested_model: false,
    deprecated: false,
  }
}

function setModels(models: AvailableModels[]) {
  mockAvailableModels.set(models)
}

// Provider where the model does NOT support logprobs (single algorithm: llm_as_judge only)
const noLogprobsProvider: AvailableModels = {
  provider_name: "OpenAI",
  provider_id: "openai",
  models: [
    makeModel("gpt-4o", "GPT-4o", {
      suggested_for_evals: true,
      supports_logprobs: false,
    }),
  ],
}

// Provider where the model DOES support logprobs (two algorithms: llm_as_judge + g_eval)
const logprobsProvider: AvailableModels = {
  provider_name: "OpenAI",
  provider_id: "openai",
  models: [
    makeModel("gpt-4o", "GPT-4o", {
      suggested_for_evals: true,
      supports_logprobs: true,
    }),
  ],
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LlmJudgeForm", () => {
  afterEach(() => {
    cleanup()
    setModels([])
  })

  describe("E16: model card min-height", () => {
    it("model cards have min-h-[120px] class", async () => {
      setModels([noLogprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: { task_id: "task1" },
      })
      await tick()

      const modelCards = container.querySelectorAll(
        ".card.card-bordered.cursor-pointer",
      )
      expect(modelCards.length).toBeGreaterThan(0)
      for (const card of modelCards) {
        expect(card.classList.contains("min-h-[120px]")).toBe(true)
      }
    })
  })

  describe("E17: dropped string", () => {
    it("does not contain 'Supports graded scoring across the full score range.'", () => {
      setModels([noLogprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: { task_id: "task1" },
      })
      expect(container.textContent).not.toContain(
        "Supports graded scoring across the full score range.",
      )
    })
  })

  describe("E18: hide algorithm section for single-algorithm model", () => {
    it("hides algorithm section when model only supports default algorithm", async () => {
      setModels([noLogprobsProvider])
      // Use provider_id / model_id as model_name / provider_name (matches dropdown behavior)
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      const algoSection = container.querySelector(
        '[data-testid="algorithm-section"]',
      )
      expect(algoSection).toBeNull()
      expect(container.textContent).not.toContain("Select Judge Algorithm")
    })

    it("shows algorithm section when model supports G-Eval (logprobs)", async () => {
      setModels([logprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      const algoSection = container.querySelector(
        '[data-testid="algorithm-section"]',
      )
      expect(algoSection).not.toBeNull()
      expect(container.textContent).toContain("Select Judge Algorithm")
    })

    it("auto-selects the single algorithm so form is valid on model select (section hidden)", async () => {
      // When only one algorithm is available, the section is hidden and
      // update_unsupported_algos_and_default_algo auto-selects llm_as_judge.
      // This means can_submit_llm (!!selected_algo && !!combined_model_name) is true.
      setModels([noLogprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      // Section hidden = algorithm was auto-selected (only 1 option)
      const algoSection = container.querySelector(
        '[data-testid="algorithm-section"]',
      )
      expect(algoSection).toBeNull()

      // No radio buttons visible - user doesn't need to pick
      const radios = container.querySelectorAll('input[type="radio"]')
      expect(radios.length).toBe(0)
    })

    it("algorithm section is shown if the section would wrongly appear for single-option model", async () => {
      // This test verifies the section does NOT show for a model without logprobs,
      // and DOES show for a model with logprobs. This is a guard test: if someone
      // reverts the hide logic, the single-algo test above fails.
      setModels([noLogprobsProvider])
      const { container: c1 } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()
      expect(c1.querySelector('[data-testid="algorithm-section"]')).toBeNull()

      cleanup()

      setModels([logprobsProvider])
      const { container: c2 } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()
      expect(
        c2.querySelector('[data-testid="algorithm-section"]'),
      ).not.toBeNull()
    })
  })

  describe("E19: algorithm card sizing (reverted to pre-Phase-6)", () => {
    it("algorithm cards use w-[260px] and aspect-[5/6]", async () => {
      setModels([logprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      const algoCards = container.querySelectorAll(
        '[data-testid="algorithm-section"] .card.card-bordered',
      )
      expect(algoCards.length).toBeGreaterThan(0)
      for (const card of algoCards) {
        expect(card.classList.contains("w-[260px]")).toBe(true)
        expect(card.classList.contains("aspect-[5/6]")).toBe(true)
        expect(card.classList.contains("p-6")).toBe(true)
      }
    })

    it("algorithm cards do NOT use the shrunken Phase-6 sizes", async () => {
      setModels([logprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      const algoCards = container.querySelectorAll(
        '[data-testid="algorithm-section"] .card.card-bordered',
      )
      expect(algoCards.length).toBeGreaterThan(0)
      for (const card of algoCards) {
        expect(card.classList.contains("w-[156px]")).toBe(false)
        expect(card.classList.contains("p-4")).toBe(false)
      }
    })

    it("radio buttons use my-8 spacing (pre-Phase-6)", async () => {
      setModels([logprobsProvider])
      const { container } = render(LlmJudgeForm, {
        props: {
          task_id: "task1",
          model_name: "gpt-4o",
          provider_name: "openai",
          combined_model_name: "openai/gpt-4o",
        },
      })
      await tick()

      const radios = container.querySelectorAll(
        '[data-testid="algorithm-section"] input[type="radio"]',
      )
      expect(radios.length).toBeGreaterThan(0)
      for (const radio of radios) {
        expect(radio.classList.contains("my-8")).toBe(true)
        expect(radio.classList.contains("my-4")).toBe(false)
      }
    })
  })
})
