/**
 * The island outline (docs/DESIGN.md §2.4, F-413). At rest the island is an
 * arc: a shallow circle segment hanging from the top edge of the screen.
 * Open, it is a body with continuous (superellipse) bottom corners and
 * concave fillets ("the neck") where it meets the edge. `arc` blends the two
 * (1 = segment, 0 = body), so one outline morphs through every state.
 *
 * Both shapes use the same fixed point count, so consecutive frames and the
 * blend interpolate cleanly. The outline starts above y = 0 so a stroke (the
 * rim) never shows along the screen edge itself.
 */
export interface Outline {
  /** Horizontal center, px. */
  cx: number;
  /** Body width (arc: chord length), without the neck, px. */
  width: number;
  /** Height from the top edge (arc: depth at the center), px. */
  height: number;
  /** Bottom corner radius, px. */
  radius: number;
  /** Neck fillet radius, px. */
  neck: number;
  /** Superellipse exponent for the bottom corners (2 = circle). */
  exponent: number;
  /** Blend toward the circle segment: 1 = arc, 0 = body. */
  arc: number;
}

const POINTS_PER_CURVE = 10;
/** Points between the two overscan corners: four curves of POINTS_PER_CURVE + 1. */
const INNER_POINTS = 4 * (POINTS_PER_CURVE + 1);
/** The closing edge runs this far above the window so the rim stroke stays hidden. */
const OVERSCAN = 2;

/** Values clamped so the outline is always valid, whatever the spring values. */
export function fitted(outline: Outline): Outline {
  const width = Math.max(outline.width, 0);
  const height = Math.max(outline.height, 0);
  const neck = Math.max(0, Math.min(outline.neck, height / 2));
  const radius = Math.max(0, Math.min(outline.radius, width / 2, height - neck));
  const arc = Math.max(0, Math.min(outline.arc, 1));
  return { ...outline, width, height, neck, radius, arc };
}

function corner(
  cx: number,
  cy: number,
  r: number,
  from: number,
  to: number,
  exponent: number,
): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= POINTS_PER_CURVE; i += 1) {
    const t = from + ((to - from) * i) / POINTS_PER_CURVE;
    const cos = Math.cos(t);
    const sin = Math.sin(t);
    out.push([
      cx + r * Math.sign(cos) * Math.abs(cos) ** (2 / exponent),
      cy + r * Math.sign(sin) * Math.abs(sin) ** (2 / exponent),
    ]);
  }
  return out;
}

/** The open shape: neck, bottom corners, neck (INNER_POINTS points). */
function bodyPoints({
  cx,
  width,
  height,
  radius: r,
  neck: f,
  exponent,
}: Outline): [number, number][] {
  const x0 = cx - width / 2;
  const x1 = cx + width / 2;
  const q = Math.PI / 2;
  return [
    // Left neck: concave, from the edge down into the body's side.
    ...corner(x0 - f, f, f, -q, 0, 2),
    // Bottom-left corner, then bottom-right (y grows downward).
    ...corner(x0 + r, height - r, r, Math.PI, q, exponent),
    ...corner(x1 - r, height - r, r, q, 0, exponent),
    // Right neck back up to the edge.
    ...corner(x1 + f, f, f, Math.PI, Math.PI + q, 2),
  ];
}

/**
 * The resting shape: a circle segment with chord `width` on the top edge and
 * depth `height` (capped at a half circle), INNER_POINTS points left to right.
 */
function segmentPoints({ cx, width, height }: Outline): [number, number][] {
  const half = width / 2;
  const depth = Math.min(height, half);
  if (half === 0 || depth === 0) {
    return Array.from({ length: INNER_POINTS }, (_, i): [number, number] => [
      cx - half + (width * i) / (INNER_POINTS - 1),
      0,
    ]);
  }
  // Circle through both chord ends and the lowest point.
  const r = (half * half + depth * depth) / (2 * depth);
  const theta = Math.asin(Math.min(1, half / r));
  const cy = depth - r;
  // An odd sample count puts a point exactly at the lowest spot; it is used
  // twice so the segment has as many points as the body.
  const samples = INNER_POINTS - 1;
  const points = Array.from({ length: samples }, (_, i): [number, number] => {
    const phi = -theta + (2 * theta * i) / (samples - 1);
    return [cx + r * Math.sin(phi), Math.max(0, cy + r * Math.cos(phi))];
  });
  const middle = (samples - 1) / 2;
  return [...points.slice(0, middle + 1), ...points.slice(middle)];
}

export function outlinePoints(input: Outline): [number, number][] {
  const outline = fitted(input);
  const body = bodyPoints(outline);
  const segment = segmentPoints(outline);
  const a = outline.arc;
  const inner = body.map(([bx, by], i): [number, number] => {
    const [sx, sy] = segment[i] ?? [bx, by];
    return [bx + (sx - bx) * a, by + (sy - by) * a];
  });
  const first = inner[0] ?? [outline.cx, 0];
  const last = inner[inner.length - 1] ?? [outline.cx, 0];
  return [[first[0], -OVERSCAN], ...inner, [last[0], -OVERSCAN]];
}

export function outlinePath(outline: Outline): string {
  const parts = outlinePoints(outline).map(
    ([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`,
  );
  return `${parts.join(" ")} Z`;
}

/** Bounding box of the visible outline (neck included), rounded outward. */
export function outlineBounds(outline: Outline): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const { cx, width, height, neck, arc } = fitted(outline);
  const side = neck * (1 - arc);
  const left = Math.floor(cx - width / 2 - side);
  const right = Math.ceil(cx + width / 2 + side);
  const depth = arc === 1 ? Math.min(height, width / 2) : height;
  return { x: left, y: 0, width: right - left, height: Math.ceil(depth) };
}
