import { describe, expect, it } from "vitest"
import {
  FIT_MARGIN,
  PAN_KEEP,
  ZOOM_MAX,
  ZOOM_STEP,
  center_on,
  clamp_viewport,
  ensure_visible,
  fit,
  fit_zoom,
  min_zoom,
  pan_by,
  resize_keep_center,
  wheel_delta_px,
  wheel_zoom_factor,
  zoom_at,
  zoom_step,
  type Point,
  type Size,
  type Viewport,
} from "./lineage_viewport"

const VIEW: Size = { width: 500, height: 500 }
const WORLD: Size = { width: 1000, height: 1000 }
const IDENTITY: Viewport = { k: 1, tx: 0, ty: 0 }

function world_point(vp: Viewport, screen: Point): Point {
  return { x: (screen.x - vp.tx) / vp.k, y: (screen.y - vp.ty) / vp.k }
}

describe("fit_zoom and min_zoom", () => {
  it("shrinks a world larger than the view", () => {
    const view = { width: 548, height: 548 }
    expect(fit_zoom({ width: 1000, height: 500 }, view)).toBe(0.5)
  })

  it("never zooms past 100% to fit a small world", () => {
    expect(fit_zoom({ width: 100, height: 100 }, VIEW)).toBe(1)
  })

  it("is 1 for an empty world", () => {
    expect(fit_zoom({ width: 0, height: 0 }, VIEW)).toBe(1)
  })

  it("stays positive when the view is smaller than its margins", () => {
    const k = fit_zoom(WORLD, { width: FIT_MARGIN, height: FIT_MARGIN })
    expect(k).toBeGreaterThan(0)
  })

  it("floors at 50%, or lower when the fit needs it", () => {
    expect(min_zoom({ width: 100, height: 100 }, VIEW)).toBe(0.5)
    const huge = { width: 10000, height: 10000 }
    expect(min_zoom(huge, VIEW)).toBeCloseTo((500 - 2 * FIT_MARGIN) / 10000)
  })
})

describe("fit", () => {
  it("centers the world in the view", () => {
    expect(
      fit({ width: 100, height: 50 }, { width: 500, height: 300 }),
    ).toEqual({ k: 1, tx: 200, ty: 125 })
  })

  it("shows all of a large world", () => {
    const vp = fit(WORLD, VIEW)
    expect(vp.tx).toBeCloseTo(FIT_MARGIN)
    expect(vp.ty).toBeCloseTo(FIT_MARGIN)
    expect(vp.tx + WORLD.width * vp.k).toBeCloseTo(VIEW.width - FIT_MARGIN)
  })
})

describe("zoom_at and zoom_step", () => {
  it("keeps the world point under the cursor fixed", () => {
    const cursor = { x: 100, y: 200 }
    const before = world_point(IDENTITY, cursor)
    const vp = zoom_at(IDENTITY, cursor, 1.5, WORLD, VIEW)
    expect(vp.k).toBe(1.5)
    expect(world_point(vp, cursor).x).toBeCloseTo(before.x)
    expect(world_point(vp, cursor).y).toBeCloseTo(before.y)
  })

  it("clamps the zoom to its range", () => {
    expect(zoom_at(IDENTITY, { x: 0, y: 0 }, 10, WORLD, VIEW).k).toBe(ZOOM_MAX)
    expect(zoom_at(IDENTITY, { x: 0, y: 0 }, 0.01, WORLD, VIEW).k).toBe(
      min_zoom(WORLD, VIEW),
    )
  })

  it("steps in and out about the center of the view", () => {
    const center = { x: VIEW.width / 2, y: VIEW.height / 2 }
    const start: Viewport = { k: 1, tx: -100, ty: -50 }
    const before = world_point(start, center)

    const zoomed_in = zoom_step(start, 1, WORLD, VIEW)
    expect(zoomed_in.k).toBeCloseTo(ZOOM_STEP)
    expect(world_point(zoomed_in, center).x).toBeCloseTo(before.x)
    expect(world_point(zoomed_in, center).y).toBeCloseTo(before.y)

    const zoomed_out = zoom_step(start, -1, WORLD, VIEW)
    expect(zoomed_out.k).toBeCloseTo(1 / ZOOM_STEP)
    expect(world_point(zoomed_out, center).x).toBeCloseTo(before.x)
  })
})

