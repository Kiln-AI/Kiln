// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"

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
      "At least one of minimum or maximum count must be set.",
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
      "Minimum count must be less than or equal to maximum count.",
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

  it("validate returns error when a tool has empty name", () => {
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
      "All expected tools must have a name.",
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
