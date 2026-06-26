// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import("./__tests__/form_element_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/utils/form_list.svelte", async () => {
  const { default: Stub } = await import("./__tests__/form_list_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/ui/collapse.svelte", async () => {
  const { default: Stub } = await import("./__tests__/collapse_stub.svelte")
  return { default: Stub }
})

vi.mock("./tag_input.svelte", async () => {
  const { default: Stub } = await import("./__tests__/tag_input_stub.svelte")
  return { default: Stub }
})

const PatternMatchForm = (await import("./pattern_match_form.svelte")).default
const ExactMatchForm = (await import("./exact_match_form.svelte")).default
const ContainsForm = (await import("./contains_form.svelte")).default
const SetCheckForm = (await import("./set_check_form.svelte")).default
const StepCountCheckForm = (await import("./step_count_check_form.svelte"))
  .default
const ToolCallCheckForm = (await import("./tool_call_check_form.svelte"))
  .default

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
})

describe("PatternMatchForm", () => {
  it("validate returns error for empty pattern", () => {
    const { component } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Regular expression is required.",
    )
  })

  it("validate returns error for invalid regex", () => {
    const { component } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "[invalid",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Invalid regular expression pattern.",
    )
  })

  it("validate returns null for valid regex", () => {
    const { component } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "^hello.*world$",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })

  it("getProperties returns current properties", () => {
    const { component } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_not_match" as const,
          value_expression: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.type).toBe("pattern_match")
    expect(props.pattern).toBe("test")
    expect(props.mode).toBe("must_not_match")
  })
})

describe("ExactMatchForm", () => {
  it("validate returns error when expected_value source is selected but empty", () => {
    const { component } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Expected value is required.")
  })

  it("validate returns null when expected_value is set", () => {
    const { component } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })
})

describe("ContainsForm", () => {
  it("validate returns error when substring source is selected but empty", () => {
    const { component } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Substring is required.")
  })

  it("validate returns null when substring is set", () => {
    const { component } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })
})

describe("SetCheckForm", () => {
  it("validate returns error when expected_set is empty", () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: [],
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Expected set must contain at least one value.",
    )
  })

  it("validate returns null when expected_set has values", () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a", "b"],
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })

  it("getProperties always sends explicit mode", () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "superset" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.mode).toBe("superset")
    expect(props.type).toBe("set_check")
  })
})

describe("StepCountCheckForm", () => {
  it("validate returns error when neither min nor max is set", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "At least one bound must be set.",
    )
  })

  it("validate returns error when min > max", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: 10,
          max_count: 5,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Minimum must be less than or equal to maximum.",
    )
  })

  it("validate returns null when only min is set", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "model_responses" as const,
          min_count: 1,
          max_count: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })

  it("validate returns null when both min and max are set correctly", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "turns" as const,
          min_count: 2,
          max_count: 10,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })
})

describe("ExactMatchForm radio groups", () => {
  it("renders radio inputs for match source", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const radios = container.querySelectorAll(
      'input[type="radio"][name="exact_match_source"]',
    )
    expect(radios).toHaveLength(2)
  })

  it("defaults source to expected_value when expected_value is set", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const expectedRadio = container.querySelector(
      'input[type="radio"][value="expected_value"]',
    ) as HTMLInputElement
    expect(expectedRadio.checked).toBe(true)
  })

  it("defaults source to reference_key when reference_key is set", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    expect(refRadio.checked).toBe(true)
  })

  it("validate returns error for expected_value source with empty value", () => {
    const { component } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Expected value is required.")
  })
})

describe("ContainsForm radio groups", () => {
  it("renders radio inputs for search string source", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const radios = container.querySelectorAll(
      'input[type="radio"][name="contains_source"]',
    )
    expect(radios).toHaveLength(2)
  })

  it("defaults source to reference_key when reference_key is set", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    expect(refRadio.checked).toBe(true)
  })
})

describe("SetCheckForm radio groups + tag input", () => {
  it("renders radio inputs for expected set source", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const radios = container.querySelectorAll(
      'input[type="radio"][name="set_check_source"]',
    )
    expect(radios).toHaveLength(2)
  })

  it("renders tag input stub for expected_set source", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a", "b"],
          reference_key: null,
        },
      },
    })
    const tagInput = container.querySelector(
      '[data-testid="tag-input-set_check_expected_set"]',
    )
    expect(tagInput).toBeTruthy()
  })

  it("defaults source to reference_key when reference_key is set", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    expect(refRadio.checked).toBe(true)
  })
})

