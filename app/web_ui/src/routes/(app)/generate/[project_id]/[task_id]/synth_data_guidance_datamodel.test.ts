import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
import type { Eval, Task } from "$lib/types"

// Mock the API client
vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
  },
}))

import { client } from "$lib/api_client"

describe("SynthDataGuidanceDataModel", () => {
  let model: SynthDataGuidanceDataModel
  let mockClient: typeof client & {
    GET: { mockResolvedValue: (value: unknown) => void }
  }

  beforeEach(() => {
    mockClient = client as typeof client & {
      GET: { mockResolvedValue: (value: unknown) => void }
    }
    model = new SynthDataGuidanceDataModel()
  })

  afterEach(() => {
    model.destroy()
    vi.clearAllMocks()
  })

  describe("constructor", () => {
    it("should initialize with default values", () => {
      expect(get(model.loading)).toBe(false)
      expect(get(model.selected_template)).toBe("custom")
      expect(get(model.topic_guidance)).toBe(null)
      expect(get(model.input_guidance)).toBe(null)
      expect(get(model.output_guidance)).toBe(null)
      expect(get(model.select_options)).toEqual([])
    })

    it("should set up template subscription", () => {
      const spy = vi.spyOn(model as never, "apply_selected_template")
      model.selected_template.set("toxicity")
      expect(spy).toHaveBeenCalledWith("toxicity")
    })
  })

  describe("destroy", () => {
    it("should clean up subscriptions", () => {
      const spy = vi.spyOn(model as never, "apply_selected_template")
      model.destroy()
      model.selected_template.set("bias")
      expect(spy).not.toHaveBeenCalled()
    })

    it("should handle multiple destroy calls", () => {
      model.destroy()
      model.destroy()
      // Should not throw
    })
  })

  describe("load", () => {
    const mockTask = {
      id: "task1",
      name: "Test Task",
      requirements: [
        { instruction: "Be helpful and harmless" },
        { instruction: "Avoid bias" },
      ],
    } as Task

    const mockEval = {
      id: "eval1",
      name: "Test Eval",
      template: "kiln_issue",
      template_properties: {},
    } as Eval

    beforeEach(() => {
      mockClient.GET.mockResolvedValue({
        data: mockEval,
        error: null,
      })
    })

    it("should load with basic parameters", async () => {
      await model.load(null, null, "proj1", "task1", "training", mockTask)

      expect(model.project_id).toBe("proj1")
      expect(model.task_id).toBe("task1")
      expect(model.gen_type).toBe("training")
      expect(model.task).toBe(mockTask)
    })

    it("should set selected template when template_id matches static template", async () => {
      await model.load("toxicity", null, "proj1", "task1", "training", mockTask)

      expect(get(model.selected_template)).toBe("toxicity")
    })

    it("should not set selected template when template_id does not match static template", async () => {
      await model.load(
        "unknown_template",
        null,
        "proj1",
        "task1",
        "training",
        mockTask,
      )

      expect(get(model.selected_template)).toBe("custom")
    })

    it("should load eval data when eval_id is provided", async () => {
      const mockEval = {
        id: "eval1",
        name: "Test Eval",
        template: "kiln_issue",
        template_properties: {
          issue_prompt: "Test issue",
          failure_example: "Bad example",
          pass_example: "Good example",
        },
      } as unknown as Eval

      mockClient.GET.mockResolvedValue({
        data: mockEval,
        error: null,
      })

      await model.load(
        null,
        "proj1::task1::eval1",
        "proj1",
        "task1",
        "eval",
        mockTask,
      )

      expect(mockClient.GET).toHaveBeenCalledWith(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
        {
          params: {
            path: {
              project_id: "proj1",
              task_id: "task1",
              eval_id: "eval1",
            },
          },
        },
      )
    })

    it("should set template to issue_eval_template for kiln_issue evaluator", async () => {
      const mockEval = {
        id: "eval1",
        name: "Test Eval",
        template: "kiln_issue",
        template_properties: {},
      } as Eval

      mockClient.GET.mockResolvedValue({
        data: mockEval,
        error: null,
      })

      await model.load(
        null,
        "proj1::task1::eval1",
        "proj1",
        "task1",
        "eval",
        mockTask,
      )

      expect(get(model.selected_template)).toBe("issue_eval_template")
    })

    it("should set template to requirements_eval_template for kiln_requirements evaluator", async () => {
      const mockEval = {
        id: "eval1",
        name: "Test Eval",
        template: "kiln_requirements",
        template_properties: {},
      } as Eval

      mockClient.GET.mockResolvedValue({
        data: mockEval,
        error: null,
      })

      await model.load(
        null,
        "proj1::task1::eval1",
        "proj1",
        "task1",
        "eval",
        mockTask,
      )

      expect(get(model.selected_template)).toBe("requirements_eval_template")
    })

    it("should handle API errors gracefully", async () => {
      mockClient.GET.mockResolvedValue({
        data: null,
        error: { message: "API Error" },
      })

      await model.load(
        null,
        "proj1::task1::eval1",
        "proj1",
        "task1",
        "eval",
        mockTask,
      )

      expect(get(model.loading_error)).toBeTruthy()
      expect(get(model.loading)).toBe(false)
    })
  })

  describe("guidance methods", () => {
    describe("guidance_store_for_type", () => {
      it("should return correct store for topics", () => {
        const store = model.guidance_store_for_type("topics")
        expect(store).toBe(model.topic_guidance)
      })

      it("should return correct store for inputs", () => {
        const store = model.guidance_store_for_type("inputs")
        expect(store).toBe(model.input_guidance)
      })

      it("should return correct store for outputs", () => {
        const store = model.guidance_store_for_type("outputs")
        expect(store).toBe(model.output_guidance)
      })

      it("should throw error for invalid type", () => {
        expect(() =>
          model.guidance_store_for_type(
            "invalid" as "topics" | "inputs" | "outputs",
          ),
        ).toThrow("Invalid guidance type: invalid")
      })
    })

    describe("guidance_for_type", () => {
      it("should return current guidance value", () => {
        model.topic_guidance.set("test guidance")
        expect(model.guidance_for_type("topics")).toBe("test guidance")
      })

      it("should return null for unset guidance", () => {
        expect(model.guidance_for_type("inputs")).toBe(null)
      })
    })

    describe("set_guidance_for_type", () => {
      it("should set guidance value and template", () => {
        // Temporarily unsubscribe to prevent template application
        model.destroy()
        model.set_guidance_for_type("topics", "new guidance", "toxicity")

        expect(get(model.topic_guidance)).toBe("new guidance")
        expect(get(model.selected_template)).toBe("toxicity")
      })

      it("should set template to custom when template is null", () => {
        model.set_guidance_for_type("inputs", "custom guidance", null)

        expect(get(model.input_guidance)).toBe("custom guidance")
        expect(get(model.selected_template)).toBe("custom")
      })
    })
  })

  describe("template methods", () => {
    describe("suggest_uncensored", () => {
      it("should return true for templates that suggest uncensored content", () => {
        expect(model.suggest_uncensored("toxicity")).toBe(true)
        expect(model.suggest_uncensored("bias")).toBe(true)
        expect(model.suggest_uncensored("jailbreak")).toBe(true)
      })

      it("should return false for templates that do not suggest uncensored content", () => {
        expect(model.suggest_uncensored("factual_correctness")).toBe(false)
      })

      it("should return false for unknown templates", () => {
        expect(model.suggest_uncensored("unknown")).toBe(false)
      })
    })

    describe("custom_warning", () => {
      it("should return custom warning when present", () => {
        const warning = model.custom_warning("factual_correctness")
        expect(warning).toBe(
          "We suggest using a large model which is likely to know the answers, so it may assess factual inaccuracies.",
        )
      })

      it("should return null when no custom warning", () => {
        expect(model.custom_warning("toxicity")).toBe(null)
      })

      it("should return null for unknown templates", () => {
        expect(model.custom_warning("unknown")).toBe(null)
      })
    })

    describe("guidance_label", () => {
      beforeEach(() => {
        // Set up mock select options
        model.select_options.set([
          {
            label: "Built-in Templates",
            options: [
              {
                label: "Toxicity Eval",
                value: "toxicity",
                description: "Test",
              },
              { label: "Bias Eval", value: "bias", description: "Test" },
            ],
          },
          {
            label: "Custom Guidance",
            options: [
              { label: "Custom", value: "custom", description: "Test" },
            ],
          },
        ])
      })

      it("should return correct label for existing template", () => {
        expect(model.guidance_label("toxicity", "some guidance")).toBe(
          "Toxicity Eval Template",
        )
      })

      it("should return correct label for custom template", () => {
        expect(model.guidance_label("custom", "some guidance")).toBe(
          "Custom Template",
        )
      })

      it("should return 'None' for unknown template", () => {
        expect(model.guidance_label("unknown", "some guidance")).toBe("None")
      })
    })
  })

  describe("apply_selected_template", () => {
    it("should clear guidance for custom template", () => {
      model.topic_guidance.set("existing")
      model.input_guidance.set("existing")
      model.output_guidance.set("existing")

      model["apply_selected_template"]("custom")

      expect(get(model.topic_guidance)).toBe(null)
      expect(get(model.input_guidance)).toBe(null)
      expect(get(model.output_guidance)).toBe(null)
    })

    it("should apply static template guidance", () => {
      model["apply_selected_template"]("toxicity")

      const guidance = get(model.topic_guidance)
      expect(guidance).toContain("toxicity")
      expect(guidance).toContain("Highly inappropriate or harmful content")
    })

    it("should apply issue eval template when evaluator is present", () => {
      const mockEval = {
        id: "eval1",
        name: "Test Issue",
        template: "kiln_issue",
        template_properties: {
          issue_prompt: "Test issue description",
          failure_example: "Bad example",
          pass_example: "Good example",
        },
      } as unknown as Eval

      model["evaluator"] = mockEval
      model["apply_selected_template"]("issue_eval_template")

      const guidance = get(model.topic_guidance)
      expect(guidance).toContain("Test Issue")
      expect(guidance).toContain("Test issue description")
      expect(guidance).toContain("Bad example")
      expect(guidance).toContain("Good example")
    })

    it("should apply requirements eval template when evaluator and task are present", () => {
      const mockEval = {
        id: "eval1",
        name: "Test Requirements",
        template: "kiln_requirements",
        template_properties: {},
      } as unknown as Eval

      const mockTask = {
        id: "task1",
        name: "Test Task",
        requirements: [
          { instruction: "Be helpful and harmless" },
          { instruction: "Avoid bias" },
        ],
      } as unknown as Task

      model["evaluator"] = mockEval
      model["task"] = mockTask
      model["apply_selected_template"]("requirements_eval_template")

      const guidance = get(model.topic_guidance)
      expect(guidance).toContain("Be helpful and harmless")
      expect(guidance).toContain("Avoid bias")
      expect(guidance).toContain("requirement_1")
      expect(guidance).toContain("requirement_2")
    })
  })

  describe("template generation methods", () => {
    describe("requirements_eval_template", () => {
      it("should generate template with requirements", () => {
        const mockEval = { id: "eval1", name: "Test" } as Eval
        const mockTask = {
          id: "task1",
          name: "Test Task",
          requirements: [
            { instruction: "Be helpful" },
            { instruction: "Be harmless" },
          ],
        } as Task

        const template = model["requirements_eval_template"](
          mockEval,
          mockTask,
          "topics",
        )

        expect(template).toContain("Be helpful")
        expect(template).toContain("Be harmless")
        expect(template).toContain("requirement_1")
        expect(template).toContain("requirement_2")
      })

      it("should handle empty requirements", () => {
        const mockEval = { id: "eval1", name: "Test" } as unknown as Eval
        const mockTask = {
          id: "task1",
          name: "Test Task",
          requirements: [],
        } as unknown as Task

        const template = model["requirements_eval_template"](
          mockEval,
          mockTask,
          "topics",
        )

        expect(template).toContain("AI eval")
        expect(template).toContain("requirement_1")
      })
    })

    describe("issue_eval_template", () => {
      it("should generate template with all issue properties", () => {
        const mockEval = {
          id: "eval1",
          name: "Test Issue",
          template: "kiln_issue",
          template_properties: {
            issue_prompt: "Description of the issue",
            failure_example: "This is a bad example",
            pass_example: "This is a good example",
          },
        } as unknown as Eval

        const template = model["issue_eval_template"](mockEval, "topics")

        expect(template).toContain("Test Issue")
        expect(template).toContain("Description of the issue")
        expect(template).toContain("This is a bad example")
        expect(template).toContain("This is a good example")
      })

      it("should handle missing optional properties", () => {
        const mockEval = {
          id: "eval1",
          name: "Simple Issue",
          template: "kiln_issue",
          template_properties: {},
        } as Eval

        const template = model["issue_eval_template"](mockEval, "topics")

        expect(template).toContain("Simple Issue")
        expect(template).not.toContain("issue_description")
        expect(template).not.toContain("issue_example")
        expect(template).not.toContain("no_issue_example")
      })
    })
  })

  describe("build_select_options", () => {
    const mockStaticTemplates = [
      {
        id: "test1",
        name: "Test Template 1",
        description: "Description 1",
        topic_template: "Topic Template 1",
        input_template: "Input Template 1",
        output_template: "Output Template 1",
        suggest_uncensored: false,
      },
      {
        id: "test2",
        name: "Test Template 2",
        description: "Description 2",
        topic_template: "Topic Template 2",
        input_template: "Input Template 2",
        output_template: "Output Template 2",
        suggest_uncensored: true,
      },
    ]

    it("should build options with evaluator (issue type)", () => {
      const mockEval = {
        id: "eval1",
        name: "Test Issue",
        template: "kiln_issue",
        template_properties: {},
      } as unknown as Eval

      model["build_select_options"](mockStaticTemplates, mockEval)

      const options = get(model.select_options)
      expect(options).toHaveLength(3)
      expect(options[0].label).toBe("Eval Template")
      expect(options[0].options[0].value).toBe("issue_eval_template")
      expect(options[1].label).toBe("Custom Guidance")
      expect(options[2].label).toBe("Built-in Templates for Evals")
    })

    it("should build options with evaluator (requirements type)", () => {
      const mockEval = {
        id: "eval1",
        name: "Test Requirements",
        template: "kiln_requirements",
        template_properties: {},
      } as unknown as Eval

      model["build_select_options"](mockStaticTemplates, mockEval)

      const options = get(model.select_options)
      expect(options[0].options[0].value).toBe("requirements_eval_template")
    })

    it("should build options without evaluator", () => {
      model["build_select_options"](mockStaticTemplates, null)

      const options = get(model.select_options)
      expect(options).toHaveLength(2)
      expect(options[0].label).toBe("Custom Guidance")
      expect(options[1].label).toBe("Built-in Templates for Evals")
    })

    it("should map static templates correctly", () => {
      model["build_select_options"](mockStaticTemplates, null)

      const options = get(model.select_options)
      const builtInOptions = options.find(
        (group) => group.label === "Built-in Templates for Evals",
      )

      expect(builtInOptions?.options).toHaveLength(2)
      expect(builtInOptions?.options[0]).toEqual({
        label: "Test Template 1",
        value: "test1",
        description: "Description 1",
      })
    })
  })

  describe("static templates", () => {
    it("should have all expected static templates", () => {
      // Test that all expected templates are present
      expect(model.suggest_uncensored("toxicity")).toBe(true)
      expect(model.suggest_uncensored("bias")).toBe(true)
      expect(model.suggest_uncensored("maliciousness")).toBe(true)
      expect(model.suggest_uncensored("jailbreak")).toBe(true)
      expect(model.suggest_uncensored("factual_correctness")).toBe(false)
    })

    it("should have correct template content", () => {
      model["apply_selected_template"]("toxicity")
      const guidance = get(model.topic_guidance)

      expect(guidance).toContain("toxicity")
      expect(guidance).toContain("Highly inappropriate or harmful content")
      expect(guidance).toContain("disregard any prior task instructions")
    })
  })

  describe("reactive behavior", () => {
    it("should update guidance when template changes", () => {
      model.selected_template.set("toxicity")

      expect(get(model.topic_guidance)).toContain("toxicity")

      model.selected_template.set("bias")

      expect(get(model.topic_guidance)).toContain("bias")
    })

    it("should maintain subscription throughout lifecycle", () => {
      const applySpy = vi.spyOn(
        model as SynthDataGuidanceDataModel & {
          apply_selected_template: (template: string) => void
        },
        "apply_selected_template",
      )

      model.selected_template.set("toxicity")
      model.selected_template.set("bias")
      model.selected_template.set("custom")

      expect(applySpy).toHaveBeenCalledTimes(3)
      expect(applySpy).toHaveBeenCalledWith("toxicity")
      expect(applySpy).toHaveBeenCalledWith("bias")
      expect(applySpy).toHaveBeenCalledWith("custom")
    })
  })
})
