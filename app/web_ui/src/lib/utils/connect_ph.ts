import posthog from "posthog-js"
import { client } from "$lib/api_client"

export async function setup_ph_work_user() {
  try {
    const { data, error } = await client.GET("/api/settings")
    if (error) {
      throw error
    }

    // Only identify the user if the user explicitly registered as a work user (for commercial use) during setup
    // Users who specify they are using Kiln for personal use are not identified
    if (
      data.user_type === "work" &&
      typeof data.work_use_contact === "string"
    ) {
      posthog.identify(data.work_use_contact, {
        email: data.work_use_contact,
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