describe("Radio source switching clears inactive value", () => {
  it("ExactMatchForm: switching to reference_key clears expected_value", async () => {
    const { component, container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    await fireEvent.click(refRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.expected_value).toBeNull()
  })

  it("ExactMatchForm: switching to expected_value clears reference_key", async () => {
    const { component, container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const valRadio = container.querySelector(
      'input[type="radio"][value="expected_value"]',
    ) as HTMLInputElement
    await fireEvent.click(valRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.reference_key).toBeNull()
  })

  it("ContainsForm: switching to reference_key clears substring", async () => {
    const { component, container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    await fireEvent.click(refRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.substring).toBeNull()
  })

  it("ContainsForm: switching to substring clears reference_key", async () => {
    const { component, container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const subRadio = container.querySelector(
      'input[type="radio"][value="substring"]',
    ) as HTMLInputElement
    await fireEvent.click(subRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.reference_key).toBeNull()
  })

  it("SetCheckForm: switching to reference_key clears expected_set", async () => {
    const { component, container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a", "b"],
          reference_key: null,
        },
      },
    })
    const refRadio = container.querySelector(
      'input[type="radio"][value="reference_key"]',
    ) as HTMLInputElement
    await fireEvent.click(refRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.expected_set).toBeNull()
  })

  it("SetCheckForm: switching to expected_set clears reference_key", async () => {
    const { component, container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const setRadio = container.querySelector(
      'input[type="radio"][value="expected_set"]',
    ) as HTMLInputElement
    await fireEvent.click(setRadio)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.reference_key).toBeNull()
  })
})

describe("ToolCallCheckForm", () => {
  it("validate returns error when no tools are defined", () => {
    const { component } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "At least one expected tool must be defined.",
    )
  })

  it("validate returns error when a tool has empty name, with tool index", () => {
    const { component } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Expected Tool #1 is missing a name.",
    )
  })

  it("validate error identifies the correct tool index", () => {
    const { component } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [
            { tool_name: "search", expected_args: null },
            { tool_name: "", expected_args: null },
          ],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe(
      "Expected Tool #2 is missing a name.",
    )
  })

  it("validate returns null when tools are properly defined", () => {
    const { component } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search_web", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBeNull()
  })
})

// Phase 7: Redesigned forms — genuinely new tests for relabel, tooltips,
// progressive disclosure, section structure, and reference_key validation path.
// Pre-existing contract tests (getProperties shape, validate pass/fail for
// expected_value/substring sources, radio switching) are NOT duplicated here.

describe("Phase 7: reference_key validation path", () => {
  it("ExactMatch validate returns error when reference_key source is selected but empty", async () => {
    const { component } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "key",
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({
      properties: {
        type: "exact_match" as const,
        case_sensitive: true,
        value_expression: null,
        expected_value: null,
        reference_key: null,
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Reference key is required.")
  })

  it("Contains validate returns error when reference_key source is selected but empty", async () => {
    const { component } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "key",
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({
      properties: {
        type: "contains" as const,
        case_sensitive: true,
        mode: "must_contain" as const,
        value_expression: null,
        substring: null,
        reference_key: null,
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Reference key is required.")
  })
})

describe("Phase 7: Relabeled fields and Jinja tooltips", () => {
  it("ExactMatch has 'Output Value' label with Jinja tooltip", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })

  it("PatternMatch has 'Output Value' label with Jinja tooltip", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-pattern_match_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })

  it("Contains has 'Output Value' label with Jinja tooltip", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-contains_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })
})

describe("Phase 7: Progressive disclosure and section structure", () => {
  it("ExactMatch shows only expected_value input when fixed value selected", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-exact_match_expected_value"]',
      ),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="form-element-exact_match_reference_key"]',
      ),
    ).toBeNull()
    expect(
      container.querySelector('[data-testid="radio-group-exact_match_source"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="exact-match-expected-section"]'),
    ).toBeTruthy()
  })

  it("ExactMatch shows only reference_key input when reference data selected", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-exact_match_expected_value"]',
      ),
    ).toBeNull()
    expect(
      container.querySelector(
        '[data-testid="form-element-exact_match_reference_key"]',
      ),
    ).toBeTruthy()
  })

  it("Contains shows only substring input when fixed substring selected", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-contains_substring"]',
      ),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="form-element-contains_reference_key"]',
      ),
    ).toBeNull()
    expect(
      container.querySelector('[data-testid="radio-group-contains_source"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="contains-expected-section"]'),
    ).toBeTruthy()
  })

  it("Contains shows only reference_key input when reference data selected", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-contains_substring"]',
      ),
    ).toBeNull()
    expect(
      container.querySelector(
        '[data-testid="form-element-contains_reference_key"]',
      ),
    ).toBeTruthy()
  })

  it("PatternMatch renders match mode radio group and section titles", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="radio-group-pattern_match_mode"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="pattern-match-pattern-section"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="pattern-match-mode-section"]'),
    ).toBeTruthy()
  })

  it("Contains renders match mode radio group and section titles", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="radio-group-contains_mode"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="contains-mode-section"]'),
    ).toBeTruthy()
  })

  it("PatternMatch has regex tooltip", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "regular expression",
    )
  })
})

