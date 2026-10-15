/**
 * Greedy centre-first circle packing inside a fixed circle.
 *
 * Circles are placed one at a time, largest first. Each new circle goes to
 * the position nearest the centre where it touches two placed circles (or
 * one placed circle and the boundary) without overlapping anything. Small
 * circles therefore fall into the gaps between large ones.
 *
 * The layout is deterministic: the same input always gives the same output,
 * whatever the order of the input array.
 */

export type PackItem = {
  id: string
  r: number
  /** Items with a lower pass are placed first. Default 0. */
  pass?: number
}

export type PackedCircle = PackItem & { x: number; y: number }

export type PackResult = {
  placed: PackedCircle[]
  unplaced: PackItem[]
}

type Pt = { x: number; y: number }

const EPS = 1e-6
const TOL = 1e-4

/** Intersection points of two circles. Empty when they do not meet. */
export function circleIntersections(
  ax: number,
  ay: number,
  ar: number,
  bx: number,
  by: number,
  br: number,
): Pt[] {
  const dx = bx - ax
  const dy = by - ay
  const d = Math.hypot(dx, dy)
  if (d < EPS) return []
  if (d > ar + br + EPS) return []
  if (d < Math.abs(ar - br) - EPS) return []
  const a = (ar * ar - br * br + d * d) / (2 * d)
  const h2 = ar * ar - a * a
  const h = h2 > 0 ? Math.sqrt(h2) : 0
  const mx = ax + (a * dx) / d
  const my = ay + (a * dy) / d
  if (h < EPS) return [{ x: mx, y: my }]
  const ox = (-dy * h) / d
  const oy = (dx * h) / d
  return [
    { x: mx + ox, y: my + oy },
    { x: mx - ox, y: my - oy },
  ]
}

function fits(c: Pt, r: number, placed: PackedCircle[]): boolean {
  for (const p of placed) {
    if (Math.hypot(c.x - p.x, c.y - p.y) < p.r + r - TOL) return false
  }
  return true
}

function findSpot(r: number, R: number, placed: PackedCircle[]): Pt | null {
  if (r > R + EPS) return null
  if (placed.length === 0) return { x: 0, y: 0 }
  const inner = R - r // the centre must stay within this radius
  const candidates: Pt[] = []
  for (let i = 0; i < placed.length; i++) {
    const p = placed[i]
    const d = p.r + r
    // Touching p and the boundary.
    if (inner >= 0) {
      candidates.push(...circleIntersections(p.x, p.y, d, 0, 0, inner))
    }
    // Touching p on the line through the centre (covers a circle at the
    // centre, where the boundary candidates are concentric and vanish).
    const len = Math.hypot(p.x, p.y)
    const ux = len < EPS ? 1 : p.x / len
    const uy = len < EPS ? 0 : p.y / len
    candidates.push({ x: p.x + ux * d, y: p.y + uy * d })
    candidates.push({ x: p.x - ux * d, y: p.y - uy * d })
    // Touching p and q.
    for (let j = i + 1; j < placed.length; j++) {
      const q = placed[j]
      candidates.push(...circleIntersections(p.x, p.y, d, q.x, q.y, q.r + r))
    }
  }
  let best: Pt | null = null
  let bestDist = Infinity
  let bestAngle = Infinity
  for (const c of candidates) {
    const dist = Math.hypot(c.x, c.y)
    if (dist + r > R + TOL) continue
    if (!fits(c, r, placed)) continue
    const angle = Math.atan2(c.y, c.x)
    const closer = dist < bestDist - 1e-7
    const tie = Math.abs(dist - bestDist) <= 1e-7 && angle < bestAngle
    if (closer || tie) {
      best = c
      bestDist = dist
      bestAngle = angle
    }
  }
  return best
}

/**
 * The first two circles straddle the centre and touch at it, as in the
 * front-chain method, so later circles settle around a balanced core. A
 * circle too large for that sits at the centre.
 */
function firstSpot(
  first: PackItem,
  second: PackItem | undefined,
  R: number,
): Pt | null {
  if (first.r > R + EPS) return null
  if (second && second.r > 0 && first.r + second.r <= R + EPS) {
    return { x: -second.r, y: 0 }
  }
  return { x: 0, y: 0 }
}

