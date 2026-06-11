// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import AskUserQuestion from "./ask_user_question.svelte"

afterEach(() => cleanup())

describe("AskUserQuestion card", () => {
  it("renders the question, each option's main line + explanation, and 'Chat about this'", () => {
    const { getByText, getByRole } = render(AskUserQuestion, {
      props: {
        question: "Which model should we use?",
        suggestedAnswers: [
          { answer: "GPT-4o", explanation: "Best quality, higher cost." },
          { answer: "Llama 3", explanation: "Open and cheap." },
        ],
        onPick: vi.fn(),
        onChat: vi.fn(),
      },
    })

    expect(getByText("Which model should we use?")).toBeTruthy()
    expect(getByText("GPT-4o")).toBeTruthy()
    expect(getByText("Best quality, higher cost.")).toBeTruthy()
    expect(getByText("Llama 3")).toBeTruthy()
    expect(getByText("Open and cheap.")).toBeTruthy()
    // "Chat about this" is always present.
    expect(
      getByRole("button", {
        name: /chat about this/i,
      }),
    ).toBeTruthy()
  })

  it("one click on an option calls onPick with that answer's main line", async () => {
    const onPick = vi.fn()
    const { getByRole } = render(AskUserQuestion, {
      props: {
        question: "Pick one",
        suggestedAnswers: [{ answer: "Option A", explanation: "" }],
        onPick,
        onChat: vi.fn(),
      },
    })

    await fireEvent.click(
      getByRole("button", { name: /send answer: option a/i }),
    )
    expect(onPick).toHaveBeenCalledWith("Option A")
  })

  it("'Chat about this' calls onChat", async () => {
    const onChat = vi.fn()
    const { getByRole } = render(AskUserQuestion, {
      props: {
        question: "Pick one",
        suggestedAnswers: [],
        onPick: vi.fn(),
        onChat,
      },
    })

    await fireEvent.click(getByRole("button", { name: /chat about this/i }))
    expect(onChat).toHaveBeenCalledTimes(1)
  })

  it("with no suggested answers shows just the question + 'Chat about this'", () => {
    const { getByText, getByRole, queryAllByRole } = render(AskUserQuestion, {
      props: {
        question: "Open ended?",
        suggestedAnswers: [],
        onPick: vi.fn(),
        onChat: vi.fn(),
      },
    })
    expect(getByText("Open ended?")).toBeTruthy()
    expect(getByRole("button", { name: /chat about this/i })).toBeTruthy()
    // The only button is "Chat about this" (no option buttons).
    expect(queryAllByRole("button")).toHaveLength(1)
  })

  it("collapses to 'You chose: <answer>' once resolved with a pick", () => {
    const { getByText, queryByRole } = render(AskUserQuestion, {
      props: {
        question: "Pick one",
        suggestedAnswers: [{ answer: "Option A", explanation: "why" }],
        resolution: { kind: "pick", answer: "Option A" },
        onPick: vi.fn(),
        onChat: vi.fn(),
      },
    })
    expect(getByText(/you chose:/i)).toBeTruthy()
    expect(getByText("Option A")).toBeTruthy()
    // Resolved card is non-interactive (no buttons).
    expect(queryByRole("button")).toBeNull()
  })

  it("collapses to 'You chose to chat about this' once resolved with chat", () => {
    const { getByText, queryByRole } = render(AskUserQuestion, {
      props: {
        question: "Pick one",
        suggestedAnswers: [],
        resolution: { kind: "chat" },
        onPick: vi.fn(),
        onChat: vi.fn(),
      },
    })
    expect(getByText(/you chose to chat about this/i)).toBeTruthy()
    expect(queryByRole("button")).toBeNull()
  })

  it("disables the option + chat buttons while disabled", () => {
    const { getByRole } = render(AskUserQuestion, {
      props: {
        question: "Pick one",
        suggestedAnswers: [{ answer: "Option A", explanation: "" }],
        disabled: true,
        onPick: vi.fn(),
        onChat: vi.fn(),
      },
    })
    expect(
      (
        getByRole("button", {
          name: /send answer: option a/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(
      (getByRole("button", { name: /chat about this/i }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })
})