// Phase 8: Redesigned set_check, tool_call_check, step_count_check forms.
// Tests verify new section structure, radio groups, progressive disclosure,
// and that getProperties()/validate() contracts are preserved exactly.

describe("Phase 8: SetCheckForm section structure and progressive disclosure", () => {
  it("renders Expected Values section with testid", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="set-check-expected-section"]'),
    ).toBeTruthy()
  })

  it("renders Comparison Mode section with radio group", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="set-check-mode-section"]'),
    ).toBeTruthy()
    expect(
      container.querySelector('[data-testid="radio-group-set_check_mode"]'),
    ).toBeTruthy()
  })

  it("renders disclosure radio group for expected set source", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="radio-group-set_check_source"]'),
    ).toBeTruthy()
  })

  it("shows tag input when fixed set selected, hides reference key input", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a", "b"],
          reference_key: null,
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="tag-input-set_check_expected_set"]',
      ),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="form-element-set_check_reference_key"]',
      ),
    ).toBeNull()
  })

  it("shows reference key input when reference data selected, hides tag input", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-set_check_reference_key"]',
      ),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="tag-input-set_check_expected_set"]',
      ),
    ).toBeNull()
  })

  it("has 'Output Value' label with Jinja tooltip", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-set_check_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })

  it("Output Value description ends with 'Must be an array.'", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-set_check_value_expression"]',
    )
    const desc = formElement?.getAttribute("data-description") || ""
    expect(desc).toContain("Leave blank to compare entire output")
    expect(desc).toContain("Must be an array.")
  })

  it("renders all three comparison mode options", () => {
    const { getAllByText } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    expect(getAllByText("Equal").length).toBeGreaterThan(0)
    expect(getAllByText("Subset").length).toBeGreaterThan(0)
    expect(getAllByText("Superset").length).toBeGreaterThan(0)
  })

  it("validate returns error when reference_key source is selected but empty", async () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "key",
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({
      properties: {
        type: "set_check" as const,
        mode: "equal" as const,
        value_expression: null,
        expected_set: null,
        reference_key: null,
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).validate()).toBe("Reference key is required.")
  })

  it("getProperties nulls expected_set when reference_key source selected", () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "my_key",
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.expected_set).toBeNull()
    expect(props.reference_key).toBe("my_key")
  })

  it("getProperties nulls reference_key when expected_set source selected", () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a", "b"],
          reference_key: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.reference_key).toBeNull()
    expect(props.expected_set).toEqual(["a", "b"])
  })
})

