<script>
  import "../app.css"
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"
</script>

<div class="hero min-h-[100vh]">
  <div class="hero-content text-center">
    <div class="max-w-lg">
      <h1 class="text-5xl font-bold">{$_("errors.embarrassing")}</h1>
      <p class="py-6 text-2xl">
        {$_("errors.occurred")}: {$page?.error?.message}
      </p>
      <div>
        <a href="/" class="btn btn-primary btn-wide">{$_("common.back_home")}</a
        >
      </div>
    </div>
  </div>
</div>
