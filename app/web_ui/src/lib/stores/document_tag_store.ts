import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { get } from "svelte/store"

export type DocumentTagCounts = Record<string, number>

export const document_tag_store_by_project_id = writable<
  Record<string, DocumentTagCounts>
>({})

const loading_document_tags = writable<Record<string, boolean>>({})

export async function load_document_tags(
  project_id: string,
): Promise<DocumentTagCounts> {
  try {
    // Return early if already loading
    if (get(loading_document_tags)[project_id]) {
      return {}
    }
    loading_document_tags.set({
      ...get(loading_document_tags),
      [project_id]: true,
    })

    // Check if tags are already loaded
    const existing_tag_counts = get(document_tag_store_by_project_id)[
      project_id
    ]
    if (existing_tag_counts) {
      return existing_tag_counts
    }
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/documents/tag_counts",
      {
        params: {
          path: { project_id },
        },
      },
    )
    if (error) {
      console.error("Error loading document tags", error)
      return {}
    }
    const tag_counts: DocumentTagCounts = data
    document_tag_store_by_project_id.set({
      ...get(document_tag_store_by_project_id),
      [project_id]: tag_counts,
    })
    return tag_counts
  } catch (error: unknown) {
    console.error("Error loading document tags", error)
    return {}
  } finally {
    loading_document_tags.set({
      ...get(loading_document_tags),
      [project_id]: false,
    })
  }
}

export function increment_document_tag(
  project_id: string,
  tag: string,
): DocumentTagCounts {
  const tag_counts = get(document_tag_store_by_project_id)[project_id]
  if (!tag_counts) {
    console.error(
      "Attempted to increment a document tag, but no tag counts found for project",
      project_id,
    )
    return {}
  }

  if (tag_counts) {
    tag_counts[tag] = (tag_counts[tag] || 0) + 1
  }
  document_tag_store_by_project_id.set({
    ...get(document_tag_store_by_project_id),
    [project_id]: tag_counts,
  })
  return tag_counts
}