describe("Phase 8: ToolCallCheckForm section structure and progressive disclosure", () => {
  it("renders Match Mode section with radio group", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="tool-call-match-mode-section"]'),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="radio-group-tool_call_check_match_mode"]',
      ),
    ).toBeTruthy()
  })

  it("renders all four match mode options", () => {
    const { getAllByText } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(getAllByText("Any").length).toBeGreaterThan(0)
    expect(getAllByText("All (any order)").length).toBeGreaterThan(0)
    expect(getAllByText("Ordered (in list order)").length).toBeGreaterThan(0)
    expect(getAllByText("Never").length).toBeGreaterThan(0)
  })

  it("shows Unlisted Tool Calls section when match_mode is not 'never'", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="tool-call-unexpected-section"]'),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="radio-group-tool_call_check_on_unexpected"]',
      ),
    ).toBeTruthy()
  })

  it("hides Unlisted Tool Calls section when match_mode is 'never'", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "never" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="tool-call-unexpected-section"]'),
    ).toBeNull()
  })

  it("renders Expected Tools section with testid", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="tool-call-expected-tools-section"]',
      ),
    ).toBeTruthy()
  })

  it("getProperties returns current match_mode", () => {
    const { component } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "ordered" as const,
          on_unexpected_tools: "fail" as const,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.match_mode).toBe("ordered")
    expect(props.on_unexpected_tools).toBe("fail")
  })

  it("getProperties syncs arg rows to properties", async () => {
    const initProps = {
      type: "tool_call_check" as const,
      expected_tools: [
        {
          tool_name: "search",
          expected_args: {
            query: { value: "hello world", match_mode: "exact" as const },
          },
        },
      ],
      match_mode: "all" as const,
      on_unexpected_tools: "ignore" as const,
    }
    const { component } = render(ToolCallCheckForm, {
      props: { properties: initProps },
    })
    // Null out expected_args on properties directly, diverging from
    // the internal arg_rows (which still hold the deserialized "query" row).
    // If sync_args_to_properties is unwired, getProperties returns this null.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(initProps.expected_tools[0] as any).expected_args = null
    await tick()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    // sync_args_to_properties must have restored args from internal arg_rows
    expect(props.expected_tools[0].expected_args).not.toBeNull()
    expect(props.expected_tools[0].expected_args.query).toEqual({
      value: "hello world",
      match_mode: "exact",
    })
  })
})

describe("Phase 8: StepCountCheckForm section structure and progressive disclosure", () => {
  it("renders What to Count section with radio group", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: 1,
          max_count: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="step-count-type-section"]'),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="radio-group-step_count_check_count_type"]',
      ),
    ).toBeTruthy()
  })

  it("renders all three count type options with descriptions", () => {
    const { getAllByText } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(getAllByText("Tool calls").length).toBeGreaterThan(0)
    expect(getAllByText("Model responses").length).toBeGreaterThan(0)
    expect(getAllByText("Turns").length).toBeGreaterThan(0)
  })

  it("renders Bounds section with testid", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(
      container.querySelector('[data-testid="step-count-bounds-section"]'),
    ).toBeTruthy()
  })

  it("getProperties returns correct count_type", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "model_responses" as const,
          min_count: 2,
          max_count: 10,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.count_type).toBe("model_responses")
    expect(props.min_count).toBe(2)
    expect(props.max_count).toBe(10)
  })

  it("getProperties returns properties directly (not a copy with nulled fields)", () => {
    const { component } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "turns" as const,
          min_count: 5,
          max_count: null,
        },
      },
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props = (component as any).getProperties()
    expect(props.type).toBe("step_count_check")
    expect(props.count_type).toBe("turns")
    expect(props.min_count).toBe(5)
    expect(props.max_count).toBeNull()
  })

  it("renders min and max count form elements", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(
      container.querySelector(
        '[data-testid="form-element-step_count_check_min"]',
      ),
    ).toBeTruthy()
    expect(
      container.querySelector(
        '[data-testid="form-element-step_count_check_max"]',
      ),
    ).toBeTruthy()
  })

  it("renders count type descriptions", () => {
    const { getAllByText } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(
      getAllByText("Count each tool or function call the agent made.").length,
    ).toBeGreaterThan(0)
    expect(
      getAllByText(
        "Count each response the model generated (one per inference call).",
      ).length,
    ).toBeGreaterThan(0)
    expect(
      getAllByText(
        "Count conversational turns (each user-then-assistant exchange counts as one turn).",
      ).length,
    ).toBeGreaterThan(0)
  })
})

// UI polish tests: hidden duplicate labels, indent wrappers, moved controls,
// placeholders, renamed sections, and regex tooltip content.

