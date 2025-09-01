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

### Fonts

- You should never set a font-face, it’s an app wide standard non-serif font
- You may set font-weight:
  - font-normal: used for most text
  - font-medium: used for headers, table header, etc
  - font-light: stylish light text often used for subtitles
  - font-bold: usually not needed, use medium
- You may set font size using daisyUI sizes: text-xs, text-sm, text-lg, text-xl, text-2xl

### Controls
