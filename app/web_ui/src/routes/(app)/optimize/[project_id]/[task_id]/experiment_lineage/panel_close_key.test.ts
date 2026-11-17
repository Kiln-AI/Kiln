// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { closes_panel } from "./panel_close_key"

afterEach(() => {
  document.body.innerHTML = ""
})

function key_on(target: Element, init: KeyboardEventInit): KeyboardEvent {
  let seen: KeyboardEvent | null = null
  const listener = (event: Event) => {
    seen = event as KeyboardEvent
  }
  window.addEventListener("keydown", listener)
  target.dispatchEvent(
    new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init }),
  )
  window.removeEventListener("keydown", listener)
  if (!seen) {
    throw new Error("keydown did not reach the window")
  }
  return seen
}

function add(html: string): Element {
  document.body.insertAdjacentHTML("beforeend", html)
  return document.body.lastElementChild as Element
}

describe("closes_panel", () => {
  it("closes on an Escape from anywhere on the page", () => {
    const text = add("<p>Notes</p>")
    expect(closes_panel(key_on(text, { key: "Escape" }))).toBe(true)
    expect(closes_panel(key_on(document.body, { key: "Escape" }))).toBe(true)
  })

  it("ignores other keys", () => {
    expect(closes_panel(key_on(document.body, { key: "Enter" }))).toBe(false)
  })

  it("ignores an Escape another handler already took", () => {
    const button = add("<button>Close</button>")
    button.addEventListener("keydown", (event) => event.preventDefault())
    expect(closes_panel(key_on(button, { key: "Escape" }))).toBe(false)
  })

  it.each([
    "<input />",
    "<textarea></textarea>",
    "<select></select>",
    '<div contenteditable="true"><span>typing</span></div>',
  ])("ignores an Escape typed into %s", (html) => {
    const field = add(html)
    const target = field.querySelector("span") ?? field
    expect(closes_panel(key_on(target, { key: "Escape" }))).toBe(false)
  })

  it("ignores an Escape while a dialog is open", () => {
    const dialog = add("<dialog open><p>Input Transformer</p></dialog>")
    expect(
      closes_panel(
        key_on(dialog.firstElementChild as Element, { key: "Escape" }),
      ),
    ).toBe(false)
  })
})