describe("Standard controls: visible labels (no hidden labels)", () => {
  it("OutputValueField shows visible 'Output Value' label", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const valueExprField = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(valueExprField?.getAttribute("data-hide-label")).toBe("false")
    expect(valueExprField?.getAttribute("data-label")).toBe("Output Value")
  })

  it("ExactMatch expected_value field shows visible 'Value' label", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_expected_value"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Value")
  })

  it("ExactMatch reference_key field shows visible 'Reference Data Field' label", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_reference_key"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Reference Data Field")
  })

  it("PatternMatch regex field shows visible 'Regular Expression' label", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Regular Expression")
  })

  it("Contains substring field shows visible 'Value' label", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_substring"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Value")
  })

  it("Contains reference_key field shows visible 'Reference Data Field' label", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_reference_key"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Reference Data Field")
  })

  it("SetCheck reference_key field shows visible 'Reference Data Field' label", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-set_check_reference_key"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-label")).toBe("Reference Data Field")
  })
})

describe("UI polish: conditional inputs indented under radio selection", () => {
  it("ExactMatch expected_value input is wrapped in indent container", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_expected_value"]',
    )
    const parent = field?.parentElement
    expect(parent?.classList.contains("ml-4")).toBe(true)
    expect(parent?.classList.contains("border-l")).toBe(true)
    expect(parent?.classList.contains("pl-4")).toBe(true)
  })

  it("ExactMatch reference_key input is wrapped in indent container", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_reference_key"]',
    )
    const parent = field?.parentElement
    expect(parent?.classList.contains("ml-4")).toBe(true)
    expect(parent?.classList.contains("border-l")).toBe(true)
  })

  it("Contains substring input is wrapped in indent container", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_substring"]',
    )
    const parent = field?.parentElement
    expect(parent?.classList.contains("ml-4")).toBe(true)
    expect(parent?.classList.contains("border-l")).toBe(true)
  })

  it("Contains reference_key input is wrapped in indent container", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_reference_key"]',
    )
    const parent = field?.parentElement
    expect(parent?.classList.contains("ml-4")).toBe(true)
    expect(parent?.classList.contains("border-l")).toBe(true)
  })
})

describe("UI polish: case-sensitive moved out of OutputValueField", () => {
  it("ExactMatch has case-sensitive in its own Comparison Options section", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const optionsSection = container.querySelector(
      '[data-testid="exact-match-options-section"]',
    )
    expect(optionsSection).toBeTruthy()
    const caseSensitive = optionsSection?.querySelector(
      '[data-testid="form-element-exact_match_case_sensitive"]',
    )
    expect(caseSensitive).toBeTruthy()
  })

  it("ExactMatch case-sensitive is separate from OutputValueField", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const optionsSection = container.querySelector(
      '[data-testid="exact-match-options-section"]',
    )
    const caseSensitive = optionsSection?.querySelector(
      '[data-testid="form-element-exact_match_case_sensitive"]',
    )
    expect(caseSensitive).toBeTruthy()
  })

  it("Contains has case-sensitive in its own Comparison Options section", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const optionsSection = container.querySelector(
      '[data-testid="contains-options-section"]',
    )
    expect(optionsSection).toBeTruthy()
    const caseSensitive = optionsSection?.querySelector(
      '[data-testid="form-element-contains_case_sensitive"]',
    )
    expect(caseSensitive).toBeTruthy()
  })

  it("Contains case-sensitive is separate from OutputValueField", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const optionsSection = container.querySelector(
      '[data-testid="contains-options-section"]',
    )
    const caseSensitive = optionsSection?.querySelector(
      '[data-testid="form-element-contains_case_sensitive"]',
    )
    expect(caseSensitive).toBeTruthy()
  })
})

describe("UI polish: placeholders on inputs", () => {
  it("ExactMatch expected_value has placeholder", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_expected_value"]',
    )
    expect(field?.getAttribute("data-placeholder")).toBe("e.g. yes")
  })

  it("ExactMatch reference_key has placeholder", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_reference_key"]',
    )
    expect(field?.getAttribute("data-placeholder")).toBe("e.g. expected_answer")
  })

  it("PatternMatch regex field has placeholder", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    expect(field?.getAttribute("data-placeholder")).toBe("e.g. ^(yes|no)$")
  })

  it("Contains substring has placeholder", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_substring"]',
    )
    expect(field?.getAttribute("data-placeholder")).toBe("e.g. success")
  })

  it("Contains reference_key has placeholder", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_reference_key"]',
    )
    expect(field?.getAttribute("data-placeholder")).toBe(
      "e.g. expected_keyword",
    )
  })
})

