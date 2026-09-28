## Card Styling

A card is for a clickable item or an item in a list. Never use a card to group content on a form or a review screen; use headers and spacing for that (see `frontend_design_guide.md`, Layout and containers).

When styling cards use the following classes:

- Always use `card card-bordered border-base-300 shadow-md`
- If the card is a click target, add `hover:shadow-lg hover:border-primary/50 transition-all duration-200`
- Typically leave the background color unset, but if a darker background is needed use `bg-base-200`
- How you control size/padding depends on the use case. Use an appropriate approach

Example

```
<div
  class="card card-bordered border-base-300 shadow-md"
  >
  <!-- Content here -->
</div>
```
