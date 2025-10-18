import { localStorageStore } from "./local_storage_store"
import type { Writable } from "svelte/store"

// For the user's "Select account" registration

type RegistrationState = {
  selected_account_type: "personal" | "work" | null
  work_email: string | null
}

const default_registration_state: RegistrationState = {
  selected_account_type: null,
  work_email: null,
}

// Private, used to store the registration state
export const registration_state: Writable<RegistrationState> =
  localStorageStore("registration_state", default_registration_state)