describe("Standard controls: PatternMatch uses single FormElement with 'Regular Expression' label", () => {
  it("Pattern FormElement has label 'Regular Expression' (no duplicate section title)", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="pattern-match-pattern-section"]',
    )
    expect(section).toBeTruthy()
    const formElement = section?.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    expect(formElement?.getAttribute("data-label")).toBe("Regular Expression")
    const heading = section?.querySelector("h3")
    expect(heading).toBeNull()
  })
})

describe("UI polish: regex tooltip is educational", () => {
  it("PatternMatch regex tooltip explains what regex is with an example", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("regular expression")
    expect(tooltip).toContain("regex")
    expect(tooltip).toContain("^yes$")
  })
})

describe("Standard controls: reference key info tooltips", () => {
  it("ExactMatch reference_key has info_description about Jinja extractor syntax", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_reference_key"]',
    )
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("reference data object")
    expect(tooltip).toContain("Jinja extractor syntax")
  })

  it("Contains reference_key has info_description about Jinja extractor syntax", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_reference_key"]',
    )
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("reference data object")
    expect(tooltip).toContain("Jinja extractor syntax")
  })

  it("SetCheck reference_key has description mentioning array and Jinja tooltip", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-set_check_reference_key"]',
    )
    const desc = field?.getAttribute("data-description") || ""
    expect(desc).toContain("document.tags")
    expect(desc).toContain("Must be an array.")
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("reference data object")
    expect(tooltip).toContain("Jinja extractor syntax")
  })
})

describe("Standard controls: OutputValueField is a plain FormElement", () => {
  it("OutputValueField renders as a standard FormElement without FormSection wrapper", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="output-value-section"]',
    )
    expect(section).toBeNull()
    const formElement = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
  })
})

describe("Standard controls: description and tooltip on visible-label fields", () => {
  it("OutputValueField has description and Jinja tooltip with visible label", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-description")).toContain("user.status")
    expect(field?.getAttribute("data-info-description")).toContain("Jinja")
  })

  it("PatternMatch regex field has description and tooltip with visible label", () => {
    const { container } = render(PatternMatchForm, {
      props: {
        properties: {
          type: "pattern_match" as const,
          pattern: "test",
          mode: "must_match" as const,
          value_expression: null,
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-pattern_match_pattern"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-description")).toContain("pattern")
    expect(field?.getAttribute("data-info-description")).toContain(
      "regular expression",
    )
  })

  it("ExactMatch reference_key has description and Jinja tooltip with visible label", () => {
    const { container } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "my_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-exact_match_reference_key"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-description")).toContain(
      "user.expected_status",
    )
    expect(field?.getAttribute("data-info-description")).toContain(
      "reference data object",
    )
  })

  it("Contains reference_key has description and Jinja tooltip with visible label", () => {
    const { container } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-contains_reference_key"]',
    )
    expect(field?.getAttribute("data-hide-label")).toBe("false")
    expect(field?.getAttribute("data-description")).toContain(
      "user.expected_status",
    )
    expect(field?.getAttribute("data-info-description")).toContain(
      "reference data object",
    )
  })
})

// ──────────────────────────────────────────────────────────────────
// Phase 9: set_check, tool_call_check, step_count_check UI polish
// ──────────────────────────────────────────────────────────────────