describe("pan_by and clamping", () => {
  it("pans by the given distance", () => {
    expect(pan_by(IDENTITY, -30, -40, WORLD, VIEW)).toEqual({
      k: 1,
      tx: -30,
      ty: -40,
    })
  })

  it("keeps PAN_KEEP px of the world in view on each axis", () => {
    const far_right = pan_by(IDENTITY, 10000, 10000, WORLD, VIEW)
    expect(far_right.tx).toBe(VIEW.width - PAN_KEEP)
    expect(far_right.ty).toBe(VIEW.height - PAN_KEEP)

    const far_left = pan_by(IDENTITY, -10000, -10000, WORLD, VIEW)
    expect(far_left.tx).toBe(PAN_KEEP - WORLD.width)
    expect(far_left.ty).toBe(PAN_KEEP - WORLD.height)
  })

  it("keeps all of a world smaller than PAN_KEEP in view", () => {
    const tiny = { width: 20, height: 20 }
    expect(pan_by(IDENTITY, -100, 1000, tiny, VIEW)).toEqual({
      k: 1,
      tx: 0,
      ty: VIEW.height - 20,
    })
  })

  it("clamps zoom and pan together", () => {
    expect(clamp_viewport({ k: 5, tx: 9999, ty: 0 }, WORLD, VIEW)).toEqual({
      k: ZOOM_MAX,
      tx: VIEW.width - PAN_KEEP,
      ty: 0,
    })
  })
})

describe("center_on", () => {
  it("puts the point at the center of the view", () => {
    expect(center_on({ x: 300, y: 400 }, 1, WORLD, VIEW)).toEqual({
      k: 1,
      tx: -50,
      ty: -150,
    })
  })

  it("clamps the zoom", () => {
    expect(center_on({ x: 300, y: 400 }, 5, WORLD, VIEW).k).toBe(ZOOM_MAX)
  })
})

describe("ensure_visible", () => {
  const node = (x: number, y: number) => ({ x, y, w: 14, h: 14 })

  it("doesn't move when the node is already visible", () => {
    const vp = { k: 1, tx: -100, ty: -100 }
    expect(ensure_visible(vp, node(300, 300), WORLD, VIEW)).toEqual(vp)
  })

  it("pans a node past the right or bottom edge back in", () => {
    const vp = ensure_visible(IDENTITY, node(600, 700), WORLD, VIEW)
    expect(vp.tx).toBe(VIEW.width - FIT_MARGIN - 614)
    expect(vp.ty).toBe(VIEW.height - FIT_MARGIN - 714)
  })

  it("pans a node past the left or top edge back in", () => {
    const vp = ensure_visible(
      { k: 1, tx: -300, ty: -400 },
      node(100, 200),
      WORLD,
      VIEW,
    )
    expect(vp.tx).toBe(FIT_MARGIN - 100)
    expect(vp.ty).toBe(FIT_MARGIN - 200)
  })

  it("accounts for the zoom", () => {
    const vp = ensure_visible({ k: 2, tx: 0, ty: 0 }, node(300, 0), WORLD, VIEW)
    expect(300 * 2 + vp.tx + 14 * 2).toBe(VIEW.width - FIT_MARGIN)
  })
})

describe("resize_keep_center", () => {
  it("keeps the point at the center of the view", () => {
    const vp = { k: 2, tx: 10, ty: 20 }
    const old_view = { width: 500, height: 400 }
    const new_view = { width: 300, height: 600 }
    const before = world_point(vp, { x: 250, y: 200 })
    const after_vp = resize_keep_center(vp, old_view, new_view)
    expect(after_vp).toEqual({ k: 2, tx: -90, ty: 120 })
    expect(world_point(after_vp, { x: 150, y: 300 })).toEqual(before)
  })

  it("doesn't clamp", () => {
    const vp = { k: 1, tx: 5000, ty: 0 }
    expect(resize_keep_center(vp, VIEW, VIEW)).toEqual(vp)
  })
})

describe("wheel helpers", () => {
  it("converts each delta mode to pixels", () => {
    expect(wheel_delta_px(3, 0, 500)).toBe(3)
    expect(wheel_delta_px(3, 1, 500)).toBe(48)
    expect(wheel_delta_px(1, 2, 500)).toBe(500)
  })

  it("zooms in on a negative delta and out on a positive one", () => {
    expect(wheel_zoom_factor(0)).toBe(1)
    expect(wheel_zoom_factor(-100)).toBeGreaterThan(1)
    expect(wheel_zoom_factor(100)).toBeLessThan(1)
    expect(wheel_zoom_factor(-100) * wheel_zoom_factor(100)).toBeCloseTo(1)
  })
})
