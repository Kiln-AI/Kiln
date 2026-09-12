## Frontend Controls

On top of DaisyUI’s CSS controls like btn, we have svelte controls you can use for more consistent style.

Use existing controls wherever possible to ensure consistent visual design.

Use the control, or say in your plan which control you looked at and why it does not fit. A screen that is built from Tailwind classes copied off a house control is not using the control, and it will drift.

### App Specific Svelte Controls

The following controls are commonly used in our design language:

- `app_page.svelte` - a page of our app including title, subtitle, and action buttons in standard position/size
- `property_list.svelte` - a list of properties in a grid with name, value and optional tooltips/links. Optional list title.
- `form_element.svelte`/`form_container.svelte`/`form_list.svelte` - a series of controls for building forms with submit buttons, spinners, errors, validation, input controls, etc.
- `info_tooltip.svelte` - a way to display a tooltip from an “i” info icon, and uses floating_ui to not break doc flow.
- `warning.svelte` - show message box with icon and text. Can be a warning, informational or success.
- `intro.svelte` - used for empty screens before data is added. Teaches user about concept, and has buttons guiding them to an action.
- `dialog.svelte` a modal dialog with close button, title, area for content, and action buttons.
- `edit_dialog.svelte` a dialog for editing properties like name/description. Has save/cancel buttons.
- `float.svelte` - a low-level wrapper for `@floating-ui/dom` positioning. Prefer higher-level components (`floating_menu.svelte`, `info_tooltip.svelte`) when they fit your use case.
- `floating_menu.svelte` / `table_action_menu.svelte` - floating dropdown menus using `@floating-ui/dom`. Use instead of DaisyUI's `dropdown-content` class, which breaks inside tables, dialogs, and scroll areas. `table_action_menu.svelte` is a convenience wrapper that includes the "..." ellipsis button with hover-to-open; `floating_menu.svelte` is the generic version with a trigger slot.
- `settings_header.svelte` - a header-only element (title, optional subtitle, bottom rule). The title for any read-only section or any section of a form.
- `output.svelte` - renders any read-only text or JSON, with copy and pretty-printing. The body for any read-only content: plans, overviews, summaries, traces, descriptions.
- `see_all_dialog.svelte` - `Dialog` + `Output` for read-only content behind a button.
- `kiln_section.svelte` - a `SettingsHeader` over a list of `settings_item.svelte` rows; use for settings-style pages.
- `run/rating.svelte` - the Rating and Feedback selection buttons (`btn btn-sm btn-outline`, `btn-secondary` when selected). The selection-button style for the whole app; copy its classes when a control cannot use it directly.
- `run_config_component/` - the model, tools and skills pickers. Never rebuild a picker.
- `collapse.svelte` - the only expander. Never write `aria-expanded`, a chevron with `rotate-180`, or a `{#if expanded}` block by hand.

Read the control's code to better understand it and its parameters. Optionally search for an existing use of the control to see it in use.

### Tables

The prompt/doc `tables_style.md` has an example of our table styling

### Cards

The prompt/doc `card_style.md` has an example of our card styling

### DaisyUI Controls

DaisyUI also has many controls, all of which meet our style guide. Feel free to use any of them, unless there's already a better app specific control for the task (like there are for forms and collapse). Examples include btn, loading, progress, etc.
