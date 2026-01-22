import { goto } from "$app/navigation"

export function redirect_to_work(replaceState: boolean = true) {
  if (window.location.search.includes("home_after_registration=true")) {
    goto("/setup/register_work?home_after_registration=true", {
      replaceState: replaceState,
    })
  } else {
    goto("/setup/register_work", { replaceState: replaceState })
  }
}

export function redirect_to_personal(replaceState: boolean = true) {
  if (window.location.search.includes("home_after_registration=true")) {
    goto("/setup/register_personal?home_after_registration=true", {
      replaceState: replaceState,
    })
  } else {
    goto("/setup/register_personal", { replaceState: replaceState })
  }
}

export function redirect_after_registration(replaceState: boolean = false) {
  if (window.location.search.includes("home_after_registration=true")) {
    goto("/", { replaceState: replaceState })
  } else {
    goto("/setup/support", { replaceState: replaceState })
  }
}
