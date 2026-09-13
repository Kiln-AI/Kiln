---
name: kiln-ui
description: Build or change anything under app/web_ui with Kiln's house controls and styles only. Invoke before touching any .svelte file, and before writing a task that names a screen, dialog, card, form, button, header or progress state. Produces a component plan, a sibling-screen comparison, a gate run and a handback a reviewer can verify without looking at pixels.
allowed-tools: Read Grep Glob Bash
---

# kiln-ui: house controls or justify

Kiln screens are built from a small set of shared controls and DaisyUI classes. A screen assembled from Tailwind copied off a house control looks right in a screenshot and wrong next to the rest of the app, and the next screen copies it. This skill exists because that happened repeatedly on the eval builder while every unit passed review and visual sign-off. The fix is not "read the guide harder": it is to write down which control each element is, before code, and to prove it at handback in a form that does not need eyes.

## 0. Read, every time (5 minutes)

1. `.agents/frontend_design_guide.md` and `.agents/frontend_controls.md`.
2. `.agents/card_style.md` and `.agents/tables_style.md`.
3. The control list below. Open the source of every control you plan to use; the props are the contract.

## 1. The house controls and when each is the answer

| Control | Path | It is the answer when |
|---|---|---|
| `AppPage` | `routes/(app)/app_page.svelte` | The page title, subtitle, breadcrumbs and top-right action buttons. Every page. The only `text-2xl font-bold` on a screen. |
| `SettingsHeader` | `lib/ui/settings_header.svelte` | A section title inside the page, with optional subtitle. Read-only sections, form sections, "Case 3 of 10". |
| `KilnSection` | `lib/ui/kiln_section.svelte` | A `SettingsHeader` over a list of `SettingsItem` rows (settings-style pages). |
| `Output` | `lib/ui/output.svelte` | Any read-only text or JSON: overview, plan, description, trace field, summary. Never a tinted div. |
| `SeeAllDialog` | `lib/ui/see_all_dialog.svelte` | Read-only content behind a button, in a wide dialog with Close. |
| `Dialog` | `lib/ui/dialog.svelte` | Any modal. Title, width, `action_buttons`. Never a hand-rolled overlay. |
| `EditDialog` | `lib/ui/edit_dialog.svelte` | Editing name/description-style properties with Save/Cancel. |
| `FormContainer` + `FormElement` | `lib/utils/form_container.svelte`, `lib/utils/form_element.svelte` | Anything the user types or picks. Labels, help text, `info_description`, validation, the submit row. Never `<label>`, `<textarea>`, `<input>`, `<select>` by hand. |
| `Warning` | `lib/ui/warning.svelte` | A message with an icon (warning, info, success, error, gray). Default `text_size`; never change its font from the call site. |
| `Intro` | `lib/ui/intro.svelte` | An empty or entry screen: icon, title, paragraphs, buttons. |
| `Collapse` | `lib/ui/collapse.svelte` | Anything that expands. The only expander. |
| `PropertyList` | `lib/ui/property_list.svelte` | Name/value pairs with tooltips and links. |
| `InfoTooltip` | `lib/ui/info_tooltip.svelte` | An "i" with a tooltip. Never a hover div. |
| Rating buttons | `routes/(app)/run/rating.svelte` (see "Rating and Feedback" in `lib/ui/run_sidebar.svelte`) | Any pick-one selection: agree/disagree, pass/fail. unchosen `btn btn-sm btn-outline` at full contrast, chosen filled `btn btn-sm btn-secondary`. Never `btn-success`/`btn-error`. |
| `RunConfigComponent`, `SavedRunConfigsDropdown`, `AvailableModelsDropdown` | `lib/ui/run_config_component/` | Model, tools, skills and run-config pickers. Never rebuilt. |
| Animations | `lib/ui/animations/analyzing_animation.svelte`, `conversation_animation.svelte`, `refining_animation.svelte` | Progress and waiting screens. Title and description props only; counts go in the description string. |
| `FloatingMenu`, `TableActionMenu` | `lib/ui/floating_menu.svelte`, `table_action_menu.svelte` | Dropdown menus. |
| DaisyUI `btn` | | The grey default button for every secondary action. `btn-primary` once per screen. `btn-outline btn-primary` for pick-one-of-many. Nothing else. |

Reference screens (what "looks like Kiln" means): the Edit Task form (`routes/(app)/settings/edit_task/[project_id]/[task_id]/`), the Run page (`routes/(app)/run/+page.svelte`, including Rating and Feedback in `lib/ui/run_sidebar.svelte`), and the synthetic data flow (`routes/(app)/generate/[project_id]/[task_id]/synth_kiln_pro.svelte`). Do not take "house" from the nearest screen on your branch; take it from these.

## 2. Component plan, before code (required)

Write a component plan before the first edit (in the PR description, or a `COMPONENT_PLAN.md` beside your notes; never committed to the app). One row per visible element on every screen state you touch:

```
| Element | House control used | Sibling screen it matches | Justification if custom |
|---|---|---|---|
| Step title "Case 3 of 10" | SettingsHeader | edit_task form section header | |
| Overview body | Output | run page Output block | |
| Agree / Disagree | rating.svelte classes | Rating and Feedback | |
| Hint under the reason box | Warning (default text_size) | eval_configs page advisory | |
```

