# Phase 3: Transition Animations

## Goal

Add a smooth expand/collapse animation for the sidebar on large screens. The sidebar animates to/from the floating chat icon position using a curved arc path (macOS minimize-style).

## Approach

Use CSS animations with a nested element technique for per-axis easing, creating an arc motion path.

### DOM Structure Changes

- Always render the sidebar in the DOM on lg+ screens (remove `{#if expanded}` conditional for the visual panel)
- Add outer wrapper for translateX animation (ease-out) and inner wrapper for translateY animation (ease-in)
- Keep `{#if expanded}` for the spacer div (instant toggle for layout purposes)

### Animation States

Track animation state with a variable: `idle`, `collapsing`, `expanding`.

**Collapsing flow:**
1. Set state to `collapsing`, trigger CSS animation classes
2. Outer wrapper animates translateX rightward (ease-out)
3. Inner wrapper animates translateY downward (ease-in)
4. Opacity fades to 0 (faster than movement)
5. On `animationend`, set `expanded = false`, state back to `idle`

**Expanding flow:**
1. Set `expanded = true`, state to `expanding`
2. Reverse animations play
3. On `animationend`, state back to `idle`

### CSS Animation Details

- Duration: ~400ms
- Outer: translateX with `cubic-bezier(0.33, 1, 0.68, 1)` (ease-out)
- Inner: translateY with `cubic-bezier(0.32, 0, 0.67, 0)` (ease-in)
- Opacity: fades faster than movement via separate timing
- Overflow hidden + fixed width during animation to prevent reflow
- Only transform and opacity animated (compositor-friendly)

### Floating Icon Coordination

- During collapse animation: icon hidden
- After collapse completes: icon visible
- When expanding starts: icon hidden immediately
- After expand completes: sidebar visible in resting state

## Files Modified

- `app/web_ui/src/routes/(app)/chat_bar.svelte` — animation logic and CSS

## Testing

Manual testing only. Visual animations are verified by inspection.