describe("SetCheckForm UI polish", () => {
  it("tag input has a visible label when fixed values source is selected", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const label = container.querySelector('[data-testid="tag-input-label"]')
    expect(label).toBeTruthy()
    expect(label?.textContent).toBe("Expected Values")
  })

  it("comparison mode descriptions use plain language", () => {
    const { getAllByText } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    expect(
      getAllByText(
        "The output must contain exactly the expected values, with no extras and nothing missing.",
      ).length,
    ).toBeGreaterThan(0)
    expect(
      getAllByText(
        "Every output value must appear in the expected values (extras in expected are OK).",
      ).length,
    ).toBeGreaterThan(0)
    expect(
      getAllByText(
        "Every expected value must appear in the output (extra output values are OK).",
      ).length,
    ).toBeGreaterThan(0)
  })

  it("reference key field has info_description tooltip about Jinja extractor", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-set_check_reference_key"]',
    )
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("reference data object")
    expect(tooltip).toContain("Jinja extractor syntax")
  })

  it("conditional tag input is wrapped in indent container", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const tagInput = container.querySelector(
      '[data-testid="tag-input-set_check_expected_set"]',
    )
    const indent = tagInput?.closest(".ml-4.border-l.pl-4")
    expect(indent).toBeTruthy()
  })

  it("conditional reference key input is wrapped in indent container", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "ref_key",
        },
      },
    })
    const field = container.querySelector(
      '[data-testid="form-element-set_check_reference_key"]',
    )
    const parent = field?.parentElement
    expect(parent?.classList.contains("ml-4")).toBe(true)
    expect(parent?.classList.contains("border-l")).toBe(true)
    expect(parent?.classList.contains("pl-4")).toBe(true)
  })

  it("section title is 'Expected Values' not 'Expected Set'", () => {
    const { container } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: ["a"],
          reference_key: null,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="set-check-expected-section"]',
    )
    const heading = section?.querySelector("h3")
    expect(heading?.textContent).toBe("Expected Values")
  })
})

describe("ToolCallCheckForm UI polish", () => {
  it("Expected Tools section appears before Match Mode section in DOM", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const sections = container.querySelectorAll("[data-testid]")
    const sectionIds = Array.from(sections).map((s) =>
      s.getAttribute("data-testid"),
    )
    const toolsIdx = sectionIds.indexOf("tool-call-expected-tools-section")
    const matchIdx = sectionIds.indexOf("tool-call-match-mode-section")
    expect(toolsIdx).toBeGreaterThanOrEqual(0)
    expect(matchIdx).toBeGreaterThanOrEqual(0)
    expect(toolsIdx).toBeLessThan(matchIdx)
  })

  it("does not duplicate 'Expected Tools' as both section title and item header", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const toolsSection = container.querySelector(
      '[data-testid="tool-call-expected-tools-section"]',
    )
    expect(toolsSection).toBeTruthy()
    const headings = toolsSection?.querySelectorAll("h3")
    const headingTexts = Array.from(headings || []).map(
      (h) => h.textContent || "",
    )
    expect(headingTexts.filter((t) => t === "Expected Tools")).toHaveLength(1)
  })

  it("arg row header says 'Comparison' not 'Match'", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [
            {
              tool_name: "search",
              expected_args: {
                query: { value: "test", match_mode: "exact" as const },
              },
            },
          ],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const argMatchField = container.querySelector(
      '[data-testid="form-element-arg_match_0_0"]',
    )
    expect(argMatchField?.getAttribute("data-label")).toBe("Comparison")
  })

  it("tool fields are nested with indent pattern", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const toolNameField = container.querySelector(
      '[data-testid="form-element-tool_name_0"]',
    )
    const indent = toolNameField?.closest(".ml-4.border-l.pl-4")
    expect(indent).toBeTruthy()
  })

  it("match mode descriptions distinguish 'any order' vs 'in list order'", () => {
    const { getAllByText } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    expect(getAllByText("All (any order)").length).toBeGreaterThan(0)
    expect(getAllByText("Ordered (in list order)").length).toBeGreaterThan(0)
  })

  it("subtitle contextualizes for 'never' mode", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "never" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="tool-call-expected-tools-section"]',
    )
    const subtitle = section?.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle?.textContent).toContain("must NOT call")
  })

  it("subtitle for non-never mode says 'expected to call'", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="tool-call-expected-tools-section"]',
    )
    const subtitle = section?.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle?.textContent).toContain("expected to call")
  })

  it("section title is 'Unlisted Tool Calls' not 'On Unexpected Tools'", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const section = container.querySelector(
      '[data-testid="tool-call-unexpected-section"]',
    )
    const heading = section?.querySelector("h3")
    expect(heading?.textContent).toBe("Unlisted Tool Calls")
  })

  it("Expected Arguments collapse has a description", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [{ tool_name: "search", expected_args: null }],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const collapse = container.querySelector('[data-testid="collapse-stub"]')
    expect(collapse?.getAttribute("data-title")).toBe("Expected Arguments")
  })

  it("arg value field has info_description about JSON format", () => {
    const { container } = render(ToolCallCheckForm, {
      props: {
        properties: {
          type: "tool_call_check" as const,
          expected_tools: [
            {
              tool_name: "search",
              expected_args: {
                query: { value: "test", match_mode: "exact" as const },
              },
            },
          ],
          match_mode: "all" as const,
          on_unexpected_tools: "ignore" as const,
        },
      },
    })
    const argValueField = container.querySelector(
      '[data-testid="form-element-arg_value_0_0"]',
    )
    const tooltip = argValueField?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("JSON")
    expect(tooltip).toContain("quoted")
  })
})

