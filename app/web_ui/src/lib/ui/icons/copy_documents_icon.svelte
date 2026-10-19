<!-- A document (file_icon.svelte squircle + text lines) with a second copy
     behind it, top-right, drawn as outline only. A mask knocks the front
     document's footprint out of the back outline so the two read as stacked.
     Sized so the pair fills the canvas like a standard icon (~2–22). Strokes are
     1.875 = 1.5 / 0.8, so after the scale(0.8) they render a true 1.5 — matching
     the app's other icons. Inherits currentColor. -->
<svg
  class="h-full w-full"
  viewBox="0 0 24 24"
  fill="none"
  xmlns="http://www.w3.org/2000/svg"
>
  <mask id="copy-documents-knockout">
    <rect x="0" y="0" width="24" height="24" fill="white" />
    <rect x="2.3" y="6" width="14.4" height="16" rx="3.2" fill="black" />
  </mask>

  <!-- Back document: outline only, behind, masked where the front overlaps. -->
  <g mask="url(#copy-documents-knockout)">
    <path
      transform="translate(4.9 0.4) scale(0.8)"
      d="M3 10C3 6.22876 3 4.34315 4.17157 3.17157C5.34315 2 7.22876 2 11 2H13C16.7712 2 18.6569 2 19.8284 3.17157C21 4.34315 21 6.22876 21 10V14C21 17.7712 21 19.6569 19.8284 20.8284C18.6569 22 16.7712 22 13 22H11C7.22876 22 5.34315 22 4.17157 20.8284C3 19.6569 3 17.7712 3 14V10Z"
      stroke="currentColor"
      stroke-width="1.875"
    />
  </g>

  <!-- Front document: full squircle + text lines. -->
  <g transform="translate(-0.1 4.4) scale(0.8)">
    <path
      d="M3 10C3 6.22876 3 4.34315 4.17157 3.17157C5.34315 2 7.22876 2 11 2H13C16.7712 2 18.6569 2 19.8284 3.17157C21 4.34315 21 6.22876 21 10V14C21 17.7712 21 19.6569 19.8284 20.8284C18.6569 22 16.7712 22 13 22H11C7.22876 22 5.34315 22 4.17157 20.8284C3 19.6569 3 17.7712 3 14V10Z"
      stroke="currentColor"
      stroke-width="1.875"
    />
    <path
      d="M8 12H16"
      stroke="currentColor"
      stroke-width="1.875"
      stroke-linecap="round"
    />
    <path
      d="M8 8H16"
      stroke="currentColor"
      stroke-width="1.875"
      stroke-linecap="round"
    />
    <path
      d="M8 16H13"
      stroke="currentColor"
      stroke-width="1.875"
      stroke-linecap="round"
    />
  </g>
</svg>
