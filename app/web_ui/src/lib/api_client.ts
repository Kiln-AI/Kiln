import createClient from "openapi-fetch"
import type { paths } from "./api_schema"

export const base_url = "http://localhost:8757"

export const client = createClient<paths>({
  baseUrl: base_url,
})
