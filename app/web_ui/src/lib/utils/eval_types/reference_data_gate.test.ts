import { describe, it, expect } from "vitest"
import {
  uses_reference_data_llm_judge,
  uses_reference_data_code_eval,
} from "./reference_data_gate"

describe("uses_reference_data_llm_judge", () => {
  it("returns true when prompt contains reference_data", () => {
    expect(uses_reference_data_llm_judge("{{ reference_data.answer }}")).toBe(
      true,
    )
  })

  it("returns true for reference_data without Jinja syntax", () => {
    expect(
      uses_reference_data_llm_judge("Check reference_data for answer"),
    ).toBe(true)
  })

  it("returns false when prompt does not contain reference_data", () => {
    expect(uses_reference_data_llm_judge("{{ final_message }}")).toBe(false)
  })

  it("returns false for empty prompt", () => {
    expect(uses_reference_data_llm_judge("")).toBe(false)
  })
})

describe("uses_reference_data_code_eval", () => {
  it("returns true when body uses reference_data dict access", () => {
    const code = `def score(output, trace, reference_data, task_input):
    expected = reference_data.get("answer")
    return {"q": 1.0 if output == expected else 0.0}`
    expect(uses_reference_data_code_eval(code)).toBe(true)
  })

  it("returns true when body uses reference_data bracket access", () => {
    const code = `def score(output, trace, reference_data, task_input):
    val = reference_data["expected"]
    return {"q": 1.0 if val else 0.0}`
    expect(uses_reference_data_code_eval(code)).toBe(true)
  })

  it("returns false when only the signature mentions reference_data", () => {
    const code = `def score(output, trace, reference_data, task_input):
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false for async signature-only mention", () => {
    const code = `async def score(output, trace, reference_data, task_input):
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false for docstring mentioning reference_data", () => {
    const code = `def score(output, trace, reference_data, task_input):
    """Uses reference_data for ground truth."""
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false for empty code", () => {
    expect(uses_reference_data_code_eval("")).toBe(false)
  })

  it("returns false when reference_data is only in a comment", () => {
    const code = `def score(output, trace, reference_data, task_input):
    # reference_data has the expected answer
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns true when reference_data used in nested function", () => {
    const code = `def score(output, trace, reference_data, task_input):
    def helper():
        return reference_data["key"]
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(true)
  })

  it("returns false for the default starter code (docstring + signature only)", () => {
    const code = `def score(output, trace, reference_data, task_input):
    """Score the model output.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of reference/expected data (if any).
        task_input: The original task input string.

    Returns:
        no_dark_humour: return 0.0 for Fail or 1.0 for Pass
    """
    if not output:
        return {"no_dark_humour": 0.0}
    return {"no_dark_humour": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns true when body reads reference_data.get after a docstring", () => {
    const code = `def score(output, trace, reference_data, task_input):
    """Grade output."""
    expected = reference_data.get("expected_answer", "")
    return {"q": 1.0 if output == expected else 0.0}`
    expect(uses_reference_data_code_eval(code)).toBe(true)
  })

  it("returns false for multi-line def score(...) signature with reference_data param but no body usage", () => {
    const code = `def score(
    output,
    trace,
    reference_data,
    task_input,
):
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false for multi-line async def score signature", () => {
    const code = `async def score(
    output,
    trace,
    reference_data,
    task_input,
):
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false when reference_data appears only in a single-quoted string", () => {
    const code = `def score(output):
    msg = 'reference_data is not used here'
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false when reference_data appears only in a double-quoted string", () => {
    const code = `def score(output):
    msg = "reference_data is not used here"
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns false for triple-quoted string with reference_data spanning multiple lines", () => {
    const code = `def score(output):
    msg = """
    This mentions reference_data
    across multiple lines.
    """
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(false)
  })

  it("returns true when real usage exists alongside comment and docstring mentions", () => {
    const code = `def score(output, trace, reference_data, task_input):
    """Uses reference_data for ground truth."""
    # reference_data has the answer
    val = reference_data["key"]
    return {"q": 1.0}`
    expect(uses_reference_data_code_eval(code)).toBe(true)
  })
})
