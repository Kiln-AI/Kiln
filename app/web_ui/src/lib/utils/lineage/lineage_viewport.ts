// The world maps to the screen as `screen = world * k + t`. View coordinates
// are relative to the canvas element.

export interface Viewport {
  k: number
  tx: number
  ty: number
}

export interface Size {
  width: number
  height: number
}

export interface Point {
  x: number
  y: number
}

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

export const ZOOM_MAX = 2
export const ZOOM_FLOOR = 0.5
export const ZOOM_STEP = 1.25
export const FIT_MARGIN = 24
export const PAN_KEEP = 40

/** The zoom that shows the whole world with a margin, never above 100%. */
export function fit_zoom(world: Size, view: Size): number {
  if (world.width <= 0 || world.height <= 0) {
    return 1
  }
  // A view smaller than its margins still gets a positive zoom.
  const room_x = Math.max(view.width - 2 * FIT_MARGIN, 1)
  const room_y = Math.max(view.height - 2 * FIT_MARGIN, 1)
  return Math.min(room_x / world.width, room_y / world.height, 1)
}

export function min_zoom(world: Size, view: Size): number {
  return Math.min(ZOOM_FLOOR, fit_zoom(world, view))
}

/**
 * Clamps the zoom to its range, and the pan so that at least PAN_KEEP px of
 * the world stays in view on each axis (less when the world or the view is
 * smaller than that).
 */
export function clamp_viewport(
  vp: Viewport,
  world: Size,
  view: Size,
): Viewport {
  const k = Math.min(Math.max(vp.k, min_zoom(world, view)), ZOOM_MAX)
  return {
    k,
    tx: clamp_pan(vp.tx, world.width * k, view.width),
    ty: clamp_pan(vp.ty, world.height * k, view.height),
  }
}

export function fit(world: Size, view: Size): Viewport {
  const k = fit_zoom(world, view)
  return clamp_viewport(
    {
      k,
      tx: (view.width - world.width * k) / 2,
      ty: (view.height - world.height * k) / 2,
    },
    world,
    view,
  )
}

/** Zooms to `k`, keeping the world point under `point` fixed on screen. */
export function zoom_at(
  vp: Viewport,
  point: Point,
  k: number,
  world: Size,
  view: Size,
): Viewport {
  const next_k = clamp_viewport({ ...vp, k }, world, view).k
  const world_x = (point.x - vp.tx) / vp.k
  const world_y = (point.y - vp.ty) / vp.k
  return clamp_viewport(
    {
      k: next_k,
      tx: point.x - world_x * next_k,
      ty: point.y - world_y * next_k,
    },
    world,
    view,
  )
}

/** One zoom step in (1) or out (-1), about the center of the view. */
export function zoom_step(
  vp: Viewport,
  direction: 1 | -1,
  world: Size,
  view: Size,
): Viewport {
  return zoom_at(
    vp,
    { x: view.width / 2, y: view.height / 2 },
    vp.k * ZOOM_STEP ** direction,
    world,
    view,
  )
}

export function pan_by(
  vp: Viewport,
  dx: number,
  dy: number,
  world: Size,
  view: Size,
): Viewport {
  return clamp_viewport(
    { k: vp.k, tx: vp.tx + dx, ty: vp.ty + dy },
    world,
    view,
  )
}

/** Zooms to `k` with the world `point` at the center of the view. */
export function center_on(
  point: Point,
  k: number,
  world: Size,
  view: Size,
): Viewport {
  const next_k = clamp_viewport({ k, tx: 0, ty: 0 }, world, view).k
  return clamp_viewport(
    {
      k: next_k,
      tx: view.width / 2 - point.x * next_k,
      ty: view.height / 2 - point.y * next_k,
    },
    world,
    view,
  )
}

/** Pans the least distance that brings the world `rect` within `margin` of the view's edges. */
export function ensure_visible(
  vp: Viewport,
  rect: Rect,
  world: Size,
  view: Size,
  margin: number = FIT_MARGIN,
): Viewport {
  const dx = shift_into_view(
    rect.x * vp.k + vp.tx,
    rect.w * vp.k,
    view.width,
    margin,
  )
  const dy = shift_into_view(
    rect.y * vp.k + vp.ty,
    rect.h * vp.k,
    view.height,
    margin,
  )
  return pan_by(vp, dx, dy, world, view)
}

/**
 * Keeps the point at the center of the view in place when the view resizes.
 * Doesn't clamp: the next interaction does.
 */
export function resize_keep_center(
  vp: Viewport,
  old_view: Size,
  new_view: Size,
): Viewport {
  return {
    k: vp.k,
    tx: vp.tx + (new_view.width - old_view.width) / 2,
    ty: vp.ty + (new_view.height - old_view.height) / 2,
  }
}

const DOM_DELTA_LINE = 1
const DOM_DELTA_PAGE = 2
const LINE_HEIGHT_PX = 16

/** Converts a WheelEvent delta to pixels from its `deltaMode`. */
export function wheel_delta_px(
  delta: number,
  delta_mode: number,
  view_height: number,
): number {
  switch (delta_mode) {
    case DOM_DELTA_LINE:
      return delta * LINE_HEIGHT_PX
    case DOM_DELTA_PAGE:
      return delta * view_height
    default:
      return delta
  }
}

/** Scrolling up (a negative delta) zooms in. */
export function wheel_zoom_factor(delta_y_px: number): number {
  return Math.exp(-delta_y_px / 200)
}

function clamp_pan(t: number, world_px: number, view_px: number): number {
  const keep = Math.min(PAN_KEEP, world_px, view_px)
  return Math.min(Math.max(t, keep - world_px), view_px - keep)
}

function shift_into_view(
  start: number,
  length: number,
  view_px: number,
  margin: number,
): number {
  if (start < margin) {
    return margin - start
  }
  const overflow = start + length - (view_px - margin)
  return overflow > 0 ? -overflow : 0
}
