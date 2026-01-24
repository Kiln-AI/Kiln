import posthog from "posthog-js"
import { client } from "$lib/api_client"

export async function setup_ph_user() {
  try {
    const { data, error } = await client.GET("/api/settings")
    if (error) {
      throw error
    }

    // Only identify the user if the user explicitly registered with Kiln using their email
    const email = data.work_use_contact || data.personal_use_contact
    if (typeof email === "string" && email.length > 0) {
      posthog.identify(email, {
        email: email,
        user_type: data.user_type,
      })
    } else {
      posthog.setPersonProperties({
        user_type: data.user_type,
      })
    }
  } catch (error) {
    // Non critical error, just log it
    console.error("Error setting up PostHog", error)
  }
}