describe("StepCountCheckForm UI polish", () => {
  it("min and max inputs are in a side-by-side flex row", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const boundsRow = container.querySelector('[data-testid="bounds-row"]')
    expect(boundsRow).toBeTruthy()
    expect(boundsRow?.classList.contains("flex")).toBe(true)
    const minField = boundsRow?.querySelector(
      '[data-testid="form-element-step_count_check_min"]',
    )
    const maxField = boundsRow?.querySelector(
      '[data-testid="form-element-step_count_check_max"]',
    )
    expect(minField).toBeTruthy()
    expect(maxField).toBeTruthy()
  })

  it("bounds error is shown once, not duplicated on both inputs", async () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: 10,
          max_count: 5,
        },
      },
    })
    // Before blur, no error is shown (bounds_touched is false)
    expect(
      container.querySelectorAll('[data-testid="bounds-error"]'),
    ).toHaveLength(0)

    // Fire blur on the wrapper div to trigger on_bounds_blur
    const boundsRow = container.querySelector('[data-testid="bounds-row"]')
    const blurWrapper = boundsRow?.parentElement
    expect(blurWrapper).toBeTruthy()
    await fireEvent.blur(blurWrapper!)
    await tick()

    // Error should appear exactly once (not on each input individually)
    const errorElements = container.querySelectorAll(
      '[data-testid="bounds-error"]',
    )
    expect(errorElements).toHaveLength(1)
    expect(errorElements[0].textContent).toContain("Minimum must be")
  })

  it("min field has placeholder 'No minimum'", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const minField = container.querySelector(
      '[data-testid="form-element-step_count_check_min"]',
    )
    expect(minField?.getAttribute("data-placeholder")).toBe("No minimum")
  })

  it("max field has placeholder 'No maximum'", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const maxField = container.querySelector(
      '[data-testid="form-element-step_count_check_max"]',
    )
    expect(maxField?.getAttribute("data-placeholder")).toBe("No maximum")
  })

  it("min label is 'Minimum' not 'Minimum Count'", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const minField = container.querySelector(
      '[data-testid="form-element-step_count_check_min"]',
    )
    expect(minField?.getAttribute("data-label")).toBe("Minimum")
  })

  it("max label is 'Maximum' not 'Maximum Count'", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const maxField = container.querySelector(
      '[data-testid="form-element-step_count_check_max"]',
    )
    expect(maxField?.getAttribute("data-label")).toBe("Maximum")
  })

  it("bounds are nested with indent pattern", () => {
    const { container } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "tool_calls" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    const boundsRow = container.querySelector('[data-testid="bounds-row"]')
    const indent = boundsRow?.closest(".ml-4.border-l.pl-4")
    expect(indent).toBeTruthy()
  })

  it("turns description clarifies user-then-assistant exchange", () => {
    const { getAllByText } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "turns" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(
      getAllByText(
        "Count conversational turns (each user-then-assistant exchange counts as one turn).",
      ).length,
    ).toBeGreaterThan(0)
  })

  it("model_responses description clarifies one per inference call", () => {
    const { getAllByText } = render(StepCountCheckForm, {
      props: {
        properties: {
          type: "step_count_check" as const,
          count_type: "model_responses" as const,
          min_count: null,
          max_count: null,
        },
      },
    })
    expect(
      getAllByText(
        "Count each response the model generated (one per inference call).",
      ).length,
    ).toBeGreaterThan(0)
  })
})
