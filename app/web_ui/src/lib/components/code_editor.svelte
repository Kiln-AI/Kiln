<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte"

  export let value: string = ""
  export let readonly: boolean = false
  export let placeholder: string = ""
  export let min_height: string = "200px"

  const dispatch = createEventDispatcher<{ change: string }>()

  let container: HTMLDivElement
  let view: import("@codemirror/view").EditorView | undefined
  let loading = true

  onMount(async () => {
    const [
      { EditorView, keymap, placeholder: placeholderExt, lineNumbers },
      { EditorState },
      { python },
      { defaultKeymap, history, historyKeymap },
      { syntaxHighlighting, defaultHighlightStyle },
    ] = await Promise.all([
      import("@codemirror/view"),
      import("@codemirror/state"),
      import("@codemirror/lang-python"),
      import("@codemirror/commands"),
      import("@codemirror/language"),
    ])

    const extensions = [
      lineNumbers(),
      history(),
      syntaxHighlighting(defaultHighlightStyle),
      python(),
      keymap.of([...defaultKeymap, ...historyKeymap]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          value = update.state.doc.toString()
          dispatch("change", value)
        }
      }),
      EditorView.theme({
        "&": { minHeight: min_height },
        ".cm-scroller": { overflow: "auto" },
        ".cm-content": { fontFamily: "monospace", fontSize: "14px" },
        ".cm-gutters": {
          backgroundColor: "transparent",
          borderRight: "1px solid oklch(var(--bc) / 0.2)",
        },
      }),
    ]

    if (placeholder) {
      extensions.push(placeholderExt(placeholder))
    }

    if (readonly) {
      extensions.push(EditorState.readOnly.of(true))
    }

    view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions,
      }),
      parent: container,
    })

    loading = false
  })

  onDestroy(() => {
    view?.destroy()
  })

  export function setValue(newValue: string) {
    if (view) {
      const currentValue = view.state.doc.toString()
      if (currentValue !== newValue) {
        view.dispatch({
          changes: {
            from: 0,
            to: view.state.doc.length,
            insert: newValue,
          },
        })
      }
    }
    value = newValue
  }

  export function getValue(): string {
    return view ? view.state.doc.toString() : value
  }
</script>

<div
  class="code-editor-wrapper rounded-lg border border-base-300 overflow-hidden"
>
  {#if loading}
    <div
      class="flex items-center justify-center bg-base-200/50"
      style="min-height: {min_height}"
    >
      <div class="loading loading-spinner loading-md"></div>
    </div>
  {/if}
  <div
    bind:this={container}
    class:hidden={loading}
    class="code-editor-container"
  ></div>
</div>
