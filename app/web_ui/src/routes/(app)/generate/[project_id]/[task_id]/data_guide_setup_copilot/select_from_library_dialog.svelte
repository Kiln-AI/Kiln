<script lang="ts" context="module">
  // What this dialog emits per pick. Text is resolved by the inline extraction
  // step (which extractor to use is the user's choice), so picks carry only an
  // identity.
  export type LibraryPick = {
    document_id: string
    label: string
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagFirstSelector, {
    type TagFirstItem,
  } from "./tag_first_selector.svelte"
  import ExtractorPicker from "$lib/components/extractor_picker.svelte"
  import { client } from "$lib/api_client"
  import type { KilnDocument } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import Intro from "$lib/ui/intro.svelte"
  import CopyDocumentsIcon from "$lib/ui/icons/copy_documents_icon.svelte"

  export let project_id: string
  // Document IDs already added as entries; filtered out so the user can't
  // double-add the same doc.
  export let existing_document_ids: string[] = []
  // Tags applied to picked documents so a later extraction run, scoped by these
  // tags, catches them. Applied whether or not extraction happens in-dialog.
  export let auto_tags: string[] = []
  // When true (default), the dialog runs extraction inline before closing. When
  // false, picks are added (and tagged) and the dialog closes immediately —
  // extraction is deferred to the caller (e.g. the data guide's Continue step).
  export let extract_after_pick: boolean = true

  let dialog: Dialog | null = null
  let selector: TagFirstSelector
  let extractor_picker: ExtractorPicker
  let extracting = false
  // Guards against re-adding the same picks as entries if the user retries a
  // failed extraction without closing the dialog.
  let committed = false
  let documents: KilnDocument[] = []
  // True when the library has documents but they're all already added — lets the
  // empty state distinguish "library is empty" from "you've added them all".
  let all_added = false
  // True when the raw library has any tagged docs (before filtering out
  // already-added ones) — lets the empty state say "you've added all your
  // tagged docs" instead of wrongly claiming nothing is tagged.
  let library_has_tagged = false
  let loading = false
  let load_error: KilnError | null = null
  let selected_ids: string[] = []

  const dispatch = createEventDispatcher<{
    add: { picks: LibraryPick[] }
    extraction_complete: { extractor_config_id: string; error_count: number }
  }>()

  export async function show() {
    selected_ids = []
    committed = false
    load_error = null
    selector?.reset()
    extractor_picker?.reset()
    dialog?.show()
    await load_documents()
  }

  function close() {
    dialog?.close()
    return true
  }

  // Open the Document Library in a new tab and close this dialog — it loads its
  // document list once on open and doesn't live-refresh, so leaving it open
  // would show stale data after the user tags/uploads documents.
  function go_to_library() {
    window.open(`/docs/library/${project_id}`, "_blank", "noopener")
    close()
  }

  async function load_documents() {
    loading = true
    load_error = null
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/documents",
        { params: { path: { project_id } } },
      )
      if (fetch_error) throw fetch_error
      const all_docs = (data || []).filter((d) => !!d.id)
      documents = all_docs.filter((d) => !existing_document_ids.includes(d.id!))
      all_added = documents.length === 0 && all_docs.length > 0
      library_has_tagged = all_docs.some((d) => !!d.tags && d.tags.length > 0)
    } catch (e) {
      load_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  // The picker is tag-first, so untagged documents can't be selected here. When
  // no available document is tagged we show an empty state nudging the user to
  // tag their docs rather than rendering an empty table.
  $: has_tagged_docs = documents.some((d) => !!d.tags && d.tags.length > 0)

  // Empty-state copy, by reason. Note `library_has_tagged` is the raw library
  // (before filtering out already-added docs), which lets us say "you've added
  // them all" instead of wrongly claiming nothing is tagged.
  $: empty_state =
    documents.length === 0
      ? all_added
        ? {
            title: "All Documents Added",
            description:
              "You've already added every document in your library. Upload more documents to your library to add them here.",
          }
        : {
            title: "No Documents To Add",
            description:
              "Your document library is empty. Upload documents to your library to add them here.",
          }
      : library_has_tagged
        ? {
            title: "No Tagged Documents To Add",
            description:
              "You've already added all of your tagged documents. Tag more documents in the Document Library to add them here.",
          }
        : {
            title: "No Tagged Documents To Add",
            description:
              "Only tagged documents can be added here. Tag your documents in the Document Library to add them here.",
          }

  // Newest-first, matching the library's default sort.
  $: selector_items = [...documents]
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .filter((d) => !!d.id)
    .map(
      (d): TagFirstItem => ({
        id: d.id as string,
        text: d.friendly_name,
        tags: d.tags ?? [],
        date: d.created_at,
      }),
    )

  function library_tags_href(tags: string[]): string {
    const params = new URLSearchParams()
    tags.forEach((t) => params.append("tags", t))
    return `/docs/library/${project_id}?${params.toString()}`
  }

  function build_picks(): LibraryPick[] {
    const picks: LibraryPick[] = []
    for (const id of selected_ids) {
      const doc = documents.find((d) => d.id === id)
      if (doc) picks.push({ document_id: id, label: doc.friendly_name })
    }
    return picks
  }

  // Apply the auto-tags so the inline extraction run (scoped by those tags)
  // catches the picked docs. Awaited before extraction to avoid a race.
  async function tag_documents(document_ids: string[]) {
    if (auto_tags.length === 0 || document_ids.length === 0) return
    const { error } = await client.POST(
      "/api/projects/{project_id}/documents/edit_tags",
      {
        params: { path: { project_id } },
        body: { document_ids, add_tags: auto_tags },
      },
    )
    // Surface tagging failures so callers don't proceed to a tag-scoped
    // extraction (or a deferred add) with untagged docs.
    if (error) throw error
  }

  // Runs before the picker starts extraction: add the picks as entries (once)
  // and ensure they carry the auto-tags.
  async function before_extraction() {
    const picks = build_picks()
    if (picks.length === 0) return
    if (!committed) {
      dispatch("add", { picks })
      committed = true
    }
    await tag_documents(picks.map((p) => p.document_id))
  }

  function handle_extraction_complete(
    event: CustomEvent<{ extractor_config_id: string; error_count: number }>,
  ) {
    dispatch("extraction_complete", event.detail)
    close()
  }

  // Deferred-extraction path (extract_after_pick = false): add the picks as
  // text-less entries, tag them so the caller's later run catches them, then
  // signal the dialog to close. Extraction is the caller's responsibility.
  async function handle_add_without_extraction(): Promise<boolean> {
    const picks = build_picks()
    if (picks.length === 0) return false
    dispatch("add", { picks })
    await tag_documents(picks.map((p) => p.document_id))
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  width="wide"
  title="Select from Document Library"
  action_buttons={extract_after_pick || !has_tagged_docs
    ? []
    : [
        {
          label: "Add",
          asyncAction: handle_add_without_extraction,
          disabled: selected_ids.length === 0,
          isPrimary: true,
        },
      ]}
>
  <p slot="subtitle" class="text-sm font-light">
    Add examples from your
    <a
      href={`/docs/library/${project_id}`}
      target="_blank"
      rel="noopener"
      class="link">Document Library</a
    >
    by tag.
  </p>

  {#if loading}
    <div class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else if load_error}
    <div class="text-error text-sm">
      Failed to load documents: {load_error.getMessage()}
    </div>
  {:else if !has_tagged_docs}
    <!-- Empty state for: nothing in the library (race past the uploader's
         library_has_docs gating), everything already added, or documents that
         exist but have no tags (untagged docs can't be picked tag-first). -->
    <div class="py-8 flex justify-center">
      <Intro
        title={empty_state.title}
        description_paragraphs={[empty_state.description]}
        action_buttons={[
          {
            label: "Go to Document Library",
            onClick: go_to_library,
            is_primary: true,
          },
        ]}
      >
        <div slot="icon" class="h-12 w-12">
          <CopyDocumentsIcon />
        </div>
      </Intro>
    </div>
  {:else}
    {#if !extracting}
      <TagFirstSelector
        bind:this={selector}
        items={selector_items}
        count_header="Documents"
        unit_singular="document"
        unit_plural="documents"
        filtered_href={library_tags_href}
        bind:selected_ids
      />
    {/if}

    {#if extract_after_pick && selected_ids.length > 0}
      <div class="mt-6">
        <ExtractorPicker
          bind:this={extractor_picker}
          bind:extracting
          target_tags={auto_tags}
          preselect_default_extractor={true}
          show_run_button={true}
          run_button_label="Add"
          description="Convert your selected documents to text so they can be used as example inputs."
          before_run={before_extraction}
          on:extraction_complete={handle_extraction_complete}
        />
      </div>
    {/if}
  {/if}
</Dialog>
