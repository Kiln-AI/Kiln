// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
// Pins the behavior restored by flipping SHOW_REFERENCE_DATA_UI back on, so the
// gated code paths don't rot while reference data is hidden from the UI.
vi.mock("$lib/utils/eval_types/reference_data_ui", () => ({
  SHOW_REFERENCE_DATA_UI: true,
}))

import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import("./__tests__/form_element_stub.svelte")
  return { default: Stub }
})

vi.mock("./tag_input.svelte", async () => {
  const { default: Stub } = await import("./__tests__/tag_input_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const { default: Stub } = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub }
})

const ExactMatchForm = (await import("./exact_match_form.svelte")).default
const ContainsForm = (await import("./contains_form.svelte")).default
const SetCheckForm = (await import("./set_check_form.svelte")).default

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
      container.querySelector(
        '[data-testid="form-element-exact_match_source"]',
      ),
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
      container.querySelector('[data-testid="form-element-contains_source"]'),
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
})

describe("Phase 8: SetCheckForm section structure and progressive disclosure", () => {
  it("renders Expected Values radio with label", () => {
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
    const el = container.querySelector(
      '[data-testid="form-element-set_check_source"]',
    )
    expect(el).toBeTruthy()
    expect(el?.getAttribute("data-label")).toBe("Expected Values")
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
})

describe("Standard controls: visible labels (no hidden labels)", () => {
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

describe("UI polish: placeholders on inputs", () => {
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
    expect(field?.getAttribute("data-placeholder")).toBe("e.g. expected_answer")
  })
})

describe("Standard controls: reference key info tooltips", () => {
  it("ExactMatch reference_key has info_description about top-level field", () => {
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
    expect(tooltip).toContain("top-level field")
    expect(tooltip).toContain("expected_answer")
  })

  it("Contains reference_key has info_description about top-level field", () => {
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
    expect(tooltip).toContain("top-level field")
    expect(tooltip).toContain("expected_answer")
  })

  it("SetCheck reference_key has description and tooltip about top-level field", () => {
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
    expect(desc).toContain("reference data")
    expect(desc).toContain("expected value")
    const tooltip = field?.getAttribute("data-info-description") || ""
    expect(tooltip).toContain("top-level field")
    expect(tooltip).toContain("expected_answer")
  })
})

describe("Standard controls: description and tooltip on visible-label fields", () => {
  it("ExactMatch reference_key has description and tooltip with visible label", () => {
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
    expect(field?.getAttribute("data-description")).toContain("reference data")
    expect(field?.getAttribute("data-info-description")).toContain(
      "top-level field",
    )
  })

  it("Contains reference_key has description and tooltip with visible label", () => {
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
    expect(field?.getAttribute("data-description")).toContain("reference data")
    expect(field?.getAttribute("data-info-description")).toContain(
      "top-level field",
    )
  })
})

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
    const header = container.querySelector(
      '[data-testid="form-element-set_check_expected_values_header"]',
    )
    expect(header).toBeTruthy()
    expect(header?.getAttribute("data-label")).toBe("Values")
    expect(header?.getAttribute("data-description")).toBe(
      "Add items by typing and pressing Enter or comma.",
    )
  })

  it("reference key field has info_description tooltip about top-level field", () => {
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
    expect(tooltip).toContain("top-level field")
    expect(tooltip).toContain("expected_answer")
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

  it("label is 'Expected Values' not 'Expected Set'", () => {
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
    const el = container.querySelector(
      '[data-testid="form-element-set_check_source"]',
    )
    expect(el?.getAttribute("data-label")).toBe("Expected Values")
  })
})

describe("required_reference_fields computation", () => {
  it("ExactMatch: empty when fixed value source is selected", () => {
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
    expect((component as any).required_reference_fields).toEqual([])
  })

  it("ExactMatch: contains key when reference_key source is selected", async () => {
    const { component } = render(ExactMatchForm, {
      props: {
        properties: {
          type: "exact_match" as const,
          case_sensitive: true,
          value_expression: null,
          expected_value: null,
          reference_key: "expected_answer",
        },
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).required_reference_fields).toEqual([
      "expected_answer",
    ])
  })

  it("ExactMatch: empty when reference_key source is selected but key is null", async () => {
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
    // Switch to reference_key source
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
    expect((component as any).required_reference_fields).toEqual([])
  })

  it("Contains: contains key when reference_key source is selected", async () => {
    const { component } = render(ContainsForm, {
      props: {
        properties: {
          type: "contains" as const,
          case_sensitive: true,
          mode: "must_contain" as const,
          value_expression: null,
          substring: null,
          reference_key: "expected_keyword",
        },
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).required_reference_fields).toEqual([
      "expected_keyword",
    ])
  })

  it("Contains: empty when substring source is selected", () => {
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
    expect((component as any).required_reference_fields).toEqual([])
  })

  it("SetCheck: contains key when reference_key source is selected", async () => {
    const { component } = render(SetCheckForm, {
      props: {
        properties: {
          type: "set_check" as const,
          mode: "equal" as const,
          value_expression: null,
          expected_set: null,
          reference_key: "expected_tags",
        },
      },
    })
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).required_reference_fields).toEqual([
      "expected_tags",
    ])
  })

  it("SetCheck: empty when expected_set source is selected", () => {
    const { component } = render(SetCheckForm, {
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).required_reference_fields).toEqual([])
  })
})