function placementOrder(a: PackItem, b: PackItem): number {
  const pass = (a.pass ?? 0) - (b.pass ?? 0)
  if (pass !== 0) return pass
  if (a.r !== b.r) return b.r - a.r
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

/**
 * Packs `items` inside a circle of radius `R` centred at the origin.
 * `fixed` circles are already in place and are not moved or returned.
 * Items that do not fit anywhere are returned in `unplaced`.
 */
export function packInCircle(
  items: PackItem[],
  R: number,
  fixed: PackedCircle[] = [],
): PackResult {
  const order = [...items].sort(placementOrder)
  const placed: PackedCircle[] = [...fixed]
  const unplaced: PackItem[] = []
  for (const item of order) {
    if (!(item.r > 0)) {
      unplaced.push(item)
      continue
    }
    const spot =
      placed.length === 0
        ? firstSpot(item, order[1], R)
        : findSpot(item.r, R, placed)
    if (spot) {
      placed.push({ ...item, x: spot.x, y: spot.y })
    } else {
      unplaced.push(item)
    }
  }
  return { placed: placed.slice(fixed.length), unplaced }
}

export type WeightedItem = { id: string; weight: number; pass?: number }

export type WeightedPackResult = PackResult & {
  /** r = scale * sqrt(weight) for every placed circle. */
  scale: number
}

/**
 * Packs items whose circle AREA is proportional to `weight`.
 *
 * The scale is set so the circles fill `fill` (0..1) of the boundary area.
 * When the circles do not all fit at that scale, the scale shrinks in
 * small steps until they do.
 */
export function packWeighted(
  items: WeightedItem[],
  R: number,
  fill: number,
): WeightedPackResult {
  const valid = items.filter((i) => i.weight > 0)
  const invalid = items.filter((i) => !(i.weight > 0))
  const totalW = valid.reduce((s, i) => s + i.weight, 0)
  if (valid.length === 0) {
    return { scale: 0, placed: [], unplaced: invalid.map(toPackItem) }
  }
  let scale = Math.sqrt((Math.max(fill, 0) * R * R) / totalW)
  const build = (k: number) =>
    packInCircle(
      valid.map((i) => ({
        id: i.id,
        r: k * Math.sqrt(i.weight),
        pass: i.pass,
      })),
      R,
    )
  let result = build(scale)
  let tries = 0
  while (result.unplaced.length > 0 && tries < 60) {
    scale *= 0.96
    result = build(scale)
    tries++
  }
  return {
    scale,
    placed: recentre(result.placed, R),
    unplaced: [...result.unplaced, ...invalid.map(toPackItem)],
  }
}

/**
 * Moves the packed cluster so its smallest enclosing circle sits at the
 * origin, when that keeps every circle inside the boundary. The greedy
 * placement grows from the first two circles, so the cluster can lean to
 * one side; this balances it.
 */
export function recentre(placed: PackedCircle[], R: number): PackedCircle[] {
  if (placed.length === 0) return placed
  // Approximate smallest enclosing circle: start at the area-weighted
  // centroid and step toward the farthest circle with shrinking steps.
  let totalA = 0
  let cx = 0
  let cy = 0
  for (const c of placed) {
    const a = c.r * c.r
    totalA += a
    cx += c.x * a
    cy += c.y * a
  }
  cx /= totalA
  cy /= totalA
  let radius = 0
  for (let k = 1; k <= 200; k++) {
    let far = placed[0]
    let farD = -Infinity
    for (const c of placed) {
      const d = Math.hypot(c.x - cx, c.y - cy) + c.r
      if (d > farD) {
        farD = d
        far = c
      }
    }
    radius = farD
    const dx = far.x - cx
    const dy = far.y - cy
    const len = Math.hypot(dx, dy)
    if (len < EPS) break
    const step = 1 / (k + 1)
    cx += (dx / len) * (farD - radiusGuess(placed, cx, cy)) * step
    cy += (dy / len) * (farD - radiusGuess(placed, cx, cy)) * step
  }
  if (radius > R + TOL) return placed
  if (Math.hypot(cx, cy) < TOL) return placed
  return placed.map((c) => ({ ...c, x: c.x - cx, y: c.y - cy }))
}

/** The radius an enclosing circle at (cx, cy) needs, ignoring the farthest. */
function radiusGuess(placed: PackedCircle[], cx: number, cy: number): number {
  let best = 0
  let second = 0
  for (const c of placed) {
    const d = Math.hypot(c.x - cx, c.y - cy) + c.r
    if (d > best) {
      second = best
      best = d
    } else if (d > second) {
      second = d
    }
  }
  return placed.length > 1 ? second : 0
}

function toPackItem(i: WeightedItem): PackItem {
  return { id: i.id, r: 0, pass: i.pass }
}

/** Sum of circle areas divided by the boundary area, 0..1. */
export function packingDensity(placed: PackedCircle[], R: number): number {
  if (!(R > 0)) return 0
  const area = placed.reduce((s, c) => s + c.r * c.r, 0)
  return area / (R * R)
}
