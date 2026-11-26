<script lang="ts">
  // How the second sentence names what the user trusts.
  export let code_label: string = "the code"
</script>

<div class="flex flex-row items-start gap-4">
  <!-- exclaim icon from warning.svelte (keep in sync) -->
  <svg
    class="w-10 h-10 text-warning flex-none"
    fill="currentColor"
    viewBox="0 0 256 256"
    xmlns="http://www.w3.org/2000/svg"
    data-testid="trust-warning-icon"
  >
    <path
      d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
    />
  </svg>
  <div class="flex flex-col gap-2 text-sm text-left">
    <p>
      This project wants to run Python code on your machine. Only proceed if you
      trust {code_label} and this project.
    </p>
    <p class="font-bold">Never paste code from a stranger or the internet.</p>
  </div>
</div>
