## Design Guide

We highly value great design, both visual and user interaction design. Follow this design guide when building components.

### General Design Style

- We’re a modern B2B saas app with a focus on great typography
- We value modern design and minimalism.
- We highly value uniform design across the app (color palette, fonts, layouts, controls, etc)
- We value consistency. We almost always want to use standard controls from our existing control set. These include DaisyUI controls, and the custom svelte controls described in the “frontend_controls.md” prompt

### User Messages and Strings

- We’re designing for both technical and non-technical users
  - Strings should be clear, descriptive, but not overly verbose.
  - Use plain language wherever possible, but technical language where appropriate
  - Use tooltips and info_description to add additional details which explain concepts to less experienced users. We want to avoid experienced users seeing these definitions over and over (outside of tooltips), but also avoid new users frequently having to leave the app for docs.
- We often hide advanced options which are optional and might confuse or intimidate inexperienced users in an “Advanced” section with our collapse.svelte control.
- Empty screens should be treated as opportunities for education and to get them excited about the feature. Explain the benefits and have a positive call to action.

### Color Palette

We use color sparingly, but with intent. Usually to call attention to primary action, or errors. You almost always should be using a named color from the pre-defined palette described here.

Our colors are named, a Daisy UI convention. For example the color “primary” could be applied to a button as “btn-primary” or to text as “text-primary”.

- `primary` is a blue color we use for primary actions, most typically buttons
  - There should only be one primary button on a screen at a time.
  - In some cases where the primary goal is to select one of many options we use `btn-outline btn-primary` for all multiple options.
- `success`, `error`, and `warning`: green, red and yellow colors used for status messages. Use sparingly, only for important messages. Can be used for text, buttons, etc.
- `secondary` - black, used sparingly but allowed for adding more emphasis to a button/badge than the default gray
- Text colors
  - `text-base` - standard text color, near black
  - `text-gray-500` - lighter text color for secondary text
- Background colors:
  - `bg-base-100` - white. Typically don’t set a background color and inherit this.
  - `bg-base-200` - light grey background for cards/blocks/table-headers

### Layout and containers

- We almost never draw a box. Content sits directly on the page, grouped by headers and spacing, the way the Edit Task form and the Run page do. Do not invent rounded, bordered, tinted or shadowed containers to group content.
- The only boxes we draw are the documented ones: a table's frame (see `tables_style.md`), a card for a clickable or list item (see `card_style.md`), a `Warning` for a message, and `collapse.svelte` for hidden content. If none of those is the element, it is not a box.
- Read-only content (a plan, a summary, an overview, a trace, a description) renders with `settings_header.svelte` for its title and `output.svelte` for its body. Not a tinted div.
- Every screen that asks the user for input is a form. Use `form_container.svelte` and `form_element.svelte` for the whole thing: section headers, labels, fields, help text, the submit row. Do not write `<label>`, `<textarea>` or `<input>` by hand, and do not restate FormElement's label classes on a hand-written label.
- One title per screen: the page title comes from `app_page.svelte`. Inside the page, use `settings_header.svelte` for section titles. Do not add a second `text-2xl font-bold` heading inside the body.
- A progress or waiting screen is the house animation control (`analyzing_animation.svelte` or `conversation_animation.svelte`) with its own title and description props, nothing else. If a count must be shown, it goes in the description string, not in an extra line under the animation with its own weight and size.

### Buttons

- The default button is the plain grey `btn`. Use it for Previous, Cancel, Close, secondary actions, and anything that is not the one primary action.
- `btn-outline` has exactly two sanctioned uses: `btn-outline btn-primary` for picking one of several equal options, and the selection recipe below. Nowhere else.
- `btn-ghost` is not a house button. Buttons that sit on a tinted surface must still read as buttons; if a button is the same colour as what it sits on, it is the wrong button.
- Selection buttons (agree/disagree, pass/fail, yes/no) are the second sanctioned use. They follow the Rating and Feedback style: unchosen is `btn btn-sm btn-outline` at full contrast, chosen is filled `btn btn-sm btn-secondary` (drop `btn-outline`; the outline-plus-secondary form renders transparent and cannot be told from unchosen). Never `btn-success` or `btn-error` for a choice. Red and green are for errors and status, not for disagreement.
- Two buttons side by side are the same size. Never a small `btn-sm` next to a `btn-primary min-w-64`.
- Pairs are named as pairs: "Previous" and "Next", never "Previous" and "Continue". A disabled Previous is hidden, not greyed.
- Button labels are the action, not the verb "View": "Full Trace", "Eval Description", "Eval". The one accepted exception today is "View Eval" on a success screen, where nothing else reads right.
- One primary button per screen. (Already in this guide; restated because it was not followed.)

### Fonts

- You should never set a font-face, it’s an app wide standard non-serif font
- You may set font-weight:
  - font-normal: used for most text
  - font-medium: used for headers, table header, etc
  - font-light: stylish light text often used for subtitles
  - font-bold: usually not needed, use medium
- You may set font size using daisyUI sizes: text-xs, text-sm, text-lg, text-xl, text-2xl
- Use `font-medium` for every header inside the page, `font-normal` for body, `font-light` for subtitles and captions. Do not mix a bold title, a light-grey caption and a normal-weight count on the same screen.
- Never set a font size or weight on a shared control from the call site. `Warning`, `Intro`, the animations and the headers own their type. If a control's default looks wrong on your screen, the screen is wrong, not the control.
