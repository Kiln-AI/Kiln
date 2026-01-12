import createClient from "openapi-fetch"
import type { paths } from "./api_schema"
import { KilnApiBaseUrl } from "../config"

export const client = createClient<paths>({
  baseUrl: KilnApiBaseUrl,
})
