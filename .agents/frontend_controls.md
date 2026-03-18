## Frontend Controls

On top of DaisyUI’s CSS controls like btn, we have svelte controls you can use for more consistent style.

Use existing controls wherever possible to ensure consistent visual design.

### App Specific Svelte Controls

The following controls are commonly used in our design language:

- `app_page.svelte` - a page of our app including title, subtitle, and action buttons in standard position/size
- `property_list.svelte` - a list of properties in a grid with name, value and optional tooltips/links. Optional list title.
- `form_element.svelte`/`form_container.svelte`/`form_list.svelte` - a series of controls for building forms with submit buttons, spinners, errors, validation, input controls, etc.
- `info_tooltip.svelte` - a way to display a tooltip from an “i” info icon
- `warning.svelte` - show message box with icon and text. Can be a warning, informational or success.
- `intro.svelte` - used for empty screens before data is added. Teaches user about concept, and has buttons guiding them to an action.
- `dialog.svelte` a modal dialog with close button, title, area for content, and action buttons.
- `edit_dialog.svelte` a dialog for editing properties like name/description. Has save/cancel buttons.
- `collapse.svelte` a collapsible section, often titled "Advanced Options" to hide optional controls

Read the control's code to better understand it and its parameters. Optionally search for an existing use of the control to see it in use.

### Tables

The prompt/doc `tables_style.md` has an example of our table styling

### Cards

The prompt/doc `card_style.md` has an example of our card styling

### DaisyUI Controls

DaisyUI also has many controls, all of which meet our style guide. Feel free to use any of them, unless there's already a better app specific control for the task (like there are for forms and collapse). Examples include btn, loading, progress, etc.
