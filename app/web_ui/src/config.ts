import { env } from "$env/dynamic/public"

export const WebsiteName: string = "Kiln Studio"
export const WebsiteBaseUrl: string = "https://kiln.tech"
export const WebsiteDescription: string = "Build ML Products with Kiln Studio"
export const KindeAccountDomain: string =
  env.PUBLIC_KINDE_ACCOUNT_DOMAIN || "https://account.kiln.tech"
export const KindeAccountClientId: string =
  env.PUBLIC_KINDE_ACCOUNT_CLIENT_ID || "2428f47a1e0b404b82e68400a2d580c6"
export const KilnApiBaseUrl: string =
  env.PUBLIC_KILN_API_BASE_URL || "http://localhost:8757"
