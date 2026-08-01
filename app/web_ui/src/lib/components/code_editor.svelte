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
  // Set when CodeMirror could not be brought up at all. Bringing it up is five
  // dynamic imports and a pile of setup, every step of which can fail for
  // reasons that are nothing to do with this component - a dev server serving a
  // stale optimized dep (two copies of @codemirror/state break its instanceof
  // checks), a chunk that never arrives, a browser the bundle does not run on.
  // Without this the failure was invisible: `loading` stayed true forever, so a
  // dead editor and a slow one looked exactly alike, and the user got a spinner
  // that never resolved with nothing said anywhere.
  let load_error: string | null = null

  onMount(async () => {
    try {
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
    } catch (error) {
      // Logged as well as shown: the message the user needs ("this is plain
      // text now") and the one whoever debugs it needs are different, and the
      // second one belongs in the console with its stack.
      console.error(
        "Code editor failed to load, falling back to plain text",
        error,
      )
      load_error = error instanceof Error ? error.message : String(error)
      // A view that was constructed and then failed later would leave a
      // half-built editor in the DOM under the fallback.
      view?.destroy()
      view = undefined
    } finally {
      loading = false
    }
  })

  function on_fallback_input(event: Event) {
    value = (event.currentTarget as HTMLTextAreaElement).value
    dispatch("change", value)
  }

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
  {:else if load_error}
    <!-- Fallback. Unhighlighted code beats no code: everything CodeMirror was
         carrying here is a reading aid, and the code itself is the content. An
         editable one falls back to a textarea rather than a <pre> for the same
         reason - losing the highlighting is a worse view, losing the input is a
         dead page. -->
    <div
      class="px-3 py-2 text-xs bg-warning/10 border-b border-base-300 text-base-content/70"
    >
      Code editor failed to load — showing plain text.
      <span class="opacity-70">({load_error})</span>
    </div>
    {#if readonly}
      <pre
        class="code-editor-fallback overflow-auto p-3 text-sm"
        style="min-height: {min_height}">{value}</pre>
    {:else}
      <textarea
        class="code-editor-fallback w-full p-3 text-sm bg-transparent resize-y focus:outline-none"
        style="min-height: {min_height}"
        {placeholder}
        {value}
        on:input={on_fallback_input}
      ></textarea>
    {/if}
  {/if}
  <div
    bind:this={container}
    class:hidden={loading || load_error !== null}
    class="code-editor-container"
  ></div>
</div>

<style>
  /* Matches the CodeMirror content it stands in for */
  .code-editor-fallback {
    font-family: monospace;
    font-size: 14px;
    white-space: pre;
    tab-size: 4;
  }
</style>
