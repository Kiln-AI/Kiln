import createClient from "openapi-fetch"
import type { paths } from "./api_schema"

const api_port = import.meta.env.VITE_API_PORT || "8757"
export const base_url = `http://localhost:${api_port}`

export const client = createClient<paths>({
  baseUrl: base_url,
})
