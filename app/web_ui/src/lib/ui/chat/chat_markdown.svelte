<script lang="ts">
  import { Marked, type Token } from "marked"
  import DOMPurify from "dompurify"
  import hljs from "highlight.js/lib/core"
  import json from "highlight.js/lib/languages/json"
  import javascript from "highlight.js/lib/languages/javascript"
  import typescript from "highlight.js/lib/languages/typescript"
  import python from "highlight.js/lib/languages/python"
  import bash from "highlight.js/lib/languages/bash"

  hljs.registerLanguage("json", json)
  hljs.registerLanguage("javascript", javascript)
  hljs.registerLanguage("js", javascript)
  hljs.registerLanguage("typescript", typescript)
  hljs.registerLanguage("ts", typescript)
  hljs.registerLanguage("python", python)
  hljs.registerLanguage("py", python)
  hljs.registerLanguage("bash", bash)
  hljs.registerLanguage("shell", bash)
  hljs.registerLanguage("sh", bash)

  function escapeHtml(s: string): string {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
  }

  const md = new Marked({
    gfm: true,
    renderer: {
      code({ text, lang }: { text: string; lang?: string }) {
        const code = text ?? ""
        const language = (lang ?? "").toLowerCase()
        let highlighted: string
        if (language && hljs.getLanguage(language)) {
          try {
            highlighted = hljs.highlight(code, { language }).value
          } catch {
            highlighted = escapeHtml(code)
          }
        } else {
          try {
            highlighted = hljs.highlightAuto(code).value
          } catch {
            highlighted = escapeHtml(code)
          }
        }
        return `<pre class="hljs rounded-lg bg-base-300/40 overflow-x-auto p-3 text-sm"><code>${highlighted}</code></pre>`
      },
      codespan({ text }: { text: string }) {
        return `<code class="px-1.5 py-0.5 rounded bg-base-300/50 text-sm font-mono text-base-content/90">${escapeHtml(text ?? "")}</code>`
      },
      blockquote({ tokens }: { tokens: Token[] }) {
        const inner = this.parser.parse(tokens)
        return `<blockquote class="border-l-4 border-base-300 pl-4 my-2 text-base-content/80">${inner}</blockquote>`
      },
    },
  })

  const ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "span",
    "div",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
  ]
  const ALLOWED_ATTR = [
    "href",
    "target",
    "rel",
    "class",
    "colspan",
    "rowspan",
    "scope",
  ]

  export let text: string = ""

  $: rawHtml = text ? (md.parse(text, { async: false }) as string) : ""
  $: sanitized = rawHtml
    ? DOMPurify.sanitize(rawHtml, {
        ALLOWED_TAGS,
        ALLOWED_ATTR,
        ALLOWED_URI_REGEXP:
          /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
      })
    : ""
</script>

<svelte:head>
  <link rel="stylesheet" href="/styles/highlightjs.min.css" />
</svelte:head>

{#if sanitized}
  <div
    class="chat-markdown prose prose-sm max-w-none overflow-x-auto leading-tight prose-p:my-3 prose-ul:my-3 prose-ol:my-3 prose-li:my-2 prose-headings:mt-3 prose-headings:mb-1 prose-pre:my-1.5 prose-blockquote:my-1.5 prose-table:my-2 prose-a:link"
  >
    {@html sanitized}
  </div>
{:else}
  <span class="whitespace-pre-wrap">{text || ""}</span>
{/if}