Rules:
- No custom row without a justification that names the control you tried and the prop it lacks. "Looks better" is not a justification. "The control has no prop for X" is; propose the prop as a separate shared-control change (section 4).
- Every WARN and FAIL the gate reports (section 5) must map to a row.
- One row per screen for vertical rhythm: which container owns the gap between sections and the one or two values used (the house form runs on 24 between fields; use one gap inside a block). Children carry no margins. The handback carries the measured distances next to the sibling's.
- Name ONE sibling screen the new screen must read like. The handback ships a side-by-side with it. Some reference screens predate a control (the Edit Task form's section heads are hand-rolled); match the control, and record the difference as known.
- If the task did not name the sibling, pick the nearest of the three reference screens and say so in the plan.

## 3. Build rules

- Never write `<label>`, `<textarea>`, `<input>`, `<select>` in a route file. FormElement owns them.
- Never write `aria-expanded`, a chevron with `rotate-180`, or an `{#if expanded}` block. Collapse owns disclosure.
- Never draw a box: no `rounded*` + `border`/`bg-*` + padding on a div. The documented card string (`card card-bordered border-base-300 shadow-md`) is for clickable or list items only. A table frame is `rounded-lg border` and nothing else.
- Never set `text_size`, `filled_icon`, `font-*` or `text-*` on a shared control from the call site.
- Never use `btn-success`/`btn-error` for a choice; never `btn-ghost`; `btn-outline` only as `btn-outline btn-primary` for pick-one.
- Button labels: no "View". Pairs are Previous/Next. One `btn-primary` per screen. Side-by-side buttons are the same size.
- Fonts: `font-medium` headers, `font-normal` body, `font-light` subtitles. Text colours: base or `text-gray-500`. Backgrounds: none or `bg-base-200`.
- Copy: short declarative sentences, no em-dashes, Title Case for step and dialog titles.

## 4. Shared controls are a separate change

Any diff under `lib/ui/`, `lib/components/`, `lib/utils/form_*`, `app_page.svelte`, or the shared synthetic-data components (`generate/[project_id]/[task_id]/kiln_pro_*.svelte`) is a change to every screen that uses the control. It is never folded into a feature change. It needs its own stated decision ("Warning gains prop X because Y"), its own commit, the list of call sites touched, and a review by the control's owner. The gate's `SHARED_CONTROL_TOUCHED` hit is not a false positive; it is the reminder that the decision must be written down. Expect the first unit on a screen that was built from custom CSS to need several: every hand-rolled element was a control that lacked something (an actions slot, a slot for rich content, an aria attribute). Each is its own additive commit with a test that the existing render path is unchanged; never widen a control from a call site.

## 5. Gate, on the diff (required)

```
bash .agents/skills/kiln-ui/ui_gate.sh --range <base>..<tip>     # the branch's commits
bash .agents/skills/kiln-ui/ui_gate.sh --worktree                 # before committing, untracked files included
bash .agents/skills/kiln-ui/ui_gate.sh --files <file>...           # audit whole .svelte files
```

- The gate skips comment spans, including multi-line ones, so prose that mentions a class name is not a hit. Markup before or after a comment on the same line is still reviewed.
- Exit 1 = FAIL hits. Fix them, or justify each by file:line in the component plan (a justification is a row, not a comment in the code).
- WARN hits must appear as rows in the plan. INFO hits are listed in the handback.
- Do not add allowlist lines for the screen you are building. `ui_gate_allow.txt` is for house idioms already shipped on a reference screen.
- The three reference screens run at 0 FAIL / 1 WARN; a new change is expected to land at 0 FAIL.

## 6. Review lens: house control or justify

Reviewers of a UI change apply this lens alongside the usual ones. For each visible element the diff adds or restyles: (1) which house control renders it, or which plan row justifies a custom element; (2) whether any shared control under `lib/` changed and whether the change states that decision; (3) whether the screen reads like the named sibling (compare the two screenshots, not the diff); (4) whether the gate output attached to the change is clean or every hit is justified. Report each miss as a finding:

```
FILE:LINE: <route file>:<line>
CLAIM: <element> is a custom <box|label|expander|button|font> where <control> is the house answer.
FAILURE: the screen diverges from <sibling screen> in <what a user sees>; the next screen copies it.
SEVERITY: minor (major if a shared control changed without a stated decision)
EVIDENCE: the class string, the control's prop that covers it, the plan row that is missing.
```

Style findings under this lens are valid findings.

## 7. Handback contract (the reviewer signs off on these, not on pixels)

The PR description or handback carries, in this order:
1. The component plan, final (every row resolved).
2. The gate output for `--range <base>..<tip>`, verbatim, with each FAIL/WARN mapped to a plan row.
3. A side-by-side screenshot: the new screen next to its named sibling, same window width.
4. The list of shared controls touched (or "none"), each with the stated decision that authorised it.
5. Test counts and the usual checks.
6. An independent screenshot review: a fresh session that gets only the owner's spec (verbatim), the guides and the screenshots, and returns a per-line verdict plus a ranked critique. It must not see the plan or the walk notes. Its findings are fixed or answered before the handback is sent. Builders who have stared at a screen for an hour miss a dimmed button; a fresh reader does not.

A reviewer reads 1, 2 and 4 before opening 3. A change whose gate output is missing or whose plan has an unjustified custom row is not ready for review.
